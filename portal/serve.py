#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
网点决策台 · 本地服务（可选增强形态）

不启动也能用：`index.html` 双击即可离线打开，四个模块中的三个（冲击评估 / 风险归因 / 口径实验室）
完全不依赖本服务。

启动本服务后解锁的能力：
    POST /api/intake   —— 上传客户自己的 CSV/TSV，**在本机真实调用 datakit 跑五阶段体检**，
                          并自动预填「数据准入体检」问卷（ID 稳定性 / 坐标可用性 / 缺失是否随机 /
                          时间跨度 / 面板平衡度）。

体检项共 8 条，其中两条是本项目踩过的坑固化成的规则（相对通用报告的增量）：
    ⑦ 疑似时序泄漏特征 —— 实体级常量列 + 名字像聚合/终值（对位 project2：
       全期关闭率 join 回逐年、期末存款用于每一年）。
    ⑧ 空间口径稳健性 —— 换权重个数（k=4/8）与换聚合尺度（≈1km/5km）后 Moran's I 是否翻转
       （对位 project6：同一方法在不同数据上差数十倍）。

安全与合规边界（刻意设计）：
    * 仅监听 127.0.0.1，不对外暴露；
    * 上传文件落在 portal/.tmp/<uuid>/，**响应结束后立刻整目录删除**（不持久化客户数据）；
    * 文件名只取 basename，静态服务做目录穿越防护；
    * 单次请求体上限 64 MB。

用法：
    ./.venv/Scripts/python.exe portal/serve.py            # 默认 http://127.0.0.1:8765
    ./.venv/Scripts/python.exe portal/serve.py --port 9000 --no-browser
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import posixpath
import re
import shutil
import sys
import tempfile
import traceback
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs, unquote

PORTAL = Path(__file__).resolve().parent
REPO = PORTAL.parent
MAX_BODY = 64 * 1024 * 1024

# ---------------- datakit（真实依赖，不做假调用） ----------------
try:
    import datakit as dk
    import pandas as pd
    DK_OK, DK_ERR = True, ""
except Exception as e:  # pragma: no cover
    DK_OK, DK_ERR = False, f"{type(e).__name__}: {e}"

# ---------------- 泛化接入 / 重估内核（本目录新增，与具体数据集解耦） ----------------
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    import ingest as ing
    import refit as rf
    ING_OK, ING_ERR = True, ""
except Exception as e:  # pragma: no cover
    ING_OK, ING_ERR = False, f"{type(e).__name__}: {e}"

MAX_BATCH_BODY = 512 * 1024 * 1024      # 批量上传上限（本机目录模式不受此限）


# --------------------------------------------------------------------------- #
# 列名自动识别（客户数据列名千奇百怪，必须容错）
# --------------------------------------------------------------------------- #
_PATTERNS = {
    "year": [r"^year$", r"^fiscal_?year$", r"^yr$", r"年份", r"^stat_?year$", r"^period$"],
    "id": [r"^uni?numbr$", r"^brnum$", r"^store_?id$", r"^shop_?id$", r"^site_?id$",
           r"^branch_?id$", r"^outlet_?id$", r"^entity_?id$", r"网点", r"门店", r"^id$"],
    "lat": [r"^lat$", r"^latitude$", r"纬度", r"^y$"],
    "lon": [r"^lon$", r"^lng$", r"^long$", r"^longitude$", r"经度", r"^x$"],
    "value": [r"^depsumbr$", r"^deposits?$", r"^sales$", r"^revenue$", r"^amount$",
              r"^turnover$", r"^gmv$", r"^volume$", r"存款", r"销售额", r"营收", r"^value$"],
    "entity_name": [r"^name$", r"^store_?name$", r"^bank_?name$", r"名称", r"^title$"],
}


def detect_columns(cols: list[str]) -> dict:
    low = {c: str(c).strip().lower() for c in cols}
    out: dict[str, str | None] = {}
    for role, pats in _PATTERNS.items():
        hit = None
        for p in pats:
            for c, lc in low.items():
                if re.search(p, lc):
                    hit = c
                    break
            if hit:
                break
        # 未命中时退化为宽松包含匹配（仅对明确的语义角色）
        if hit is None and role in ("year", "lat", "lon"):
            for c, lc in low.items():
                if role in lc:
                    hit = c
                    break
        out[role] = hit
    return out


