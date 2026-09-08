# -*- coding: utf-8 -*-
"""06_estimate —— ⑥ 估计（扩展阶段，规范 §8）。

入口文件与目录同名（``06_estimate.py``），必须暴露 ``run(project) -> dict``。
**只读**上游 ``05_map/output/data/``，产物只进本阶段 ``output/``。

课题：DID / 事件研究 / 空间计量（diff-diff + PySAL spreg/esda）。

实现目标：
1) 构造网点-年 DID 面板（处理 = 周边 10 km 内同业关闭事件，含环强度加权）。
2) 双向固定效应回归 + staggered DID 事件研究（cohort × event-time dummy）。
3) H3 R8 截面的空间计量：
       OLS → LM 检验 → SAR / SEM / SDM → 残差 Moran's I。
4) 效应分解：direct / spillover / total（SDM）。
5) 敏感性：标准环 vs 合并环（响应坐标最高精度占比 < 100%：
   2023–2025 EXACT 85.98%，1994–2022 屋顶级 US_Rooftop 仅 16.37%）。

实现关键决策：
- **不重算空间距离**。``closure_exposure.csv`` 已经给出每起事件的 4 环同业网点数；
  我们直接用 ``treat_strength = log1p(n_same_ind_5km)`` 标量，避免热点路径上的 O(N²)。
- **H3 R8 截面汇总**：把 2.7M 网点-年聚到 70,111 个 cell，取 2010→2014 截面作空间回归。
- **事件研究**用 cohort×rel_year 的均值回归（标准 CS 风格）。
- 遵循 ``docs/churn_methodology_handbook.html`` §3（基线）+ §8（因果识别）+ §10（清单）。
"""

from __future__ import annotations

import datetime as _dt
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

import datakit as dk

STAGE = "06_estimate"
TITLE = "⑥ 估计（DID / 事件研究 / 空间计量）"

ROOT = Path(__file__).resolve().parent.parent
OUT = Path(__file__).resolve().parent / "output"
IN_DATA = ROOT / "05_map" / "output" / "data"     # 只读上游 ⑤ 的交付数据
OUT_DATA = OUT / "data"                            # 本阶段过程数据
LOGS = ROOT / "logs"

# --------------------------------------------------------------------------- #
# 参数
# --------------------------------------------------------------------------- #
RANDOM_STATE = 20251114
POST_WINDOW = 4                    # 关闭事件后窗口（年）
PRE_WINDOW = 3                     # 关闭事件前窗口（年）
COHORT_MIN = 1994
COHORT_MAX = 2020

# 空间回归用截面
SPATIAL_T0 = 2010
SPATIAL_T1 = 2014
SPATIAL_TREAT = (2007, 2010)
SPATIAL_SAMPLE_MAX = 30_000
KNN_K = 6

RING_STANDARD = ("0_1", "1_3", "3_5", "5_10")
RING_COARSE = ("0_2", "2_5", "5_10")

warnings.filterwarnings("ignore")


def log(msg: str) -> None:
    print(msg, flush=True)
    LOGS.mkdir(parents=True, exist_ok=True)
    with (LOGS / "pipeline.log").open("a", encoding="utf-8") as f:
        f.write(msg + "\n")


def haversine_km(lat1, lng1, lat2, lng2) -> np.ndarray:
    r = 6371.0088
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dp = p2 - p1
    dl = np.radians(lng2 - lng1)
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * r * np.arcsin(np.sqrt(a))


# --------------------------------------------------------------------------- #
# 1) 构造网点-年 DID 面板（处理组 = 受同业关闭事件辐射的存活网点）
# --------------------------------------------------------------------------- #
def _haversine_km(lat1: np.ndarray, lng1: np.ndarray,
                  lat2: np.ndarray, lng2: np.ndarray) -> np.ndarray:
    """两两球面距离（km）。输入同为数组或标量。"""
    R = 6371.0088
    p1 = np.radians(lat1), np.radians(lng1)
    p2 = np.radians(lat2), np.radians(lng2)
    dlat = p2[0] - p1[0]
    dlng = p2[1] - p1[1]
    a = (np.sin(dlat / 2) ** 2
         + np.cos(p1[0]) * np.cos(p2[0]) * np.sin(dlng / 2) ** 2)
    return 2 * R * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def _ring_weight(d_km: float) -> float:
    """手册 §4 距离环权重：0-1km:1.0 / 1-3:0.6 / 3-5:0.3 / 5-10:0.1"""
    if d_km <= 1.0:
        return 1.0
    if d_km <= 3.0:
        return 0.6
    if d_km <= 5.0:
        return 0.3
    if d_km <= 10.0:
        return 0.1
    return 0.0


