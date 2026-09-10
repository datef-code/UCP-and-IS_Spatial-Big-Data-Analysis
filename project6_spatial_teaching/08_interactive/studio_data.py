# -*- coding: utf-8 -*-
"""08_interactive · 数据层：把上游产物读成「教材事实表」。

为什么单独拆一层
----------------
08 是**展示层**，本不该自己算指标。但上游格级 CSV（``L2_spatial_lag.csv`` /
``mapped.csv``）受仓库根 ``.gitignore`` 约束**不入库**（``*/*/*/*.csv``），
而重跑 05_map 又要 30 GB 原始数据。于是这里定一条明确口径：

1. **唯一权威源 = ``05_map/output/<ds>/ladder_report.json``**：入库、L0/L1/L2/L3
   四层齐全，教材里的每个数字都能追到它；
2. **``02_profile/output/<ds>/profile.yaml``** 提供许可与口径语义（教学必须讲合规）；
3. **``04_validate/output/<ds>/version_lock.json``** 提供可复现证据；
4. **格级 CSV 是**可选增强**：在 → 出可交互散点/演化动图；不在 → 相关面板降级为
   「说明 + 上游静态图」，**绝不让整个阶段失败**（本阶段 ``blocking: false``）。

一句话：**数字来自上游，文案来自这里；缺数据要明说，不许编。**
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

DS_ORDER = ["fdic", "sz_bike", "snap_brightkite", "snap_gowalla"]

#: 数据集的**编辑性描述**（不含任何指标数字，数字一律来自上游产物）。
#: 为什么要分开：文案可以随教材迭代，数字必须与管线一致；混在一起就容易把
#: 「讲法」和「事实」一起改坏。
DS_STORY: dict[str, dict[str, str]] = {
    "fdic": dict(
        short="FDIC", scene="全美 · 稀疏",
        one_liner="网点散布全美，格与格之间大量空档。",
        watch="孤岛率接近三成——I 低不一定是「没有空间效应」，可能只是邻居搭不起来。",
    ),
    "sz_bike": dict(
        short="深圳单车", scene="同城 · 极密",
        one_liner="八百多万条骑行挤在 2,661 个格里，密度极高。",
        watch="平均邻居 5.07（六边形满配是 6），孤岛只有 4.5% —— 教科书式的强聚集。",
    ),
    "snap_brightkite": dict(
        short="Brightkite", scene="全球 · 稀疏",
        one_liner="签到散落全球，22.8 万个格里 6.7 万个是孤岛。",
        watch="孤岛率最高、I 最低（0.013）——先怀疑数据本身的稀疏度。",
    ),
    "snap_gowalla": dict(
        short="Gowalla", scene="全球 · 中等",
        one_liner="同为全球签到，但比 Brightkite 更密、孤岛率更低。",
        watch="与 Brightkite 是同类型数据，I 却差 38 倍 —— 对比这一对最能说明问题。",
    ),
}

DS_LABEL = {
    "fdic": "FDIC 网点关闭",
    "sz_bike": "深圳共享单车",
    "snap_brightkite": "Brightkite 签到",
    "snap_gowalla": "Gowalla 签到",
}

#: Okabe–Ito 色盲友好配色（规范 §8.8 要求图表配色可区分）
DS_COLOR = {"fdic": "#0072B2", "sz_bike": "#D55E00",
            "snap_brightkite": "#009E73", "snap_gowalla": "#CC79A7"}

RING_FALLBACK = [[0, 1], [1, 3], [3, 5], [5, 10]]


# --------------------------------------------------------------------------- #
def _read_json(p: Path) -> dict | None:
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def _read_yaml(p: Path) -> dict | None:
    return (yaml.safe_load(p.read_text(encoding="utf-8")) or None) if p.exists() else None


def h3_cell_area_km2(res: int) -> float | None:
    """H3 分辨率对应的平均六边形面积（km²）——**算**出来，不写死。

    教材里要回答「R8 一格多大」，这个数字直接决定「多远算邻居」的直觉。
    """
    try:
        import h3
        return float(h3.average_hexagon_area(res, unit="km^2"))
    except Exception:
        return None


# --------------------------------------------------------------------------- #
def load_dataset(root: Path, ds: str) -> dict[str, Any]:
    """读单个数据集的全部教材事实（数字全部来自上游产物）。"""
    lr = _read_json(root / "05_map" / "output" / ds / "ladder_report.json")
    if lr is None:
        raise FileNotFoundError(f"缺少 05_map/output/{ds}/ladder_report.json（先跑 ⑤ 映射）")

    t = lr["tiers"]
    l0, l1, l2, l3 = t["L0"], t["L1"], t["L2"], t["L3"]

    cells = int(l0["cells"])
    points = int(l0["points"])
    islands = int(l1.get("islands") or 0)
    n = int(l1.get("n") or cells)

    rings: list[dict[str, Any]] = []
    for a, b in (l3.get("ring_km") or RING_FALLBACK):
        tag = f"{a:g}_{b:g}km"
        s = (l3.get("mean_spill_by_ring") or {}).get(f"spill_{tag}")
        d = (l3.get("mean_spill_density_by_ring") or {}).get(f"spillden_{tag}")
        rings.append({"a": float(a), "b": float(b), "label": f"{a:g}–{b:g} km",
                      "spill": (float(s) if s is not None else None),
                      "density": (float(d) if d is not None else None)})

    top10 = l0.get("value_top10_cells") or {}
    v_total = float(l0.get("value_total") or 0.0)

    prof = _read_yaml(root / "02_profile" / "output" / ds / "profile.yaml") or {}
    lic = prof.get("license") or {}

    story = DS_STORY.get(ds, {})
    return {
        "key": ds,
        "label": DS_LABEL.get(ds, ds),
        "short": story.get("short", ds),
        "scene": story.get("scene", ""),
        "one_liner": story.get("one_liner", ""),
        "watch": story.get("watch", ""),
        "color": DS_COLOR.get(ds, "#64748B"),
        # ---- L0 ----
        "h3_res": int(l0.get("h3_res") or 8),
        "points": points,
        "cells": cells,
        "points_per_cell": (points / cells) if cells else None,
        "value_total": v_total,
        "top10_share": (sum(float(v) for v in top10.values()) / v_total) if v_total else None,
        # ---- L1 ----
        "n": n,
        "mean_neighbors": float(l1.get("mean_neighbors") or 0.0),
        "islands": islands,
        "island_rate": (islands / n) if n else None,
        "transform": l1.get("transform", "R"),
        # ---- L2 ----
        "moran_i": float(l2.get("moran_i") or 0.0),
        "lag_corr": float(l2.get("lag_corr") or 0.0),
        "value_mean": float(l2.get("value_mean") or 0.0),
        "lag_mean": float(l2.get("spatial_lag_mean") or 0.0),
        # ---- L3 ----
        "rings": rings,
        "ring_note": l3.get("note", ""),
        "centers": int(l3.get("centers") or 0),
        # ---- 合规 ----
        "role": lic.get("role", "—"),
        "license": lic.get("license", "—"),
        "restriction": lic.get("restriction", ""),
        "value_semantics": prof.get("value_semantics", ""),
    }


def load_locks(root: Path, datasets: list[str]) -> dict[str, dict]:
    out = {}
    for ds in datasets:
        lk = _read_json(root / "04_validate" / "output" / ds / "version_lock.json")
        if lk:
            out[ds] = lk
    return out


def load_facts(root: Path, datasets: list[str] | None = None) -> dict[str, Any]:
    """汇总成教材事实表（供所有交互件与电子书共用）。"""
    order = datasets or DS_ORDER
    rows = [load_dataset(root, ds) for ds in order]
    return {
        "order": order,
        "datasets": {r["key"]: r for r in rows},
        "rows": rows,
        "locks": load_locks(root, order),
        "h3_res": rows[0]["h3_res"] if rows else 8,
        "cell_area_km2": h3_cell_area_km2(rows[0]["h3_res"]) if rows else None,
        "ring_labels": [r["label"] for r in (rows[0]["rings"] if rows else [])],
    }


# --------------------------------------------------------------------------- #
# 可选增强：格级 CSV
# --------------------------------------------------------------------------- #
def csv_status(root: Path, datasets: list[str]) -> dict[str, Any]:
    """检查格级 CSV 是否可用。

    返回 ``{"available": bool, "present": [ds...], "missing": [ds...]}``。
    **缺数据要明说**，前端据此把散点面板换成降级说明，而不是画一张假图。
    """
    present, missing = [], []
    for ds in datasets:
        p = root / "05_map" / "output" / ds / "L2_spatial_lag.csv"
        (present if p.exists() else missing).append(ds)
    return {"available": bool(present), "present": present, "missing": missing}


# --------------------------------------------------------------------------- #
# 06_visualize 的静态图（教材配图）
# --------------------------------------------------------------------------- #
FIG_SLOTS = [
    ("l0", "01-L0-cell-value-ecdf.png", "L0 · 格值 ECDF：值有多集中"),
    ("l2", "02-L2-moran-scatter.png", "L2 · Moran 散点：斜率就是 I"),
    ("l3", "03-L3-ring-spillover.png", "L3 · 距离环溢出密度衰减"),
]


def collect_static_figs(root: Path, datasets: list[str], assets_dir: Path) -> dict[str, dict[str, str]]:
    """把 06_visualize 的 PNG 复制到 ``output/assets/fig/`` 并返回相对路径表。

    为什么要复制一份：教材要求「挪动不丢图」。``06_visualize`` 是另一个阶段，
    直接相对引用会让 ``08_interactive/output`` 单独拷走时图全裂。
    """
    assets_dir.mkdir(parents=True, exist_ok=True)
    out: dict[str, dict[str, str]] = {}
    for ds in datasets:
        slots = {}
        for slot, fname, _title in FIG_SLOTS:
            src = root / "06_visualize" / "output" / ds / "figures" / fname
            if not src.exists():
                continue
            dst = assets_dir / f"{ds}-{fname}"
            if (not dst.exists()) or (src.stat().st_mtime > dst.stat().st_mtime):
                dst.write_bytes(src.read_bytes())
            slots[slot] = dst.name
        if slots:
            out[ds] = slots
    return out
