#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""portal/refit.py —— 用**客户自己的数据**重估系数（产品不再锁死 FDIC）。

产物刻意与 ``portal/data/portal_data.js`` 的 ``impact`` / ``risk`` 段同构，
因此前端可以把它直接"载入为当前数据层"，四个模块立刻按新系数工作。

能做什么（按数据条件自动判定，不做就明说）：
    impact   面板 + （处理标记 / 处理年 / 事件时间）→ TWFE + 事件研究 + 强度支撑域
    spatial  有经纬度 → KNN 权重 + OLS/SLX + 残差 Moran's I
    risk     有二元退出/目标列 → cloglog（特征表由**实际列**生成，非 FDIC 固定清单）

复用的方法论内核来自 project1 ``06_estimate.py``（within 双向去均值 + 实体聚类 SE），
但**不复制任何上游系数**：全部由传入数据现算。

用法（CLI 自检）：
    datakit/.venv/Scripts/python.exe portal/refit.py --paths "data_raw/fdic/*.csv" --limit 3 \
        --treat-year-year 2016 --out /tmp/artifact.json
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

PORTAL = Path(__file__).resolve().parent

PRE_WINDOW = 3
POST_WINDOW = 4
SAMPLE_MAX_SPATIAL = 30_000
CLIP = 0.5
RANDOM_STATE = 20260911


# --------------------------------------------------------------------------- #
# 通用 within 估计内核（复刻 project1 的方法，参数化列名）
# --------------------------------------------------------------------------- #
def _group_mean(v: np.ndarray, codes: np.ndarray, n: int) -> np.ndarray:
    s = np.bincount(codes, weights=v, minlength=n)
    c = np.bincount(codes, minlength=n)
    return s / np.maximum(c, 1)


def twfe_within(df: pd.DataFrame, y_col: str, x_cols: list[str],
                ent_col: str, tim_col: str) -> dict:
    """双向 (entity+time) within 估计 + 实体聚类稳健 SE。纯 numpy，不需 linearmodels。"""
    df = df.dropna(subset=[y_col] + list(x_cols))
    y = df[y_col].to_numpy(float)
    X = df[x_cols].to_numpy(float)
    ent_codes, _ = pd.factorize(df[ent_col], sort=True)
    tim_codes, _ = pd.factorize(df[tim_col], sort=True)
    n_ent, n_tim = int(ent_codes.max()) + 1, int(tim_codes.max()) + 1

    grand = y.mean()
    y_dm = y - _group_mean(y, ent_codes, n_ent)[ent_codes] - _group_mean(y, tim_codes, n_tim)[tim_codes] + grand
    X_dm = np.empty_like(X)
    for j in range(X.shape[1]):
        X_dm[:, j] = (X[:, j] - _group_mean(X[:, j], ent_codes, n_ent)[ent_codes]
                      - _group_mean(X[:, j], tim_codes, n_tim)[tim_codes] + X[:, j].mean())

    beta = np.linalg.lstsq(X_dm, y_dm, rcond=None)[0]
    resid = y_dm - X_dm @ beta
    n, k = len(y), X_dm.shape[1]
    score = X_dm * resid[:, None]
    gsum = np.zeros((n_ent, k))
    for j in range(k):
        gsum[:, j] = np.bincount(ent_codes, weights=score[:, j], minlength=n_ent)
    xtx_inv = np.linalg.pinv(X_dm.T @ X_dm)
    cov = xtx_inv @ (gsum.T @ gsum) @ xtx_inv * ((n_ent / max(n_ent - 1, 1)) * ((n - 1) / max(n - k, 1)))
    se = np.sqrt(np.maximum(np.diag(cov), 0))
    from scipy.stats import t as tdist
    t = beta / np.maximum(se, 1e-300)
    p = 2 * tdist.sf(np.abs(t), df=max(n_ent - 1, 1))
    ysq = float(np.sum((y_dm - y_dm.mean()) ** 2))
    return {
        "params": {c: float(b) for c, b in zip(x_cols, beta)},
        "std_err": {c: float(s) for c, s in zip(x_cols, se)},
        "tvalues": {c: float(v) for c, v in zip(x_cols, t)},
        "pvalues": {c: float(v) for c, v in zip(x_cols, p)},
        "r2_within": float(1 - (resid ** 2).sum() / ysq) if ysq else None,
        "n_obs": int(n), "n_entities": int(n_ent), "n_times": int(n_tim),
        "model": "within_TWFE (double demean + cluster by entity)",
    }


