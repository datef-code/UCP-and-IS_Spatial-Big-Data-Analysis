# -*- coding: utf-8 -*-
"""05_map —— ⑤ 映射（空间结构化）。

入口文件与目录同名（``05_map.py``），规范见 ``datakit/PROJECT_STRUCTURE.md`` §2-⑤。

回答「原始字段怎么变成分析字段」：

* 网点-年面板：派生存款年度变动额 / 变动率（结果变量）；
* 网点维度：经纬度 → H3 R8 网格（``dk.MappingScheme.geocode``）+ 事件判定；
* exposure 结构：以关闭事件为圆心构造距离环（标准环 + 坐标精度敏感性合并环），
  各环内**同 BKCLASS（同业）**网点数 = 处理组强度，同 MSABR 存活网点 = 对照。

L1 设计取向：直接用**空间特征**（各环强度列）进入模型，而非区域 one-hot。
口径常量写在 ``config/mapping.yaml``（纯业务意图，全人写）。
"""
from __future__ import annotations

import datetime as _dt
from pathlib import Path

import numpy as np
import pandas as pd

import datakit as dk

STAGE = "05_map"
TITLE = "⑤ 映射（H3 网格 + 关闭事件距离环 exposure）"

ROOT = Path(__file__).resolve().parent.parent
OUT = Path(__file__).resolve().parent / "output"
DATA = OUT / "data"

H3_RES = 8                      # 平均边长 ≈ 0.46 km，匹配 0–1 km 细环
RING_K = 23                     # 23 圈 H3 网格 ≈ 10 km 半径
RINGS_FINE = [(0.0, 1.0), (1.0, 3.0), (3.0, 5.0), (5.0, 10.0)]     # 方案标准环
RINGS_COARSE = [(0.0, 2.0), (2.0, 5.0), (5.0, 10.0)]               # 坐标精度敏感性合并环

_PANEL_COLS = ["UNINUMBR", "YEAR", "CERT", "BKCLASS", "MSABR",
               "DEPSUMBR", "dep_chg", "dep_chg_rate", "acq_year"]


def haversine_km(lat1, lng1, lat2, lng2) -> np.ndarray:
    """向量化 haversine 距离（km）。"""
    r = 6371.0088
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dp = p2 - p1
    dl = np.radians(lng2 - lng1)
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * r * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def build_panel(cleaned: pd.DataFrame) -> pd.DataFrame:
    """网点-年长表 + 存款年度变动额 / 变动率。"""
    long = cleaned.sort_values(["UNINUMBR", "YEAR"]).reset_index(drop=True)
    g = long.groupby("UNINUMBR", sort=False)
    long["dep_chg"] = g["DEPSUMBR"].diff()
    prev = g["DEPSUMBR"].shift(1)
    long["dep_chg_rate"] = np.where(prev > 0, long["dep_chg"] / prev, np.nan).astype("float64")
    long["acq_year"] = long["SIMS_ACQUIRED_DATE"].dt.year
    return long


def build_branch_dim(long: pd.DataFrame, last_year: int, first_year: int,
                     project) -> pd.DataFrame:
    """网点维度表 + H3 网格 + 事件判定（映射由 datakit 执行，业务口径在此声明）。"""
    g = long.sort_values(["UNINUMBR", "YEAR"]).groupby("UNINUMBR", sort=False)
    first, last = g.first(), g.tail(1).set_index("UNINUMBR")
    dim = pd.DataFrame({
        "UNINUMBR": last.index,
        "CERT": last["CERT"], "BKCLASS": last["BKCLASS"], "MSABR": last["MSABR"],
        "METROBR": last["METROBR"],
        "first_year": first["YEAR"].to_numpy(), "last_year": last["YEAR"].to_numpy(),
        "est_year": first["SIMS_ESTABLISHED_DATE"].dt.year.to_numpy(),
        "acq_year": last["SIMS_ACQUIRED_DATE"].dt.year.to_numpy(),
        "BRNUM_first": first["BRNUM"].to_numpy(), "BRNUM_last": last["BRNUM"].to_numpy(),
        "DEPSUMBR_last": last["DEPSUMBR"].to_numpy(),
        "lat": last["SIMS_LATITUDE"].to_numpy(), "lng": last["SIMS_LONGITUDE"].to_numpy(),
        "projection": last["SIMS_PROJECTION"].to_numpy(),
    }).reset_index(drop=True)
    dim["UNINUMBR"] = dim["UNINUMBR"].astype("int64")

    # --- datakit 映射：地理编码（H3）+ 事件判定派生 ---
    scheme = (dk.MappingScheme()
              .geocode("lat", "lng", resolution=H3_RES,
                       reason="R8 平均边长 ≈ 0.46 km，匹配 0–1 km 细环")
              .derive("event_type", lambda d: np.select(
                  [d["acq_year"].notna(), d["last_year"] >= last_year],
                  ["closed_ma", "alive_censored"], default="attrition_missing"),
                  reason="区分并购关闭 / 仍存活（右删失）/ 数据缺失")
              .derive("left_truncated", lambda d: (d["est_year"] < first_year).fillna(True).astype(int),
                      reason="设立年份早于观测起点 → 左截断标记"))
    mapped = dk.map(dim, scheme)
    dim = mapped.dataset.frame
    dim["event_type"] = pd.Series(np.select(
        [dim["acq_year"].notna(), dim["last_year"] >= last_year],
        ["closed_ma", "alive_censored"], default="attrition_missing"), index=dim.index)
    return dim, mapped.report


