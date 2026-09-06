"""数据映射（流程第 5 步）。

「不同想法 → 不同映射方案」。:class:`MappingScheme` 把一种**映射口径**固化为一组可复用的
操作（重命名、派生、分箱、独热、编码、聚合、空间网格化），应用到数据集后产出映射报告，
从而把「从原始字段到分析字段」的转换过程标准化、可追溯、可复现。

典型用法::

    scheme = dk.MappingScheme()
    scheme.rename({"SIMS_LATITUDE": "lat", "SIMS_LONGITUDE": "lng"})
    scheme.derive("deposit_gap", "DEPSUM - DEPDOM", reason="存款差额")
    scheme.bin("DEPSUMBR", bins=[0, 1e5, 1e6, float("inf")], labels=["小", "中", "大"])
    result = dk.map(ds, scheme)
    result.dataset   # 映射后的 Dataset
    result.to_markdown()
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping

import pandas as pd

from .core import Dataset

__all__ = ["MappingOp", "MappingScheme", "MapResult", "map"]


@dataclass
class MappingOp:
    """一个原子映射操作。"""

    op: str
    params: dict[str, Any] = field(default_factory=dict)
    reason: str = ""

    def label(self) -> str:
        return self.op


class MappingScheme:
    """映射方案：顺序映射操作的流畅构建器。"""

    def __init__(self) -> None:
        self.ops: list[MappingOp] = []

    def rename(self, mapping: Mapping[str, str], reason: str = "") -> "MappingScheme":
        self.ops.append(MappingOp("rename", {"mapping": dict(mapping)}, reason))
        return self

    def derive(self, name: str, expr: str | Callable[[pd.DataFrame], pd.Series],
               reason: str = "") -> "MappingScheme":
        self.ops.append(MappingOp("derive", {"name": name, "expr": expr}, reason))
        return self

    def bin(self, field: str, bins: Iterable[float], labels: Iterable[str] | None = None,
            reason: str = "") -> "MappingScheme":
        self.ops.append(MappingOp("bin", {"field": field, "bins": list(bins), "labels": list(labels) if labels else None}, reason))
        return self

    def onehot(self, columns: Iterable[str], reason: str = "") -> "MappingScheme":
        self.ops.append(MappingOp("onehot", {"columns": list(columns)}, reason))
        return self

    def code(self, field: str, mapping: Mapping[Any, Any], default: Any = None,
             reason: str = "") -> "MappingScheme":
        self.ops.append(MappingOp("code", {"field": field, "mapping": dict(mapping), "default": default}, reason))
        return self

    def aggregate(self, group_by: Iterable[str], agg: Mapping[str, str | list[str]],
                  reason: str = "") -> "MappingScheme":
        self.ops.append(MappingOp("aggregate", {"group_by": list(group_by), "agg": dict(agg)}, reason))
        return self

    def geocode(self, lat_field: str, lng_field: str, resolution: int = 8,
                reason: str = "") -> "MappingScheme":
        self.ops.append(MappingOp("geocode", {"lat_field": lat_field, "lng_field": lng_field, "resolution": resolution}, reason))
        return self

    def drop(self, columns: Iterable[str], reason: str = "") -> "MappingScheme":
        self.ops.append(MappingOp("drop", {"columns": list(columns)}, reason))
        return self

    @classmethod
    def from_spec(cls, spec: Iterable[dict[str, Any]]) -> "MappingScheme":
        """从配置字典列表构建映射方案（便于把映射口径外置到配置文件）。"""
        scheme = cls()
        for item in spec:
            op = item["op"]
            reason = item.get("reason", "")
            if op == "rename":
                scheme.rename(item["mapping"], reason)
            elif op == "derive":
                scheme.derive(item["name"], item["expr"], reason)
            elif op == "bin":
                scheme.bin(item["field"], item["bins"], item.get("labels"), reason)
            elif op == "onehot":
                scheme.onehot(item["columns"], reason)
            elif op == "code":
                scheme.code(item["field"], item["mapping"], item.get("default"), reason)
            elif op == "aggregate":
                scheme.aggregate(item["group_by"], item["agg"], reason)
            elif op == "geocode":
                scheme.geocode(item["lat_field"], item["lng_field"], item.get("resolution", 8), reason)
            elif op == "drop":
                scheme.drop(item["columns"], reason)
            else:
                raise ValueError(f"unknown mapping op: {op}")
        return scheme


@dataclass
class MapResult:
    """映射结果：映射后的数据集 + 映射报告。"""

    dataset: Dataset
    report: list[dict[str, Any]] = field(default_factory=list)

    def to_report(self) -> dict[str, Any]:
        return {"operations": self.report, "shape": list(self.dataset.shape)}

    def to_markdown(self) -> str:
        lines = ["# 数据映射报告", "",
                 f"- 映射后形状：{self.dataset.shape[0]} 行 × {self.dataset.shape[1]} 列", ""]
        for r in self.report:
            lines.append(f"- `{r['op']}`：{r['detail']}" + (f"（{r['reason']}）" if r.get("reason") else ""))
        lines.append("")
        return "\n".join(lines)


def map(dataset: Dataset | pd.DataFrame, scheme: MappingScheme) -> MapResult:
    """按映射方案应用操作，返回 :class:`MapResult`。"""
    frame = dataset.frame if isinstance(dataset, Dataset) else dataset
    frame = frame.copy()
    report: list[dict[str, Any]] = []

    for op in scheme.ops:
        p = op.params
        if op.op == "rename":
            frame = frame.rename(columns=p["mapping"])
            report.append({"op": "rename", "detail": str(p["mapping"]), "reason": op.reason})
        elif op.op == "derive":
            name, expr = p["name"], p["expr"]
            if callable(expr):
                frame[name] = expr(frame)
            else:
                frame[name] = frame.eval(expr)
            report.append({"op": "derive", "detail": f"新增列 {name}", "reason": op.reason})
        elif op.op == "bin":
            labels = p.get("labels")
            frame[f"{p['field']}_bin"] = pd.cut(frame[p["field"]], bins=p["bins"], labels=labels)
            report.append({"op": "bin", "detail": f"{p['field']} → {p['field']}_bin", "reason": op.reason})
        elif op.op == "onehot":
            cols = p["columns"]
            dummies = pd.get_dummies(frame[cols], prefix=cols)
            frame = pd.concat([frame.drop(columns=cols), dummies], axis=1)
            report.append({"op": "onehot", "detail": f"独热编码 {cols}", "reason": op.reason})
        elif op.op == "code":
            frame[f"{p['field']}_code"] = frame[p["field"]].map(p["mapping"]).fillna(p.get("default"))
            report.append({"op": "code", "detail": f"{p['field']} → {p['field']}_code", "reason": op.reason})
        elif op.op == "aggregate":
            frame = frame.groupby(p["group_by"], as_index=False).agg(p["agg"])
            report.append({"op": "aggregate", "detail": f"按 {p['group_by']} 聚合", "reason": op.reason})
        elif op.op == "geocode":
            try:
                import h3  # type: ignore
            except ImportError as exc:
                raise ImportError("空间网格化需要可选依赖 'h3'，请执行: uv add h3 或 pip install h3") from exc
            lat_f, lng_f, res = p["lat_field"], p["lng_field"], p["resolution"]
            cells, skipped = [], 0
            for lat, lng in zip(frame[lat_f], frame[lng_f]):
                if pd.isna(lat) or pd.isna(lng):
                    cells.append(None)
                    skipped += 1
                    continue
                cells.append(h3.latlng_to_cell(float(lat), float(lng), res))
            frame["h3"] = cells
            report.append({"op": "geocode", "reason": op.reason,
                           "detail": f"新增列 h3 (res={res})"
                                     + (f"；{skipped} 行坐标缺失，h3 置空" if skipped else "")})
        elif op.op == "drop":
            frame = frame.drop(columns=p["columns"])
            report.append({"op": "drop", "detail": f"删除列 {p['columns']}", "reason": op.reason})
        else:
            raise ValueError(f"unknown mapping op: {op.op}")

    if isinstance(dataset, Dataset):
        out = dataset.with_frame(frame)
    else:
        out = Dataset(frame)
    return MapResult(dataset=out, report=report)
