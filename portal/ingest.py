#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""portal/ingest.py —— 泛化数据接入内核（与具体数据集解耦）。

设计目标（对应产品的三条硬伤）：
    1. **多份文件**：一份数据由 N 个文件组成，按列名并集纵向拼接（缺列补空并登记）。
    2. **字段不固定**：角色（entity/time/lat/lon/value/...）由**内容**推断，不依赖列名；
       自动推断只是起点，人工可在前端覆盖，并可存为「映射模板」复用。
    3. **形态不固定**：识别 panel / event_log / cross_section / time_series / network / unknown，
       按形态路由到不同体检规则集，而不是硬套「网点-年面板」。

数据流：
    Source（文件） → Dataset（合并表） → Mapping（角色） → Shape（形态） → Health（体检）

对外只暴露纯函数 + 一个 ``DatasetBundle`` 数据类，便于单测与服务层复用。
    python portal/ingest.py --paths "data_raw/fdic/*.csv" --limit 20000
"""

from __future__ import annotations

import gzip
import json
import re
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

PORTAL = Path(__file__).resolve().parent
TEMPLATE_DIR = PORTAL / ".templates"

# 角色（越靠前的越"结构性"，体检与重估都依赖）
ROLES = ("entity", "time", "event_time", "lat", "lon", "value", "group")

_ROLE_HINT = {
    "entity": r"(^|_)(id|uid|code|key|uuid|no|num|number|cert|brnum|store|shop|site|branch|outlet|user|node|src|dst|from|to)($|_)",
    "time": r"(year|yr|date|time|period|month|quarter|day|ts|timestamp|年份|年度|日期)",
    "event_time": r"(event|acq|closed|close|exit|death|end|failure|surviv|churn|退出|关闭|事件)",
    "lat": r"(lat|latitude|纬度|^y$)",
    "lon": r"(lon|lng|long|longitude|经度|^x$)",
    "value": r"(value|amount|dep|deposit|sales|revenue|turnover|gmv|volume|count|num_|存款|金额|销售额|营收|单量)",
    "group": r"(class|type|category|group|segment|tier|industry|region|state|province|类别|类型|分层|行业|地区)",
}

# 只读一个文件时的兜底上限（避免误把 30GB 目录读进内存）
DEFAULT_FILE_LIMIT = 200
DEFAULT_ROW_LIMIT_PER_FILE = 200_000


# --------------------------------------------------------------------------- #
# 1) Source / 读取
# --------------------------------------------------------------------------- #
@dataclass
class SourceMeta:
    path: str
    name: str
    rows: int
    cols: int
    bytes: int
    format: str
    ok: bool = True
    error: str | None = None

    def to_dict(self) -> dict:
        return {"path": self.path, "name": self.name, "rows": self.rows, "cols": self.cols,
                "bytes": self.bytes, "format": self.format, "ok": self.ok, "error": self.error}


@dataclass
class DatasetBundle:
    """一份「数据集」：合并后的表 + 每份文件摘要 + 列覆盖差异。"""
    frame: pd.DataFrame
    sources: list[SourceMeta] = field(default_factory=list)
    missing_note: list[str] = field(default_factory=list)

    @property
    def rows(self) -> int:
        return int(len(self.frame))

    @property
    def columns(self) -> list[str]:
        return [str(c) for c in self.frame.columns]

    @property
    def source_count(self) -> int:
        return len(self.sources)

    def schema_diff(self) -> dict:
        """哪些列只在部分文件里出现（多源拼接的常见坑）。"""
        per_file: dict[str, set] = {}
        for s in self.sources:
            per_file[s.name] = set(s.__dict__.get("columns", []) or [])
        if not per_file:
            return {"partial_columns": [], "all_columns": self.columns}
        cols_by_file = {k: v for k, v in per_file.items() if v}
        if not cols_by_file:
            return {"partial_columns": [], "all_columns": self.columns}
        n = len(cols_by_file)
        counts: dict[str, int] = {}
        for v in cols_by_file.values():
            for c in v:
                counts[c] = counts.get(c, 0) + 1
        partial = sorted([c for c, k in counts.items() if 0 < k < n])
        return {
            "partial_columns": [{"column": c, "in_files": counts[c], "of_files": n} for c in partial],
            "all_columns": self.columns,
        }


def expand_sources(paths: Iterable[str], limit: int = DEFAULT_FILE_LIMIT,
                   recursive: bool = True) -> tuple[list[Path], list[str]]:
    """把「路径 / 目录 / 通配符」展开成文件列表。返回 (文件, 提示)。

    - 目录：递归取支持的数据文件
    - 通配符：``data_raw/fdic/*.csv``
    - 上限保护：超过 ``limit`` 只取前 limit 个并给出提示
    """
    exts = {".csv", ".tsv", ".txt", ".json", ".jsonl", ".ndjson", ".xlsx", ".gz"}
    files: list[Path] = []
    notes: list[str] = []
    for raw in paths:
        p = Path(str(raw).strip().strip('"').strip("'"))
        if not p.is_absolute():
            p = (PORTAL.parent / p) if not p.exists() else p
        if p.is_dir():
            it = p.rglob("*") if recursive else p.glob("*")
            hits = [q for q in sorted(it) if q.is_file() and _inner_ext(q) in exts]
            if not hits:
                notes.append(f"{p} 下未找到可读数据文件")
            files.extend(hits)
        elif any(ch in str(raw) for ch in "*?["):
            base = p.parent if p.parent.exists() else PORTAL.parent
            hits = [q for q in sorted(base.glob(p.name)) if q.is_file()]
            if not hits:
                notes.append(f"通配符未匹配到文件：{raw}")
            files.extend(hits)
        elif p.is_file():
            files.append(p)
        else:
            notes.append(f"路径不存在：{raw}")
    # 去重 + 排序，保持稳定
    seen, uniq = set(), []
    for f in files:
        rp = str(f.resolve())
        if rp not in seen:
            seen.add(rp)
            uniq.append(f)
    if len(uniq) > limit:
        notes.append(f"匹配到 {len(uniq)} 个文件，超过上限 {limit}，只取前 {limit} 个（可用 --limit 调整）")
        uniq = uniq[:limit]
    return uniq, notes


def _inner_ext(p: Path) -> str:
    name = p.name
    if name.lower().endswith(".gz"):
        name = name[:-3]
    return Path(name).suffix.lower()


def _sniff_sep(sample: str) -> str:
    cands = {",": sample.count(","), "\t": sample.count("\t"),
             ";": sample.count(";"), "|": sample.count("|")}
    best = max(cands, key=lambda k: cands[k])
    return best if cands[best] > 0 else ","


def read_any(path: str | Path, nrows: int | None = None) -> tuple[pd.DataFrame, str]:
    """读任意分隔文本（含 .gz），自动嗅探分隔符 / 编码 / 有无表头。

    刻意不依赖 datakit：``.txt`` / 无表头 / 多编码 这些真实场景它覆盖不到。
    """
    p = Path(path)
    ext = _inner_ext(p)
    if ext in (".xlsx", ".xls"):
        return pd.read_excel(p, nrows=nrows), "xlsx"
    if ext in (".json", ".jsonl", ".ndjson"):
        return pd.read_json(p, lines=ext in (".jsonl", ".ndjson")), ext.lstrip(".")

    opener = gzip.open if p.name.lower().endswith(".gz") else open
    last_exc: Exception | None = None
    for enc in ("utf-8-sig", "utf-8", "gb18030", "latin-1"):
        try:
            with opener(p, "rt", encoding=enc, newline="") as f:      # type: ignore[operator]
                head = f.read(64 * 1024)
            sep = _sniff_sep(head)
            frame = pd.read_csv(p, sep=sep, encoding=enc, nrows=nrows,
                                low_memory=False, compression="infer")
            break
        except UnicodeDecodeError as exc:
            last_exc = exc
            continue
        except Exception as exc:                                      # 解析类错误直接抛
            raise
    else:
        raise ValueError(f"{p.name} 无法用常见编码解码（binary?）：{last_exc}")

    # 无表头检测：列名全部看起来像数字 → 首行其实是数据
    cols = [str(c) for c in frame.columns]
    if cols and sum(_looks_data_name(c) for c in cols) >= max(1, 0.6 * len(cols)):
        # 首行其实是数据 → 无表头，重读并给出 c0..cn 占位列名（角色由内容推断，不靠名字）
        frame = pd.read_csv(p, sep=sep, encoding=enc, header=None, nrows=nrows,
                            low_memory=False, compression="infer")
        frame.columns = [f"c{i}" for i in range(frame.shape[1])]
    return frame, ext.lstrip(".")


def _looks_number(s: str) -> bool:
    try:
        float(s)
        return True
    except (TypeError, ValueError):
        return False


def _looks_data_name(s: str) -> bool:
    """列名是否"其实是数据"：数字 / ISO 时间 / 长十六进制串（无表头文件的特征）。"""
    t = str(s).strip()
    if not t:
        return True
    if _looks_number(t):
        return True
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}([ T].*)?", t):
        return True
    if re.fullmatch(r"[0-9a-fA-F]{16,}", t):
        return True
    return False


def load_sources(paths: Iterable[str], limit: int = DEFAULT_FILE_LIMIT,
                 row_limit: int | None = DEFAULT_ROW_LIMIT_PER_FILE) -> DatasetBundle:
    """把多个源文件读入并按列名并集拼接成一份 Dataset。"""
    files, notes = expand_sources(paths, limit=limit)
    if not files:
        raise FileNotFoundError("没有可读的数据文件：" + "；".join(notes) or "（空路径）")
    frames, metas = [], []
    for f in files:
        try:
            df, fmt = read_any(f, nrows=row_limit)
        except Exception as exc:
            metas.append(SourceMeta(str(f), f.name, 0, 0, f.stat().st_size if f.exists() else 0,
                                    _inner_ext(f).lstrip("."), ok=False, error=f"{type(exc).__name__}: {exc}"))
            notes.append(f"{f.name} 读取失败：{type(exc).__name__}: {exc}")
            continue
        m = SourceMeta(str(f), f.name, len(df), df.shape[1],
                       f.stat().st_size if f.exists() else 0, fmt, ok=True)
        m.__dict__["columns"] = [str(c) for c in df.columns]           # 供 schema_diff 用
        metas.append(m)
        if len(files) > 1:
            df = df.copy()
            df["__source_file"] = f.name                              # 多源拼接时保留来源
        frames.append(df)
    if not frames:
        raise RuntimeError("所有源文件都读取失败：" + "；".join(notes[:3]))
    big = pd.concat(frames, ignore_index=True, sort=False)
    return DatasetBundle(frame=big, sources=metas, missing_note=notes)


# --------------------------------------------------------------------------- #
# 2) Mapping：内容级角色推断（不依赖列名）
# --------------------------------------------------------------------------- #
def _col_stats(s: pd.Series) -> dict:
    n = int(len(s))
    nn = int(s.notna().sum())
    out = {"n": n, "not_null": nn, "null_rate": float(1 - nn / n) if n else None,
           "dtype": str(s.dtype), "n_unique": int(s.nunique(dropna=True))}
    num = pd.to_numeric(s, errors="coerce")
    if num.notna().sum() >= max(3, 0.5 * nn):
        out["numeric"] = True
        q = num.dropna()
        out["min"], out["max"] = float(q.min()), float(q.max())
        # 用分位数判定值域：个别脏值（如 FDIC 里经纬度写反的 2 行）不该让整列失去角色
        out["q01"], out["q99"] = float(q.quantile(0.01)), float(q.quantile(0.99))
        out["std"] = float(q.std()) if len(q) > 1 else 0.0
        out["integer_like"] = bool(np.allclose(q % 1, 0, atol=1e-9)) if len(q) else False
    else:
        out["numeric"] = False
    return out


def infer_mapping(df: pd.DataFrame) -> dict:
    """按内容推断角色，返回 {role: column|None, "_candidates": {...}, "_columns": {...}}。

    三条硬约束（对应真实踩过的误判）：
      1. **年份优先**：整数且值域在 1600–2200 → time，多期再加权（单期会自然降级）；
         日期列默认是 event_time，只有名字明确是时间时才当 time。
      2. **坐标必须成对且有语义**：lat/lon 至少一个列名带坐标语义才采纳，
         避免把任意落在 [-90,90] 的整数列（如 BRSERTYP）当纬度；浮点列优先。
      3. **实体要看"期上重复"**：有 time 时，实体候选按「跨期重复率」加权，
         每行唯一的代理主键（如 FDIC 的 ID）会被自动降权。
    """
    cols = [str(c) for c in df.columns if str(c) != "__source_file"]
    stats = {c: _col_stats(df[c]) for c in cols}
    rows = max(1, len(df))
    hints = {c: {r: bool(re.search(p, str(c).lower())) for r, p in _ROLE_HINT.items()} for c in cols}

    score: dict[str, dict[str, float]] = {r: {} for r in ROLES}

    def zero_rate(c: str) -> float:
        v = pd.to_numeric(df[c], errors="coerce")
        if not len(v):
            return 0.0
        return float((v == 0).mean())

    # ---- (A) time：整数年份 / 名字像时间 ----
    dt_cols: set[str] = set()
    for c, st in stats.items():
        h = hints[c]
        lo, hi = st.get("min"), st.get("max")
        if st.get("numeric") and st.get("integer_like") and lo is not None and hi is not None \
                and 1600 <= lo and hi <= 2200:
            s = 6 + 3 * h["time"] + (2 if st["n_unique"] >= 2 else 0)
            score["time"][c] = s
        if not st.get("numeric") and st["not_null"] >= 5 and st["n_unique"] >= 2:
            sample = df[c].dropna().astype(str).head(400)
            if sample.str.contains(r"\d{4}[-/]\d{1,2}", regex=True, na=False).mean() > 0.8:
                dt = pd.to_datetime(df[c], errors="coerce", format="mixed")
                if dt.notna().mean() > 0.9:
                    # 日期列默认是 event_time；即便名字像时间，也不当"期"维度
                    # （真实踩坑：行程数据的 START_TIME 是时间戳，不是面板的期）
                    score["event_time"][c] = score["event_time"].get(c, 0) + 4
                    dt_cols.add(c)

    # ---- (B) lat / lon：值域(稳健分位) + 语义名 ----
    for c, st in stats.items():
        if not st.get("numeric"):
            continue
        h = hints[c]
        lo, hi = st.get("q01"), st.get("q99")
        if lo is None or hi is None:
            continue
        floatish = not st.get("integer_like")
        lat_min_spread = 0.0 if h["lat"] else 0.5     # 带语义名时不苛求跨度（城市级数据可能很窄）
        lon_min_spread = 0.0 if h["lon"] else 0.5
        if -90 <= lo and hi <= 90 and (hi - lo) > lat_min_spread:
            score["lat"][c] = (3 if floatish else 1) + 6 * h["lat"]
        if -180 <= lo and hi <= 180 and (hi - lo) > lon_min_spread:
            score["lon"][c] = (3 if floatish else 1) + 6 * h["lon"]

    # ---- (C) entity / value / group / event_time：基础分 ----
    for c, st in stats.items():
        h = hints[c]
        uniq, card = st["n_unique"], st["n_unique"] / rows
        if st.get("numeric"):
            if (st.get("std") or 0) > 0 and st["n_unique"] >= 3:
                s = 2 + 4 * h["value"] + min(2.0, np.log10(max(st["n_unique"], 1)))
                if zero_rate(c) > 0.5:
                    s -= 1.5                       # 过半为 0 → 更像粗粒度汇总
                score["value"][c] = s
            if st.get("integer_like") and uniq >= 20 and not h["time"]:
                score["entity"][c] = score["entity"].get(c, 0) + 2 + 4 * h["entity"]
        else:
            if uniq >= 20 and c not in dt_cols:        # 时间戳不是实体
                score["entity"][c] = 3 + 4 * h["entity"] + min(3.0, card * 6)
                if uniq >= 0.98 * rows and not h["entity"]:
                    score["entity"][c] -= 1.5   # 每行唯一且名字不像 ID → 疑似行号
        if 2 <= uniq <= 60 and not st.get("integer_like"):
            score["group"][c] = 2 + 3 * h["group"]
        if h["event_time"]:
            score["event_time"][c] = score["event_time"].get(c, 0) + 3

    # ---- 选 time（先定时间维，"entity 跨期重复"才能算） ----
    selected: dict[str, str | None] = {}
    used: dict[str, str] = {}
    t_cands = sorted(((c, s) for c, s in score["time"].items()), key=lambda kv: -kv[1])
    selected["time"] = t_cands[0][0] if t_cands else None
    if selected["time"]:
        used[selected["time"]] = "time"

    # ---- entity：面板的实体**必须在期上重复**，否则算不出任何一个体的时间变化 ----
    # （真实踩坑：FDIC 的 ID 列形如 1994_10002_0，是行级代理键，每期唯一 → 不能当面板实体）
    if selected["time"]:
        board = sorted(((c, s) for c, s in score["entity"].items() if c not in used),
                       key=lambda kv: -kv[1])[:12]
        for c, base in board:
            try:
                g = df.groupby(c)[selected["time"]].nunique()
                rep = float((g >= 2).mean()) if len(g) else 0.0
            except Exception:
                rep = 0.0
            score["entity"][c] = base + 8.0 * rep - (6.0 if rep < 0.05 else 0.0)
    e_cands = sorted(((c, s) for c, s in score["entity"].items() if c not in used), key=lambda kv: -kv[1])
    selected["entity"] = e_cands[0][0] if e_cands else None
    if selected["entity"]:
        used[selected["entity"]] = "entity"

    # ---- lat / lon：成对 + 坐标列必须是"带语义名"或"浮点列" ----
    # （真实踩坑：FDIC 的 BRSERTYP 是落在 [-90,90] 的整数分类码，被误判成纬度）
    def _coord_pool(role: str) -> list[str]:
        pool = []
        for c, _ in sorted(((c, s) for c, s in score[role].items() if c not in used),
                           key=lambda kv: -kv[1]):
            if hints[c][role] or not stats[c].get("integer_like"):
                pool.append(c)
        return pool

    lat_pool, lon_pool = _coord_pool("lat"), _coord_pool("lon")
    lat0 = lat_pool[0] if lat_pool else None
    lon0 = next((c for c in lon_pool if c != lat0), None)
    # 语义名优先；无表头数据（c0/c1…）允许纯内容配对，但要求经度跨度 ≥ 纬度跨度
    # 且两者都是浮点 —— 让 brightkite 这类无表头日志也能定位坐标，同时挡住分类码误配。
    if lat0 and lon0:
        named = hints[lat0]["lat"] or hints[lon0]["lon"]
        floatish_pair = (not stats[lat0].get("integer_like") and
                         not stats[lon0].get("integer_like") and
                         (stats[lon0].get("q99", 0) - stats[lon0].get("q01", 0)) >=
                         (stats[lat0].get("q99", 0) - stats[lat0].get("q01", 0)))
        ok_pair = bool(named or floatish_pair)
    else:
        ok_pair = False
    if ok_pair:
        selected["lat"], selected["lon"] = lat0, lon0
        used[lat0], used[lon0] = "lat", "lon"
    else:
        selected["lat"] = selected["lon"] = None

    # ---- 若没有整数"期"列，但存在日期列：退回用日期当时间维（如纯时序） ----
    if not selected.get("time"):
        d_cands = sorted(((c, s) for c, s in score["event_time"].items() if c not in used),
                         key=lambda kv: -kv[1])
        if d_cands and not selected.get("entity"):
            selected["time"] = d_cands[0][0]
            used[selected["time"]] = "time"

    # ---- 其余角色 ----
    for role in ("event_time", "value", "group"):
        cand = sorted(((c, s) for c, s in score[role].items() if c not in used), key=lambda kv: -kv[1])
        selected[role] = cand[0][0] if cand else None
        if selected[role]:
            used[selected[role]] = role

    return {
        **selected,
        "_candidates": {r: sorted(score[r].items(), key=lambda kv: -kv[1])[:8] for r in ROLES},
        "_columns": stats,
    }


def mapping_of(mapping: dict, roles: Iterable[str] = ROLES) -> dict:
    """只取角色→列，去掉 ``_candidates`` 等元数据。"""
    return {r: mapping.get(r) for r in roles}


# --------------------------------------------------------------------------- #
# 3) Shape：形态识别
# --------------------------------------------------------------------------- #
def _is_datetime_like(s: pd.Series) -> bool:
    if pd.api.types.is_datetime64_any_dtype(s):
        return True
    if pd.api.types.is_numeric_dtype(s):
        return False
    sample = s.dropna().astype(str).head(200)
    if not len(sample):
        return False
    return bool(sample.str.contains(r"\d{4}[-/]\d{1,2}", regex=True, na=False).mean() > 0.8)


def detect_shape(df: pd.DataFrame, mapping: dict) -> dict:
    ent, tm, ev = mapping.get("entity"), mapping.get("time"), mapping.get("event_time")
    lat, lon, val = mapping.get("lat"), mapping.get("lon"), mapping.get("value")
    rows, n_ent = len(df), (int(df[ent].nunique()) if ent else 0)

    # ---- 网络/边表：没有时间维、没有坐标，但有 ≥2 个高基数 ID 列 ----
    if not tm and not (lat and lon):
        id_cols = []
        for c in df.columns:
            if str(c) == "__source_file":
                continue
            s = df[c]
            if _is_datetime_like(s):                       # 时间戳不是"节点 ID"
                continue
            uniq = int(s.nunique(dropna=True))
            if uniq < 50 or uniq / max(rows, 1) < 0.005:
                continue
            if (not pd.api.types.is_numeric_dtype(s)) or bool(np.allclose(
                    pd.to_numeric(s, errors="coerce").dropna() % 1, 0, atol=1e-9)):
                id_cols.append(str(c))
        if len(id_cols) >= 2:
            return {"kind": "network", "has_entity": True, "has_time": False, "has_geo": False,
                    "note": f"疑似边表：{', '.join(id_cols[:3])}（可用度分布/连通分量分析）"}

    if ent and tm:
        dup = int(df.duplicated(subset=[ent, tm]).sum())
        kind = "panel" if dup == 0 else "repeated_panel"
        return {"kind": kind, "has_entity": True, "has_time": True, "has_geo": bool(lat and lon),
                "dup_entity_time": dup,
                "note": ("实体-时间唯一 → 标准面板" if dup == 0 else
                         f"(实体,时间) 有 {dup} 条重复 → 需先聚合或确认主键")}
    if ent and ev:
        return {"kind": "event_log", "has_entity": True, "has_time": False, "has_geo": bool(lat and lon),
                "note": "实体 + 事件时间 → 生存/事件流（无逐年面板）"}
    if ent and not tm and n_ent and rows / max(n_ent, 1) > 3:
        return {"kind": "event_log", "has_entity": True, "has_time": False, "has_geo": bool(lat and lon),
                "note": "单实体多行 → 事件流/明细"}
    if ev and not ent and not tm:
        return {"kind": "time_series", "has_entity": False, "has_time": True, "has_geo": bool(lat and lon),
                "note": "只有事件/时间列、无实体 → 时间序列"}
    if lat and lon and not ent:
        return {"kind": "cross_section", "has_entity": False, "has_time": False, "has_geo": True,
                "note": "有坐标无实体-时间 → 空间横截面"}
    if tm and not ent:
        return {"kind": "time_series", "has_entity": False, "has_time": True, "has_geo": bool(lat and lon),
                "note": "只有时间列 → 时间序列"}
    # 网络：两个高基数 ID 列 + 无 value
    id_cols = []
    for c in df.columns:
        s = df[c]
        if not pd.api.types.is_numeric_dtype(s) and s.nunique(dropna=True) / max(rows, 1) > 0.1:
            id_cols.append(str(c))
    if len(id_cols) >= 2 and not val:
        return {"kind": "network", "has_entity": True, "has_time": False, "has_geo": False,
                "note": f"疑似边表（{', '.join(id_cols[:3])}）"}
    return {"kind": "unknown", "has_entity": bool(ent), "has_time": bool(tm), "has_geo": bool(lat and lon),
            "note": "未能识别出实体-时间结构，请人工指定字段角色"}


# --------------------------------------------------------------------------- #
# 4) Health：按形态路由的体检规则集
# --------------------------------------------------------------------------- #
def _c(level: str, key: str, title: str, value: str, note: str = "", action: str = "") -> dict:
    return {"level": level, "key": key, "title": title, "value": value, "note": note, "action": action}


def health(df: pd.DataFrame, mapping: dict, shape: dict) -> dict:
    kind = shape["kind"]
    ent, tm, ev = mapping.get("entity"), mapping.get("time"), mapping.get("event_time")
    lat, lon, val = mapping.get("lat"), mapping.get("lon"), mapping.get("value")
    checks: list[dict] = []
    rows = len(df)

    checks.append(_c("ok" if rows >= 500 else "warn", "scale", "数据规模",
                     f"{rows:,} 行 × {df.shape[1]} 列",
                     "行数是固定效应与聚类稳健标准误的前提。",
                     "" if rows >= 500 else "样本量偏小，聚类标准误可能不可靠。"))

    if lat and lon:
        miss = float((df[lat].isna() | df[lon].isna()).mean())
        checks.append(_c("ok" if miss <= 0.2 else "danger", "geo", "坐标可用性",
                         f"缺失率 {miss*100:.2f}%",
                         f"字段：{lat} / {lon}。坐标是距离环与暴露强度的唯一前提。",
                         "" if miss <= 0.2 else "坐标缺失 > 20% → 空间口径不可用，先补地理编码。"))

    if kind in ("panel", "repeated_panel") and tm:
        ys = pd.to_numeric(df[tm], errors="coerce").dropna()
        if ys.nunique() >= 2:
            span = int(ys.max()) - int(ys.min()) + 1
            checks.append(_c("ok" if span >= 5 else "danger", "span", "时间跨度",
                             f"{int(ys.min())}–{int(ys.max())}（{span} 期，覆盖 {ys.nunique()} 个取值）",
                             "事件研究需事件前后多个窗口，跨度 ≥ 5 才有意义。",
                             "" if span >= 5 else "跨度不足 5 → 无法做事件前后窗口。"))
        if ent:
            per = df.groupby(tm)[ent].nunique()
            occ = df.groupby(ent)[tm].nunique()
            ent_stats = {
                "entities": int(df[ent].nunique()),
                "periods": int(df[tm].nunique()),
                "rows_per_entity_median": float(occ.median()),
                "entities_full_span_rate": float((occ >= int(df[tm].nunique())).mean()),
            }
            checks.append(_c("ok", "panel", "面板平衡度",
                             f"每期实体 {int(per.min()):,} ~ {int(per.max()):,}",
                             f"中位在册 {ent_stats['rows_per_entity_median']:.0f} 期，"
                             f"全期在册 {ent_stats['entities_full_span_rate']*100:.1f}%。"))
            checks.append(_c("warn", "key", "主键候选诊断",
                             f"{ent_stats['entities']:,} 个实体 / {rows:,} 行",
                             "主键是否「稳定」无法自动判定（实体不跨全期是正常的开关店行为）："
                             "若只有一个候选键，请用「名称+地址+坐标」二次校验并给出准确率。"))
    if kind == "event_log":
        if ent:
            per = df.groupby(ent).size()
            checks.append(_c("ok", "event_log", "实体-事件覆盖",
                             f"{df[ent].nunique():,} 个实体，中位 {float(per.median()):.0f} 条/实体",
                             "事件流可用于生存/风险建模；需确认是否有右删失标记。"))
        if ev:
            dt = pd.to_datetime(df[ev], errors="coerce")
            if dt.notna().any():
                checks.append(_c("ok", "event_time", "事件时间覆盖",
                                 f"{dt.min()} ~ {dt.max()}", "事件时间决定观察窗与删失口径。"))
    if kind == "cross_section" and lat and lon:
        checks.append(_c("ok", "cross_section", "空间横截面",
                         f"{rows:,} 个点位", "可用于空间自相关与空间回归（无时间维）。"))
    if kind == "network":
        checks.append(_c("warn", "network", "网络形态",
                         f"{rows:,} 条边", "边表可做度分布/连通分量，但需指明 source/target 角色。"))
    if kind == "unknown":
        checks.append(_c("danger", "shape", "形态未识别",
                         "无法确定数据结构",
                         "请人工指定实体/时间/坐标/结果变量角色后重跑。",
                         "本产品不猜结构；未识别就不给结论。"))

    # 结果变量
    if val:
        s = pd.to_numeric(df[val], errors="coerce")
        checks.append(_c("ok" if s.isna().mean() < 0.1 else "warn", "outcome", "结果变量分布",
                         f"缺失 {s.isna().mean()*100:.2f}%；中位 {s.median():,.0f}；最大 {s.max():,.0f}",
                         f"字段：{val}。结果变量应是实体级连续指标。"))

    # 疑似泄漏（实体级常量 + 名字像聚合/终值）
    if ent and tm:
        lk = _leakage(df, ent, tm)
        if lk:
            checks.append(lk)

    # 多源拼接列覆盖差异
    return {"shape": kind, "checks": checks}


_LEAK_HINT = re.compile(r"(rate|ratio|closed|closure|exit|churn|lifetime|total|count|last|final|future|surviv|tenure|dur)", re.I)


def _leakage(df: pd.DataFrame, ent: str, tm: str) -> dict | None:
    if len(df) < 50:
        return None
    rows = []
    for c in df.columns:
        if str(c) in (ent, tm) or not pd.api.types.is_numeric_dtype(df[c]):
            continue
        try:
            g = df.groupby(ent)[c].nunique(dropna=True)
        except Exception:
            continue
        if len(g) < 10:
            continue
        const = float((g <= 1).mean())
        if const < 0.95:
            continue
        hinted = bool(_LEAK_HINT.search(str(c)))
        rows.append({"field": str(c), "entity_constant_rate": round(const, 4), "name_hint": hinted,
                     "verdict": ("高风险：实体级常量且名字像聚合/终值" if hinted
                                 else "需人工确认：实体级常量（可能只是不随时间变的属性）")})
    if not rows:
        return None
    rows.sort(key=lambda r: (not r["name_hint"], -r["entity_constant_rate"]))
    risky = [r for r in rows if r["name_hint"]]
    out = _c("warn" if risky else "ok", "leakage", "疑似时序泄漏特征",
             f"{len(risky)} 个高风险 / 共 {len(rows)} 个实体级常量列",
             "实体级常量若由**全期**聚合或**终期**观测得到，就把未来信息带进了每一年。",
             "对高风险列做时序外推验证（≤T 训练、预测 T+1），或改用截至当年的滚动值。")
    out["detail"] = rows[:12]
    return out


# --------------------------------------------------------------------------- #
# 5) 映射模板（复用）
# --------------------------------------------------------------------------- #
def _safe_name(name: str) -> str:
    return re.sub(r"[^0-9A-Za-z_.\u4e00-\u9fa5-]", "_", name)[:80]


def list_templates() -> list[dict]:
    if not TEMPLATE_DIR.exists():
        return []
    out = []
    for p in sorted(TEMPLATE_DIR.glob("*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            out.append({"name": d.get("name", p.stem), "saved_at": d.get("saved_at"),
                        "mapping": d.get("mapping", {}), "shape": d.get("shape"),
                        "columns": d.get("columns", [])})
        except Exception:
            continue
    return out


def save_template(name: str, mapping: dict, shape: dict | None = None,
                  columns: list[str] | None = None) -> Path:
    TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "name": name,
        "saved_at": pd.Timestamp.now().isoformat(timespec="seconds"),
        "mapping": {k: v for k, v in mapping.items() if not str(k).startswith("_")},
        "shape": (shape or {}).get("kind"),
        "columns": columns or [],
    }
    p = TEMPLATE_DIR / f"{_safe_name(name)}.json"
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


# --------------------------------------------------------------------------- #
# 6) 一体化入口
# --------------------------------------------------------------------------- #
def analyze(paths: Iterable[str], limit: int = DEFAULT_FILE_LIMIT,
            row_limit: int | None = DEFAULT_ROW_LIMIT_PER_FILE,
            override: dict | None = None) -> dict:
    """路径/文件 → 数据集 → 映射 → 形态 → 体检（供服务层与 CLI 复用）。"""
    bundle = load_sources(paths, limit=limit, row_limit=row_limit)
    df = bundle.frame
    mapping = infer_mapping(df)
    if override:
        for k, v in override.items():
            if k in ROLES and v:
                mapping[k] = v
    shape = detect_shape(df, mapping)
    hc = health(df, mapping, shape)
    return {
        "ok": True,
        "dataset": {
            "rows": bundle.rows, "columns": bundle.columns,
            "sources": [s.to_dict() for s in bundle.sources],
            "source_count": len(bundle.sources),
            "notes": bundle.missing_note,
            "schema_diff": bundle.schema_diff(),
        },
        "mapping": mapping,
        "roles": mapping_of(mapping),
        "shape": shape,
        "health": hc,
    }


def _cli() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="泛化数据接入内核 · CLI")
    ap.add_argument("--paths", nargs="+", required=True, help="文件 / 目录 / 通配符")
    ap.add_argument("--limit", type=int, default=DEFAULT_FILE_LIMIT)
    ap.add_argument("--row-limit", type=int, default=DEFAULT_ROW_LIMIT_PER_FILE)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    rep = analyze(a.paths, limit=a.limit, row_limit=a.row_limit)
    if a.json:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
        return 0
    d = rep["dataset"]
    print(f"数据集：{d['rows']:,} 行 × {len(d['columns'])} 列，来自 {d['source_count']} 个文件")
    print("角色  ：", {k: v for k, v in rep["roles"].items() if v})
    print("形态  ：", rep["shape"]["kind"], "—", rep["shape"]["note"])
    for c in rep["health"]["checks"]:
        print(f"  [{c['level']:6}] {c['key']:12} {c['title']}: {c['value']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