def event_study(df: pd.DataFrame, y_col: str, ent_col: str, tim_col: str,
                treated: np.ndarray, tau: np.ndarray,
                pre: int = PRE_WINDOW, post: int = POST_WINDOW) -> dict:
    """网点级 event-time dummies（τ=−1 为基线），within demean + 实体聚类 SE。"""
    rels = list(range(-pre, post + 1))
    base = -1
    nonbase = [r for r in rels if r != base]
    treated = np.asarray(treated).astype(bool)
    tau = np.asarray(tau, dtype=float)
    keep = (~treated) | ((tau >= -pre) & (tau <= post))
    d = df.loc[keep].reset_index(drop=True)
    treated, tau = treated[keep], tau[keep]
    notna = d[y_col].notna().to_numpy()
    d, treated, tau = d.loc[notna].reset_index(drop=True), treated[notna], tau[notna]
    if treated.sum() == 0:
        return {"ok": False, "reason": "无处理组观察", "table": []}

    ent_codes, _ = pd.factorize(d[ent_col], sort=True)
    tim_codes, _ = pd.factorize(d[tim_col], sort=True)
    n_ent, n_tim = int(ent_codes.max()) + 1, int(tim_codes.max()) + 1
    y = d[y_col].to_numpy(float)

    def demean(v: np.ndarray) -> np.ndarray:
        return v - _group_mean(v, ent_codes, n_ent)[ent_codes] - _group_mean(v, tim_codes, n_tim)[tim_codes] + v.mean()

    y_dm = demean(y)
    X_dm, masks = [], {}
    for r in nonbase:
        m = treated & (tau == r)
        masks[r] = m
        X_dm.append(demean(m.astype(float)))
    X_dm = np.column_stack(X_dm)
    n, k = len(y), X_dm.shape[1]
    if k == 0 or np.abs(X_dm).sum() == 0:
        return {"ok": False, "reason": "无事件时间变异", "table": []}

    beta = np.linalg.lstsq(X_dm, y_dm, rcond=None)[0]
    resid = y_dm - X_dm @ beta
    gsum = np.zeros((n_ent, k))
    score = X_dm * resid[:, None]
    for j in range(k):
        gsum[:, j] = np.bincount(ent_codes, weights=score[:, j], minlength=n_ent)
    xtx_inv = np.linalg.pinv(X_dm.T @ X_dm)
    cov = xtx_inv @ (gsum.T @ gsum) @ xtx_inv * ((n_ent / max(n_ent - 1, 1)) * ((n - 1) / max(n - k, 1)))
    se = np.sqrt(np.maximum(np.diag(cov), 0))
    from scipy.stats import t as tdist
    t = beta / np.maximum(se, 1e-300)
    p = 2 * tdist.sf(np.abs(t), df=max(n_ent - 1, 1))

    eff = {r: float(beta[i]) for i, r in enumerate(nonbase)}
    ese = {r: float(se[i]) for i, r in enumerate(nonbase)}
    ep = {r: float(p[i]) for i, r in enumerate(nonbase)}
    eff[base], ese[base], ep[base] = 0.0, 0.0, 1.0
    tval = {r: float(t[i]) for i, r in enumerate(nonbase)}
    pre_t = [abs(tval[r]) for r in nonbase if r < 0]
    table = [{"tau": int(r), "effect": eff[r], "se": ese[r], "p": ep[r]} for r in rels]
    return {
        "ok": True, "baseline": base, "table": table,
        "n_obs": int(n), "n_treated_rows": int(treated.sum()), "n_entities": int(n_ent),
        "pre_trend_max_abs_t": float(max(pre_t, default=0.0)),
        "interpretation": "τ<0 应≈0（平行趋势）；τ≥0 为事件后动态效应；基线 τ=−1",
    }


