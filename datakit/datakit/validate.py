"""校验分析（流程第 4 步）：断言校验 + 清洗前后对比。

两个能力：

* :func:`validate` —— 对数据集执行一组**断言**（唯一性 / 空值率 / 取值范围 / 行数…），
  产出通过/失败报告。可用于清洗前的「硬断言」（P0 阻断）或清洗后的复检。
* :func:`compare` —— 对比清洗前后的 :class:`~datakit.profile.Profile`，逐字段给出
  缺失率/异常值变化，并给出「是否继续 / 是否还原重洗」的**建议**（不替代人工决策）。

断言 DSL 见 :func:`validate` 文档。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

import pandas as pd

from .core import Dataset
from .profile import Profile, _frame_to_records

__all__ = ["CheckResult", "ValidationReport", "ComparisonReport", "validate", "compare"]


@dataclass
class CheckResult:
    """单条断言的校验结果。"""

    name: str
    passed: bool
    actual: Any = None
    expected: Any = None
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "passed": self.passed,
            "actual": self.actual,
            "expected": self.expected,
            "message": self.message,
        }


@dataclass
class ValidationReport:
    """一组断言的汇总报告。"""

    checks: list[CheckResult]
    summary: dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks)

    @property
    def pass_count(self) -> int:
        return sum(1 for c in self.checks if c.passed)

    @property
    def fail_count(self) -> int:
        return sum(1 for c in self.checks if not c.passed)

    def to_report(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "pass_count": self.pass_count,
            "fail_count": self.fail_count,
            "summary": self.summary,
            "checks": [c.to_dict() for c in self.checks],
        }

    def to_markdown(self) -> str:
        mark = "✅" if self.passed else "❌"
        lines = [f"# 校验报告 {mark}", "",
                 f"- 通过：{self.pass_count} / {len(self.checks)}", ""]
        for c in self.checks:
            status = "PASS" if c.passed else "FAIL"
            lines.append(f"- [{status}] {c.name}")
            if c.message:
                lines.append(f"  - {c.message}")
            if c.actual is not None or c.expected is not None:
                lines.append(f"  - 实际={c.actual} 期望={c.expected}")
        lines.append("")
        return "\n".join(lines)


def validate(
    dataset: Dataset | pd.DataFrame,
    assertions: Iterable[dict[str, Any] | Callable[[pd.DataFrame], tuple[bool, str]]],
) -> ValidationReport:
    """执行断言并返回 :class:`ValidationReport`。

    ``assertions`` 每项可以是字典（声明式）或可调用对象。

    声明式字典字段::

        {"name": str, "check": str, "field": str, ...额外参数}

    支持的 ``check``：

    ====================  =====================================
    check                 参数与含义
    ====================  =====================================
    ``unique``            ``field`` 值唯一
    ``null_rate_le``      ``field`` 缺失率 <= ``max``
    ``no_negative``       ``field`` 无负值
    ``range``             ``field`` 值在 ``[min, max]`` 内
    ``allowed_values``    ``field`` 值 ⊆ ``values``
    ``no_duplicates``     ``subset`` 上无重复行
    ``row_count_ge/le``   行数 >=/<= ``min``/``max``
    ``column_count_eq``   列数 == ``value``
    ``columns_eq``        列名集合 == ``columns``
    ====================  =====================================
    """
    frame = dataset.frame if isinstance(dataset, Dataset) else dataset
    checks: list[CheckResult] = []

    for spec in assertions:
        if callable(spec):
            try:
                passed, msg = spec(frame)
                checks.append(CheckResult(name=getattr(spec, "__name__", "custom"), passed=passed, message=msg))
            except Exception as exc:  # 自定义断言异常视为失败
                checks.append(CheckResult(name=getattr(spec, "__name__", "custom"), passed=False, message=str(exc)))
            continue

        name = spec.get("name", spec.get("check", "check"))
        check = spec["check"]
        f = spec.get("field")

        if check == "unique":
            s = frame[f]
            dup = int(s.duplicated().sum())
            checks.append(CheckResult(name, dup == 0, actual=dup, expected=0,
                                      message=f"字段 {f} 重复值 {dup} 个"))
        elif check == "null_rate_le":
            rate = float(frame[f].isna().mean()) if len(frame) else 0.0
            mx = spec.get("max", 0.0)
            checks.append(CheckResult(name, rate <= mx, actual=rate, expected=f"<= {mx}",
                                      message=f"字段 {f} 缺失率 {rate:.4%}"))
        elif check == "no_negative":
            s = frame[f]
            n = int((pd.to_numeric(s, errors="coerce") < 0).sum())
            checks.append(CheckResult(name, n == 0, actual=n, expected=0,
                                      message=f"字段 {f} 负值 {n} 个"))
        elif check == "range":
            s = pd.to_numeric(frame[f], errors="coerce")
            lo, hi = spec.get("min"), spec.get("max")
            out = int(((s < lo) | (s > hi)).sum())
            checks.append(CheckResult(name, out == 0, actual=out, expected=0,
                                      message=f"字段 {f} 越界 {out} 个"))
        elif check == "allowed_values":
            bad = set(frame[f].dropna().unique()) - set(spec.get("values", []))
            checks.append(CheckResult(name, not bad, actual=sorted(map(str, bad)), expected=spec.get("values"),
                                      message=f"字段 {f} 非法值 {sorted(map(str, bad))}"))
        elif check == "no_duplicates":
            subset = spec.get("subset", list(frame.columns))
            dup = int(frame.duplicated(subset=subset).sum())
            checks.append(CheckResult(name, dup == 0, actual=dup, expected=0,
                                      message=f"重复行 {dup} 条"))
        elif check == "row_count_ge":
            mn = spec.get("min", 0)
            checks.append(CheckResult(name, len(frame) >= mn, actual=len(frame), expected=f">= {mn}"))
        elif check == "row_count_le":
            mx = spec.get("max", 0)
            checks.append(CheckResult(name, len(frame) <= mx, actual=len(frame), expected=f"<= {mx}"))
        elif check == "column_count_eq":
            checks.append(CheckResult(name, len(frame.columns) == spec["value"],
                                      actual=len(frame.columns), expected=spec["value"]))
        elif check == "columns_eq":
            actual = set(frame.columns)
            expected = set(spec["columns"])
            checks.append(CheckResult(name, actual == expected,
                                      actual=sorted(actual - expected), expected="一致",
                                      message=f"缺失列 {sorted(expected - actual)} 多余列 {sorted(actual - expected)}"))
        else:
            checks.append(CheckResult(name, False, message=f"unknown check: {check}"))

    report = ValidationReport(checks=checks)
    report.summary = {"total": len(checks), "pass": report.pass_count, "fail": report.fail_count}
    return report


@dataclass
class ComparisonReport:
    """清洗前后对比报告。"""

    fields: list[dict[str, Any]]
    summary: dict[str, Any]
    recommendation: str

    def to_report(self) -> dict[str, Any]:
        return {"summary": self.summary, "recommendation": self.recommendation, "fields": self.fields}

    def to_markdown(self) -> str:
        lines = ["# 清洗前后对比报告", "",
                 f"- 建议：**{self.recommendation}**", ""]
        for k, v in self.summary.items():
            lines.append(f"- {k}: {v}")
        lines.append("")
        lines.append("| 字段 | 缺失率前 | 缺失率后 | 缺失率变化 | 异常值前 | 异常值后 |")
        lines.append("| --- | --- | --- | --- | --- | --- |")
        for f in self.fields:
            lines.append(
                f"| {f['field']} | {_pct(f['null_rate_before'])} | {_pct(f['null_rate_after'])} | "
                f"{_pct_diff(f['null_rate_diff'])} | {f['outliers_before']} | {f['outliers_after']} |"
            )
        lines.append("")
        return "\n".join(lines)


def compare(
    before: Profile,
    after: Profile,
    removed_rate: float | None = None,
    max_removed_rate: float = 0.05,
    key_fields: Iterable[str] | None = None,
) -> ComparisonReport:
    """对比清洗前后画像，给出继续/重洗建议。

    ``removed_rate`` 为清洗阶段剔除的行占比（可传入 ``clean(...).stats`` 得到），
    超过 ``max_removed_rate`` 时建议「还原并用更温和的策略重洗」。
    """
    before_fields = {f.name: f for f in before.fields}
    after_fields = {f.name: f for f in after.fields}

    before_outlier_counts = before.outliers["field"].value_counts().to_dict() if len(before.outliers) else {}
    after_outlier_counts = after.outliers["field"].value_counts().to_dict() if len(after.outliers) else {}

    fields = []
    for name in before_fields:
        bf = before_fields[name]
        af = after_fields.get(name)
        if af is None:
            fields.append({
                "field": name, "null_rate_before": bf.null_rate, "null_rate_after": None,
                "null_rate_diff": None, "outliers_before": before_outlier_counts.get(name, 0),
                "outliers_after": None,
            })
            continue
        fields.append({
            "field": name,
            "null_rate_before": bf.null_rate,
            "null_rate_after": af.null_rate,
            "null_rate_diff": af.null_rate - bf.null_rate,
            "outliers_before": before_outlier_counts.get(name, 0),
            "outliers_after": after_outlier_counts.get(name, 0),
        })

    # 建议逻辑（启发式，供人工参考）
    reasons: list[str] = []
    key_fields = set(key_fields or [])
    for f in fields:
        if key_fields and f["field"] in key_fields and f["null_rate_after"] and f["null_rate_after"] > 0:
            reasons.append(f"关键字段 {f['field']} 清洗后仍有缺失")
    if removed_rate is not None and removed_rate > max_removed_rate:
        reasons.append(f"剔除行占比 {removed_rate:.2%} 超过阈值 {max_removed_rate:.2%}")

    if reasons:
        recommendation = "建议还原数据并用更温和的策略再次清洗：" + "；".join(reasons)
    elif removed_rate is not None and removed_rate > 0:
        recommendation = "清洗已完成且剔除比例在阈值内，可进入映射阶段"
    else:
        recommendation = "清洗后与清洗前差异符合预期，可进入映射阶段"

    summary = {
        "fields": len(fields),
        "null_rate_before": before.summary.get("null_rate", 0.0),
        "null_rate_after": after.summary.get("null_rate", 0.0),
        "outliers_before": before.summary.get("outlier_count", 0),
        "outliers_after": after.summary.get("outlier_count", 0),
        "removed_rate": removed_rate,
    }
    return ComparisonReport(fields=fields, summary=summary, recommendation=recommendation)


def _pct(value: Any) -> str:
    """把比例格式化为百分比；``None`` 显示为 ``-``。"""
    return "-" if value is None else f"{value:.2%}"


def _pct_diff(value: Any) -> str:
    """把比例差格式化为带符号百分比；``None`` 显示为 ``-``。"""
    return "-" if value is None else f"{value:+.2%}"