# --------------------------------------------------------------------------- #
# 体检核心：真实计算，不用估算
# --------------------------------------------------------------------------- #
def health_check(df: "pd.DataFrame", cols: dict, dataset_report: dict) -> dict:
    n_rows = int(len(df))
    checks: list[dict] = []

    def add(key, title, value, level, note, action=""):
        checks.append({"key": key, "title": title, "value": value,
                       "level": level, "note": note, "action": action})

    # ① 规模
    add("scale", "数据规模", f"{n_rows:,} 行 × {len(df.columns)} 列",
        "ok" if n_rows >= 500 else "warn",
        "行数是固定效应与聚类稳健标准误的前提。",
        "" if n_rows >= 500 else "样本量偏小，聚类标准误可能不可靠。")

    # ② 坐标可用性
    lat, lon = cols.get("lat"), cols.get("lon")
    if lat and lon:
        miss = float((df[lat].isna() | df[lon].isna()).mean())
        level = "ok" if miss <= 0.2 else "danger"
        add("geo", "坐标可用性", f"缺失率 {miss*100:.2f}%", level,
            f"字段：{lat} / {lon}。坐标是距离环与暴露强度的唯一前提。",
            "" if level == "ok" else "坐标缺失率 > 20% → 空间口径不可用，建议先补地理编码。")
    else:
        add("geo", "坐标可用性", "未识别到经纬度列", "danger",
            "未能自动识别 lat / lon 列。",
            "请在页面手动指定经纬度列名后重跑。")

    # ③ 时间跨度
    yr = cols.get("year")
    years = []
    if yr:
        try:
            ys = pd.to_numeric(df[yr], errors="coerce").dropna()
            years = sorted(set(int(v) for v in ys))
        except Exception:
            years = []
    if len(years) >= 2:
        span = years[-1] - years[0] + 1
        lvl = "ok" if span >= 5 else "danger"
        add("span", "时间跨度", f"{years[0]}–{years[-1]}（{span} 年，{len(years)} 期）", lvl,
            "事件研究需要事件前后各若干年窗口，跨度 ≥ 5 年才有意义。",
            "" if lvl == "ok" else "跨度不足 5 年 → 无法做事件前后窗口。")
    else:
        add("span", "时间跨度", "未识别到年份列", "danger",
            "未能自动识别年份列。", "请手动指定年份列名后重跑。")

    # ④ 面板平衡度 + 主键候选
    ent = cols.get("id")
    ent_stats = {}
    if ent and years:
        per_year = df.groupby(yr).size()
        ent_per_year = df.groupby(yr)[ent].nunique()
        add("panel", "面板平衡度",
            f"每期实体数 {int(ent_per_year.min()):,} ~ {int(ent_per_year.max()):,}",
            "ok",
            f"每期行数 {int(per_year.min()):,} ~ {int(per_year.max()):,}；"
            "期数之间的实体数波动过大通常意味着 ID 口径变更或数据抽样缺口。",
            "")

        occ = df.groupby(ent)[yr].nunique()
        ent_stats = {
            "entities": int(df[ent].nunique()),
            "rows_per_entity_median": float(occ.median()),
            "entities_single_year_rate": float((occ <= 1).mean()),
            "entities_full_span_rate": float((occ >= len(years)).mean()),
        }
        add("key", "主键候选诊断",
            f"{ent_stats['entities']:,} 个实体 / {n_rows:,} 行",
            "warn",
            f"仅出现 1 期的实体占 {ent_stats['entities_single_year_rate']*100:.1f}%（"
            "可能是新开/关闭，也可能是主键重编号）；全期在册的占 "
            f"{ent_stats['entities_full_span_rate']*100:.1f}%。",
            "主键稳定性无法自动判定：本项目在 FDIC 数据上用 UNINUMBR 作为稳定键，"
            "实测 BRNUM 跨年变化率 52.19%（并购子样本 86.80%）。"
            "若你只有一个候选键，请务必用「名称+地址+坐标」模糊匹配做二次校验并给出准确率。")
    else:
        add("key", "主键候选诊断", "未识别到实体 ID 列", "danger",
            "未能自动识别实体 ID 列。", "请手动指定实体 ID 列名后重跑。")

    # ⑤ 缺失是否随机（按年份看关键字段缺失集中度）
    key_fields = [c for c in (lat, lon, cols.get("value")) if c]
    if yr and key_fields:
        rows = []
        for f in key_fields:
            by_year = df.groupby(yr)[f].apply(lambda s: float(s.isna().mean()))
            if by_year.empty:
                continue
            overall = float(df[f].isna().mean())
            worst_year = float(by_year.max())
            rows.append({"field": f, "overall": overall, "worst_year": worst_year,
                         "concentration": (worst_year / overall) if overall > 0 else None})
        if rows:
            worst = max(rows, key=lambda r: r["worst_year"])
            lvl = "warn" if worst["worst_year"] > 0.05 else "ok"
            add("missingness", "缺失是否随机", f"最差年份缺失率 {worst['worst_year']*100:.2f}%", lvl,
                "按年份分组检查缺失集中度。缺失若高度集中于某些年份，说明早年样本系统性不可用，"
                "事件研究的早期年份代表性弱。",
                "本项目实测：剔除的 120,261 行（4.26%）**100% 集中在 1994–2010**。")
            checks[-1]["detail"] = rows

    # ⑥ 结果变量分布
    val = cols.get("value")
    if val:
        s = pd.to_numeric(df[val], errors="coerce")
        add("outcome", "结果变量分布",
            f"缺失 {s.isna().mean()*100:.2f}%；中位数 {s.median():,.0f}；最大 {s.max():,.0f}",
            "ok" if s.isna().mean() < 0.1 else "warn",
            f"字段：{val}。结果变量必须是**门店级连续指标**——只有公司级汇总则无法构造门店级 outcome。",
            "")

    # ⑦ 目标泄漏体检（对位 project2 的坑：全期聚合特征 join 回逐年）
    leak_note, leak_rows = _leakage_check(df, cols)
    if leak_note:
        add("leakage", "疑似时序泄漏特征", leak_note["value"], leak_note["level"],
            leak_note["note"], leak_note["action"])
        checks[-1]["detail"] = leak_rows

    # ⑧ 空间口径稳健性（对位 project6 的坑：换权重/换尺度 Moran's I 翻转）
    sp = _spatial_robustness_check(df, cols)
    if sp:
        add("spatial_robust", "空间口径稳健性", sp["value"], sp["level"], sp["note"], sp["action"])
        if sp.get("detail"):
            checks[-1]["detail"] = sp["detail"]

    return {"rows": n_rows, "checks": checks, "entity_stats": ent_stats,
            "years": {"min": years[0], "max": years[-1], "n": len(years)} if years else None}


