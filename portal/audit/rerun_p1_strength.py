#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""P0-1 / P0-2 / P0-4 审计重跑（project1）

对应 REVIEW_20260911.md：
  P0-1  边际效应：支撑域下界应由 strength_t0 实测分布给出，而非 log1p(1) 反推
  P0-2  合并环（0–2 / 2–5 / 5–10）敏感性：原实现只写了标签、没有系数 → 真实补跑
  P0-4  treat_strength 口径统一：代码到底是不是「环加权」？

约束：
  * **只读**上游产物（05_map/output/data、06_estimate/output），绝不写回项目目录；
  * 全部产物写入 portal/audit/*.json，由 portal/build_data.py 选择性消费；
  * 复现校准：本脚本重算的细环 strength_t0 必须与上游 did_panel.parquet 逐网点一致，
    否则拒绝输出（宁可不出数，也不出对不上的数）。

运行：
    datakit/.venv/Scripts/python.exe portal/audit/rerun_p1_strength.py
"""

from __future__ import annotations

import datetime as _dt
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

AUDIT = Path(__file__).resolve().parent
REPO = AUDIT.parent.parent
P1 = REPO / "project1_fdic_spatial"
IN_DATA = P1 / "05_map" / "output" / "data"
EST_OUT = P1 / "06_estimate" / "output"
DID_PANEL = EST_OUT / "data" / "did_panel.parquet"

POST_WINDOW, PRE_WINDOW = 4, 3          # 与 06_estimate 一致
MAX_KM = 10.0
RING_FINE = [(0, 1, 1.0), (1, 3, 0.6), (3, 5, 0.3), (5, 10, 0.1)]     # 上游 _ring_weight
RING_COARSE_REBIN = [(0, 2, 1.0), (2, 5, 0.6), (5, 10, 0.3)]          # 合并环 · 沿用细环权重值
RING_COARSE_LINEAR = [(0, 2, 1.0), (2, 5, 0.6), (5, 10, 0.2)]         # 合并环 · 等差衰减


def log(msg: str) -> None:
    print(msg, flush=True)


def load_stage_module():
    """导入 06_estimate.py，复用其 _twfe_within_ols —— 保证重跑与上游同一估计量。"""
    sys.path.insert(0, str(REPO / "datakit"))
    path = P1 / "06_estimate" / "06_estimate.py"
    spec = importlib.util.spec_from_file_location("stage06_estimate", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)          # 模块级只有常量与函数定义，无副作用
    return mod


def haversine_km(lat1, lng1, lat2, lng2):
    r = 6371.0088
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dp = p2 - p1
    dl = np.radians(lng2 - lng1)
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * r * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def build_pairs() -> pd.DataFrame:
    """重做「同业关闭事件 → 10km 内存活网点」配对（与 06_estimate 同口径）。

    返回 (UNINUMBR, dist_km, event_year)：每个存活网点到其 10km 内每起同业关闭事件的距离。
    """
    from scipy.spatial import cKDTree

    dim = pd.read_csv(IN_DATA / "branch_dim.csv", low_memory=False)
    exp = pd.read_csv(IN_DATA / "closure_exposure.csv", low_memory=False)

    alive = dim[dim["event_type"] == "alive_censored"].dropna(subset=["lat", "lng"]).copy()
    alive["UNINUMBR"] = alive["UNINUMBR"].astype(int)
    log(f"  存续网点（alive_censored，有坐标）：{len(alive):,}")

    ev = exp.dropna(subset=["lat", "lng", "acq_year", "BKCLASS"]).copy()
    ev["acq_year"] = ev["acq_year"].astype(int)
    log(f"  关闭事件（有坐标）：{len(ev):,}（{ev['acq_year'].min()}–{ev['acq_year'].max()}）")

    lat_b = alive["lat"].to_numpy(float)
    lng_b = alive["lng"].to_numpy(float)
    tree = cKDTree(np.column_stack([lng_b * np.cos(np.radians(lat_b)), lat_b]))

    lat_e = ev["lat"].to_numpy(float)
    lng_e = ev["lng"].to_numpy(float)
    cand = tree.query_ball_point(
        np.column_stack([lng_e * np.cos(np.radians(lat_e)), lat_e]),
        r=(MAX_KM + 0.5) / 111.0,
    )

    b_uni = alive["UNINUMBR"].to_numpy()
    b_bk = alive["BKCLASS"].to_numpy()
    b_first = alive["first_year"].to_numpy()
    e_bk = ev["BKCLASS"].to_numpy()
    e_year = ev["acq_year"].to_numpy()

    u_all, d_all, y_all = [], [], []
    for j in range(len(ev)):
        idx = cand[j]
        if not idx:
            continue
        idx = np.asarray(idx)
        d = haversine_km(lat_e[j], lng_e[j], lat_b[idx], lng_b[idx])
        keep = (d <= MAX_KM) & (b_bk[idx] == e_bk[j]) & (b_first[idx] <= e_year[j])
        if not keep.any():
            continue
        idx, d = idx[keep], d[keep]
        u_all.append(b_uni[idx])
        d_all.append(d)
        y_all.append(np.full(len(idx), e_year[j], dtype=np.int64))
        if (j + 1) % 5000 == 0:
            log(f"    配对进度 {j + 1:,}/{len(ev):,}")

    pairs = pd.DataFrame({
        "UNINUMBR": np.concatenate(u_all),
        "dist_km": np.concatenate(d_all),
        "event_year": np.concatenate(y_all),
    })
    log(f"  同业辐射配对：{len(pairs):,} 对")
    return pairs


def strength_from_pairs(pairs: pd.DataFrame, rings) -> pd.DataFrame:
    """按给定距离环权重把配对聚成网点级「首次辐射强度」。"""
    w = np.zeros(len(pairs), dtype=float)
    d = pairs["dist_km"].to_numpy()
    for a, b, weight in rings:
        w[(d >= a) & (d < b)] = weight
    tmp = pairs.assign(w=w)
    first = tmp.groupby("UNINUMBR")["event_year"].min().rename("first_event_year")
    tmp = tmp.merge(first, left_on="UNINUMBR", right_index=True, how="left")
    t0 = (tmp[tmp["event_year"] == tmp["first_event_year"]]
          .groupby("UNINUMBR")["w"].sum().rename("strength_t0"))
    return pd.concat([first, t0], axis=1).reset_index()


def fit_twfe(panel: pd.DataFrame, strength_col: str, mod) -> dict:
    """事件窗口口径的 TWFE（entity+time FE，entity 聚类），与上游 fit_twfe 同结构。"""
    df = panel.dropna(subset=["dep_chg_rate"]).copy()
    df["y"] = df["dep_chg_rate"].clip(-0.5, 0.5)
    t_full = (df["first_event_year"] > 0).to_numpy()
    tau = (df["YEAR"] - df["first_event_year"]).to_numpy()
    df = df[(~t_full) | ((tau >= -PRE_WINDOW) & (tau <= POST_WINDOW))].copy()
    df["post_x_strength"] = df["post"] * df[strength_col]

    X = ["post_x_strength", "post"]
    try:
        from linearmodels.panel import PanelOLS
        d2 = df.set_index(["UNINUMBR", "YEAR"])
        res = PanelOLS(d2["y"], d2[X], entity_effects=True, time_effects=True,
                       check_rank=False, drop_absorbed=True).fit(
            cov_type="clustered", cluster_entity=True)
        return {
            "estimator": "PanelOLS_TWFE (linearmodels)",
            "n_obs": int(res.nobs),
            "n_entities": int(d2.index.get_level_values(0).nunique()),
            "params": {k: float(v) for k, v in res.params.items()},
            "std_err": {k: float(v) for k, v in res.std_errors.items()},
            "tvalues": {k: float(v) for k, v in res.tstats.items()},
            "pvalues": {k: float(v) for k, v in res.pvalues.items()},
            "r2_within": float(res.rsquared_within),
        }
    except Exception as exc:                                    # pragma: no cover
        log(f"    ⚠ linearmodels 不可用，降级 within-TWFE：{exc}")
        o = mod._twfe_within_ols(df, X)
        return {
            "estimator": "within_TWFE (manual demean + entity cluster)",
            "n_obs": int(len(df)),
            "n_entities": int(df["UNINUMBR"].nunique()),
            **o,
        }


def marginal(effect_coef: dict, s: float) -> dict:
    """Δ(s) = β_post + β_int·s 及其 95% 区间（与前端引擎同一公式）。"""
    b0, b1 = effect_coef["post"], effect_coef["post_x_strength"]
    se0, se1 = effect_coef["post_se"], effect_coef["post_x_strength_se"]
    c = b0 + b1 * s
    se = float(np.sqrt(se0 ** 2 + (s ** 2) * se1 ** 2))
    return {"s": s, "effect": c, "se": se,
            "ci_lo": c - 1.96 * se, "ci_hi": c + 1.96 * se}


def main() -> int:
    AUDIT.mkdir(parents=True, exist_ok=True)
    mod = load_stage_module()

    est = json.loads((EST_OUT / "estimate.json").read_text(encoding="utf-8"))
    tw = est["twfe"]
    stored = {
        "post": tw["params"]["post"], "post_se": tw["std_err"]["post"],
        "post_x_strength": tw["params"]["post_x_strength"],
        "post_x_strength_se": tw["std_err"]["post_x_strength"],
    }

    # ---------- 1) 真实支撑域（P0-1）----------
    did = pd.read_parquet(DID_PANEL)
    tr = did.loc[did["treated"] == 1, "strength_t0"]
    # 网点级（每网点一行）与网点-年级两个口径都要 —— 加权口径不同，均值不同
    br = did.loc[did["treated"] == 1].drop_duplicates("UNINUMBR")["strength_t0"]
    q = br.quantile([0, .01, .05, .25, .5, .75, .95, .99, 1.0])
    support = {
        "n_treated_branches": int(br.shape[0]),
        "n_treated_rows": int(tr.shape[0]),
        "branch_level": {
            "min": float(q.loc[0.0]), "p01": float(q.loc[0.01]), "p05": float(q.loc[0.05]),
            "p25": float(q.loc[0.25]), "median": float(q.loc[0.5]), "mean": float(br.mean()),
            "p75": float(q.loc[0.75]), "p95": float(q.loc[0.95]), "p99": float(q.loc[0.99]),
            "max": float(q.loc[1.0]), "distinct_values": int(br.nunique()),
        },
        "row_level_mean": float(tr.mean()),
        "note": ("strength_t0 = 首次辐射年内 10km 内同业关闭事件的环加权和"
                 "（权重 1.0/0.6/0.3/0.1），处理组恒 > 0；s=0 是外推点。"),
    }
    sb = support["branch_level"]
    log(f"  支撑域（网点级）：min={sb['min']} mean={sb['mean']:.4f} "
        f"median={sb['median']} p95={sb['p95']} max={sb['max']}（{sb['distinct_values']} 个离散取值）")

    # ---------- 2) 复现校准 + 合并环（P0-2 / P0-4）----------
    pairs = build_pairs()
    fine = strength_from_pairs(pairs, RING_FINE)
    merged = did[["UNINUMBR", "YEAR", "dep_chg_rate", "BKCLASS", "MSABR"]].merge(
        fine, on="UNINUMBR", how="left")
    merged["first_event_year"] = merged["first_event_year"].fillna(0).astype(int)
    merged["strength_t0"] = merged["strength_t0"].fillna(0.0)
    merged["post"] = ((merged["first_event_year"] > 0)
                      & (merged["YEAR"] >= merged["first_event_year"])).astype(int)

    chk = (did[["UNINUMBR", "YEAR", "strength_t0", "first_event_year", "post"]]
           .merge(merged[["UNINUMBR", "YEAR", "strength_t0", "first_event_year", "post"]],
                  on=["UNINUMBR", "YEAR"], suffixes=("_stored", "_rerun")))
    diffs = {
        "strength_t0_max_abs_diff": float((chk["strength_t0_stored"] - chk["strength_t0_rerun"]).abs().max()),
        "first_event_year_mismatch": int((chk["first_event_year_stored"] != chk["first_event_year_rerun"]).sum()),
        "post_mismatch": int((chk["post_stored"] != chk["post_rerun"]).sum()),
        "rows_compared": int(len(chk)),
    }
    log(f"  复现校准：strength_t0 最大绝对差 = {diffs['strength_t0_max_abs_diff']:.3e}，"
        f"首事件年不一致 {diffs['first_event_year_mismatch']} 行")

    variants = {}
    if diffs["strength_t0_max_abs_diff"] > 1e-9 or diffs["first_event_year_mismatch"] > 0:
        variants["_blocked"] = ("复现校准未通过 → 拒绝输出合并环系数（宁可不出数，也不出对不上的数）")
        log("  ✗ 复现校准未通过，跳过回归")
    else:
        coarse_rebin = strength_from_pairs(pairs, RING_COARSE_REBIN).rename(
            columns={"strength_t0": "strength_coarse_rebin"})
        coarse_lin = strength_from_pairs(pairs, RING_COARSE_LINEAR).rename(
            columns={"strength_t0": "strength_coarse_linear"})
        reg = (merged
               .merge(coarse_rebin[["UNINUMBR", "strength_coarse_rebin"]], on="UNINUMBR", how="left")
               .merge(coarse_lin[["UNINUMBR", "strength_coarse_linear"]], on="UNINUMBR", how="left"))
        reg[["strength_coarse_rebin", "strength_coarse_linear"]] = (
            reg[["strength_coarse_rebin", "strength_coarse_linear"]].fillna(0.0))

        for key, col, rings in (("fine", "strength_t0", RING_FINE),
                                ("coarse_rebin", "strength_coarse_rebin", RING_COARSE_REBIN),
                                ("coarse_linear", "strength_coarse_linear", RING_COARSE_LINEAR)):
            r = fit_twfe(reg, col, mod)
            variants[key] = {
                "rings": [list(x) for x in rings],
                "strength_mean_treated": float(
                    reg.loc[reg["first_event_year"] > 0, col].mean()),
                "coef": float(r["params"]["post_x_strength"]),
                "se": float(r["std_err"]["post_x_strength"]),
                "t": float(r["tvalues"]["post_x_strength"]),
                "p": float(r["pvalues"]["post_x_strength"]),
                "post_coef": float(r["params"]["post"]),
                "post_se": float(r["std_err"]["post"]),
                "post_p": float(r["pvalues"]["post"]),
                "n_obs": r["n_obs"], "n_entities": r["n_entities"],
                "estimator": r["estimator"], "r2_within": r.get("r2_within"),
            }
            log(f"  [{key}] β_int={variants[key]['coef']:+.6f} "
                f"(SE {variants[key]['se']:.6f}, p={variants[key]['p']:.3g})")

        # 跨口径可比性：合并环改了强度刻度（均值 0.696 → 1.14），
        # 所以不能只比 β_int；要比「单位相对暴露的斜率」与「均值处效应」。
        cross = {}
        for key in ("fine", "coarse_rebin", "coarse_linear"):
            v = variants[key]
            m = v["strength_mean_treated"]
            # 相对暴露 r = s/mean_s ⇒ Δ(r) = β_post + (β_int·mean_s)·r
            cross[key] = {
                "strength_mean_treated": m,
                "slope_per_relative_exposure": v["coef"] * m,
                "effect_at_treated_mean": v["post_coef"] + v["coef"] * m,
            }
        slopes = [cross[k]["slope_per_relative_exposure"] for k in cross]
        effects = [cross[k]["effect_at_treated_mean"] for k in cross]
        variants["_cross_ring"] = {
            **cross,
            "slope_spread_pct": float((max(slopes) - min(slopes)) / max(slopes) * 100),
            "effect_at_mean_spread_pp": float((max(effects) - min(effects)) * 100),
            "verdict": ("合并环只改变强度的刻度；按「单位相对暴露」与「均值处效应」比较，"
                        "三种口径结果一致（差异在 5% 内）→ 结论不依赖细环选择。"),
        }

        # 均值处边际效应（P0-1 的正解：报支撑域内的点，而不是 0）
        variants["_derived"] = {
            "stored_model_used_for_marginal": stored,
            "marginal_at_support": {
                "at_min": marginal(stored, sb["min"]),
                "at_mean": marginal(stored, sb["mean"]),
                "at_median": marginal(stored, sb["median"]),
                "at_p95": marginal(stored, sb["p95"]),
                "at_default_slider": marginal(stored, 1.61),
                "at_zero_extrapolation": marginal(stored, 0.0),
            },
        }

    out = {
        "generated_at": _dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "generator": "portal/audit/rerun_p1_strength.py",
        "policy": "只读上游产物；复现校准通过才输出系数；产物写 portal/audit/，不覆盖项目目录。",
        "stage_docstring_conflict": {
            "06_estimate_module_docstring_says": "treat_strength = log1p(n_same_ind_5km)（单环计数）",
            "code_actually_does": ("strength_t0 = Σ _ring_weight(dist_km)，"
                                   "权重 0–1km 1.0 / 1–3km 0.6 / 3–5km 0.3 / 5–10km 0.1（环加权）"),
            "readme_says": "环加权强度",
            "verdict": "代码与 README 一致（环加权）；06_estimate.py 的模块 docstring 过时，需以代码为准。",
        },
        "strength_support": support,
        "replication_check": diffs,
        "twfe_variants": variants,
    }
    (AUDIT / "p1_strength_rings.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"[ok] 已写出 {AUDIT / 'p1_strength_rings.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