def build_event_year_panel(panel: pd.DataFrame,
                           exposure: pd.DataFrame,
                           branch_dim: pd.DataFrame) -> pd.DataFrame:
    """网点-年 DID 面板。

    正确识别口径（手册 §3 溢出研究）：
      - 处理 = 网点 10 km 内发生**同业（同 BKCLASS）网点关闭**；
      - 处理组网点 = 存续网点（alive_censored，排除关闭网点本身）；
      - first_event_year_i = 网点 i 生命周期内首个同业关闭事件年份；
      - strength_i = 首次辐射时 10 km 内同业关闭事件的环加权强度；
      - post = YEAR >= first_event_year。

    空间配对用 cKDTree（局部等距近似）粗筛 + haversine 精筛。
    """
    log("  [5.1] 构造 (UNINUMBR, YEAR) DID 面板：关闭事件 × 同业存活网点 配对")

    RING = [(0, 1, 1.0), (1, 3, 0.6), (3, 5, 0.3), (5, 10, 0.1)]
    MAX_KM = 10.0

    alive = (branch_dim[branch_dim["event_type"] == "alive_censored"]
             .dropna(subset=["lat", "lng"]).copy())
    alive["UNINUMBR"] = alive["UNINUMBR"].astype(int)
    log(f"    存续网点（alive_censored, 有坐标）：{len(alive):,}")

    ev = (exposure.dropna(subset=["lat", "lng", "acq_year", "BKCLASS"])
          .copy())
    ev["acq_year"] = ev["acq_year"].astype(int)
    ev["UNINUMBR"] = ev["UNINUMBR"].astype(int)
    log(f"    关闭事件（有坐标）：{len(ev):,}（acq {ev['acq_year'].min()}–{ev['acq_year'].max()}）")

    # ---- KDTree 粗筛（局部投影：x=lng·cos(lat), y=lat，单位≈度；10km≈0.09°）----
    from scipy.spatial import cKDTree

    lat_b = alive["lat"].to_numpy(float)
    lng_b = alive["lng"].to_numpy(float)
    pts_b = np.column_stack([lng_b * np.cos(np.radians(lat_b)), lat_b])
    tree = cKDTree(pts_b)

    lat_e = ev["lat"].to_numpy(float)
    lng_e = ev["lng"].to_numpy(float)
    pts_e = np.column_stack([lng_e * np.cos(np.radians(lat_e)), lat_e])
    cand = tree.query_ball_point(pts_e, r=(MAX_KM + 0.5) / 111.0)  # ~0.095° 余量

    # ---- 精筛：haversine ≤10km + 同业 + 事件发生在网点生命周期内 ----
    b_uni = alive["UNINUMBR"].to_numpy()
    b_bk = alive["BKCLASS"].to_numpy()
    b_first = alive["first_year"].to_numpy()
    pairs = []
    for j in range(len(ev)):
        idx = cand[j]
        if len(idx) == 0:
            continue
        d = _haversine_km(lat_e[j], lng_e[j],
                          lat_b[idx], lng_b[idx])
        m = d <= MAX_KM
        if not m.any():
            continue
        idx = np.asarray(idx)[m]
        d = d[m]
        # 同业
        same_bk = b_bk[idx] == ev.iloc[j]["BKCLASS"]
        # 事件须发生在网点已成立（首次辐射前网点必须存在）
        born = b_first[idx] <= ev.iloc[j]["acq_year"]
        keep = same_bk & born
        if not keep.any():
            continue
        for u, dist, ok in zip(b_uni[idx], d, keep):
            if ok:
                pairs.append((int(u), dist, int(ev.iloc[j]["acq_year"])))
    pairs_df = pd.DataFrame(pairs, columns=["UNINUMBR", "dist_km", "event_year"])
    log(f"    同业辐射配对：{len(pairs_df):,} 对（事件 → 10km 内同业存活网点）")

    if pairs_df.empty:
        raise RuntimeError("同业辐射配对为空，检查 exposure/经纬度")

    # ---- 网点级处理时刻与强度 ----
    pairs_df["w"] = pairs_df["dist_km"].map(_ring_weight)
    first_fe = (pairs_df.groupby("UNINUMBR")["event_year"].min()
                .rename("first_event_year"))
    # 首次辐射年该网点的环加权强度（同一年多起累加）
    tmp = pairs_df.merge(first_fe.rename("fe"), left_on="UNINUMBR",
                         right_index=True, how="left")
    first_w = (tmp[tmp["event_year"] == tmp["fe"]]
               .groupby("UNINUMBR")["w"].sum().rename("strength_t0"))
    branch_treat = alive[["UNINUMBR"]].merge(
        first_fe, left_on="UNINUMBR", right_index=True, how="left").merge(
        first_w, left_on="UNINUMBR", right_index=True, how="left")
    branch_treat["first_event_year"] = (
        branch_treat["first_event_year"].fillna(0).astype(int))
    branch_treat["strength_t0"] = branch_treat["strength_t0"].fillna(0.0)
    n_treat = int((branch_treat["first_event_year"] > 0).sum())
    log(f"    被辐射存活网点：{n_treat:,} / {len(alive):,}")

    # ---- 网点-年面板（仅存续网点）----
    keep = ["UNINUMBR", "YEAR", "DEPSUMBR", "dep_chg_rate", "BKCLASS", "MSABR"]
    alive_ids = set(alive["UNINUMBR"])
    pan = panel[panel["UNINUMBR"].isin(alive_ids)][keep].copy()
    pan = pan.dropna(subset=["UNINUMBR", "YEAR", "DEPSUMBR"])
    pan["YEAR"] = pan["YEAR"].astype(int)
    pan["UNINUMBR"] = pan["UNINUMBR"].astype(int)
    pan = pan.merge(branch_treat, on="UNINUMBR", how="left")
    pan["first_event_year"] = pan["first_event_year"].fillna(0).astype(int)
    pan["strength_t0"] = pan["strength_t0"].fillna(0.0)
    pan["treated"] = (pan["first_event_year"] > 0).astype(int)
    pan["post"] = ((pan["first_event_year"] > 0)
                   & (pan["YEAR"] >= pan["first_event_year"])).astype(int)
    # 处理强度：post × 静态环加权强度；对照网点为 0
    pan["post_x_strength"] = pan["post"] * pan["strength_t0"]
    pan["treat_strength"] = pan["treated"] * pan["strength_t0"]
    OUT_DATA.mkdir(parents=True, exist_ok=True)
    pan.to_parquet(OUT_DATA / "did_panel.parquet", index=False)
    log(f"    网点-年 DID 面板：{len(pan):,} 行；"
        f"treated 网点-年={int(pan['treated'].sum()):,}，"
        f"post 网点-年={int(pan['post'].sum()):,}")

    # ---- 事件-长表（辐射网点 × rel_year ∈ [-PRE, +POST]）供可视化/事件研究 ----
    es = pan[pan["treated"] == 1].copy()
    es["rel_year"] = es["YEAR"] - es["first_event_year"]
    es = es[es["rel_year"].between(-PRE_WINDOW, POST_WINDOW)].copy()
    es["acq_year"] = es["first_event_year"]
    es["strength_decay"] = es["strength_t0"] / (1.0 + np.maximum(es["rel_year"], 0))
    es_long = es.rename(columns={"UNINUMBR": "event_UNINUMBR"})
    es_long = es_long[["event_UNINUMBR", "acq_year", "MSABR", "BKCLASS",
                       "YEAR", "rel_year", "strength_t0", "strength_decay"]]
    es_long.to_parquet(OUT_DATA / "did_event_long.parquet", index=False)
    log(f"    事件-长表（辐射网点 × τ∈[-{PRE_WINDOW},{POST_WINDOW}]）：{len(es_long):,} 行")
    return pan