# 名字里带这些语义的实体级常量列，最可能是「全期聚合后回填」的泄漏特征
_LEAK_HINT = re.compile(r"(rate|ratio|closed|closure|exit|churn|lifetime|total|n_|count|"
                        r"last|final|future|surviv|tenure|dur)", re.I)


def _leakage_check(df, cols) -> tuple[dict | None, list]:
    """① 实体级常量 + ② 名字像聚合/终值 → 疑似把未来信息回填到每一年。

    这就是 project2 上真实踩过的坑：bank_closed_rate 按 CERT 对全期聚合后 join 回逐年、
    DEPSUMBR_last 是终期值却用于每一年。此处只做「可疑度排序」，不下结论。
    """
    ent, yr = cols.get("id"), cols.get("year")
    if not ent or not yr or len(df) < 50:
        return None, []
    rows = []
    num_cols = [c for c in df.columns
                if c not in (ent, yr) and pd.api.types.is_numeric_dtype(df[c])]
    for c in num_cols:
        try:
            g = df.groupby(ent)[c].nunique(dropna=True)
        except Exception:
            continue
        if len(g) < 10:
            continue
        const_rate = float((g <= 1).mean())
        if const_rate < 0.95:
            continue
        hinted = bool(_LEAK_HINT.search(str(c)))
        rows.append({"field": c, "entity_constant_rate": round(const_rate, 4),
                     "name_hint": hinted,
                     "verdict": ("高风险：实体级常量且名字像聚合/终值"
                                 if hinted else "需人工确认：实体级常量（可能只是不随时间变的属性）")})
    rows.sort(key=lambda r: (not r["name_hint"], -r["entity_constant_rate"]))
    risky = [r for r in rows if r["name_hint"]]
    if not rows:
        return None, []
    level = "warn" if risky else "ok"
    value = (f"{len(risky)} 个高风险 / 共 {len(rows)} 个实体级常量列" if rows else "未发现实体级常量列")
    return {
        "value": value, "level": level,
        "note": ("实体级常量列在「网点-年」面板里对同一实体各年取同一个值 —— "
                 "若该值是用**全期**数据聚合出来的（如历史关闭率）或来自**终期**观测"
                 "（如期末存款），它就把未来信息带进了每一年，随机划分的指标会系统性偏乐观。"),
        "action": ("对高风险列做时序外推验证（用 ≤T 训练、预测 T+1）；"
                   "或改用截至当年的滚动窗口值，并把它作为敏感性分析报告。"),
    }, rows[:12]