def build_exposure(dim: pd.DataFrame, project) -> pd.DataFrame:
    """关闭事件 × 距离环 → exposure 表（空间结构化核心，课题专属）。"""
    import h3

    geo = dim[dim["lat"].notna() & dim["lng"].notna()].copy()
    geo["h3"] = [h3.latlng_to_cell(la, ln, H3_RES) for la, ln in zip(geo["lat"], geo["lng"])]
    project.log(f"    [⑤] H3 R{H3_RES} 网格化：{len(geo):,} 网点 → {geo['h3'].nunique():,} 个格")

    cell_map = {cell: np.asarray(idx) for cell, idx in geo.groupby("h3").indices.items()}
    lat_a, lng_a = geo["lat"].to_numpy(), geo["lng"].to_numpy()
    ind_a = geo["BKCLASS"].fillna("NA").to_numpy()

    ev = geo[geo["event_type"] == "closed_ma"]
    project.log(f"    [⑤] 关闭事件（有坐标）{len(ev):,} 起，逐事件构造距离环 …")

    fine_names = [f"same_ind_ring_{a:g}_{b:g}km".replace(".", "p") for a, b in RINGS_FINE]
    coarse_names = [f"same_ind_ring_{a:g}_{b:g}km".replace(".", "p") for a, b in RINGS_COARSE]
    rows = []
    for n, (i, r) in enumerate(ev.iterrows(), 1):
        disk = h3.grid_disk(r["h3"], RING_K)
        cand = [cell_map[c] for c in disk if c in cell_map]
        if cand:
            cand = np.concatenate(cand)
            cand = cand[cand != i]
        else:
            cand = np.empty(0, dtype=int)
        if len(cand):
            d = haversine_km(r["lat"], r["lng"], lat_a[cand], lng_a[cand])
            bk = r["BKCLASS"] if pd.notna(r["BKCLASS"]) else "NA"
            d_same = d[ind_a[cand] == bk]
        else:
            d_same = np.empty(0)
        row = {
            "UNINUMBR": r["UNINUMBR"], "acq_year": r["acq_year"], "CERT": r["CERT"],
            "BKCLASS": r["BKCLASS"], "MSABR": r["MSABR"],
            "lat": r["lat"], "lng": r["lng"], "h3": r["h3"],
            "n_same_ind_10km": int(len(d_same)),
        }
        for (a, b), name in zip(RINGS_FINE, fine_names):
            row[name] = int(((d_same >= a) & (d_same < b)).sum())
        for (a, b), name in zip(RINGS_COARSE, coarse_names):
            row[name] = int(((d_same >= a) & (d_same < b)).sum())
        rows.append(row)
        if n % 10000 == 0:
            project.log(f"      已处理 {n:,}/{len(ev):,} 起关闭事件")
    exposure = pd.DataFrame(rows)
    DATA.mkdir(parents=True, exist_ok=True)
    exposure.to_csv(DATA / "closure_exposure.csv", index=False)
    return exposure


