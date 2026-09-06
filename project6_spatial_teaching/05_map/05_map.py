# -*- coding: utf-8 -*-
"""05_map —— ⑤ 映射（教学主线 L0→L3 四阶认知阶梯）。

回答「原始字段怎么变成分析字段，映射后的数据长什么样」：

* **L0 H3 网格化**：点 → R8 格（平均边长 ≈ 0.46 km），值聚合到格（datakit 内核能力）；
* **L1 空间权重矩阵**：H3 邻接 → ``libpysal`` W，行标准化，孤岛标记（``spatial_ladder.py``）；
* **L2 空间滞后**：``Wx`` + Moran's I；
* **L3 距离环溢出**：Top-N 热点为圆心，0–1 / 1–3 / 3–5 / 5–10 km 环内溢出值。

口径（分辨率 / 热点数 / 距离环 / 抽样日）全部来自 ``config/``，改口径不改代码。

产物（``output/<dataset>/``）：``map.yaml``/``map.md``、``lineage.csv``、``fields.csv``、
``mapped.csv``、``L2_spatial_lag.csv``、``L3_ring_spillover.csv``、``ladder_report.json``。
"""
from __future__ import annotations

import datetime as _dt
import sys
from pathlib import Path

import numpy as np
import pandas as pd

import datakit as dk

sys.path.insert(0, str(Path(__file__).resolve().parent))
import spatial_ladder as sl  # noqa: E402

STAGE = "05_map"
DATASETS = ("fdic", "sz_bike", "snap_brightkite", "snap_gowalla")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def _params(project) -> tuple[int, int, list[list[float]]]:
    """从 config/mapping.yaml 读 L0 / L3 的口径参数。"""
    ops = (project.config("mapping") or {}).get("ops") or []
    res = next((o.get("params", {}).get("res") for o in ops if o.get("op") == "geocode"), 8)
    ring = next((o for o in ops if o.get("op") == "aggregate"
                 and o.get("to") == "ring_spillover"), {})
    p = ring.get("params") or {}
    return int(res), int(p.get("hot_top_n", 100)), [list(r) for r in p.get("rings_km", [[0, 1], [1, 3], [3, 5], [5, 10]])]


def _field_report(frame: pd.DataFrame, source: dict[str, str]) -> pd.DataFrame:
    """映射后字段数据报告（规范 §2-⑤）。"""
    rows = []
    for col in frame.columns:
        s = frame[col]
        row = {"field": col, "dtype": str(s.dtype), "source": source.get(col, ""),
               "non_null": int(s.notna().sum()), "null_rate": float(s.isna().mean() if len(s) else 0.0),
               "unique": int(s.nunique(dropna=True))}
        if pd.api.types.is_numeric_dtype(s) and not pd.api.types.is_bool_dtype(s):
            v = s.dropna()
            if len(v):
                row.update({"min": float(v.min()), "max": float(v.max()),
                            "mean": float(v.mean()), "median": float(v.median())})
        rows.append(row)
    return pd.DataFrame(rows)