def _spatial_robustness_check(df, cols) -> dict | None:
    """换权重（k=4 vs k=8）与换尺度（≈1km vs ≈5km 网格）后 Moran's I 是否翻转。

    对位 project6 的坑：同一份数据，仅换空间权重/网格尺度，Moran's I 就能差几十倍甚至反号。
    """
    lat, lon, val = cols.get("lat"), cols.get("lon"), cols.get("value")
    if not (lat and lon and val) or len(df) < 200:
        return None
    try:
        import numpy as _np
        from libpysal.weights import KNN as _KNN
        from esda.moran import Moran as _Moran
    except Exception:
        return {"value": "跳过（缺少 libpysal/esda）", "level": "warn",
                "note": "本机未安装 libpysal/esda，无法做空间权重稳健性体检。",
                "action": "pip install libpysal esda 后重跑。"}
    try:
        d = df[[lat, lon, val]].apply(pd.to_numeric, errors="coerce").dropna()
        if len(d) > 20000:
            d = d.sample(20000, random_state=42)
        out = {}
        for scale_name, dec in (("≈1km", 2), ("≈5km", 1)):
            g = (d.assign(gy=d[lat].round(dec), gx=d[lon].round(dec))
                 .groupby(["gy", "gx"])[val].mean().reset_index())
            if len(g) < 30:
                continue
            coords = _np.column_stack([g["gx"], g["gy"]])
            for k in (4, 8):
                kk = min(k, len(g) - 1)
                if kk < 2:
                    continue
                w = _KNN.from_array(coords, k=kk)
                w.transform = "r"
                out[f"{scale_name}·k={k}"] = float(_Moran(g[val].to_numpy(float), w,
                                                          permutations=99).I)
        if len(out) < 2:
            return None
        vals = list(out.values())
        flips = (max(vals) > 0 > min(vals))
        spread = max(vals) - min(vals)
        level = "danger" if flips else ("warn" if spread > 0.1 else "ok")
        return {
            "value": "；".join(f"{k} I={v:.3f}" for k, v in out.items()),
            "level": level,
            "note": ("同一份数据只换空间权重个数（k=4/k=8）与聚合尺度（≈1km/≈5km），"
                     "Moran's I 的变化幅度就是「空间结论对口径的敏感度」。"),
            "action": ("出现反号 → 任何单一 Moran's I 都不能对外报，必须给出多口径区间；"
                       "本机 project6 实测同一方法在不同数据上相差数十倍。"),
            "detail": [{"spec": k, "moran_i": round(v, 4)} for k, v in out.items()],
        }
    except Exception as e:                                       # pragma: no cover
        return {"value": "计算失败", "level": "warn",
                "note": f"空间稳健性体检未完成：{type(e).__name__}: {e}", "action": ""}