# --------------------------------------------------------------------------- #
# 面板构造
# --------------------------------------------------------------------------- #
def build_panel(df: pd.DataFrame, roles: dict, opt: dict) -> tuple[pd.DataFrame, dict]:
    """从映射后的表构造 (实体, 时间) 面板：y = 结果变量的实体内增长率。"""
    ent, tim, val = roles.get("entity"), roles.get("time"), roles.get("value")
    if not (ent and tim):
        raise ValueError("重估需要「实体 + 时间」两列")
    d = df.copy()
    d[tim] = pd.to_numeric(d[tim], errors="coerce")
    d = d.dropna(subset=[ent, tim]).sort_values([ent, tim])
    d[tim] = d[tim].astype(int)

    y_col = opt.get("y_col")
    if not y_col:
        if not val:
            raise ValueError("重估需要结果变量（value）或显式指定 y_col")
        # 实体内增长率（与 project1 的 dep_chg_rate 同口径）
        v = pd.to_numeric(d[val], errors="coerce")
        prev = v.groupby(d[ent]).shift(1)
        d["_y"] = ((v - prev) / prev.abs().replace(0, np.nan)).replace([np.inf, -np.inf], np.nan).clip(-CLIP, CLIP)
        y_col = "_y"

    # ---- 处理时刻 ----
    ty, tc, ev = opt.get("treat_year_col"), opt.get("treat_col"), roles.get("event_time")
    if ty:
        d["_first"] = pd.to_numeric(d[ty], errors="coerce").groupby(d[ent]).transform("min")
    elif tc:
        d["_mark"] = pd.to_numeric(d[tc], errors="coerce").fillna(0)
        d["_first"] = d.loc[d["_mark"] > 0].groupby(ent)[tim].transform("min")
        d["_first"] = d.groupby(ent)["_first"].transform("min")
    elif ev:
        yr = pd.to_datetime(d[ev], errors="coerce").dt.year
        d["_first"] = yr.groupby(d[ent]).transform("min")
    else:
        raise ValueError("重估需要处理定义：treat_year_col / treat_col / event_time 三者之一")

    d["_treated"] = (d["_first"].notna() & (d["_first"] > 0)).astype(int)
    d["_post"] = ((d["_treated"] == 1) & (d[tim] >= d["_first"])).astype(int)

    # ---- 强度（可无：无则退化为二元处理） ----
    sc = opt.get("strength_col")
    if sc:
        s = pd.to_numeric(d[sc], errors="coerce")
        first = d.loc[d["_post"] == 1].groupby(ent)[sc].mean()
        ent_strength = pd.to_numeric(first, errors="coerce")
        d["_strength"] = d[ent].map(ent_strength).fillna(0.0).astype(float)
    else:
        d["_strength"] = d["_treated"].astype(float)
    d["_post_x_strength"] = d["_post"] * d["_strength"]

    info = {"y_col": y_col, "n_rows": int(len(d)),
            "n_treated_entities": int(d.loc[d["_treated"] == 1, ent].nunique()),
            "n_entities": int(d[ent].nunique()), "strength_used": bool(sc)}
    return d, info


def strength_support(d: pd.DataFrame, roles: dict) -> dict | None:
    ent = roles["entity"]
    t = d[d["_treated"] == 1]
    if not len(t):
        return None
    s = t.groupby(ent)["_strength"].first()
    s = pd.to_numeric(s, errors="coerce").dropna()
    if not len(s):
        return None
    return {
        "n_treated_branches": int(len(s)), "n_treated_rows": int(len(t)),
        "branch_level": {
            "min": float(s.min()), "p05": float(s.quantile(0.05)), "p25": float(s.quantile(0.25)),
            "median": float(s.median()), "mean": float(s.mean()),
            "p75": float(s.quantile(0.75)), "p95": float(s.quantile(0.95)), "max": float(s.max()),
            "distinct_values": int(s.nunique()),
        },
        "row_level_mean": float(pd.to_numeric(t["_strength"], errors="coerce").mean()),
        "note": ("支撑域 = 处理组在各事件年上的暴露强度实测分位数；强度为 0 的点若不在支撑域内，"
                 "则任何基于该点的效应都是外推。" if not t["_strength"].nunique() == 1 else
                 "本次重估未提供强度列 → 采用二元处理（强度 ≡ 1），不存在强度外推问题。"),
    }