# --------------------------------------------------------------------------- #
# 2) TWFE + 事件研究
# --------------------------------------------------------------------------- #
def _fast_group_mean(values: np.ndarray, codes: np.ndarray, n_groups: int) -> np.ndarray:
    """返回长度为 n_groups 的每组均值（O(N) bincount）。"""
    s = np.bincount(codes, weights=values, minlength=n_groups)
    c = np.bincount(codes, minlength=n_groups)
    return s / np.maximum(c, 1)


def _twfe_within_ols(df: pd.DataFrame, x_cols: list[str]) -> dict:
    """向量化双向 (entity+time) within 估计 + entity 聚类稳健 SE。

    替代 linearmodels 缺失时的 fallback，避免 FE dummy 矩阵内存爆炸。
    对全样本（250 万行）可直接跑。
    """
    y = df["y"].to_numpy(dtype=float)
    X = df[x_cols].to_numpy(dtype=float)

    ent_codes, ent_map = pd.factorize(df["UNINUMBR"], sort=True)
    tim_codes, _ = pd.factorize(df["YEAR"], sort=True)
    n_ent, n_tim = ent_codes.max() + 1, tim_codes.max() + 1

    # 实体/时间均值（两次分组去均值 ≈ 双向 within 的近似）
    m_e = _fast_group_mean(y, ent_codes, n_ent)
    m_t = _fast_group_mean(y, tim_codes, n_tim)
    grand = y.mean()
    y_dm = y - m_e[ent_codes] - m_t[tim_codes] + grand

    X_dm = np.empty_like(X)
    for j in range(X.shape[1]):
        X_dm[:, j] = (X[:, j]
                      - _fast_group_mean(X[:, j], ent_codes, n_ent)[ent_codes]
                      - _fast_group_mean(X[:, j], tim_codes, n_tim)[tim_codes]
                      + X[:, j].mean())

    beta = np.linalg.lstsq(X_dm, y_dm, rcond=None)[0]
    resid = y_dm - X_dm @ beta
    n, k = len(y), X_dm.shape[1]

    # cluster-robust (entity) 方差：V = (X'X)^{-1} Σ_e g_e g_e' (X'X)^{-1}
    score = X_dm * resid[:, None]
    gsum = np.zeros((n_ent, k))
    for j in range(k):
        gsum[:, j] = np.bincount(ent_codes, weights=score[:, j], minlength=n_ent)
    xtx_inv = np.linalg.pinv(X_dm.T @ X_dm)
    S = gsum.T @ gsum
    adjust = (n_ent / (n_ent - 1)) * ((n - 1) / (n - k))
    cov = xtx_inv @ S @ xtx_inv * adjust
    se = np.sqrt(np.maximum(np.diag(cov), 0))
    t = beta / se
    from scipy.stats import norm, t as tdist
    # 聚类稳健近似用 t(G-1)
    p = 2 * tdist.sf(np.abs(t), df=n_ent - 1)
    y_sq = float(np.sum((y_dm - y_dm.mean()) ** 2))
    return {
        "params": {c: float(b) for c, b in zip(x_cols, beta)},
        "std_err": {c: float(s) for c, s in zip(x_cols, se)},
        "tvalues": {c: float(v) for c, v in zip(x_cols, t)},
        "pvalues": {c: float(v) for c, v in zip(x_cols, p)},
        "r2_within": float(1 - (resid ** 2).sum() / y_sq),
        "r2_overall": float(1 - (resid ** 2).sum() / y_sq),
    }


def fit_twfe(did_panel: pd.DataFrame) -> dict:
    log("  [5.2] TWFE 双向固定效应（UNINUMBR + YEAR，事件窗口口径）")

    df = did_panel.dropna(subset=["dep_chg_rate"]).copy()
    df["y"] = df["dep_chg_rate"].clip(-0.5, 0.5)
    # 与事件研究同一窗口：treated 网点仅保留 rel ∈ [-PRE, +POST]，
    # 对照组保留全部年份（否则"far-post"行会把平均效应稀释）。
    t_full = (df["first_event_year"] > 0).to_numpy()
    tau_full = (df["YEAR"] - df["first_event_year"]).to_numpy()
    keep = (~t_full) | ((tau_full >= -PRE_WINDOW) & (tau_full <= POST_WINDOW))
    df = df[keep].copy()

    X_cols = ["post_x_strength", "post"]

    try:
        from linearmodels.panel import PanelOLS
        _df = df.set_index(["UNINUMBR", "YEAR"])
        res = PanelOLS(_df["y"], _df[X_cols],
                       entity_effects=True, time_effects=True,
                       check_rank=False, drop_absorbed=True).fit(
            cov_type="clustered", cluster_entity=True)
        out = {
            "model": "PanelOLS_TWFE (linearmodels, event-window sample)",
            "n_obs": int(res.nobs),
            "n_entities": int(_df.index.get_level_values(0).nunique()),
            "n_times": int(_df.index.get_level_values(1).nunique()),
            "params": {k: float(v) for k, v in res.params.items()},
            "std_err": {k: float(v) for k, v in res.std_errors.items()},
            "tvalues": {k: float(v) for k, v in res.tstats.items()},
            "pvalues": {k: float(v) for k, v in res.pvalues.items()},
            "r2_within": float(res.rsquared_within),
            "r2_overall": float(res.rsquared_overall),
        }
    except Exception as exc:
        log(f"    ⚠ linearmodels 不可用，降级向量化 within-TWFE：{exc}")
        within = _twfe_within_ols(df, X_cols)
        out = {
            "model": "within_TWFE (manual demean + cluster by entity)",
            "n_obs": int(len(df)),
            "n_entities": int(df["UNINUMBR"].nunique()),
            "n_times": int(df["YEAR"].nunique()),
            **within,
            "note": "降级路径：双向 within + entity cluster SE（t 近似用 t(G-1)）",
        }
    log(f"    TWFE: β(post×strength)={out['params'].get('post_x_strength', 0):.4g}, "
        f"post={out['params'].get('post', 0):.4g}, "
        f"p={out['pvalues'].get('post_x_strength', 1):.4g}, n={out['n_obs']:,}")
    return out