def run(project) -> dict:
    """构建面板 + 网点维度 + exposure，产出映射报告与下游数据。"""
    project.log(f"[{STAGE}] {TITLE}")
    cfg = project.config("mapping")
    DATA.mkdir(parents=True, exist_ok=True)

    cleaned_pq = ROOT / "03_clean" / "output" / "cleaned.parquet"
    if cleaned_pq.exists():
        cleaned = pd.read_parquet(cleaned_pq)
    else:
        cleaned = pd.read_csv(ROOT / "03_clean" / "output" / "cleaned.csv", low_memory=False)

    last_year = int(cleaned["YEAR"].max())
    first_year = int(cleaned["YEAR"].min())

    # ① 长表面板
    long = build_panel(cleaned)
    long[_PANEL_COLS].to_parquet(DATA / "branch_year_panel.parquet", index=False)
    project.log(f"    [⑤] 网点-年面板 {len(long):,} 行 → data/branch_year_panel.parquet")

    # ② 网点维度（H3 + 事件判定）
    dim, map_report = build_branch_dim(long, last_year, first_year, project)
    dim.to_csv(DATA / "branch_dim.csv", index=False)
    dist = dim["event_type"].value_counts().to_dict()

    # ③ exposure（关闭事件 × 距离环）
    exposure = build_exposure(dim, project)
    fine_names = [c for c in exposure.columns if c.startswith("same_ind_ring_") and c.endswith("km")]
    fine_names = [c for c in fine_names if c not in
                  {"same_ind_ring_0p2_2km", "same_ind_ring_2p5_5km", "same_ind_ring_5p10_10km"}]
    mean_by_ring = {c: float(exposure[c].mean()) for c in exposure.columns
                    if c.startswith("same_ind_ring_")} if len(exposure) else {}

    DATA.mkdir(parents=True, exist_ok=True)
    exposure.to_csv(OUT / "mapped.csv", index=False)

    # ④ 字段血缘 + 映射后字段数据报告
    lineage = pd.DataFrame(_lineage_rows())
    mapped_fields = _field_report(exposure)

    report = {
        "stage": STAGE,
        "mapped_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "scheme": {"source": "config/mapping.yaml", "ops": cfg.get("ops") or []},
        "operations": map_report + [
            {"op": "derive", "detail": "长表新增列 dep_chg / dep_chg_rate",
             "reason": "存款年度变动额 / 变动率（结果变量）"},
            {"op": "aggregate", "detail": f"关闭事件 × 距离环 exposure（{len(exposure):,} 行）",
             "reason": "处理组强度 = 各环内同 BKCLASS 网点数；对照 = 同 MSABR 存活网点"},
        ],
        "shape": {
            "panel_rows": int(len(long)), "branch_dim_rows": int(len(dim)),
            "exposure_rows": int(len(exposure)), "exposure_cols": int(exposure.shape[1]),
            "h3_cells": int(dim["h3"].nunique()) if "h3" in dim.columns else None,
        },
        "h3": {"version": _h3_version(), "res": H3_RES, "ring_k": RING_K},
        "rings_km": {"fine": RINGS_FINE, "coarse_sensitivity": RINGS_COARSE},
        "event_type_dist": {k: int(v) for k, v in dist.items()},
        "mean_same_ind_by_ring": {k: round(v, 2) for k, v in mean_by_ring.items()},
        "exposure_structure": {
            "treated": "各环内同业（同 BKCLASS）网点数 = 处理组强度",
            "control": "同 MSABR 存活网点（远环 / 同城对照，见 04_validate control_coverage）",
        },
        "l1_design_note": "L1 设计取向：空间特征（距离环强度列）而非区域 one-hot",
        "mapped_fields": mapped_fields,
        "outputs": ["mapped.csv", "data/branch_year_panel.parquet",
                    "data/branch_dim.csv", "data/closure_exposure.csv"],
    }
    project.write_stage(STAGE, "map", report,
                        tables={"lineage": lineage, "fields": pd.DataFrame(mapped_fields)},
                        markdown=_md(report, map_report, lineage))
    project.log(f"    [⑤] 网点 {len(dim):,}（{dist}）；exposure {len(exposure):,} 行；"
                f"各环同业均值 { {k: round(v, 2) for k, v in mean_by_ring.items()} }")
    return {
        "stage": STAGE,
        "panel_rows": int(len(long)),
        "branches": int(len(dim)),
        "h3_cells": int(dim["h3"].nunique()) if "h3" in dim.columns else 0,
        "closure_events": int(len(exposure)),
        "event_type_dist": {k: int(v) for k, v in dist.items()},
    }


def _h3_version() -> str:
    try:
        import h3
        return str(h3.__version__)
    except Exception:
        return "unavailable"