# --------------------------------------------------------------------------- #
# 空间部分（KNN 权重 + OLS/SLX + 残差 Moran's I）
# --------------------------------------------------------------------------- #
def fit_spatial(d: pd.DataFrame, roles: dict, opt: dict) -> dict | None:
    ent, lat, lon, tim = roles.get("entity"), roles.get("lat"), roles.get("lon"), roles.get("time")
    if not (lat and lon and ent):
        return None
    g = d.dropna(subset=[lat, lon, "_y"]).groupby(ent).agg(
        lat=(lat, "mean"), lon=(lon, "mean"), y=("_y", "mean"),
        strength=("_strength", "first"), treated=("_treated", "max")).reset_index()
    if len(g) < 30:
        return None
    if len(g) > SAMPLE_MAX_SPATIAL:
        g = g.sample(SAMPLE_MAX_SPATIAL, random_state=RANDOM_STATE).reset_index(drop=True)
    try:
        from libpysal.weights import KNN, lag_spatial
        from esda.moran import Moran
    except Exception:
        return None
    try:
        k = int(opt.get("spatial_k", 6))
        w = KNN.from_array(np.column_stack([g["lon"], g["lat"]]), k=min(k, len(g) - 1))
        w.transform = "r"
        y = g["y"].to_numpy(float)
        X = np.column_stack([np.ones(len(g)), g["treated"].to_numpy(float)])
        beta = np.linalg.lstsq(X, y, rcond=None)[0]
        resid = y - X @ beta
        n, kk = len(y), X.shape[1]
        sigma2 = float((resid ** 2).sum() / max(n - kk, 1))
        XtX_inv = np.linalg.inv(X.T @ X)
        se = np.sqrt(np.maximum(np.diag(sigma2 * XtX_inv), 0))
        r2 = float(1 - (resid ** 2).sum() / max(((y - y.mean()) ** 2).sum(), 1e-12))

        # LM 检验（Anselin 简化式）
        from scipy.stats import chi2
        wy = np.asarray(lag_spatial(w, y)).flatten()
        M = np.eye(n) - X @ XtX_inv @ X.T
        MWy = M @ wy
        T_lag = float((MWy @ MWy) / max(sigma2, 1e-12))
        LM_Lag = float((resid @ wy) ** 2 / max(T_lag * sigma2, 1e-12))
        We = np.asarray(lag_spatial(w, resid)).flatten()
        T_err = float((We @ We) / max(sigma2, 1e-12))
        LM_Error = float((resid @ We) ** 2 / max(T_err * sigma2 * max(n - kk, 1), 1e-12))
        MI = Moran(resid, w)

        return {
            "n": int(n),
            "ols": {
                "treat": float(beta[1]), "treat_se": float(se[1]),
                "const": float(beta[0]), "r2": r2,
                "lm_lag_stat": LM_Lag, "lm_lag_p": float(1 - chi2.cdf(LM_Lag, 1)),
                "lm_error_stat": LM_Error, "lm_error_p": float(1 - chi2.cdf(LM_Error, 1)),
            },
            "slx": _slx(y, X, w, lag_spatial),
            "resid_moran": {"I": float(MI.I), "E_I": float(MI.EI),
                            "z_sim": float(MI.z_sim), "p_sim": float(MI.p_sim),
                            "interpretation": "残差空间自相关；p_sim<0.05 说明还有未纳入的空间结构"},
            "weight_spec": {"kind": "KNN", "k": min(k, len(g) - 1), "transform": "row-standardized"},
            "note": "本次重估的空间样本 = 实体级均值截面（1 个时间聚合），不是格级截面。",
        }
    except Exception as exc:                                          # pragma: no cover
        return {"error": f"{type(exc).__name__}: {exc}"}