def _human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.2f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024.0
    return f"{n:.2f} TB"


def _catalog_brief(cat: dict) -> dict:
    """把 Catalog.to_report() 收敛成前端要的几个数（字段名以产物实测为准）。"""
    groups = cat.get("groups") or {}
    total = 0
    for g in groups.values():
        try:
            total += int(g.get("total_size") or 0)
        except Exception:
            pass
    return {
        "file_count": cat.get("file_count"),
        "group_count": cat.get("group_count"),
        "total_bytes": total,
        "total_size_human": _human_size(total) if total else None,
    }


def suggested_answers(cols: dict, hc: dict) -> dict:
    """把体检结果翻译成准入体检问卷的预填答案（可由用户覆盖）。"""
    ents = hc.get("entity_stats") or {}
    geo = next((c for c in hc["checks"] if c["key"] == "geo"), None)
    miss = None
    if geo and "缺失率" in geo["value"]:
        try:
            miss = float(geo["value"].split("缺失率")[1].replace("%", "").strip()) / 100
        except Exception:
            miss = None
    return {
        "stableId": bool(cols.get("id")),
        # 主键"匹配准确率"**无法**由单键自动推出：实体不跨全期是正常的（开关店）。
        # 必须由人工用「名称+地址+坐标」二次校验后填写，故此处留空而不给一个误导性的数。
        "idMatchRate": None,
        "coordNullRate": round(miss, 4) if miss is not None else None,
        "outcomeLevel": "store" if cols.get("value") else None,
        "years": (hc["years"]["n"] if hc.get("years") else None),
        "eventDefined": None,
        "exogenous": None,
    }


