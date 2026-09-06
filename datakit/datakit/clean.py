"""数据清洗（流程第 3 步）+ 决策日志。

设计要点：

* 清洗由一组 :class:`CleanAction` 顺序执行，每个动作都写进 :class:`DecisionLog`，
  记录「哪一列 / 多少行 / 原值概况 / 处理后概况 / 原因 / 是否可逆」，保证可审计。
* 空值处理**不一律删除**：是否处理、如何处理由字段角色与动作显式决定。
* 清洗返回新的 :class:`Dataset`，源数据与上游 ``Dataset`` 均不被修改。

典型用法::

    plan = dk.CleanPlan()
    plan.drop_na(subset=["BRNUM", "CERT"], reason="主键缺失")
    plan.fill("DEPSUMBR", method="median", reason="时变协变量缺失填充")
    result = dk.clean(ds, plan)
    result.dataset          # 清洗后的 Dataset
    result.decisions        # 决策日志（可导出 Markdown/DataFrame）
"""

from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from typing import Any, Callable, Iterable

import numpy as np
import pandas as pd

from .core import Dataset

__all__ = ["CleanAction", "CleanPlan", "CleanResult", "DecisionLog", "clean"]


@dataclass
class CleanAction:
    """一个原子清洗动作。"""

    op: str                       # drop_na / fill / clip / replace / drop_duplicates / astype / winsorize / drop_columns / filter
    field: str | list[str] | None = None
    reason: str = ""
    reversible: bool = True
    params: dict[str, Any] = dc_field(default_factory=dict)

    def label(self) -> str:
        f = self.field if isinstance(self.field, str) else ",".join(self.field or [])
        return f"{self.op}({f})" if f else self.op


class DecisionLog:
    """决策日志：一组结构化决策记录。"""

    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    def add(self, step: int, action: str, field: str | None, reason: str,
            affected_rows: int, detail: str, reversible: bool = True,
            before: Any = None, after: Any = None, dropped: Any = None) -> None:
        rec: dict[str, Any] = {
            "step": step,
            "action": action,
            "field": field,
            "reason": reason,
            "affected_rows": affected_rows,
            "detail": detail,
            "reversible": reversible,
        }
        if before is not None:
            rec["before"] = before
        if after is not None:
            rec["after"] = after
        if dropped is not None:
            rec["dropped_indices"] = dropped
        self.records.append(rec)

    def to_frame(self) -> pd.DataFrame:
        return pd.DataFrame(self.records)

    def to_markdown(self) -> str:
        if not self.records:
            return "# 清洗决策日志\n\n（无清洗动作）\n"
        lines = ["# 清洗决策日志", ""]
        for r in self.records:
            lines.append(f"- **步骤 {r['step']}** `{r['action']}` 字段={r.get('field')} "
                         f"影响行={r['affected_rows']} 可逆={r['reversible']}")
            lines.append(f"  - 原因：{r.get('reason')}")
            lines.append(f"  - 说明：{r.get('detail')}")
        lines.append("")
        return "\n".join(lines)