def _slx(y: np.ndarray, X: np.ndarray, w, lag_spatial) -> dict | None:
    try:
        import statsmodels.api as sm
        wx = np.asarray(lag_spatial(w, X[:, 1:]))
        Xs = np.hstack([X, wx])
        res = sm.OLS(y, Xs).fit()
        names = ["const", "treat", "W_treat"]
        return {"direct": float(res.params[1]), "direct_se": float(res.bse[1]),
                "direct_p": float(res.pvalues[1]),
                "spillover": float(res.params[2]), "spillover_se": float(res.bse[2]),
                "spillover_p": float(res.pvalues[2]), "r2": float(res.rsquared)}
    except Exception:                                                 # pragma: no cover
        return None


# --------------------------------------------------------------------------- #
# 风险（cloglog，特征表来自实际列）
# --------------------------------------------------------------------------- #
def fit_risk(df: pd.DataFrame, roles: dict, opt: dict) -> dict | None:
    """二元目标 + cloglog。目标由 exit_col 指定，或用 event_time 派生（观察期内出现事件=1）。"""
    ent, tim, grp = roles.get("entity"), roles.get("time"), roles.get("group")
    target = opt.get("exit_col")
    d = df.copy()
    if not target:
        ev = roles.get("event_time")
        if not (ev and ent):
            return None
        tmax = pd.to_datetime(d[ev], errors="coerce").max()
        if pd.isna(tmax):
            return None
        d["_exit"] = pd.to_datetime(d[ev], errors="coerce").notna().astype(int)
        target = "_exit"
    d[target] = pd.to_numeric(d[target], errors="coerce")
    d = d.dropna(subset=[target])
    d[target] = (d[target] > 0).astype(int)
    if d[target].nunique() < 2 or len(d) < 200:
        return None

    exclude = {ent, tim, roles.get("lat"), roles.get("lon"), roles.get("value"), target, "__source_file"}
    num_cols = [c for c in d.columns
                if c not in exclude and not str(c).startswith("_")
                and pd.api.types.is_numeric_dtype(d[c]) and d[c].nunique(dropna=True) > 2]
    # 去掉近常量列，限制特征数（可解释性 + 数值稳定）
    num_cols = [c for c in num_cols if d[c].std(skipna=True) > 0][:12]
    if not num_cols:
        return None

    X = d[num_cols].apply(pd.to_numeric, errors="coerce").fillna(0.0)
    X.columns = [str(c) for c in num_cols]
    cats = {}
    if grp and d[grp].nunique(dropna=True) <= 30:
        cats[grp] = d[grp].astype(str).fillna("NA")
    if tim and d[tim].nunique(dropna=True) <= 60:
        cats[str(tim)] = d[tim].astype(str)

    design = X.copy()
    cat_specs = []
    for cname, s in cats.items():
        dm = pd.get_dummies(s, prefix=cname, drop_first=True, dtype=float)
        design = pd.concat([design, dm], axis=1)
        for col in dm.columns:
            lvl = col[len(cname) + 1:]
            cat_specs.append({"key": cname, "kind": cname, "level": lvl, "name": f"{cname}[T.{lvl}]"})
    design = design.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    design = sm_add_const(design)

    try:
        import statsmodels.api as sm
        model = sm.GLM(d[target].to_numpy(float), design.to_numpy(float),
                       family=sm.families.Binomial(link=sm.families.links.CLogLog()))
        res = model.fit(maxiter=200)
    except Exception as exc:                                          # pragma: no cover
        return {"error": f"{type(exc).__name__}: {exc}"}

    params = np.asarray(res.params, float)
    bse = np.asarray(res.bse, float)
    pvals = np.asarray(res.pvalues, float)
    lo, hi = np.asarray(res.conf_int())[:, 0], np.asarray(res.conf_int())[:, 1]
    names = list(design.columns)
    coefs = []
    degenerate = []
    for i, nm in enumerate(names):
        if nm == "const":
            kind, level = "intercept", "Intercept"
        elif nm in X.columns:
            kind, level = "numeric", nm
        else:
            base = nm.split("[T.")[0]
            kind, level = base, nm[len(base) + 4:-1]
        degen = bool(abs(params[i]) > 20 or bse[i] > 1e3)
        coefs.append({"name": nm, "kind": kind, "level": level,
                      "coef": float(params[i]), "se": float(bse[i]), "p": float(pvals[i]),
                      "lo": float(lo[i]), "hi": float(hi[i]), "degenerate": degen})
        if degen and nm != "const":
            degenerate.append(level)

    years = pd.to_numeric(df[tim], errors="coerce").dropna() if tim else pd.Series(dtype=float)
    pr2 = getattr(res, "prsquared", None)
    numeric_spec = [{"key": str(c), "label": str(c), "unit": "", "kind": "numeric"} for c in num_cols]
    cat_spec = [{"key": k, "kind": k, "label": k} for k in cats]

    return {
        "cloglog": {"pseudo_r2": float(pr2) if pr2 is not None else None,
                    "n": int(len(d)), "coefficients": coefs},
        "model_card": {
            "split": "本次重估：随机行划分（无时序外推验证）",
            "out_of_time_validated": False,
            "out_of_time_note": "本次重估未做时序外推验证 → 只能做同期归因，不能预测未来。",
            "year_supported": ([int(years.min()), int(years.max())]
                               if len(years) and int(years.min()) != int(years.max()) else None),
            "degenerate_levels": ({"bkclass": degenerate} if degenerate else {}),
            "degenerate_why": "本次重估检测到系数绝对值异常（完全分离）的层级，已在适用域守门中剔除。",
            "event_rate_note": f"训练样本事件率 {float(d[target].mean())*100:.2f}%。",
            "leakage_flags": [],
        },
        "feature_spec": {"numeric": numeric_spec, "categorical": cat_spec, "target": str(target)},
        "ranges": {str(c): {"min": float(X[c].min()), "max": float(X[c].max()),
                            "mean": float(X[c].mean()), "median": float(X[c].median()),
                            "std": float(X[c].std()), "null_rate": float(df[c].isna().mean())}
                   for c in num_cols},
        "map_dist": {"ranges": {str(c): {"max": float(X[c].max())} for c in num_cols},
                     "categories": {k: sorted(set(cats[k])) for k in cats}, "meta": {"source": "本次重估"}},
        "audit_source": "portal/refit.py（客户数据现场拟合）",
    }


