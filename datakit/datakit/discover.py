"""数据采集 / 发现（流程第 1 步）。

给定一个根目录，递归识别其中的数据文件，做指纹（大小/列数/可选 MD5 与行数），
并按「目录 + 文件名模式」把文件聚合为**数据集分组**，从而回答：

* 目录下有哪些数据文件、分布在哪些子文件夹？
* 哪些文件同属一个数据集（例如 ``fdic_sod_1994.csv … fdic_sod_2025.csv`` 是一组）？
* 每个数据集的规模、列结构、来源指纹是什么？

产物是一个 :class:`Catalog`，可导出为 JSON 报告或 Markdown 清单。

**只读约束**：本模块对源文件只做只读探测，绝不写入或修改源文件。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from .io import SUPPORTED_FORMATS, detect_format, md5_of_file

__all__ = ["Source", "Catalog", "scan", "discover"]

_DIGIT_RUN = re.compile(r"\d+")

# 默认忽略：隐藏文件、下划线开头的元数据文件、日志
_DEFAULT_EXCLUDE = ("_*", ".*")


@dataclass
class Source:
    """单个数据文件的元信息与指纹。"""

    path: str
    name: str
    format: str
    parent: str = ""          # 相对根目录的父目录（"." 表示根）
    size: int | None = None
    md5: str | None = None
    rows: int | None = None
    cols: int | None = None
    columns: list[str] = field(default_factory=list)
    group: str | None = None  # 所属数据集分组名

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "name": self.name,
            "format": self.format,
            "parent": self.parent,
            "size": self.size,
            "md5": self.md5,
            "rows": self.rows,
            "cols": self.cols,
            "columns": self.columns,
            "group": self.group,
        }


class Catalog:
    """采集结果：一组 ``Source`` 及其分组视图。"""

    def __init__(self, root: str, sources: list[Source]):
        self.root = root
        self.sources = sources
        self.groups: dict[str, list[Source]] = {}
        for src in sources:
            self.groups.setdefault(src.group or "<ungrouped>", []).append(src)

    def __len__(self) -> int:
        return len(self.sources)

    def to_frame(self) -> pd.DataFrame:
        """转成 pandas 表格（便于再分析）。"""
        return pd.DataFrame([s.to_dict() for s in self.sources])

    def to_report(self) -> dict[str, Any]:
        """JSON 报告结构。"""
        return {
            "root": self.root,
            "file_count": len(self.sources),
            "group_count": len(self.groups),
            "groups": {
                name: {
                    "file_count": len(srcs),
                    "formats": sorted({s.format for s in srcs}),
                    "total_size": sum(s.size or 0 for s in srcs),
                    "files": [s.to_dict() for s in srcs],
                }
                for name, srcs in sorted(self.groups.items())
            },
        }

    def to_markdown(self) -> str:
        """Markdown 人读清单。"""
        lines = [f"# 数据采集清单：{self.root}", "",
                 f"- 文件总数：{len(self.sources)}", f"- 数据集分组：{len(self.groups)}", ""]
        for name, srcs in sorted(self.groups.items()):
            lines.append(f"## 数据集：{name}")
            lines.append(f"- 文件数：{len(srcs)}")
            for s in srcs:
                meta = [f"size={s.size}"] if s.size is not None else []
                if s.cols is not None:
                    meta.append(f"cols={s.cols}")
                if s.rows is not None:
                    meta.append(f"rows={s.rows}")
                suffix = f" ({', '.join(meta)})" if meta else ""
                lines.append(f"  - {s.name}{suffix}")
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"


def _stem_pattern(name: str) -> str:
    """把文件名中的连续数字替换为 ``#``，用于识别「同构多文件数据集」。"""
    stem = name
    for ext in (".gz", ".csv", ".tsv", ".json", ".jsonl", ".ndjson", ".xml", ".rdf", ".ttl", ".nt", ".n3", ".xlsx", ".txt"):
        if stem.lower().endswith(ext):
            stem = stem[: -len(ext)]
            break
    return _DIGIT_RUN.sub("#", stem)