class CleanPlan:
    """清洗计划：顺序动作的流畅构建器。"""

    def __init__(self) -> None:
        self.actions: list[CleanAction] = []

    def drop_na(self, subset: Iterable[str], reason: str = "") -> "CleanPlan":
        self.actions.append(CleanAction("drop_na", list(subset), reason=reason, reversible=False))
        return self

    def fill(self, field: str, method: str = "constant", value: Any = None,
             reason: str = "") -> "CleanPlan":
        self.actions.append(CleanAction("fill", field, reason=reason, params={"method": method, "value": value}))
        return self

    def clip(self, field: str, lower: float | None = None, upper: float | None = None,
             reason: str = "", on_violation: str = "clip") -> "CleanPlan":
        """越界值处理：``clip`` 截断到边界，``to_null`` 置空（越界坐标/金额宜置空而非截断）。"""
        self.actions.append(CleanAction(
            "clip", field, reason=reason,
            params={"lower": lower, "upper": upper, "on_violation": on_violation}))
        return self

    def replace(self, field: str, to_replace: Any, value: Any, reason: str = "") -> "CleanPlan":
        self.actions.append(CleanAction("replace", field, reason=reason, params={"to_replace": to_replace, "value": value}))
        return self

    def drop_duplicates(self, subset: Iterable[str] | None = None, keep: str = "first",
                        reason: str = "") -> "CleanPlan":
        self.actions.append(CleanAction("drop_duplicates", list(subset) if subset else None,
                                        reason=reason, params={"keep": keep}))
        return self

    def astype(self, field: str, dtype: Any, reason: str = "") -> "CleanPlan":
        self.actions.append(CleanAction("astype", field, reason=reason, params={"dtype": dtype}))
        return self

    def winsorize(self, field: str, quantile: float = 0.01, reason: str = "") -> "CleanPlan":
        self.actions.append(CleanAction("winsorize", field, reason=reason, params={"quantile": quantile}))
        return self

    def drop_columns(self, columns: Iterable[str], reason: str = "") -> "CleanPlan":
        self.actions.append(CleanAction("drop_columns", list(columns), reason=reason, reversible=False))
        return self

    def filter(self, predicate: Callable[[pd.DataFrame], pd.Series], reason: str = "") -> "CleanPlan":
        self.actions.append(CleanAction("filter", None, reason=reason, reversible=False, params={"predicate": predicate}))
        return self

    @classmethod
    def from_spec(cls, spec: Iterable[dict[str, Any]]) -> "CleanPlan":
        """从配置字典列表构建计划（便于把清洗口径外置到配置文件）。

        例::

            CleanPlan.from_spec([
                {"op": "drop_na", "field": ["BRNUM"], "reason": "主键缺失"},
                {"op": "fill", "field": "DEPSUMBR", "method": "median"},
            ])
        """
        plan = cls()
        for item in spec:
            op = item["op"]
            reason = item.get("reason", "")
            field = item.get("field")
            if op == "drop_na":
                plan.drop_na(item.get("field") or [], reason)
            elif op == "fill":
                plan.fill(field, method=item.get("method", "constant"), value=item.get("value"), reason=reason)
            elif op == "clip":
                plan.clip(field, lower=item.get("lower"), upper=item.get("upper"),
                          on_violation=item.get("on_violation", "clip"), reason=reason)
            elif op == "replace":
                plan.replace(field, item["to_replace"], item.get("value"), reason=reason)
            elif op == "drop_duplicates":
                plan.drop_duplicates(item.get("subset"), keep=item.get("keep", "first"), reason=reason)
            elif op == "astype":
                plan.astype(field, item["dtype"], reason=reason)
            elif op == "winsorize":
                plan.winsorize(field, quantile=item.get("quantile", 0.01), reason=reason)
            elif op == "drop_columns":
                plan.drop_columns(item.get("field") or [], reason)
            else:
                raise ValueError(f"unknown clean op: {op}")
        return plan


@dataclass
class CleanResult:
    """清洗结果：清洗后的数据集 + 决策日志 + 统计摘要。"""

    dataset: Dataset
    decisions: DecisionLog
    stats: dict[str, Any] = dc_field(default_factory=dict)