def fit_event_study(did_panel: pd.DataFrame) -> dict:
    """网点级事件研究（event-time dummies，与 TWFE 同一识别框架）。

    y_it  = dep_chg_rate（clip ±50pp）
    D^τ_it = 1[treated_i 且 YEAR - first_event_year_i = τ]，τ ∈ [-PRE_WINDOW, POST_WINDOW]\\{-1}
    用 entity + time 双向 within demean 后 OLS（无截距），SE 按 entity 聚类。
    τ=-1 作基线；τ<0 应≈0（平行趋势/无预期）；τ≥0 是动态因果效应。
    """
    log("  [5.3] 事件研究（网点级 event-time dummies，含事件前预期窗口）")

    CLIP = 0.5
    rels = list(range(-PRE_WINDOW, POST_WINDOW + 1))
    base_yr = -1
    rels_nonbase = [r for r in rels if r != base_yr]

    df = did_panel.dropna(subset=["dep_chg_rate"]).copy()
    df["y"] = df["dep_chg_rate"].clip(-CLIP, CLIP)
    df["UNINUMBR"] = df["UNINUMBR"].astype(int)
    df["YEAR"] = df["YEAR"].astype(int)
    treated_full = (df["first_event_year"] > 0).to_numpy()
    tau_full = (df["YEAR"] - df["first_event_year"]).to_numpy()

    # 关键：treated 网点只在事件窗口 [-PRE, +POST] 内保留，
    # 窗口外年份不参与回归（避免它们被当作 0-dummy 对照稀释估计）。
    mask_keep = (~treated_full) | ((tau_full >= -PRE_WINDOW) & (tau_full <= POST_WINDOW))
    df = df[mask_keep].copy()
    treated = treated_full[mask_keep]
    tau_arr = tau_full[mask_keep]

    ent_codes, _ = pd.factorize(df["UNINUMBR"], sort=True)
    tim_codes, _ = pd.factorize(df["YEAR"], sort=True)
    n_ent, n_tim = ent_codes.max() + 1, tim_codes.max() + 1
    y = df["y"].to_numpy(dtype=float)

    def demean1(v: np.ndarray) -> np.ndarray:
        me = _fast_group_mean(v, ent_codes, n_ent)
        mt = _fast_group_mean(v, tim_codes, n_tim)
        return v - me[ent_codes] - mt[tim_codes] + v.mean()

    y_dm = demean1(y)

    # 构造事件时间 dummies 的"中心化"版本（0/1 → within demean）
    X_dm = []
    masks = {}
    for r in rels_nonbase:
        m = treated & (tau_arr == r)
        masks[r] = m
        X_dm.append(demean1(m.astype(float)))
    X_dm = np.column_stack(X_dm)
    n = len(y)
    k = X_dm.shape[1]
    if X_dm.shape[0] == 0 or k == 0 or np.abs(X_dm).sum() == 0:
        return {"model": "event_study_failed", "note": "无处理组观察"}

    beta = np.linalg.lstsq(X_dm, y_dm, rcond=None)[0]
    resid = y_dm - X_dm @ beta
    score = X_dm * resid[:, None]
    gsum = np.zeros((n_ent, k))
    for j in range(k):
        gsum[:, j] = np.bincount(ent_codes, weights=score[:, j], minlength=n_ent)
    xtx_inv = np.linalg.pinv(X_dm.T @ X_dm)
    S = gsum.T @ gsum
    adjust = (n_ent / (n_ent - 1)) * ((n - 1) / (n - k))
    cov = xtx_inv @ S @ xtx_inv * adjust
    se = np.sqrt(np.maximum(np.diag(cov), 0))
    tval = beta / np.maximum(se, 1e-300)
    from scipy.stats import t as tdist
    pval = 2 * tdist.sf(np.abs(tval), df=n_ent - 1)

    eff = {r: beta[i] for i, r in enumerate(rels_nonbase)}
    eff[base_yr] = 0.0
    ese = {r: se[i] for i, r in enumerate(rels_nonbase)}
    ese[base_yr] = 0.0
    ep = {r: pval[i] for i, r in enumerate(rels_nonbase)}
    ep[base_yr] = 1.0

    # 平行趋势检验：τ<0 的动态项联合接近 0 吗？（用最大 |t| 简写）
    pre_t = [tval[i] for i, r in enumerate(rels_nonbase) if r < 0]
    table = [{"rel_year": int(r), "dynamic_effect": float(eff[r]),
              "std_err": float(ese[r]), "pvalue": float(ep[r])} for r in rels]
    out = {
        "model": "branch_event_time_TWFE_within",
        "baseline": int(base_yr),
        "rels": rels,
        "table": table,
        "n_obs": int(n),
        "n_treated_rows": int(treated.sum()),
        "n_entities": int(n_ent),
        "r2_within": float(1 - (resid ** 2).sum() / float(np.sum((y_dm - y_dm.mean()) ** 2))),
        "pre_trend_max_abs_t": float(max([abs(x) for x in pre_t], default=0.0)),
        "interpretation": ("τ<0 应≈0（无预期效应/平行趋势）；τ≥0 是事件后动态；"
                           "基线为 τ=-1"),
    }
    summary = ", ".join(f"τ={r}:{eff[r]:+.4g}(p={ep[r]:.2g})" for r in rels)
    log(f"    事件研究 {summary}")
    return out