# --------------------------------------------------------------------------- #
# HTTP 服务
# --------------------------------------------------------------------------- #
class Handler(BaseHTTPRequestHandler):
    server_version = "SDP/2.0"
    protocol_version = "HTTP/1.1"

    # ---- 工具 ----
    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _static(self, relpath: str):
        relpath = unquote(relpath)
        if relpath in ("", "/"):
            relpath = "/index.html"
        norm = posixpath.normpath(relpath).lstrip("/")
        target = (PORTAL / norm).resolve()
        try:
            target.relative_to(PORTAL.resolve())
        except ValueError:
            return self._json({"ok": False, "error": "路径越界"}, 403)
        if not target.is_file():
            return self._json({"ok": False, "error": f"未找到 {norm}"}, 404)
        data = target.read_bytes()
        ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
            ctype += "; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    # ---- 批量多文件：自定义分帧（纯标准库，避免手写 multipart） ----
    # 帧格式：可重复的  "#FILE <urlencoded-name> <bytes>\n" + <bytes> + "\n"，最后可跟 "#END\n"
    def _framed_files(self):
        job = PORTAL / ".tmp" / uuid.uuid4().hex
        (job / "raw").mkdir(parents=True, exist_ok=True)
        names = []
        while True:
            line = self.rfile.readline()
            if not line:
                break
            s = line.decode("utf-8", "replace").strip()
            if not s:
                continue
            if s == "#END":
                break
            if not s.startswith("#FILE "):
                break
            parts = s[len("#FILE "):].split()
            name = Path(unquote(parts[0])).name or "upload.csv"
            n = int(parts[1])
            p = job / "raw" / name
            remaining = n
            with p.open("wb") as f:
                while remaining > 0:
                    chunk = self.rfile.read(min(1 << 20, remaining))
                    if not chunk:
                        break
                    f.write(chunk)
                    remaining -= len(chunk)
            names.append(str(p))
        return job, names

    def _analyze(self, paths, limit, row_limit, override=None):
        rep = ing.analyze(paths, limit=limit, row_limit=row_limit, override=override)
        return rep

    # ---- 路由：泛化接入 / 重估 / 模板 ----
    def _ingest_paths(self, u):
        if not ING_OK:
            return self._json({"ok": False, "error": f"ingest 内核不可用：{ING_ERR}"}, 503)
        try:
            length = int(self.headers.get("Content-Length") or 0)
            payload = json.loads(self.rfile.read(length) or b"{}")
        except Exception as exc:
            return self._json({"ok": False, "error": f"请求体不是合法 JSON：{exc}"}, 400)
        paths = payload.get("paths") or []
        if isinstance(paths, str):
            paths = [paths]
        if not paths:
            return self._json({"ok": False, "error": "paths 为空"}, 400)
        try:
            rep = self._analyze(paths, int(payload.get("limit", ing.DEFAULT_FILE_LIMIT)),
                                payload.get("row_limit", ing.DEFAULT_ROW_LIMIT_PER_FILE),
                                payload.get("override"))
            rep["origin"] = {"mode": "paths", "paths": paths}
            return self._json(rep)
        except Exception as exc:
            return self._json({"ok": False, "error": f"{type(exc).__name__}: {exc}",
                               "trace": traceback.format_exc()[-1200:]}, 500)

    def _ingest_upload(self, u):
        if not ING_OK:
            return self._json({"ok": False, "error": f"ingest 内核不可用：{ING_ERR}"}, 503)
        job, files = self._framed_files()
        try:
            if not files:
                return self._json({"ok": False, "error": "未收到任何文件"}, 400)
            q = parse_qs(u.query)
            override = json.loads(q["override"][0]) if q.get("override") else None
            rep = self._analyze(files, limit=len(files), row_limit=None, override=override)
            rep["origin"] = {"mode": "upload", "files": [Path(f).name for f in files]}
            return self._json(rep)
        except Exception as exc:
            return self._json({"ok": False, "error": f"{type(exc).__name__}: {exc}",
                               "trace": traceback.format_exc()[-1200:]}, 500)
        finally:
            shutil.rmtree(job, ignore_errors=True)      # 不持久化上传数据

    def _refit(self, u):
        if not ING_OK:
            return self._json({"ok": False, "error": f"ingest 内核不可用：{ING_ERR}"}, 503)
        ctype = (self.headers.get("Content-Type") or "").lower()
        q = parse_qs(u.query)
        job = None
        try:
            if ctype.startswith("application/json"):
                length = int(self.headers.get("Content-Length") or 0)
                payload = json.loads(self.rfile.read(length) or b"{}")
                paths = payload.get("paths") or []
                if isinstance(paths, str):
                    paths = [paths]
                roles = payload.get("roles") or {}
                options = payload.get("options") or {}
                limit = int(payload.get("limit", ing.DEFAULT_FILE_LIMIT))
                row_limit = payload.get("row_limit", ing.DEFAULT_ROW_LIMIT_PER_FILE)
            else:
                job, paths = self._framed_files()
                limit, row_limit = len(paths), None
                roles = json.loads(q["roles"][0]) if q.get("roles") else {}
                options = json.loads(q["options"][0]) if q.get("options") else {}
            if not paths:
                return self._json({"ok": False, "error": "未提供数据（paths 或文件）"}, 400)
            bundle = ing.load_sources(paths, limit=limit, row_limit=row_limit)
            if not roles:
                roles = ing.mapping_of(ing.infer_mapping(bundle.frame))
            res = rf.refit(bundle.frame, roles, options)
            res["dataset"] = {"rows": bundle.rows, "columns": bundle.columns,
                              "source_count": bundle.source_count}
            res["roles_used"] = roles
            return self._json(res)
        except Exception as exc:
            return self._json({"ok": False, "error": f"{type(exc).__name__}: {exc}",
                               "trace": traceback.format_exc()[-1500:]}, 500)
        finally:
            if job:
                shutil.rmtree(job, ignore_errors=True)

    def _save_template(self, u):
        if not ING_OK:
            return self._json({"ok": False, "error": f"ingest 内核不可用：{ING_ERR}"}, 503)
        try:
            length = int(self.headers.get("Content-Length") or 0)
            payload = json.loads(self.rfile.read(length) or b"{}")
        except Exception as exc:
            return self._json({"ok": False, "error": f"请求体不是合法 JSON：{exc}"}, 400)
        name = str(payload.get("name") or "").strip()
        if not name:
            return self._json({"ok": False, "error": "模板名不能为空"}, 400)
        p = ing.save_template(name, payload.get("mapping") or {}, payload.get("shape"),
                              payload.get("columns"))
        return self._json({"ok": True, "saved": p.name, "templates": ing.list_templates()})

    def log_message(self, fmt, *args):  # 收敛日志
        sys.stderr.write("  [sdp] " + fmt % args + "\n")

    # ---- GET ----
    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/api/templates":
            if not ING_OK:
                return self._json({"ok": False, "error": f"ingest 内核不可用：{ING_ERR}"}, 503)
            return self._json({"ok": True, "templates": ing.list_templates()})
        if u.path == "/api/health":
            info = {"ok": True, "datakit_available": DK_OK, "datakit_error": DK_ERR,
                    "ingest_available": ING_OK, "ingest_error": ING_ERR,
                    "refit_available": ING_OK}
            if DK_OK:
                info["datakit_version"] = getattr(dk, "__version__", "unknown")
                info["pandas"] = pd.__version__
                info["python"] = sys.version.split()[0]
            info["source_data_present"] = (REPO / "data_raw").exists()
            info["note"] = ("源数据（FDIC 1.58 GB / 教学 31.1 GB）不在本机；"
                            "本服务处理的是**你上传的数据**，因此不受源数据缺失影响。")
            return self._json(info)
        return self._static(u.path)

    # ---- POST ----
    def do_POST(self):
        u = urlparse(self.path)
        # ---- 泛化接入 / 重估 / 映射模板（新增，与具体数据集解耦） ----
        if u.path == "/api/ingest":
            return self._ingest_upload(u)
        if u.path == "/api/ingest_paths":
            return self._ingest_paths(u)
        if u.path == "/api/refit":
            return self._refit(u)
        if u.path == "/api/templates":
            return self._save_template(u)
        if u.path != "/api/intake":
            return self._json({"ok": False, "error": "未知接口"}, 404)
        if not DK_OK:
            return self._json({"ok": False, "error": f"datakit 不可用：{DK_ERR}. "
                                                     f"请用仓库 venv 运行本服务。"}, 503)
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return self._json({"ok": False, "error": "Content-Length 非法"}, 400)
        if length <= 0:
            return self._json({"ok": False, "error": "请求体为空"}, 400)
        if length > MAX_BODY:
            return self._json({"ok": False, "error": f"文件超过上限 {MAX_BODY // 1024 // 1024} MB"}, 413)

        q = parse_qs(u.query)
        name = Path(q.get("name", ["upload.csv"])[0]).name or "upload.csv"
        if not re.search(r"\.(csv|tsv|txt)$", name, re.I):
            name += ".csv"
        raw = self.rfile.read(length)

        manual = {k: (q.get(k, [None])[0] or None) for k in ("id", "year", "lat", "lon", "value")}
        tmp_root = PORTAL / ".tmp"
        tmp_root.mkdir(exist_ok=True)
        job = tmp_root / uuid.uuid4().hex
        try:
            (job / "raw").mkdir(parents=True)
            fpath = job / "raw" / name
            fpath.write_bytes(raw)

            # ① datakit：采集（扫描 + 指纹）
            catalog = dk.scan(str(job / "raw"))
            cat_info = catalog.to_report() if hasattr(catalog, "to_report") else {}

            # ② datakit：读入 + 描述性统计
            ds = dk.read(str(fpath))
            df = ds.frame if hasattr(ds, "frame") else ds
            if not isinstance(df, pd.DataFrame):  # pragma: no cover
                raise RuntimeError("datakit.read 未返回 DataFrame（Dataset.frame 不可用）")
            prof = dk.profile(ds)
            prof_report = prof.to_report() if hasattr(prof, "to_report") else {}

            # ③ 列识别（自动 + 人工覆盖）
            auto = detect_columns(list(df.columns))
            cols = {k: (manual.get(k) or auto.get(k)) for k in ("id", "year", "lat", "lon", "value")}
            cols["_auto"] = auto
            cols["_manual"] = {k: v for k, v in manual.items() if v}

            # ④ 体检（datakit 画像 + 本项目方法论沉淀的规则）
            hc = health_check(df, cols, prof_report)

            # ⑤ datakit：断言校验（把体检结论固化成可复跑的断言）
            # 注意：datakit 的 check 只有 unique / null_rate_le / no_negative / range /
            #       allowed_values / no_duplicates / row_count_ge|le / column_count_eq / columns_eq
            assertions = []
            if cols["id"]:
                assertions.append({"name": "实体 ID 缺失率 = 0", "check": "null_rate_le",
                                   "field": cols["id"], "max": 0.0})
            if cols["year"]:
                assertions.append({"name": "年份缺失率 = 0", "check": "null_rate_le",
                                   "field": cols["year"], "max": 0.0})
            if cols["lat"]:
                assertions.append({"name": "纬度 ∈ [-90, 90]", "check": "range",
                                   "field": cols["lat"], "min": -90, "max": 90})
                assertions.append({"name": "坐标缺失率 ≤ 20%", "check": "null_rate_le",
                                   "field": cols["lat"], "max": 0.2})
            if cols["lon"]:
                assertions.append({"name": "经度 ∈ [-180, 180]", "check": "range",
                                   "field": cols["lon"], "min": -180, "max": 180})
            if cols["id"] and cols["year"]:
                # 本项目在 project1 固化过的同款断言：(实体, 年份) 必须唯一
                assertions.append({"name": "(实体, 年份) 唯一", "check": "no_duplicates",
                                   "subset": [cols["id"], cols["year"]]})
            if cols["value"]:
                assertions.append({"name": "结果变量无负值", "check": "no_negative",
                                   "field": cols["value"]})
            vrep = dk.validate(ds, assertions) if assertions else None
            vrep_report = vrep.to_dict() if hasattr(vrep, "to_dict") else (
                vrep.to_report() if hasattr(vrep, "to_report") else {})

            # ⑥ datakit：校验分析（清洗前后对比 —— 此处用画像对比展示口径影响）
            fields_out = []
            for f in (prof_report.get("fields") or []):
                fields_out.append({"field": f.get("name"), "dtype": f.get("dtype"),
                                   "role": f.get("role"), "null_rate": f.get("null_rate"),
                                   "unique": f.get("unique")})
            fields_out.sort(key=lambda x: -(x.get("null_rate") or 0))

            return self._json({
                "ok": True,
                "file": {"name": name, "bytes": len(raw)},
                "datakit": {
                    "version": getattr(dk, "__version__", "unknown"),
                    "catalog": _catalog_brief(cat_info),
                    "profile_summary": prof_report.get("summary"),
                    "fields": fields_out[:40],
                    "validation": vrep_report,
                },
                "columns": cols,
                "health": hc,
                "suggested_answers": suggested_answers(cols, hc),
            })
        except Exception as e:
            return self._json({"ok": False, "error": f"{type(e).__name__}: {e}",
                               "trace": traceback.format_exc()[-1200:]}, 500)
        finally:
            # 合规：不持久化客户数据 —— 无论成败立即删除
            shutil.rmtree(job, ignore_errors=True)


def main() -> int:
    ap = argparse.ArgumentParser(description="网点决策台 · 本地服务")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    url = f"http://{args.host}:{args.port}/"
    print("=" * 68)
    print("  网点决策台 · 本地服务")
    print("=" * 68)
    print(f"  地址        : {url}")
    print(f"  datakit     : {'可用 v' + str(getattr(dk, '__version__', '?')) if DK_OK else '不可用 → ' + DK_ERR}")
    print(f"  源数据      : {'存在' if (REPO / 'data_raw').exists() else '不在本机（不影响上传体检功能）'}")
    print(f"  上传上限    : {MAX_BODY // 1024 // 1024} MB；响应后立即删除，不持久化")
    print("  停止服务    : Ctrl+C")
    print("=" * 68)

    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    if not args.no_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n  已停止。")
    finally:
        srv.server_close()
        shutil.rmtree(PORTAL / ".tmp", ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
