# -*- coding: utf-8 -*-
"""L1→L3 空间算法辅助模块（05_map 阶段内，规范 §8.2 允许阶段内辅助模块）。

datakit 内核提供到「L0 网格化 + 聚合」（``MappingScheme.geocode`` / ``aggregate``），
**空间权重矩阵 / 空间滞后 / 距离环溢出**属于课题专属算法，尚未沉淀进内核（规范 §8.7），
因此由项目侧实现：H3 邻接 → libpysal W（行标准化） → ``Wx`` 与 Moran's I → 距离环溢出。

依赖：``h3``、``libpysal``（``uv sync --extra geo`` + ``uv pip install libpysal``）。
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

EARTH_R_KM = 6371.0088


def haversine_km(lat1, lng1, lat2, lng2) -> np.ndarray:
    """两点球面距离（km），向量化。"""
    r = EARTH_R_KM
    p1, p2 = np.radians(np.asarray(lat1, float)), np.radians(np.asarray(lat2, float))
    dp = p2 - p1
    dl = np.radians(np.asarray(lng2, float) - np.asarray(lng1, float))
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * r * np.arcsin(np.sqrt(a))


def build_neighbors(cells: list[str]) -> dict[str, list[str]]:
    """L1：H3 一阶邻接（grid_disk k=1，去掉自身与不在集合内的格）。"""
    import h3

    cell_set = set(cells)
    return {c: sorted(n for n in h3.grid_disk(c, 1) if n in cell_set and n != c) for c in cells}


def build_weights(neighbors: dict[str, list[str]]):
    """L1：邻接字典 → libpysal W，行标准化。"""
    from libpysal import weights

    w = weights.W(neighbors)
    w.transform = "r"
    return w


def moran_i(x: np.ndarray, w) -> float:
    """L2：全局 Moran's I（行标准化权重下 = 空间滞后与自身的回归斜率）。"""
    z = x - x.mean()
    denom = float(z @ z)
    return float((z @ (w.sparse @ z)) / denom) if denom > 0 else float("nan")


def row_sum_ok(w) -> tuple[bool, int]:
    """L1 断言：行标准化后每行权重和是否为 1（孤岛除外）。"""
    import numpy as np

    sums = np.asarray(w.sparse.sum(axis=1)).ravel()
    islands = int((sums == 0).sum())
    bad = int((np.abs(sums - 1.0) > 1e-8).sum()) - islands
    return bad == 0, islands


def cell_centroids(cells: list[str]) -> tuple[np.ndarray, np.ndarray]:
    """格子中心经纬度（用于 L3 距离计算与 mapped.csv 落盘）。"""
    import h3

    lat, lon = [], []
    for c in cells:
        la, ln = h3.cell_to_latlng(c)
        lat.append(la)
        lon.append(ln)
    return np.asarray(lat), np.asarray(lon)


def ring_spillover(cells: list[str], values: np.ndarray, top_n: int,
                   rings: list[list[float]]) -> pd.DataFrame:
    """L3：以 Top-N 热点格为圆心，统计各距离环内的溢出值。

    每个环输出三列：

    * ``spill_<a>_<b>km`` —— 环内格值**求和**（环面积越大和越大，不直接反映衰减）；
    * ``cells_<a>_<b>km`` —— 环内格数；
    * ``spillden_<a>_<b>km`` —— **溢出密度**（求和 / 环内格数），才是距离衰减的正确口径。
    """
    lat, lon = cell_centroids(cells)
    order = np.argsort(-values)[:top_n]
    rows = []
    for i in order:
        d = haversine_km(lat[i], lon[i], lat, lon)
        row: dict[str, Any] = {"center_cell": cells[i], "center_value": float(values[i])}
        for a, b in rings:
            tag = f"{a:g}_{b:g}km".replace(".", "p")
            m = (d >= a) & (d < b)
            n = int(m.sum())
            row[f"spill_{tag}"] = float(values[m].sum())
            row[f"cells_{tag}"] = n
            row[f"spillden_{tag}"] = (float(values[m].sum()) / n) if n else None
        rows.append(row)
    return pd.DataFrame(rows)
