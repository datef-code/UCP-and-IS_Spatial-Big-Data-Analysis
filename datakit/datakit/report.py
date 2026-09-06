"""报告与日志写出：把各流程阶段的产物落盘为 JSON / Markdown。

所有写出都发生在调用方指定的 ``output_dir`` 下，**从不写回源数据目录**。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

__all__ = ["write_json", "write_markdown", "write_report", "write_jsonl",
           "write_yaml", "write_csv"]


def write_json(output_dir: str | Path, name: str, obj: Any) -> Path:
    """写 JSON 文件（``name.json``），返回路径。"""
    target = Path(output_dir) / f"{name}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(obj, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    return target


def write_yaml(output_dir: str | Path, name: str, obj: Any) -> Path:
    """写 YAML 文件（``name.yaml``），返回路径。

    机读报告与 ``config/*.yaml`` 统一用 YAML：一律 ``safe_dump``
    （禁止 ``!!python/object``），保留键顺序与中文。
    """
    import yaml

    target = Path(output_dir) / f"{name}.yaml"
    target.parent.mkdir(parents=True, exist_ok=True)
    text = yaml.safe_dump(_to_yamlable(obj), allow_unicode=True,
                          sort_keys=False, default_flow_style=False)
    target.write_text(text, encoding="utf-8")
    return target


def write_csv(output_dir: str | Path, name: str, frame: "Any") -> Path:
    """写 CSV 明细表（``name.csv``），返回路径。``frame`` 为 DataFrame 或记录列表。"""
    import pandas as pd

    target = Path(output_dir) / f"{name}.csv"
    target.parent.mkdir(parents=True, exist_ok=True)
    df = frame if isinstance(frame, pd.DataFrame) else pd.DataFrame(list(frame))
    df.to_csv(target, index=False, encoding="utf-8-sig")
    return target


def _to_yamlable(obj: Any) -> Any:
    """把报告对象转成可安全 dump 的纯数据结构。"""
    if hasattr(obj, "to_report"):
        return _to_yamlable(obj.to_report())
    if hasattr(obj, "to_dict"):
        return _to_yamlable(obj.to_dict())
    if isinstance(obj, dict):
        return {str(k): _to_yamlable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_yamlable(v) for v in obj]
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, float) and obj != obj:      # NaN → None（yaml 无 NaN 字面量）
        return None
    try:
        import numpy as np
        if isinstance(obj, np.generic):
            return obj.item()
    except Exception:
        pass
    return obj


def write_markdown(output_dir: str | Path, name: str, text: str) -> Path:
    """写 Markdown 文件（``name.md``），返回路径。"""
    target = Path(output_dir) / f"{name}.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return target


def write_jsonl(output_dir: str | Path, name: str, records: Iterable[dict[str, Any]]) -> Path:
    """写 JSONL 文件（每行一个 JSON 对象）。"""
    target = Path(output_dir) / f"{name}.jsonl"
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="\n") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
    return target


def write_report(output_dir: str | Path, name: str, report: Any) -> tuple[Path, Path]:
    """写报告：同时产出 JSON 与 Markdown（若对象支持）。

    支持：dict（仅 JSON）、带 ``to_report``/``to_markdown`` 方法的报告对象。
    返回 ``(json_path, md_path)``；不适用 Markdown 时 ``md_path`` 为 ``None``。
    """
    json_path = write_json(output_dir, name, _to_jsonable(report))
    md_path = None
    if hasattr(report, "to_markdown"):
        md_path = write_markdown(output_dir, name, report.to_markdown())
    return json_path, md_path


def _to_jsonable(report: Any) -> Any:
    if isinstance(report, dict):
        return report
    if hasattr(report, "to_report"):
        return report.to_report()
    if hasattr(report, "to_dict"):
        return report.to_dict()
    return {"value": str(report)}
