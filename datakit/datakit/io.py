"""数据读写：JSON / CSV / XML / RDF / XLSX（含 ``.gz`` 压缩）。

本模块是 SDK 与外部文件的**唯一读写入口**。支持格式：

=============  ============  ==============================================
格式           扩展名        说明
=============  ============  ==============================================
CSV            ``.csv``     分隔文本，自动尝试多种编码（含 BOM / latin-1）
TSV            ``.tsv``     tab 分隔文本
JSON           ``.json``    数组或换行分隔（JSONL / NDJSON）
XML            ``.xml``     通用扁平化：重复子元素 → 记录
RDF            ``.rdf .ttl .nt .n3`` 三元组 → ``(subject, predicate, object)``
XLSX           ``.xlsx``    Excel 工作簿（第一个 sheet）
压缩           ``.gz``      CSV / JSON / TSV / 文本的 gzip 包裹
=============  ============  ==============================================

依赖策略：``pandas`` / ``numpy`` / ``openpyxl`` / ``lxml`` 为必需依赖；
``rdflib`` 为可选依赖（未安装时读 RDF 会给出明确错误）。
"""

from __future__ import annotations

import gzip
import hashlib
import json as _json
from pathlib import Path
from typing import Any

import pandas as pd

from .core import Dataset, DatasetMeta, FormatNotSupportedError

__all__ = [
    "SUPPORTED_FORMATS",
    "detect_format",
    "read",
    "read_csv",
    "read_json",
    "read_xml",
    "read_rdf",
    "read_xlsx",
    "write",
    "md5_of_file",
]

SUPPORTED_FORMATS = {
    "csv", "tsv", "json", "jsonl", "ndjson",
    "xml", "rdf", "ttl", "nt", "n3", "xlsx",
}

_EXT_MAP = {
    ".csv": "csv",
    ".tsv": "tsv",
    ".json": "json",
    ".jsonl": "jsonl",
    ".ndjson": "ndjson",
    ".xml": "xml",
    ".rdf": "rdf",
    ".ttl": "ttl",
    ".nt": "nt",
    ".n3": "n3",
    ".xlsx": "xlsx",
    ".xls": "xlsx",
    ".txt": "txt",
    ".gz": "gz",
}

_CSV_ENCODINGS = ("utf-8-sig", "utf-8", "gb18030", "latin-1")


def _strip_gz(path: Path) -> tuple[Path, bool]:
    """去掉一层 ``.gz``，返回内部路径与是否压缩。"""
    if path.suffix.lower() == ".gz":
        return Path(str(path)[:-3]), True
    return path, False


def detect_format(path: str | Path) -> str:
    """根据扩展名识别格式；``.gz`` 会向内再探一层（如 ``x.csv.gz`` → ``csv``）。"""
    p = Path(path)
    inner, gz = _strip_gz(p)
    fmt = _EXT_MAP.get(inner.suffix.lower())
    if fmt is None:
        raise FormatNotSupportedError(inner.suffix.lower() or p.name, SUPPORTED_FORMATS)
    return fmt


def md5_of_file(path: str | Path, chunk_size: int = 1024 * 1024) -> str:
    """流式计算文件 MD5（不整文件载入内存，用于只读指纹）。"""
    h = hashlib.md5()
    with Path(path).open("rb") as f:
        while True:
            block = f.read(chunk_size)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


# --------------------------------------------------------------------------- #
# 读取
# --------------------------------------------------------------------------- #
def read(path: str | Path, **kwargs: Any) -> Dataset:
    """自动识别格式并读取为 :class:`Dataset`。

    是 ``read_csv`` / ``read_json`` / ``read_xml`` / ``read_rdf`` / ``read_xlsx`` 的统一入口。
    额外的 ``kwargs`` 透传给底层 pandas 读取函数。
    """
    p = Path(path)
    fmt = detect_format(p)
    if fmt in {"csv", "tsv"}:
        return read_csv(p, **kwargs)
    if fmt in {"json", "jsonl", "ndjson"}:
        return read_json(p, **kwargs)
    if fmt == "xml":
        return read_xml(p)
    if fmt in {"rdf", "ttl", "nt", "n3"}:
        return read_rdf(p)
    if fmt == "xlsx":
        return read_xlsx(p, **kwargs)
    raise FormatNotSupportedError(fmt, SUPPORTED_FORMATS)


def _open_text(path: Path):
    """打开文本文件，自动处理 gzip。"""
    _, gz = _strip_gz(path)
    if gz:
        return gzip.open(path, "rt", encoding="utf-8", newline="")
    return path.open("r", encoding="utf-8", newline="")


def read_csv(path: str | Path, sep: str | None = None, **kwargs: Any) -> Dataset:
    """读取 CSV / TSV。

    自动尝试多种编码；失败时给出包含已尝试编码的错误信息。
    """
    p = Path(path)
    if sep is None:
        sep = "\t" if detect_format(p) == "tsv" else ","
    last_exc: Exception | None = None
    for enc in _CSV_ENCODINGS:
        try:
            frame = pd.read_csv(p, sep=sep, encoding=enc, **kwargs)
            break
        except UnicodeDecodeError as exc:  # 编码不匹配，尝试下一个
            last_exc = exc
            continue
    else:
        raise ValueError(f"cannot decode {p} with any of {_CSV_ENCODINGS}: {last_exc}") from last_exc
    return Dataset(frame, DatasetMeta(source=str(p), format=detect_format(p), rows=len(frame), cols=len(frame.columns)))