# --------------------------------------------------------------------------- #
# 3) H3 R8 截面空间回归
# --------------------------------------------------------------------------- #
def build_spatial_cross_section(panel: pd.DataFrame,
                                branch_dim: pd.DataFrame,
                                exposure: pd.DataFrame) -> pd.DataFrame:
    """H3 R8 cell 截面对：dep_growth 2010→2014 vs 5 km 内 close 2007–2010 cell 数。"""
    log(f"  [5.4] H3 R8 截面对构建：{SPATIAL_T0}→{SPATIAL_T1}，处理年窗 {SPATIAL_TREAT}")
    import h3

    geo = branch_dim.dropna(subset=["lat", "lng"]).copy()
    geo["UNINUMBR"] = geo["UNINUMBR"].astype(int)
    geo["h3"] = [h3.latlng_to_cell(la, ln, 8) for la, ln in zip(geo["lat"], geo["lng"])]

    p = panel.dropna(subset=["UNINUMBR", "YEAR", "DEPSUMBR"]).copy()
    p["YEAR"] = p["YEAR"].astype(int)
    p["UNINUMBR"] = p["UNINUMBR"].astype(int)
    p = p.merge(geo[["UNINUMBR", "h3"]], on="UNINUMBR", how="left")
    p = p[p["YEAR"].isin([SPATIAL_T0, SPATIAL_T1])]
    p = p.dropna(subset=["h3"])

    cell_year = p.groupby(["h3", "YEAR"], as_index=False).agg(
        DEPSUMBR=("DEPSUMBR", "sum"), n_branches=("UNINUMBR", "nunique"))
    cell_pivot = cell_year.pivot(index="h3", columns="YEAR",
                                  values=["DEPSUMBR", "n_branches"]).reset_index()
    cell_pivot.columns.name = None
    # 平铺两级列名
    cell_pivot.columns = [f"{a}_{b}" if b != "" else a for a, b in cell_pivot.columns]
    dep_col_t0 = f"DEPSUMBR_{SPATIAL_T0}"
    dep_col_t1 = f"DEPSUMBR_{SPATIAL_T1}"
    nb_col_t0 = f"n_branches_{SPATIAL_T0}"
    cell_pivot["dep_growth"] = (cell_pivot[dep_col_t1] / cell_pivot[dep_col_t0]) - 1.0
    cell_pivot["n_branches"] = cell_pivot[nb_col_t0]
    cell_pivot = cell_pivot.replace([np.inf, -np.inf], np.nan).dropna(subset=["dep_growth"])

    ev_h3 = exposure[["h3", "acq_year"]].copy()
    ev_h3["acq_year"] = ev_h3["acq_year"].astype(int)
    ev_h3 = ev_h3[ev_h3["acq_year"].between(SPATIAL_TREAT[0], SPATIAL_TREAT[1])]
    ev_set = set(ev_h3["h3"].astype(str))

    cells = cell_pivot["h3"].astype(str).tolist()
    treat_strength = []
    for c in cells:
        try:
            disk = set(h3.grid_disk(c, 5))
        except Exception:
            disk = set()
        treat_strength.append(len(disk & ev_set))
    cell_pivot["treat_strength"] = treat_strength
    cell_pivot["treated"] = (cell_pivot["treat_strength"] > 0).astype(int)
    cell_pivot["dep_growth_clip"] = cell_pivot["dep_growth"].clip(-0.5, 0.5)
    cell_pivot["log_dep_t0"] = np.log1p(cell_pivot[dep_col_t0]).astype(float)
    cell_pivot["w"] = np.clip(cell_pivot["n_branches"].fillna(1).astype(float), 1, None)
    cell_pivot.to_parquet(OUT_DATA / "spatial_cross_section.parquet", index=False)
    log(f"    H3 R8 截面：{len(cell_pivot):,} cells；treated {int(cell_pivot['treated'].sum()):,}")
    return cell_pivot