def _run_one(project, ds: str) -> dict:
    import h3

    res, hot_top_n, rings = _params(project)
    cleaned = pd.read_csv(project.stage_path("03_clean", ds, "cleaned.csv"))
    out_dir = project.stage_output(STAGE) / ds
    out_dir.mkdir(parents=True, exist_ok=True)

    # ---------- L0：H3 网格化 + 聚合（datakit 内核） ----------
    scheme = (dk.MappingScheme()
              .geocode("lat", "lon", resolution=res, reason=f"L0 网格化：H3 R{res}（平均边长 ≈ 0.46 km）")
              .aggregate(["h3"], {"value": "sum"}, reason="点值聚合到格（求和口径）"))
    mapped_res = dk.map(cleaned, scheme)
    cell = mapped_res.dataset.frame.rename(columns={"h3": "h3_cell"})
    cell["h3_cell"] = cell["h3_cell"].astype("string")
    cells = cell["h3_cell"].tolist()
    values = cell["value"].to_numpy(dtype=float)
    lat, lon = sl.cell_centroids(cells)
    l0 = {
        "tier": "L0", "chapter": "H3 网格化",
        "h3_version": h3.__version__, "h3_res": res,
        "points": int(len(cleaned)), "cells": int(len(cell)),
        "value_total": float(values.sum()),
        "value_top10_cells": {str(k): float(v) for k, v in
                              cell.nlargest(10, "value").set_index("h3_cell")["value"].items()},
    }
    project.log(f"[{STAGE}] {ds} L0：{len(cleaned):,} 点 → {len(cell):,} 格")

    # ---------- L1：空间权重矩阵 ----------
    neighbors = sl.build_neighbors(cells)
    w = sl.build_weights(neighbors)
    row_ok, islands = sl.row_sum_ok(w)
    l1 = {
        "tier": "L1", "chapter": "空间权重矩阵（H3 邻接 → libpysal W，行标准化）",
        "n": int(w.n), "mean_neighbors": float(w.mean_neighbors),
        "islands": int(islands), "transform": w.transform,
        "row_sum_standardized": bool(row_ok),
    }
    project.log(f"[{STAGE}] {ds} L1：n={w.n:,}，平均邻居 {w.mean_neighbors:.2f}，孤岛 {islands}")

    # ---------- L2：空间滞后 + Moran's I ----------
    lag = w.sparse @ values
    moran = sl.moran_i(values, w)
    cell["spatial_lag"] = lag
    cell["lat"] = lat
    cell["lon"] = lon
    cell["isolate"] = [len(neighbors[c]) == 0 for c in cells]
    l2 = {
        "tier": "L2", "chapter": "空间滞后（Wx）+ Moran's I",
        "moran_i": moran,
        "lag_corr": float(np.corrcoef(values, lag)[0, 1]),
        "value_mean": float(values.mean()), "spatial_lag_mean": float(lag.mean()),
    }
    project.log(f"[{STAGE}] {ds} L2：Moran's I = {moran:.4f}")

    # ---------- L3：距离环溢出 ----------
    spill = sl.ring_spillover(cells, values, hot_top_n, rings)
    spill_cols = [c for c in spill.columns if c.startswith("spill_")]
    den_cols = [c for c in spill.columns if c.startswith("spillden_")]
    l3 = {
        "tier": "L3", "chapter": "距离环溢出（热点圆心）",
        "centers": int(len(spill)), "ring_km": rings,
        "mean_spill_by_ring": {c: float(spill[c].mean()) for c in spill_cols},
        "mean_spill_density_by_ring": ({c: float(spill[c].dropna().mean()) for c in den_cols}
                                       if den_cols else {}),
        "note": "环内格数随距离增加，求和口径不衰减；按环内格均摊（溢出密度）才反映距离衰减"
                "——聚合口径影响结论，对应 L1→L2→L3 认知阶梯",
    }
    project.log(f"[{STAGE}] {ds} L3：{len(spill)} 个热点圆心 × {len(rings)} 环")

    # ---------- 落盘 ----------
    mapped = cell[["h3_cell", "lat", "lon", "value", "spatial_lag", "isolate"]]
    mapped.to_csv(out_dir / "mapped.csv", index=False, float_format="%.6f", encoding="utf-8")
    cell[["h3_cell", "value", "spatial_lag"]].to_csv(
        out_dir / "L2_spatial_lag.csv", index=False, float_format="%.6f", encoding="utf-8")
    spill.to_csv(out_dir / "L3_ring_spillover.csv", index=False, float_format="%.4f", encoding="utf-8")

    lineage = pd.DataFrame([
        {"output_field": "h3_cell", "source": "lat, lon",
         "expression": f"h3.latlng_to_cell(lat, lon, {res})", "op": "geocode",
         "engine": "h3", "reason": "L0 网格化"},
        {"output_field": "value", "source": "value",
         "expression": "sum(value) by h3_cell", "op": "aggregate",
         "engine": "pandas", "reason": "点值聚合到格"},
        {"output_field": "spatial_lag", "source": "value, W",
         "expression": "W @ value（行标准化）", "op": "spatial_lag",
         "engine": "libpysal", "reason": "L2 空间滞后"},
        {"output_field": "moran_i", "source": "value, W",
         "expression": "(z' W z) / (z' z)", "op": "derive",
         "engine": "libpysal", "reason": "L2 Moran's I"},
        {"output_field": "ring_spillover", "source": "value, h3_cell",
         "expression": f"sum(value) within rings {rings} km of top-{hot_top_n} hot cells",
         "op": "aggregate", "engine": "h3+haversine", "reason": "L3 距离环溢出"},
        {"output_field": "lat", "source": "h3_cell", "expression": "h3.cell_to_latlng(h3_cell)[0]",
         "op": "derive", "engine": "h3", "reason": "格中心纬度"},
        {"output_field": "lon", "source": "h3_cell", "expression": "h3.cell_to_latlng(h3_cell)[1]",
         "op": "derive", "engine": "h3", "reason": "格中心经度"},
        {"output_field": "isolate", "source": "W", "expression": "len(neighbors) == 0",
         "op": "derive", "engine": "libpysal", "reason": "孤岛标记（无邻居格）"},
    ])
    dk.write_csv(out_dir, "lineage", lineage)
    dk.write_csv(out_dir, "fields", _field_report(
        mapped, {"h3_cell": "lat,lon → H3", "lat": "h3_cell", "lon": "h3_cell",
                 "value": "value（聚合求和）", "spatial_lag": "W @ value", "isolate": "W"}))

    # ---------- 映射阶段断言（config/assertions.yaml 的 when: 05_map）----------
    assertions = [a for a in ((project.config("assertions") or {}).get("assertions") or [])
                  if a.get("when") == "05_map"]
    check_rows = []
    for a in assertions:
        if a["name"] == "h3_cell_not_null":
            n_null = int(mapped["h3_cell"].isna().sum())
            check_rows.append({"name": a["name"], "severity": a.get("severity", "P2"),
                               "passed": n_null == 0, "actual": n_null, "expected": 0,
                               "message": a.get("message", "")})
        elif a["name"] == "weights_row_standardized":
            check_rows.append({"name": a["name"], "severity": a.get("severity", "P2"),
                               "passed": row_ok, "actual": f"孤岛 {islands}",
                               "expected": a.get("expr", ""), "message": a.get("message", "")})
        elif a["name"] == "moran_i_in_range":
            lo, hi = a.get("min", -1), a.get("max", 1)
            ok = (moran == moran) and (lo <= moran <= hi)
            check_rows.append({"name": a["name"], "severity": a.get("severity", "P2"),
                               "passed": bool(ok), "actual": round(float(moran), 6),
                               "expected": f"[{lo}, {hi}]", "message": a.get("message", "")})
    map_blocking_fail = [c for c in check_rows if not c["passed"] and c["severity"] == "P0"]

    report = {
        "dataset": ds,
        "mapped_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "mainline": "H3 网格化 → 空间权重矩阵 → 空间滞后 → 距离环溢出",
        "params": {"h3_res": res, "hot_top_n": hot_top_n, "rings_km": rings,
                   "marked": "合成参数，非真实业务数据"},
        "shape": {"before_rows": int(len(cleaned)), "after_rows": int(len(mapped)),
                  "before_cols": int(len(cleaned.columns)), "after_cols": int(len(mapped.columns))},
        "operations": [
            {"op": "geocode", "object": "lat,lon", "result": f"h3_cell（res={res}）",
             "reason": "L0 网格化"},
            {"op": "aggregate", "object": "value by h3_cell", "result": "value（求和）",
             "reason": "点值聚合到格"},
            {"op": "spatial_weights", "object": "h3 邻接", "result": f"W（n={w.n}，行标准化）",
             "reason": "L1 空间权重矩阵"},
            {"op": "derive", "object": "Wx", "result": "spatial_lag",
             "reason": "L2 空间滞后"},
            {"op": "derive", "object": "moran(value, W)", "result": f"moran_i={moran:.6f}",
             "reason": "L2 Moran's I"},
            {"op": "aggregate", "object": f"top-{hot_top_n} 热点 × {len(rings)} 环",
             "result": "L3_ring_spillover.csv", "reason": "L3 距离环溢出"},
        ],
        "tiers": {"L0": l0, "L1": l1, "L2": l2, "L3": l3},
        "assertions": check_rows,
        "blocking_fail": len(map_blocking_fail),
        "outputs": ["mapped.csv", "L2_spatial_lag.csv", "L3_ring_spillover.csv"],
    }
    dk.write_yaml(out_dir, "map", report)

    md = [f"# ⑤ 映射报告 · {ds}", "",
          f"> 生成时间：{report['mapped_at']}　教学主线：{report['mainline']}",
          "", f"- 形状：{len(cleaned):,} 行 × {len(cleaned.columns)} 列 → "
              f"{len(mapped):,} 行 × {len(mapped.columns)} 列（点 → 格）",
          "", "## 操作明细", "", "| 操作 | 对象 | 结果 | 原因 |", "| --- | --- | --- | --- |"]
    for op in report["operations"]:
        md.append(f"| `{op['op']}` | {op['object']} | {op['result']} | {op['reason']} |")
    md += ["", "## L0→L3 四阶结果", "",
           "| 层 | 章节 | 关键指标 |", "| --- | --- | --- |"]
    md.append(f"| L0 | {l0['chapter']} | {l0['points']:,} 点 → {l0['cells']:,} 格（R{l0['h3_res']}） |")
    md.append(f"| L1 | 空间权重矩阵 | n={l1['n']:,}，平均邻居 {l1['mean_neighbors']:.2f}，孤岛 {l1['islands']} |")
    md.append(f"| L2 | 空间滞后 | Moran's I = {l2['moran_i']:.4f}，lag 相关 {l2['lag_corr']:.4f} |")
    md.append(f"| L3 | 距离环溢出 | {l3['centers']} 圆心 × {len(rings)} 环 |")
    md += ["", "## 距离环均值溢出", "",
           "| 环（km） | 平均溢出值（求和） | 溢出密度（环内格均摊） |", "| --- | ---: | ---: |"]
    for i, c in enumerate(l3["mean_spill_by_ring"]):
        d = list(l3.get("mean_spill_density_by_ring", {}).values())
        md.append(f"| {c} | {l3['mean_spill_by_ring'][c]:,.2f} | "
                  f"{(d[i] if i < len(d) else 0):,.2f} |")
    md += ["", "## 映射阶段断言", "", "| 断言 | 严重度 | 结果 | 实际 |", "| --- | --- | --- | --- |"]
    for c in check_rows:
        md.append(f"| {c['name']} | {c['severity']} | {'PASS' if c['passed'] else 'FAIL'} | {c['actual']} |")
    md += ["", "> 字段血缘见 `lineage.csv`；映射后字段数据报告见 `fields.csv`。", ""]
    dk.write_markdown(out_dir, "map", "\n".join(md))

    # 教学主线报告（扩展阶段 06 依赖；与旧产物同名，便于比对）
    dk.write_json(out_dir, "ladder_report", {
        "dataset": ds, "mainline": report["mainline"], "tiers": {"L0": l0, "L1": l1, "L2": l2, "L3": l3},
    })

    return {
        "dataset": ds,
        "cells": int(len(mapped)),
        "moran_i": round(float(moran), 4),
        "mean_neighbors": round(float(w.mean_neighbors), 2),
        "islands": int(islands),
    }


def run(project) -> dict:
    datasets = project.meta.get("datasets") or list(DATASETS)
    summaries = [_run_one(project, ds) for ds in datasets]
    return {
        "stage": STAGE,
        "cells": int(sum(s["cells"] for s in summaries)),
        "datasets": {s["dataset"]: {"cells": s["cells"], "moran_i": s["moran_i"]} for s in summaries},
    }


def main() -> None:
    import datakit as _dk
    root = Path(__file__).resolve().parent.parent
    print(run(_dk.Project.load(root)))


if __name__ == "__main__":
    main()