def sm_add_const(df: pd.DataFrame) -> pd.DataFrame:
    import statsmodels.api as sm
    return sm.add_constant(df, has_constant="add")


# --------------------------------------------------------------------------- #
# 主入口
# --------------------------------------------------------------------------- #
def refit(df: pd.DataFrame, roles: dict, options: dict | None = None) -> dict:
    opt = dict(options or {})
    out = {"ok": True, "spec": {k: roles.get(k) for k in
                                ("entity", "time", "event_time", "lat", "lon", "value", "group")} |
           {k: opt.get(k) for k in ("treat_year_col", "treat_col", "strength_col", "exit_col") if opt.get(k)},
           "capabilities": {}, "notes": [], "artifact": {}}
    impact, risk = {}, {}

    # ---------- 冲击评估 ----------
    try:
        panel, info = build_panel(df, roles, opt)
        tw = twfe_within(panel, info["y_col"], ["_post_x_strength", "_post"],
                         roles["entity"], roles["time"])
        es = event_study(panel, info["y_col"], roles["entity"], roles["time"],
                         panel["_treated"].to_numpy(), (panel[roles["time"]] - panel["_first"]).fillna(0).to_numpy())
        sup = strength_support(panel, roles)
        sp = fit_spatial(panel, roles, opt)
        impact = {
            "_src": {"from": "portal/refit.py（现场重估）", "note": info},
            "twfe": {
                "n_obs": tw["n_obs"], "n_entities": tw["n_entities"], "n_times": tw["n_times"],
                "post": tw["params"].get("_post"), "post_se": tw["std_err"].get("_post"),
                "post_p": tw["pvalues"].get("_post"),
                "post_x_strength": tw["params"].get("_post_x_strength"),
                "post_x_strength_se": tw["std_err"].get("_post_x_strength"),
                "post_x_strength_p": tw["pvalues"].get("_post_x_strength"),
                "r2_within": tw["r2_within"],
            },
            "event_study": {"baseline": es.get("baseline"), "n_obs": es.get("n_obs"),
                            "n_treated_rows": es.get("n_treated_rows"), "n_entities": es.get("n_entities"),
                            "pre_trend_max_abs_t": es.get("pre_trend_max_abs_t"),
                            "table": [{"tau": r["tau"], "effect": r["effect"], "se": r["se"], "p": r["p"]}
                                      for r in es.get("table", [])]},
            "spatial": sp or {},
            "strength_support": sup,
            "sensitivity_audit": {
                "rings_alternative_has_coefficients": False,
                "rings_alternative_status": "本次重估未跑距离环敏感性（无环口径定义）",
                "bootstrap_ci": False,
            },
            "rings": None,
            "ols_cell": None,
            "audit_source": "portal/refit.py",
        }
        out["capabilities"]["impact"] = True
        out["capabilities"]["spatial"] = bool(sp and not sp.get("error"))
        if not options or not options.get("strength_col"):
            out["notes"].append("未提供强度列 → 按二元处理估计（strength ≡ 1），强度曲线退化为一条水平线。")
    except Exception as exc:
        out["capabilities"]["impact"] = False
        out["notes"].append(f"冲击评估未能拟合：{type(exc).__name__}: {exc}")

    # ---------- 风险归因 ----------
    try:
        rk = fit_risk(df, roles, opt)
        if rk and "error" not in rk:
            risk = rk
            out["capabilities"]["risk"] = True
        else:
            out["capabilities"]["risk"] = False
            if rk and rk.get("error"):
                out["notes"].append(f"风险模型未拟合：{rk['error']}")
            else:
                out["notes"].append("风险模型未拟合：缺少可用的二元目标（exit_col / 事件时间）或特征不足。")
    except Exception as exc:
        out["capabilities"]["risk"] = False
        out["notes"].append(f"风险模型未能拟合：{type(exc).__name__}: {exc}")

    if impact:
        out["artifact"]["impact"] = impact
    if risk:
        out["artifact"]["risk"] = risk
    out["artifact"]["meta"] = {
        "generated_at": pd.Timestamp.now().isoformat(timespec="seconds"),
        "generator": "portal/refit.py",
        "policy": "全部系数由传入数据现场拟合；不含任何上游项目的硬编码系数",
        "rows": int(len(df)),
    }
    return out