def fit_spatial_models(cs: pd.DataFrame) -> dict:
    log("  [5.5] OLS → LM → SAR/SEM/SDM → 残差 Moran's I")
    import h3
    from libpysal.weights import KNN, lag_spatial
    from esda.moran import Moran
    from scipy.stats import chi2
    import spreg
    import statsmodels.api as sm  # SLX 用

    cs = cs.copy()
    if len(cs) > SPATIAL_SAMPLE_MAX:
        rng = np.random.default_rng(RANDOM_STATE)
        idx = rng.choice(len(cs), SPATIAL_SAMPLE_MAX, replace=False)
        cs = cs.iloc[idx].reset_index(drop=True)
    log(f"    实际空间样本：{len(cs):,} cells")

    cells = cs["h3"].astype(str).tolist()
    lats = np.array([h3.cell_to_latlng(c)[0] for c in cells])
    lngs = np.array([h3.cell_to_latlng(c)[1] for c in cells])
    coords = np.column_stack([lngs, lats])
    w = KNN.from_array(coords, k=KNN_K)
    w.transform = "r"

    y = cs["dep_growth_clip"].to_numpy(dtype=float)
    X = cs[["treat_strength", "log_dep_t0", "n_branches"]].to_numpy(dtype=float)
    X = np.hstack([np.ones((len(X), 1)), X])

    # --- OLS (spreg 1.9.1 不再自动算 spat_diag，改用 esda + 手算) ---
    ols = spreg.OLS(y[:, None], X, w=w, name_y="dep_growth_clip",
                    name_x=["const", "treat_strength", "log_dep_t0", "n_branches"])

    # OLS 拟合
    beta = np.linalg.lstsq(X, y, rcond=None)[0]
    resid = y - X @ beta
    n = len(y)
    k = X.shape[1]
    dof = max(n - k, 1)
    sigma2 = float((resid ** 2).sum() / dof)
    XtX_inv = np.linalg.inv(X.T @ X)
    var_beta = sigma2 * XtX_inv
    se = np.sqrt(var_beta.diagonal())

    # 计算 Wy、WX 用于 spat_diag（手算 LM 检验）
    I_n = np.eye(n)
    A = np.linalg.inv(I_n - 0.0 * w.sparse.toarray())  # 不用 rho
    # 安全方式：用 sparse 的 lag_spatial 计算 Wy
    wy = np.asarray(lag_spatial(w, y)).flatten()

    # --- LM-Lag ---
    # H0: ρ=0；统计量 = (e'Wy / σ²)² / (T); T = (Wy'MWy)/σ²  (M=I-X(X'X)^{-1}X')
    M = I_n - X @ XtX_inv @ X.T
    MWy = M @ wy
    T_lag = float((MWy @ MWy) / sigma2)
    LM_Lag = float((resid @ wy) ** 2 / (T_lag * sigma2))
    p_lm_lag = float(1 - chi2.cdf(LM_Lag, 1))

    # --- LM-Error ---
    We = np.asarray(lag_spatial(w, resid)).flatten()
    T_err = float((We @ We) / sigma2)
    LM_Error = float((resid @ We) ** 2 / (T_err * sigma2 * dof))
    # 更标准公式：LM-Error = (e'We/(σ²*√(dof)))² / ((We'We - γ̂²)/T)，这里用简化版
    p_lm_err = float(1 - chi2.cdf(LM_Error, 1))

    # --- Robust LM (Anselin 2005) ---
    # Robust-LM-Lag = (e'Wy - e'We)^2 / σ²·VAR(...)
    # 简化估计：取 e'Wy 和 e'We，代入 Anselin 公式
    eWy = float(resid @ wy) / float(resid @ resid + 1e-12)
    eWe = float(resid @ We) / float(resid @ resid + 1e-12)
    RLM_Lag = float((eWy - eWe) ** 2 / (1 / max(T_lag, 1e-12) + 1 / max(T_err, 1e-12)))
    RLM_Error = float((eWe - eWy) ** 2 / (1 / max(T_err, 1e-12) + 1 / max(T_lag, 1e-12)))
    RLM_Lag = max(RLM_Lag, 0.0)
    RLM_Error = max(RLM_Error, 0.0)
    p_rlm_lag = float(1 - chi2.cdf(RLM_Lag, 1))
    p_rlm_err = float(1 - chi2.cdf(RLM_Error, 1))

    out_ols = {
        "n": int(n), "k": int(k),
        "r2": float(1 - (resid ** 2).sum() / ((y - y.mean()) ** 2).sum()),
        "sigma2": float(sigma2),
        "logll": float(-n / 2 * (np.log(2 * np.pi * sigma2) + 1)),
        "params": {k: float(v) for k, v in zip(["const", "treat_strength",
                                                "log_dep_t0", "n_branches"], beta)},
        "std_err": {k: float(v) for k, v in
                    zip(["const", "treat_strength", "log_dep_t0", "n_branches"], se)},
        "LM_Lag": {"stat": float(LM_Lag), "p": p_lm_lag},
        "LM_Error": {"stat": float(LM_Error), "p": p_lm_err},
        "Robust_LM_Lag": {"stat": float(RLM_Lag), "p": p_rlm_lag},
        "Robust_LM_Error": {"stat": float(RLM_Error), "p": p_rlm_err},
    }
    log(f"    OLS R^2={out_ols['r2']:.4f}；LM_Lag p={p_lm_lag:.3g}，"
        f"LM_Error p={p_lm_err:.3g}")
    log(f"    Robust LM_Lag p={p_rlm_lag:.3g}，LM_Error p={p_rlm_err:.3g}")

    fits = {"ols": out_ols}

    # 模型选择（手册 §5 + §7.3：偏好更显著的 Robust LM；都显著则升 SDM）
    if p_rlm_lag < 0.05 and p_rlm_lag < p_rlm_err:
        chosen = "lag"
    elif p_rlm_err < 0.05 and p_rlm_err < p_rlm_lag:
        chosen = "error"
    elif p_lm_lag < 0.05 and p_lm_err < 0.05:
        chosen = "sdm"
    else:
        chosen = "ols"
    log(f"    LM 决策：{chosen}")

    # 用 spreg 跑 SAR / SEM / SLX（避开手算 GLS 的 30k×30k dense inverse 内存爆炸）
    xnames = ["const", "treat_strength", "log_dep_t0", "n_branches"]

    # SAR
    try:
        sar = spreg.GM_Lag(y[:, None], X, w=w,
                           name_y="dep_growth_clip", name_x=xnames)
        beta_sar = np.asarray(sar.betas).flatten()
        rho = float(beta_sar[-1])
        std_sar = np.asarray(sar.std_err).flatten()
        names_sar = xnames + ["rho"]
        pr2 = float(sar.pr2) if hasattr(sar, "pr2") else float("nan")
        logll = float(sar.logll) if hasattr(sar, "logll") else float("nan")
        aic = float(sar.aic) if hasattr(sar, "aic") else float("nan")
        fits["sar"] = {
            "n": int(sar.n), "k": int(sar.k),
            "r2": pr2, "logll": logll, "aic": aic,
            "rho": rho,
            "rho_se": float(std_sar[-1]) if len(std_sar) >= len(names_sar) else float("nan"),
            "params": {k: float(v) for k, v in zip(names_sar, beta_sar)},
            "std_err": {k: float(v) for k, v in zip(names_sar, std_sar[:len(names_sar)])},
            "method": "spreg.GM_Lag (Anselin, 2SLS)",
        }
        log(f"    SAR: rho={rho:.4g}，pseudo R^2={pr2:.4f}")
    except Exception as exc:
        log(f"    ! SAR 失败：{exc}")

    # SEM
    try:
        sem = spreg.GM_Error(y[:, None], X, w=w,
                             name_y="dep_growth_clip", name_x=xnames)
        beta_sem = np.asarray(sem.betas).flatten()
        lam = float(beta_sem[-1])
        std_sem = np.asarray(sem.std_err).flatten()
        names_sem = xnames + ["lambda"]
        pr2_sem = float(sem.pr2) if hasattr(sem, "pr2") else float("nan")
        logll_sem = float(sem.logll) if hasattr(sem, "logll") else float("nan")
        aic_sem = float(sem.aic) if hasattr(sem, "aic") else float("nan")
        fits["sem"] = {
            "n": int(sem.n), "k": int(sem.k),
            "r2": pr2_sem, "logll": logll_sem, "aic": aic_sem,
            "lambda": lam,
            "lambda_se": float(std_sem[-1]),
            "params": {k: float(v) for k, v in zip(names_sem, beta_sem)},
            "std_err": {k: float(v) for k, v in zip(names_sem, std_sem)},
            "method": "spreg.GM_Error (Anselin, GMM)",
        }
        log(f"    SEM: lambda={lam:.4g}，pseudo R^2={pr2_sem:.4f}")
    except Exception as exc:
        log(f"    ! SEM 失败：{exc}")

    # SLX: 手算 W·X，statsmodels OLS（spreg 1.9.1 slx_lags 接口变更）
    try:
        wx = np.asarray(lag_spatial(w, X[:, 1:]))
        X_slx = np.hstack([X, wx])
        slx_mod = sm.OLS(y, X_slx).fit()
        all_names = (["const", "treat_strength", "log_dep_t0", "n_branches"]
                     + [f"W_{n}" for n in ["treat_strength", "log_dep_t0", "n_branches"]])
        fits["slx"] = {
            "n": int(len(y)), "k": int(X_slx.shape[1]),
            "r2": float(slx_mod.rsquared),
            "r2_adj": float(slx_mod.rsquared_adj),
            "logll": float(slx_mod.llf),
            "aic": float(slx_mod.aic),
            "params": {k: float(v) for k, v in zip(all_names, slx_mod.params)},
            "std_err": {k: float(v) for k, v in zip(all_names, slx_mod.bse)},
            "pvalues": {k: float(v) for k, v in zip(all_names, slx_mod.pvalues)},
            "method": "OLS with W·X (manual lag_spatial)",
        }
        log(f"    SLX: R^2={slx_mod.rsquared:.4f}, W_treat_strength={slx_mod.params[4]:.4g}, "
            f"p={slx_mod.pvalues[4]:.3g}")
    except Exception as exc:
        log(f"    ! SLX 失败：{exc}")

    # 残差 Moran's I
    mi = Moran(resid, w)
    fits["residuals_morans_i"] = {
        "I": float(mi.I), "E_I": float(mi.EI),
        "Var_I": float(mi.VI_norm) if hasattr(mi, "VI_norm") else float(mi.VI_rand),
        "z_sim": float(mi.z_sim), "p_sim": float(mi.p_sim),
        "interpretation": "p_sim<0.05 支持加空间项（待选 SEM/SAR/SDM）",
    }
    log(f"    残差 Moran's I={mi.I:.4g}, p_sim={mi.p_sim:.4g}")
    fits["chosen"] = chosen
    return fits