def clean(dataset: Dataset | pd.DataFrame, plan: CleanPlan) -> CleanResult:
    """按计划执行清洗，返回 :class:`CleanResult`。"""
    frame = dataset.frame if isinstance(dataset, Dataset) else dataset
    frame = frame.copy()
    log = DecisionLog()
    stats: dict[str, Any] = {"before_rows": len(frame), "after_rows": len(frame)}

    for step, action in enumerate(plan.actions, start=1):
        before_len = len(frame)
        op = action.op
        f = action.field
        p = action.params

        if op == "drop_na":
            subset = f if f else list(frame.columns)
            mask = frame[subset].isna().any(axis=1)
            dropped = frame.index[mask].tolist()
            frame = frame.loc[~mask]
            log.add(step, op, ",".join(subset), action.reason, int(mask.sum()),
                    f"删除 {int(mask.sum())} 行（字段 {','.join(subset)} 缺失）",
                    reversible=False, dropped=dropped)

        elif op == "fill":
            s = frame[f]
            missing = int(s.isna().sum())
            method = p.get("method", "constant")
            before_summary = f"{missing} 个空值"
            if method == "constant":
                frame[f] = s.fillna(p.get("value"))
            elif method == "mean":
                frame[f] = s.fillna(s.mean())
            elif method == "median":
                frame[f] = s.fillna(s.median())
            elif method == "mode":
                mode = s.mode()
                frame[f] = s.fillna(mode[0] if len(mode) else None)
            elif method == "ffill":
                frame[f] = s.ffill()
            elif method == "bfill":
                frame[f] = s.bfill()
            else:
                raise ValueError(f"unknown fill method: {method}")
            log.add(step, op, f, action.reason, missing,
                    f"用 {method} 填充 {missing} 个空值", before=before_summary,
                    after=f"填充后剩余 {int(frame[f].isna().sum())} 个空值")

        elif op == "clip":
            s = frame[f]
            lower, upper = p.get("lower"), p.get("upper")
            on_violation = p.get("on_violation", "clip")
            clipped = ((lower is not None) & (s < lower)) | ((upper is not None) & (s > upper))
            n = int(clipped.sum())
            if on_violation == "to_null":
                frame[f] = s.mask(clipped)
                log.add(step, op, f, action.reason, n,
                        f"将 {n} 个越界值置空（[{lower}, {upper}] 之外；置空而非截断，避免伪造坐标/金额）",
                        before=f"{n} 个越界值", after=f"越界值已置为 NaN")
            else:
                frame[f] = s.clip(lower=lower, upper=upper)
                log.add(step, op, f, action.reason, n,
                        f"截断 {n} 个越界值到 [{lower}, {upper}]")

        elif op == "replace":
            before_count = int((frame[f] == p["to_replace"]).sum())
            frame[f] = frame[f].replace(to_replace=p["to_replace"], value=p["value"])
            log.add(step, op, f, action.reason, before_count,
                    f"将 {before_count} 个 {p['to_replace']!r} 替换为 {p['value']!r}")

        elif op == "drop_duplicates":
            subset = f or None
            before_count = len(frame)
            frame = frame.drop_duplicates(subset=subset, keep=p.get("keep", "first"))
            n = before_count - len(frame)
            log.add(step, op, ",".join(subset) if subset else "<all>", action.reason, n,
                    f"去重删除 {n} 行", reversible=False)

        elif op == "astype":
            frame[f] = frame[f].astype(p["dtype"])
            log.add(step, op, f, action.reason, before_len,
                    f"列 {f} 类型转换为 {p['dtype']}")

        elif op == "winsorize":
            q = p.get("quantile", 0.01)
            s = frame[f]
            lower, upper = s.quantile(q), s.quantile(1 - q)
            out = ((s < lower) | (s > upper))
            n = int(out.sum())
            frame[f] = s.clip(lower=lower, upper=upper)
            log.add(step, op, f, action.reason, n,
                    f"缩尾 {n} 个极端值到分位 [{lower:.4g}, {upper:.4g}]")

        elif op == "drop_columns":
            frame = frame.drop(columns=f)
            log.add(step, op, ",".join(f), action.reason, before_len,
                    f"删除列 {','.join(f)}", reversible=False)

        elif op == "filter":
            keep_mask = p["predicate"](frame)
            removed = int((~keep_mask).sum())
            frame = frame.loc[keep_mask]
            log.add(step, op, None, action.reason, removed,
                    f"过滤删除 {removed} 行", reversible=False)

        else:
            raise ValueError(f"unknown clean op: {op}")

        stats[f"after_{op}"] = len(frame)

    stats["after_rows"] = len(frame)
    stats["removed_rows"] = stats["before_rows"] - stats["after_rows"]

    if isinstance(dataset, Dataset):
        out = dataset.with_frame(frame)
    else:
        out = Dataset(frame)
    return CleanResult(dataset=out, decisions=log, stats=stats)