def _lineage_rows() -> list[dict]:
    """字段血缘：输出字段 ← 来源字段 / 表达式 / 映射方式。"""
    return [
        {"output": "dep_chg", "sources": "DEPSUMBR", "expr": "DEPSUMBR - DEPSUMBR.shift(1) over (UNINUMBR order by YEAR)", "op": "derive"},
        {"output": "dep_chg_rate", "sources": "DEPSUMBR", "expr": "dep_chg / DEPSUMBR.shift(1)", "op": "derive"},
        {"output": "acq_year", "sources": "SIMS_ACQUIRED_DATE", "expr": "year(SIMS_ACQUIRED_DATE)", "op": "derive"},
        {"output": "h3", "sources": "SIMS_LATITUDE, SIMS_LONGITUDE", "expr": f"h3.latlng_to_cell(lat, lng, {H3_RES})", "op": "geocode"},
        {"output": "event_type", "sources": "SIMS_ACQUIRED_DATE, YEAR", "expr": "closed_ma if acq_year notnull else (alive_censored if last_year == max_year else attrition_missing)", "op": "derive"},
        {"output": "left_truncated", "sources": "SIMS_ESTABLISHED_DATE", "expr": "int(est_year < first_observed_year)", "op": "derive"},
        {"output": "n_same_ind_10km", "sources": "h3, BKCLASS", "expr": f"count(同 BKCLASS 网点, haversine <= 10km, grid_disk(k={RING_K}))", "op": "aggregate"},
        {"output": "same_ind_ring_<a>_<b>km", "sources": "h3, BKCLASS", "expr": "count(同 BKCLASS 网点, a <= d < b km)", "op": "aggregate"},
        {"output": "BRNUM", "sources": "BRNUM", "expr": "—（跨年不稳定，不进入下游）", "op": "drop"},
    ]


def _field_report(exposure: pd.DataFrame) -> list[dict]:
    """映射后字段数据报告（逐字段类型 / 非空 / 缺失率 / 唯一值 / 统计）。"""
    rows = []
    for col in exposure.columns:
        s = exposure[col]
        rec = {"field": col, "dtype": str(s.dtype), "non_null": int(s.notna().sum()),
               "null_rate": round(float(s.isna().mean()), 6), "unique": int(s.nunique(dropna=True))}
        if pd.api.types.is_numeric_dtype(s) and s.notna().any():
            v = s.dropna()
            rec.update({"min": float(v.min()), "max": float(v.max()),
                        "mean": float(v.mean()), "median": float(v.median())})
        else:
            top = s.dropna().astype(str).value_counts().head(5)
            rec["top"] = {k: int(c) for k, c in top.items()}
        rows.append(rec)
    return rows


def _md(report: dict, map_report: list[dict], lineage: pd.DataFrame) -> str:
    lines = ["# ⑤ 映射报告（空间结构化）", "",
             f"- 映射时间：{report['mapped_at']}",
             f"- H3：v{report['h3']['version']}，res={report['h3']['res']}，grid_disk k={report['h3']['ring_k']}",
             f"- 形状：面板 {report['shape']['panel_rows']:,} 行；网点维度 {report['shape']['branch_dim_rows']:,} 行；"
             f"exposure {report['shape']['exposure_rows']:,} 行 × {report['shape']['exposure_cols']} 列",
             f"- H3 网格数：{report['shape']['h3_cells']:,}", "",
             "## 操作明细", "", "| 操作 | 结果 | 原因 |", "| --- | --- | --- |"]
    for r in report["operations"]:
        lines.append(f"| `{r['op']}` | {r['detail']} | {r.get('reason', '—')} |")

    lines += ["", "## 事件判定分布", "", "| 事件类型 | 网点数 |", "| --- | --- |"]
    for k, v in report["event_type_dist"].items():
        lines.append(f"| {k} | {v:,} |")

    lines += ["", "## 各环同业网点数均值（距离衰减）", "",
              "| 距离环 | 均值 |", "| --- | --- |"]
    for k, v in report["mean_same_ind_by_ring"].items():
        lines.append(f"| {k} | {v} |")

    lines += ["", "## 字段血缘", "", "| 输出字段 | 来源字段 | 表达式 / 方式 | 操作 |",
              "| --- | --- | --- | --- |"]
    for _, r in lineage.iterrows():
        lines.append(f"| {r['output']} | {r['sources']} | {r['expr']} | {r['op']} |")

    lines += ["", "## 映射后字段数据报告（exposure）", "",
              "| 字段 | 类型 | 非空 | 缺失率 | 唯一值 | 关键统计 |", "| --- | --- | --- | --- | --- | --- |"]
    for f in report["mapped_fields"]:
        key = "—"
        if "mean" in f:
            key = f"mean={f['mean']:.4g}, median={f['median']:.4g}, max={f['max']:.4g}"
        elif "top" in f and f["top"]:
            key = ", ".join(f"{k}({v})" for k, v in list(f["top"].items())[:3])
        lines.append(f"| {f['field']} | {f['dtype']} | {f['non_null']:,} | {f['null_rate']:.2%} | "
                     f"{f['unique']:,} | {key} |")

    lines += ["", "## exposure 结构与设计取向", "",
              f"- 处理组：{report['exposure_structure']['treated']}",
              f"- 对照组：{report['exposure_structure']['control']}",
              f"- {report['l1_design_note']}", ""]
    return "\n".join(lines)


def main() -> None:
    project = dk.Project.load(ROOT)
    print(run(project))


if __name__ == "__main__":
    main()