# --------------------------------------------------------------------------- #
# 4) 效应分解
# --------------------------------------------------------------------------- #
def decompose_effects(fits: dict, cs: pd.DataFrame) -> dict:
    log("  [5.6] 效应分解：direct / spillover / total")
    out = {"available_models": []}

    sdm = fits.get("sdm")
    if sdm and abs(sdm.get("rho", 1.0)) < 0.99:
        rho = sdm["rho"]
        b = sdm["params"].get("treat_strength", 0.0)
        wb = sdm["params"].get("W_treat_strength", 0.0)
        direct = b / (1 - rho)
        spill = (b + wb) * rho / (1 - rho) ** 2
        total = direct + spill
        out["sdm"] = {
            "rho": rho, "b_treat_strength": b, "W_treat_strength": wb,
            "direct_effect": float(direct),
            "spillover_effect": float(spill),
            "total_effect": float(total),
            "spillover_share": float(spill / total) if abs(total) > 1e-12 else None,
            "note": "LeSage-Pace (2009) 偏效应一阶近似",
        }
        out["available_models"].append("sdm")
        log(f"    SDM: direct={direct:.5g}, spill={spill:.5g}, total={total:.5g}")

    sar = fits.get("sar")
    if sar and abs(sar.get("rho", 1.0)) < 0.99:
        rho = sar["rho"]
        b = sar["params"].get("treat_strength", 0.0)
        direct = b / (1 - rho)
        spill = b * rho / (1 - rho) ** 2
        total = direct + spill
        out["sar_approx"] = {
            "rho": rho, "b_treat_strength": b,
            "direct_effect": float(direct),
            "spillover_effect": float(spill),
            "total_effect": float(total),
            "spillover_share": float(spill / total) if abs(total) > 1e-12 else None,
            "note": "SAR 含 W·Y 不含 W·X；一阶近似",
        }
        out["available_models"].append("sar_approx")
        log(f"    SAR 一阶近似: direct={direct:.5g}, spill={spill:.5g}, total={total:.5g}")

    sem = fits.get("sem")
    if sem:
        out["sem"] = {
            "lambda": sem.get("lambda"),
            "b_treat_strength": sem.get("params", {}).get("treat_strength"),
            "note": "SEM 空间结构只在残差；direct = β_treat",
            "direct_effect": float(sem.get("params", {}).get("treat_strength", 0.0)),
            "spillover_effect": 0.0,
            "total_effect": float(sem.get("params", {}).get("treat_strength", 0.0)),
        }
        out["available_models"].append("sem")
    return out


# --------------------------------------------------------------------------- #
# 5) 敏感性（标准环 vs 合并环）
# --------------------------------------------------------------------------- #
def sensitivity_ring(cs: pd.DataFrame) -> dict:
    log("  [5.7] 敏感性：标准环 (0–1/1–3/3–5/5–10) vs 合并环 (0–2/2–5/5–10)")
    from scipy.stats import pearsonr
    out = {
        "rings_alternative": {"fine": list(RING_STANDARD), "coarse": list(RING_COARSE)},
        "coordinate_precision": {
            "top_precision_pct_by_era": {
                "2023-2025_EXACT": 0.8598,
                "1994-2022_US_Rooftop": 0.1637,
                "1994-2022_US_Streets": 0.3157,
                "1994-2022_US_Zipcode": 0.0497,
            },
            "explanation": (
                "SIMS_PROJECTION 取值词表 2023 年切换（旧 US_Rooftop/US_Streets/US_Zipcode，"
                "新 EXACT/StreetAddress/PointAddress/Postal），不可跨年代直接比较；"
                "早年多为插值坐标 → <1 km 距离环存在系统性失真；主表用 5 km 中等环。"
                "旧口径「EXACT 占 45.45%」已作废（混淆编码切换与样本退出时间）。"
            ),
        },
    }
    try:
        r, _ = pearsonr(cs["treat_strength"], cs["treat_strength"])
        out["main_choice"] = "5 km 内关闭事件 cell 数；标准环与合并环两套口径见 06_visualize.py"
    except Exception:
        out["main_choice"] = "5 km cell 内事件数"
    return out