def _peek_columns(path: Path, fmt: str) -> list[str]:
    """只读表头取列名（不载入数据）。"""
    try:
        if fmt in {"csv", "tsv"}:
            sep = "\t" if fmt == "tsv" else ","
            for enc in ("utf-8-sig", "utf-8", "gb18030", "latin-1"):
                try:
                    head = pd.read_csv(path, sep=sep, nrows=0, encoding=enc)
                    return list(head.columns)
                except UnicodeDecodeError:
                    continue
        elif fmt in {"json", "jsonl", "ndjson"}:
            frame = pd.read_json(path, lines=True, nrows=0)
            return list(frame.columns)
        elif fmt == "xlsx":
            frame = pd.read_excel(path, nrows=0)
            return list(frame.columns)
    except Exception:
        return []
    return []


def _count_lines(path: Path, fmt: str) -> int | None:
    """流式统计文本类文件行数（可选，成本 O(文件大小)）。"""
    if fmt not in {"csv", "tsv", "json", "jsonl", "ndjson", "txt"}:
        return None
    if path.suffix.lower() == ".gz":
        import gzip
        opener = gzip.open
    else:
        opener = open
    try:
        with opener(path, "rt", encoding="utf-8", errors="ignore") as f:
            return sum(1 for _ in f)
    except Exception:
        return None


def scan(
    root: str | Path,
    formats: Iterable[str] | None = None,
    recursive: bool = True,
    with_md5: bool = False,
    count_rows: bool = False,
    exclude: Iterable[str] = _DEFAULT_EXCLUDE,
) -> Catalog:
    """扫描目录，识别数据文件并分组为数据集。

    参数
    ----
    root : 根目录。
    formats : 限定格式集合（默认支持全部 ``SUPPORTED_FORMATS``）。
    recursive : 是否递归子目录。
    with_md5 : 是否计算 MD5 指纹（大目录建议关闭，成本高）。
    count_rows : 是否统计行数（大目录建议关闭，成本 O(文件大小)）。
    exclude : 文件名通配忽略列表（默认忽略 ``_*`` 与 ``.*``）。
    """
    root_path = Path(root)
    wanted = set(formats) if formats else set(SUPPORTED_FORMATS)

    exclusions = tuple(exclude)
    import fnmatch

    def _ignored(name: str) -> bool:
        return any(fnmatch.fnmatch(name, pat) for pat in exclusions)

    files: list[Path] = []
    if recursive:
        iterator = root_path.rglob("*")
    else:
        iterator = root_path.glob("*")
    for p in iterator:
        if not p.is_file():
            continue
        if _ignored(p.name):
            continue
        try:
            fmt = detect_format(p)
        except Exception:
            continue
        if fmt not in wanted:
            continue
        files.append(p)

    files.sort(key=lambda p: str(p).lower())

    sources: list[Source] = []
    for p in files:
        fmt = detect_format(p)
        parent = p.parent.relative_to(root_path).as_posix() if p.parent != root_path else "."
        size = p.stat().st_size
        cols_list = _peek_columns(p, fmt)
        rows = _count_lines(p, fmt) if count_rows else None
        md5 = md5_of_file(p) if with_md5 else None
        src = Source(
            path=str(p),
            name=p.name,
            format=fmt,
            parent=parent,
            size=size,
            md5=md5,
            rows=rows,
            cols=len(cols_list) if cols_list else None,
            columns=cols_list,
        )
        sources.append(src)

    # 分组：按文件名模式（连续数字归一为 #），同模式文件视为同一数据集
    for src in sources:
        src.group = _stem_pattern(src.name)

    return Catalog(str(root_path), sources)


# 别名：discover 与 scan 同义，方便语义化调用
discover = scan