def read_json(path: str | Path, lines: bool | None = None, **kwargs: Any) -> Dataset:
    """读取 JSON（数组）或 JSONL/NDJSON（换行分隔）。

    ``lines`` 缺省时自动探测：首行非空且以 ``{`` 开头视为 JSONL。
    """
    p = Path(path)
    if lines is None:
        lines = _looks_like_jsonl(p)
    frame = pd.read_json(p, lines=lines, **kwargs)
    return Dataset(frame, DatasetMeta(source=str(p), format="jsonl" if lines else "json", rows=len(frame), cols=len(frame.columns)))


def _looks_like_jsonl(p: Path) -> bool:
    with _open_text(p) as f:
        for line in f:
            stripped = line.lstrip()
            if stripped:
                return stripped.startswith("{")
    return False


def read_xml(path: str | Path) -> Dataset:
    """通用 XML → 表格。

    规则：若根元素下存在重复的同名子元素，则将每个子元素视为一条记录，
    递归扁平化其属性与嵌套子元素为列；否则退化为「路径 → 文本」两列表。
    """
    import xml.etree.ElementTree as ET

    p = Path(path)
    with _open_text(p) as f:
        root = ET.parse(f).getroot()

    children = list(root)
    if not children:
        frame = pd.DataFrame({"path": [_tag_path(root)], "text": [root.text or ""]})
        return Dataset(frame, DatasetMeta(source=str(p), format="xml", rows=len(frame), cols=len(frame.columns)))

    tags = [c.tag for c in children]
    # 若存在重复标签，取出现次数最多的那个作为「记录」标签
    from collections import Counter
    record_tag = Counter(tags).most_common(1)[0][0]
    records = [_flatten_element(c) for c in children if c.tag == record_tag]
    frame = pd.DataFrame(records)
    return Dataset(frame, DatasetMeta(source=str(p), format="xml", rows=len(frame), cols=len(frame.columns)))


def _tag_path(elem: Any) -> str:
    return elem.tag


def _flatten_element(elem: Any) -> dict[str, Any]:
    """把 XML 元素递归压平为单层 dict（列名 = 相对路径）。"""
    out: dict[str, Any] = {}
    for key, val in elem.attrib.items():
        out[f"@{key}"] = val
    children = list(elem)
    if children:
        for child in children:
            nested = _flatten_element(child)
            for k, v in nested.items():
                col = f"{child.tag}.{k}" if k.startswith("@") or k == "#text" else f"{child.tag}_{k}"
                out[col] = v
    else:
        text = (elem.text or "").strip()
        if text:
            out["#text"] = text
    return out


def read_rdf(path: str | Path, format: str | None = None) -> Dataset:
    """读取 RDF 图为三元组表 ``(subject, predicate, object)``。

    需要可选依赖 ``rdflib``；未安装时抛出带指引的错误。
    """
    p = Path(path)
    try:
        import rdflib  # type: ignore
    except ImportError as exc:
        raise ImportError(
            "RDF 读取需要可选依赖 'rdflib'，请执行: uv add rdflib 或 pip install rdflib"
        ) from exc

    graph = rdflib.Graph()
    graph.parse(str(p), format=format)
    rows = [
        {"subject": str(s), "predicate": str(pred), "object": str(o)}
        for s, pred, o in graph
    ]
    frame = pd.DataFrame(rows, columns=["subject", "predicate", "object"])
    return Dataset(frame, DatasetMeta(source=str(p), format="rdf", rows=len(frame), cols=len(frame.columns)))


def read_xlsx(path: str | Path, sheet_name: Any = 0, **kwargs: Any) -> Dataset:
    """读取 Excel 工作簿（默认第一个 sheet）。"""
    p = Path(path)
    frame = pd.read_excel(p, sheet_name=sheet_name, **kwargs)
    return Dataset(frame, DatasetMeta(source=str(p), format="xlsx", rows=len(frame), cols=len(frame.columns)))


# --------------------------------------------------------------------------- #
# 写入
# --------------------------------------------------------------------------- #
def write(dataset: Dataset, path: str | Path, format: str | None = None, **kwargs: Any) -> Path:
    """把 :class:`Dataset` 写出到文件，格式默认按扩展名推断。"""
    p = Path(path)
    fmt = format or detect_format(p)
    p.parent.mkdir(parents=True, exist_ok=True)

    if fmt in {"csv", "tsv"}:
        sep = "\t" if fmt == "tsv" else ","
        dataset.frame.to_csv(p, sep=sep, index=False, encoding="utf-8-sig", **kwargs)
    elif fmt in {"json", "jsonl", "ndjson"}:
        lines = fmt in {"jsonl", "ndjson"}
        if lines:
            dataset.frame.to_json(p, orient="records", lines=True, force_ascii=False, **kwargs)
        else:
            dataset.frame.to_json(p, orient="records", force_ascii=False, indent=2, **kwargs)
    elif fmt == "xlsx":
        dataset.frame.to_excel(p, index=False, **kwargs)
    elif fmt in {"rdf", "ttl", "nt", "n3", "xml"}:
        raise FormatNotSupportedError(fmt, {"csv", "json", "jsonl", "xlsx"})
    else:
        raise FormatNotSupportedError(fmt, SUPPORTED_FORMATS)
    return p