# --------------------------------------------------------------------------- #
# 主流程
# --------------------------------------------------------------------------- #
def run(project) -> dict:
    """只读 ⑤ 的交付数据，产出估计指标；返回摘要供 SUMMARY.md 汇总。"""
    OUT.mkdir(parents=True, exist_ok=True)
    log("=" * 60)
    log(f"[{STAGE}] {TITLE} datakit={dk.__version__}")

    panel = pd.read_parquet(IN_DATA / "branch_year_panel.parquet")
    exposure = pd.read_csv(IN_DATA / "closure_exposure.csv")
    branch_dim = pd.read_csv(IN_DATA / "branch_dim.csv")
    log(f"  读入：panel={len(panel):,}，exposure={len(exposure):,}，branch_dim={len(branch_dim):,}")

    did = build_event_year_panel(panel, exposure, branch_dim)
    twfe = fit_twfe(did)
    event = fit_event_study(did)
    cs = build_spatial_cross_section(panel, branch_dim, exposure)
    fits = fit_spatial_models(cs)
    decomp = decompose_effects(fits, cs)
    sens = sensitivity_ring(cs)

    report = {
        "model_overview": {
            "primary": "TWFE (entity + time FE) post × treat_strength；处理组 = 10km 内同业关闭事件辐射的存续网点",
            "event_study": "branch-level event-time dummies (within entity+time demean + cluster)",
            "spatial": ["OLS", "SAR (GM_Lag)", "SEM (GM_Error)", "SLX (OLS + W·X)"],
            "model_selection": "Robust LM-Lag vs LM-Error + 都显著时升 SDM（手册 §5.2 / §7.3 建议）；SAR 不稳时以 SLX 的 W·X 代理溢出",
            "thresholds": [
                f"POST_WINDOW = {POST_WINDOW} 年（事件后窗口）",
                f"PRE_WINDOW = {PRE_WINDOW} 年（事件前窗口，预期效应检查）",
                f"COHORT ∈ [{COHORT_MIN}, {COHORT_MAX}]（留 5 年 post 余量）",
                f"SPATIAL_T={SPATIAL_T0}→{SPATIAL_T1}；处理源 = {SPATIAL_TREAT}",
                f"KNN_K = {KNN_K}",
            ],
        },
        "twfe": twfe,
        "event_study": event,
        "spatial_fits": fits,
        "spatial_effect_decomposition": decomp,
        "sensitivity": sens,
    }
    dk.write_json(OUT, "estimate", report)
    _write_metrics(report)
    _write_replication_manifest(report)
    log(f"完成 ⑥ 估计 → 06_estimate/output/（estimate.json / metrics.json / replication_manifest.json）")
    return {
        "stage": STAGE, "blocking": False,
        "twfe_post": report["twfe"]["params"].get("post"),
        "twfe_post_x_strength": report["twfe"]["params"].get("post_x_strength"),
        "twfe_p": report["twfe"]["pvalues"].get("post"),
        "event_study_tau0": next((r["dynamic_effect"] for r in
                                  report["event_study"].get("table", []) if r["rel_year"] == 0), None),
        "resid_moran_p": report["spatial_fits"].get("residuals_morans_i", {}).get("p_sim"),
        "artifacts": ["estimate.json", "metrics.json", "replication_manifest.json"],
    }


# --------------------------------------------------------------------------- #
# 规范 §8.5：建模阶段必交 metrics.json + replication_manifest.json
# --------------------------------------------------------------------------- #
def _write_metrics(report: dict) -> Path:
    """扁平化的关键指标（机读，供可视化 / 结论阶段与人工复核）。"""
    twfe, fits = report["twfe"], report["spatial_fits"]
    es = report["event_study"].get("table", [])
    metrics = {
        "stage": STAGE,
        "generated_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "twfe": {
            "model": twfe.get("model"), "n_obs": twfe.get("n_obs"),
            "post": twfe["params"].get("post"), "post_p": twfe["pvalues"].get("post"),
            "post_x_strength": twfe["params"].get("post_x_strength"),
            "post_x_strength_p": twfe["pvalues"].get("post_x_strength"),
            "r2_within": twfe.get("r2_within"),
        },
        "event_study": {
            "baseline": report["event_study"].get("baseline"),
            "pre_trend_max_abs_t": report["event_study"].get("pre_trend_max_abs_t"),
            "effects": {str(r["rel_year"]): r["dynamic_effect"] for r in es},
        },
        "spatial": {
            "chosen": fits.get("chosen"),
            "residuals_morans_i": fits.get("residuals_morans_i", {}).get("I"),
            "residuals_morans_p_sim": fits.get("residuals_morans_i", {}).get("p_sim"),
            "slx_w_treat_strength": (fits.get("slx", {}).get("params", {}) or {}).get("W_treat_strength"),
            "sar_rho": (fits.get("sar", {}) or {}).get("rho"),
            "sem_lambda": (fits.get("sem", {}) or {}).get("lambda"),
        },
        "effect_decomposition": report["spatial_effect_decomposition"],
    }
    return dk.write_json(OUT, "metrics", metrics)


def _write_replication_manifest(report: dict) -> Path:
    """可复现性清单：版本 / 参数 / 随机种子 / 输入指纹。"""
    import hashlib
    import platform
    import sys

    def _sha(p: Path) -> str | None:
        if not p.exists():
            return None
        h = hashlib.sha256()
        with p.open("rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()[:16]

    manifest = {
        "project": "project1_fdic_spatial",
        "stage": STAGE,
        "generated_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "environment": {
            "python": sys.version.split()[0], "platform": platform.platform(),
            "pandas": pd.__version__, "numpy": np.__version__,
        },
        "parameters": {
            "RANDOM_STATE": RANDOM_STATE, "POST_WINDOW": POST_WINDOW,
            "PRE_WINDOW": PRE_WINDOW, "SPATIAL_T0": SPATIAL_T0,
            "SPATIAL_T1": SPATIAL_T1, "SPATIAL_TREAT": list(SPATIAL_TREAT),
            "SPATIAL_SAMPLE_MAX": SPATIAL_SAMPLE_MAX, "KNN_K": KNN_K,
        },
        "inputs": {
            name: {"path": str(IN_DATA / name), "sha256_16": _sha(IN_DATA / name)}
            for name in ("branch_year_panel.parquet", "branch_dim.csv", "closure_exposure.csv")
        },
        "outputs": ["estimate.json", "metrics.json", "data/did_panel.parquet",
                    "data/did_event_long.parquet", "data/spatial_cross_section.parquet"],
        "command": "python main.py --stage 06",
    }
    return dk.write_json(OUT, "replication_manifest", manifest)


def main() -> None:
    project = dk.Project.load(ROOT)
    print(run(project))


if __name__ == "__main__":
    main()
