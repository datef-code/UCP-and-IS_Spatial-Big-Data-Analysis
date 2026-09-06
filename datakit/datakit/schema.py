"""字段规格（规范 §3 / §7.1）：等级 + 角色 + 业务规则 → 规则违规表。

机器负责从数据里**量得出来**的事实（类型、取值范围、缺失率），人负责**产品意图**
（这个字段有多重要、允不允许缺、什么值算不合法）。本模块把人的意图固化成
:class:`FieldSpec`，并拿数据检验它，产出「规则违规」表。

与「异常值」的区别（规范 §2-②）：

* 异常值 = **统计意义**上的离群（见 :func:`datakit.profile.detect_outliers`）；
* 规则违规 = **业务意义**上的不合法（本模块）。

典型用法::

    import datakit as dk

    specs = dk.load_schema(project.config("schema"))        # config/schema.yaml
    prof = dk.profile(ds, roles=dk.schema_roles(specs))     # 角色回灌给画像
    viol = dk.violations(ds.frame, specs)                   # 逐规则违规表
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

import pandas as pd

from .core import Role

__all__ = ["FieldSpec", "Rule", "load_schema", "schema_roles", "violations",
           "LEVELS", "LEVEL_SEVERITY"]

#: 字段等级：必需 / 重要 / 可选 / 忽略
LEVELS = ("required", "important", "optional", "ignore")

#: 等级 → 默认严重度（P0 阻断 / P1 / P2）
LEVEL_SEVERITY = {"required": "P0", "important": "P1", "optional": "P2", "ignore": "P2"}

#: 角色字符串 → :class:`~datakit.core.Role`
_ROLE_ALIAS = {
    "key": Role.KEY,
    "event": Role.EVENT,
    "time_varying": Role.TIME_VARYING,
    "spatial": Role.SPATIAL,
    "categorical": Role.CATEGORICAL,
    "numeric": Role.NUMERIC,
    "target": Role.TARGET,
    "ignore": Role.IGNORE,
}


@dataclass
class Rule:
    """一条业务规则。"""

    kind: str
    params: dict[str, Any] = field(default_factory=dict)
    message: str = ""

    @classmethod
    def from_spec(cls, spec: Mapping[str, Any]) -> "Rule":
        spec = dict(spec)
        kind = str(spec.pop("kind", ""))
        message = str(spec.pop("message", ""))
        return cls(kind=kind, params=spec, message=message)

    def label(self) -> str:
        extra = ", ".join(f"{k}={v}" for k, v in self.params.items() if k != "message")
        return f"{self.kind}({extra})" if extra else self.kind


@dataclass
class FieldSpec:
    """一个字段的规格：角色 + 等级 + 业务规则 + 说明。"""

    name: str
    role: str = "numeric"
    level: str = "optional"
    dtype: str = ""
    description: str = ""
    rules: list[Rule] = field(default_factory=list)
    note: str = ""
    missing_semantics: str = ""

    @classmethod
    def from_spec(cls, spec: Mapping[str, Any]) -> "FieldSpec":
        rules = [Rule.from_spec(r) for r in (spec.get("rules") or [])]
        return cls(
            name=str(spec["name"]),
            role=str(spec.get("role", "numeric")),
            level=str(spec.get("level", "optional")),
            dtype=str(spec.get("dtype", "")),
            description=str(spec.get("description", "")),
            rules=rules,
            note=str(spec.get("note", "")),
            missing_semantics=str(spec.get("missing_semantics", "")),
        )

    @property
    def severity(self) -> str:
        return LEVEL_SEVERITY.get(self.level, "P2")


def load_schema(spec: Mapping[str, Any] | Iterable[Mapping[str, Any]]) -> list[FieldSpec]:
    """从 ``config/schema.yaml`` 的结构解析出字段规格列表。"""
    if isinstance(spec, Mapping):
        items = spec.get("fields") or []
    else:
        items = list(spec)
    return [FieldSpec.from_spec(i) for i in items if isinstance(i, Mapping) and i.get("name")]


def schema_roles(specs: Iterable[FieldSpec]) -> dict[str, Role]:
    """把字段角色回灌给 :func:`datakit.profile.profile`。"""
    out: dict[str, Role] = {}
    for s in specs:
        role = _ROLE_ALIAS.get(s.role)
        if role is not None:
            out[s.name] = role
    return out


def violations(
    frame: pd.DataFrame,
    specs: Iterable[FieldSpec],
    sample_n: int = 5,
) -> pd.DataFrame:
    """按规格检验数据，产出「规则违规」表。

    返回列：``field`` / ``level`` / ``severity`` / ``rule`` / ``message`` /
    ``violations`` / ``rate`` / ``samples`` / ``note``。
    只报「数据里存在该字段」的规格；规格声明了但数据里没有的字段，由
    :func:`missing_fields` 单独给出警告（规范 §3.4）。
    """
    rows: list[dict[str, Any]] = []
    n = len(frame)
    for spec in specs:
        if spec.name not in frame.columns:
            continue
        s = frame[spec.name]
        for rule in spec.rules:
            mask = _eval_rule(frame, s, rule)
            count = int(mask.sum()) if mask is not None else 0
            if count == 0:
                continue
            sample = s[mask].head(sample_n).astype(str).tolist() if mask is not None else []
            rows.append({
                "field": spec.name,
                "level": spec.level,
                "severity": spec.severity,
                "rule": rule.label(),
                "message": rule.message,
                "violations": count,
                "rate": (count / n) if n else 0.0,
                "samples": sample,
                "note": spec.note,
            })
    return pd.DataFrame(rows, columns=["field", "level", "severity", "rule", "message",
                                       "violations", "rate", "samples", "note"])


def missing_fields(frame: pd.DataFrame, specs: Iterable[FieldSpec]) -> list[str]:
    """规格声明了但数据里不存在的字段（拼写错误 / 数据源变更的信号）。"""
    return [s.name for s in specs if s.name not in frame.columns]


def unregistered_fields(frame: pd.DataFrame, specs: Iterable[FieldSpec]) -> list[str]:
    """数据里有但规格未登记的字段（默认按 ``optional`` 处理）。"""
    known = {s.name for s in specs}
    return [c for c in frame.columns if c not in known]


# --------------------------------------------------------------------------- #
# 规则求值
# --------------------------------------------------------------------------- #
def _eval_rule(frame: pd.DataFrame, s: pd.Series, rule: Rule) -> pd.Series | None:
    """返回布尔掩码（True = 违规）；不支持的规则返回 None。"""
    kind = rule.kind
    p = rule.params

    if kind == "not_null":
        return s.isna()

    if kind == "unique":
        cols = p.get("fields") or [s.name]
        cols = [c for c in cols if c in frame.columns]
        return frame.duplicated(subset=cols, keep=False) if cols else None

    if kind == "non_negative":
        v = pd.to_numeric(s, errors="coerce")
        return v < 0

    if kind == "range":
        v = pd.to_numeric(s, errors="coerce")
        lo, hi = p.get("min"), p.get("max")
        mask = pd.Series(False, index=s.index)
        if lo is not None:
            mask |= v < float(lo)
        if hi is not None:
            mask |= v > float(hi)
        return mask.fillna(False)

    if kind in ("geo_lat", "geo_lon"):
        v = pd.to_numeric(s, errors="coerce")
        lo, hi = (-90.0, 90.0) if kind == "geo_lat" else (-180.0, 180.0)
        return ((v < lo) | (v > hi)).fillna(False)

    if kind == "no_future_date":
        v = pd.to_datetime(s, errors="coerce")
        now = pd.Timestamp.now()
        return (v > now).fillna(False)

    if kind == "allowed_values":
        values = set(p.get("values") or [])
        return ~s.isin(values) & s.notna()

    if kind == "regex":
        pat = str(p.get("pattern", ""))
        if not pat:
            return None
        return ~s.astype("string").str.match(pat, na=False) & s.notna()

    return None
