"""描述性统计分析（流程第 2 步）：字段画像、异常值、空值。

核心观点：**异常值与空值的判定依赖分析目的**。因此：

* 通过 :class:`Role` 声明字段角色，空值语义随之变化——
  例如 ``Role.EVENT`` 字段缺失 = 右删失（信息），``Role.KEY`` 字段缺失 = 缺陷（需处理）。
* 异常值检测方法可切换（IQR / Z-score / MAD），阈值可配置。

产物 :class:`Profile` 可导出为 JSON 报告或 Markdown，供清洗前后对比（见
:mod:`datakit.validate` 的 ``compare``）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

import numpy as np
import pandas as pd

from .core import Dataset, Role, infer_roles

__all__ = ["FieldProfile", "Profile", "profile", "detect_outliers", "null_summary", "describe"]

_NUM_QUANTILES = (0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99)


@dataclass
class FieldProfile:
    """单个字段的描述性统计画像。"""

    name: str
    dtype: str
    role: str
    count: int
    non_null: int
    null_count: int
    null_rate: float
    unique: int
    stats: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "dtype": self.dtype,
            "role": self.role,
            "count": self.count,
            "non_null": self.non_null,
            "null_count": self.null_count,
            "null_rate": self.null_rate,
            "unique": self.unique,
            **self.stats,
        }


@dataclass
class Profile:
    """全数据集画像：字段画像 + 异常值表 + 空值表。"""

    fields: list[FieldProfile]
    outliers: pd.DataFrame
    nulls: pd.DataFrame
    summary: dict[str, Any] = field(default_factory=dict)

    def to_report(self) -> dict[str, Any]:
        return {
            "summary": self.summary,
            "fields": [f.to_dict() for f in self.fields],
            "outlier_count": int(len(self.outliers)),
            "outliers": _frame_to_records(self.outliers),
            "null_summary": _frame_to_records(self.nulls),
        }

    def to_markdown(self) -> str:
        lines = ["# 描述性统计报告", ""]
        if self.summary:
            lines.append("## 概要")
            for k, v in self.summary.items():
                lines.append(f"- {k}: {v}")
            lines.append("")
        lines.append("## 字段画像")
        lines.append("")
        lines.append("| 字段 | 类型 | 角色 | 非空 | 缺失率 | 唯一值 | 关键统计 |")
        lines.append("| --- | --- | --- | --- | --- | --- | --- |")
        for f in self.fields:
            key_stats = _compact_stats(f.stats)
            lines.append(
                f"| {f.name} | {f.dtype} | {f.role} | {f.non_null} | "
                f"{f.null_rate:.2%} | {f.unique} | {key_stats} |"
            )
        lines.append("")
        if len(self.outliers):
            lines.append(f"## 异常值（共 {len(self.outliers)} 条）")
            lines.append("")
            lines.append("| 字段 | 行 | 值 | 方法 | 下界 | 上界 |")
            lines.append("| --- | --- | --- | --- | --- | --- |")
            for _, r in self.outliers.head(200).iterrows():
                lines.append(
                    f"| {r.get('field')} | {r.get('index')} | {r.get('value')} | "
                    f"{r.get('method')} | {r.get('lower_bound')} | {r.get('upper_bound')} |"
                )
            if len(self.outliers) > 200:
                lines.append(f"| … | … | （其余 {len(self.outliers) - 200} 条省略） | | | |")
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"


def _compact_stats(stats: dict[str, Any]) -> str:
    parts = []
    for k in ("min", "max", "mean", "median", "std", "negative_rate", "zero_rate", "top1"):
        if k in stats and stats[k] is not None:
            v = stats[k]
            if isinstance(v, float):
                v = f"{v:.4g}"
            parts.append(f"{k}={v}")
    return "; ".join(parts) if parts else "-"


def _frame_to_records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    if frame is None or frame.empty:
        return []
    return frame.astype(object).where(pd.notna(frame), None).to_dict(orient="records")


def _is_numeric(series: pd.Series) -> bool:
    return pd.api.types.is_numeric_dtype(series) and not pd.api.types.is_bool_dtype(series)


def _is_datetime(series: pd.Series) -> bool:
    return pd.api.types.is_datetime64_any_dtype(series)


def null_summary(frame: pd.DataFrame, roles: dict[str, Role]) -> pd.DataFrame:
    """逐字段空值统计，并结合角色给出「空值语义」。"""
    rows = []
    for col in frame.columns:
        s = frame[col]
        null_count = int(s.isna().sum())
        role = roles.get(col, Role.NUMERIC)
        rows.append({
            "field": col,
            "null_count": null_count,
            "null_rate": null_count / len(s) if len(s) else 0.0,
            "role": role.value,
            "semantic": _null_semantic(role),
        })
    return pd.DataFrame(rows)


def _null_semantic(role: Role) -> str:
    table = {
        Role.KEY: "缺陷：主键缺失，通常需剔除",
        Role.EVENT: "信息：缺失常表示右删失/未发生，不当作脏数据",
        Role.TIME_VARYING: "可选：缺失可标记或填充",
        Role.SPATIAL: "需处理：缺失坐标影响映射，可近似或置空",
        Role.CATEGORICAL: "可重编码：缺失可归入 UNKNOWN 类",
        Role.NUMERIC: "可选：缺失可标记或填充",
        Role.TARGET: "仅观测：目标缺失不自动清洗",
        Role.IGNORE: "忽略",
    }
    return table.get(role, "-")


def detect_outliers(
    frame: pd.DataFrame,
    method: str = "iqr",
    threshold: float = 1.5,
) -> pd.DataFrame:
    """检测数值列的异常值，返回一条一行的问题表。

    方法
    ----
    * ``iqr``：``x < Q1 - threshold*IQR`` 或 ``x > Q3 + threshold*IQR``
    * ``zscore``：``|z| > threshold``
    * ``mad``：``|0.6745*(x-median)/MAD| > threshold``（稳健）
    """
    method = method.lower()
    if method not in {"iqr", "zscore", "mad"}:
        raise ValueError(f"unknown outlier method: {method!r} (use iqr/zscore/mad)")

    records: list[dict[str, Any]] = []
    for col in frame.columns:
        s = frame[col]
        if not _is_numeric(s):
            continue
        valid = s.dropna()
        if valid.empty:
            continue
        arr = valid.to_numpy(dtype=float)

        if method == "iqr":
            q1, q3 = np.percentile(arr, [25, 75])
            iqr = q3 - q1
            lower, upper = q1 - threshold * iqr, q3 + threshold * iqr
            mask = (arr < lower) | (arr > upper)
            for idx, val in zip(valid.index[mask], arr[mask]):
                records.append({"field": col, "index": idx, "value": val,
                                "method": "iqr", "lower_bound": lower, "upper_bound": upper})
        elif method == "zscore":
            mean, std = arr.mean(), arr.std(ddof=0)
            if std == 0:
                continue
            z = (arr - mean) / std
            mask = np.abs(z) > threshold
            for idx, val, zv in zip(valid.index[mask], arr[mask], z[mask]):
                records.append({"field": col, "index": idx, "value": val,
                                "method": "zscore", "lower_bound": -threshold, "upper_bound": threshold})
        else:  # mad
            med = np.median(arr)
            mad = np.median(np.abs(arr - med))
            if mad == 0:
                continue
            mz = 0.6745 * (arr - med) / mad
            mask = np.abs(mz) > threshold
            for idx, val in zip(valid.index[mask], arr[mask]):
                records.append({"field": col, "index": idx, "value": val,
                                "method": "mad", "lower_bound": -threshold, "upper_bound": threshold})

    return pd.DataFrame(records, columns=["field", "index", "value", "method", "lower_bound", "upper_bound"])


def _field_stats(name: str, s: pd.Series, role: Role, top_n: int) -> FieldProfile:
    null_count = int(s.isna().sum())
    count = len(s)
    non_null = count - null_count
    stats: dict[str, Any] = {}

    if _is_numeric(s):
        v = s.dropna()
        if len(v):
            stats.update({
                "min": float(v.min()),
                "max": float(v.max()),
                "mean": float(v.mean()),
                "median": float(v.median()),
                "std": float(v.std(ddof=0)),
                "quantiles": {f"q{int(q*100)}": float(v.quantile(q)) for q in _NUM_QUANTILES},
                "negative_rate": float((v < 0).mean()),
                "zero_rate": float((v == 0).mean()),
            })
    elif _is_datetime(s):
        v = s.dropna()
        if len(v):
            stats.update({"min": str(v.min()), "max": str(v.max())})
    else:
        v = s.dropna().astype(str)
        if len(v):
            counts = v.value_counts()
            stats["top"] = {k: int(c) for k, c in counts.head(top_n).items()}
            if len(stats["top"]):
                stats["top1"] = next(iter(stats["top"]))

    return FieldProfile(
        name=name,
        dtype=str(s.dtype),
        role=role.value,
        count=count,
        non_null=non_null,
        null_count=null_count,
        null_rate=null_count / count if count else 0.0,
        unique=int(s.nunique(dropna=True)),
        stats=stats,
    )


def profile(
    dataset: Dataset | pd.DataFrame,
    roles: dict[str, str | Role] | None = None,
    outlier_method: str = "iqr",
    outlier_threshold: float = 1.5,
    top_n: int = 10,
) -> Profile:
    """对数据集做描述性统计，产出 :class:`Profile`。

    参数
    ----
    roles : 字段角色映射；缺省用 :func:`datakit.core.infer_roles` 推断。
    outlier_method : ``iqr`` / ``zscore`` / ``mad``。
    outlier_threshold : 异常值阈值（IQR 倍数 / Z 分 / MAD 修正 Z 分）。
    """
    frame = dataset.frame if isinstance(dataset, Dataset) else dataset
    role_map = infer_roles(frame.columns)
    if roles:
        for col, r in roles.items():
            role_map[col] = Role(r) if isinstance(r, str) else r

    fields = []
    for col in frame.columns:
        role = role_map.get(col, Role.NUMERIC)
        fields.append(_field_stats(col, frame[col], role, top_n))

    outliers = detect_outliers(frame, method=outlier_method, threshold=outlier_threshold)
    nulls = null_summary(frame, role_map)

    total = len(frame)
    summary = {
        "rows": total,
        "columns": len(frame.columns),
        "null_cells": int(frame.isna().sum().sum()),
        "null_rate": float(frame.isna().sum().sum() / (total * len(frame.columns))) if total and len(frame.columns) else 0.0,
        "outlier_count": int(len(outliers)),
    }
    return Profile(fields=fields, outliers=outliers, nulls=nulls, summary=summary)


# 语义化别名
describe = profile