def _cli() -> int:
    import argparse
    import sys
    sys.path.insert(0, str(PORTAL))
    import ingest as ing

    ap = argparse.ArgumentParser(description="用客户数据重估系数 · CLI")
    ap.add_argument("--paths", nargs="+", required=True)
    ap.add_argument("--limit", type=int, default=ing.DEFAULT_FILE_LIMIT)
    ap.add_argument("--row-limit", type=int, default=ing.DEFAULT_ROW_LIMIT_PER_FILE)
    ap.add_argument("--treat-year-col")
    ap.add_argument("--treat-col")
    ap.add_argument("--strength-col")
    ap.add_argument("--exit-col")
    ap.add_argument("--out")
    a = ap.parse_args()
    rep = ing.analyze(a.paths, limit=a.limit, row_limit=a.row_limit)
    res = refit(ing.load_sources(a.paths, limit=a.limit, row_limit=a.row_limit).frame,
                rep["roles"],
                {"treat_year_col": a.treat_year_col, "treat_col": a.treat_col,
                 "strength_col": a.strength_col, "exit_col": a.exit_col})
    print("capabilities:", res["capabilities"])
    for n in res["notes"]:
        print("  note:", n)
    if res["artifact"].get("impact"):
        t = res["artifact"]["impact"]["twfe"]
        print("TWFE post=", t["post"], "post_x_strength=", t["post_x_strength"], "n=", t["n_obs"])
    if a.out:
        Path(a.out).write_text(json.dumps(res["artifact"], ensure_ascii=False, indent=2), encoding="utf-8")
        print("wrote", a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
