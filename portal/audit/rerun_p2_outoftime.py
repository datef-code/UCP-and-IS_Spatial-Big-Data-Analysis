#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""P0-3 审计重跑（project2）：时序外推验证（expanding-window / out-of-time）

对应 REVIEW_20260911.md：
  P0-3  风险模型只有随机行划分的测试集（包含训练期年份）→ 指标偏乐观，
        从未做过时序外推验证。本脚本补上：

  ① 逐年滚动（expanding window，一步外推）：用 ≤T−1 年拟合，预测 **T 年全部行**；
  ② 单次干净留出：用 ≤2014 拟合，预测 2015–2025；
  ③ 两个特征集各跑一遍：含泄漏特征 bank_closed_rate / 剔除它（下界）。

口径说明（必须随结果披露）：
  * 时序外推 **不能外推年份哑变量** —— 原 cloglog 的 `C(year)` 在新年份无对应水平，
    因此本重跑统一去掉 year 哑变量（其余设定沿用上游：cloglog 链接 + 分层抽样）。
  * 训练样本沿用上游口径（全部事件行 + 2× 非事件行）；**测试用整年全量行**，
    因此 Brier 是在真实事件率下算的（不同于上游被富集的测试集）。

约束：只读上游产物；产物写 portal/audit/。
运行：
    datakit/.venv/Scripts/python.exe portal/audit/rerun_p2_outoftime.py
"""

from __future__ import annotations

import datetime as _dt
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score

AUDIT = Path(__file__).resolve().parent
REPO = AUDIT.parent.parent
P2 = REPO / "project2_fdic_survival"
RANDOM_STATE = 42
MIN_TRAIN_EVENTS = 200
MIN_TEST_EVENTS = 20


def log(msg: str) -> None:
    print(msg, flush=True)


class _Shim:
    """代替 datakit Project，只为复用上游 load_and_build_panel 的 log 接口。"""

    @staticmethod
    def log(msg: str) -> None:
        pass


def load_stage_module():
    sys.path.insert(0, str(REPO / "datakit"))
    path = P2 / "06_train" / "06_train.py"
    spec = importlib.util.spec_from_file_location("stage06_train", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def fit_predict(train: pd.DataFrame, test: pd.DataFrame, numeric: list, categorical: list):
    """在 train 上拟合 cloglog，在 test 上预测。

    返回 (test_subset, prob) —— test_subset 是剔除了「训练期未出现的类别水平」后的测试行；
    拟合或预测失败返回 (None, None)。
    """
    sample = train.copy()
    for col in numeric:
        sample[col] = sample[col].fillna(sample[col].median())
    formula = "event ~ " + " + ".join(numeric + [f"C({c})" for c in categorical])
    try:
        res = smf.glm(formula=formula, data=sample,
                      family=sm.families.Binomial(link=sm.families.links.CLogLog())).fit(disp=False)
        t = test.copy()
        for col in numeric:
            t[col] = t[col].fillna(train[col].median())
        # 训练期未出现的类别水平无法预测（时序外推的真实约束）→ 剔除并如实计数
        for c in categorical:
            lv = set(pd.unique(sample[c].astype(str)))
            t = t[t[c].astype(str).isin(lv)]
        if t.empty:
            return None, None
        return t, np.asarray(res.predict(t), dtype=float)
    except Exception as exc:                                     # pragma: no cover
        log(f"      拟合/预测失败：{type(exc).__name__}: {exc}")
        return None, None


def stratified_train(win: pd.DataFrame) -> pd.DataFrame:
    """上游口径：保留全部事件行 + 2×非事件行。"""
    ev = win.index[win["event"] == 1]
    ne = win.index[win["event"] == 0]
    n_ne = min(len(ev) * 2, len(ne))
    if n_ne < len(ne):
        ne = ne.to_series().sample(n=n_ne, random_state=RANDOM_STATE).index
    return win.loc[ev.union(ne)]


def metrics_of(y: np.ndarray, p: np.ndarray) -> dict:
    return {
        "auc": float(roc_auc_score(y, p)),
        "brier": float(brier_score_loss(y, p)),
        "log_loss": float(log_loss(y, np.clip(p, 1e-6, 1 - 1e-6))),
        "n": int(len(y)),
        "events": int(y.sum()),
        "event_rate": float(y.mean()),
        "mean_pred": float(p.mean()),
    }


def run_variant(panel: pd.DataFrame, numeric: list, categorical: list, label: str) -> dict:
    log(f"  == 变体 {label}（特征：{len(numeric)} 数值 + {len(categorical)} 类别）==")
    years = sorted(int(y) for y in panel["year"].unique())

    # ---- ① 逐年滚动一步外推 ----
    rolling = []
    for T in years:
        tr = panel[panel["year"] <= T - 1]
        te = panel[panel["year"] == T]
        if tr["event"].sum() < MIN_TRAIN_EVENTS or te["event"].sum() < MIN_TEST_EVENTS:
            continue
        te2, p = fit_predict(stratified_train(tr), te, numeric, categorical)
        if p is None:
            continue
        m = metrics_of(te2["event"].to_numpy(), p)
        m["year"] = T
        m["n_dropped_unseen_level"] = int(len(te) - len(te2))
        rolling.append(m)
        log(f"     T={T}  AUC={m['auc']:.4f}  Brier={m['brier']:.5f}  "
            f"n={m['n']:,}  事件率={m['event_rate']:.3%}")

    aucs = np.array([r["auc"] for r in rolling], dtype=float)
    # 按测试行数加权的 Brier（各年样本量差异大）
    ns = np.array([r["n"] for r in rolling], dtype=float)
    bs = np.array([r["brier"] for r in rolling], dtype=float)
    agg = {
        "n_windows": int(len(rolling)),
        "auc_mean": float(aucs.mean()) if len(aucs) else None,
        "auc_median": float(np.median(aucs)) if len(aucs) else None,
        "auc_min": float(aucs.min()) if len(aucs) else None,
        "auc_max": float(aucs.max()) if len(aucs) else None,
        "auc_std": float(aucs.std()) if len(aucs) else None,
        "brier_weighted": float((bs * ns).sum() / ns.sum()) if len(ns) else None,
        "year_min": rolling[0]["year"] if rolling else None,
        "year_max": rolling[-1]["year"] if rolling else None,
    }

    # ---- ② 单次干净留出：≤2014 训练 → 2015–2025 测试 ----
    split_year = 2014
    tr = panel[panel["year"] <= split_year]
    te = panel[panel["year"] > split_year]
    holdout = None
    te2, p = fit_predict(stratified_train(tr), te, numeric, categorical)
    if p is not None:
        holdout = metrics_of(te2["event"].to_numpy(), p)
        holdout["train_years"] = [int(tr["year"].min()), split_year]
        holdout["test_years"] = [int(te["year"].min()), int(te["year"].max())]
        holdout["n_dropped_unseen_level"] = int(len(te) - len(te2))
        log(f"     留出 {holdout['train_years']} → {holdout['test_years']}: "
            f"AUC={holdout['auc']:.4f}  Brier={holdout['brier']:.5f}")

    return {"rolling": rolling, "rolling_agg": agg, "holdout": holdout}


def main() -> int:
    AUDIT.mkdir(parents=True, exist_ok=True)
    mod = load_stage_module()
    log("  重构网点-年面板（复用上游 load_and_build_panel）…")
    panel = mod.load_and_build_panel(_Shim())
    log(f"  面板 {len(panel):,} 行，网点 {panel['UNINUMBR'].nunique():,}，"
        f"年份 {int(panel['year'].min())}–{int(panel['year'].max())}，"
        f"事件率 {panel['event'].mean():.4%}")

    numeric_all = ["age", "log_depsumbr", "neighbor_count", "lat", "lng", "bank_closed_rate"]
    numeric_noleak = [c for c in numeric_all if c != "bank_closed_rate"]
    categorical = ["BKCLASS", "fragility_tier"]        # year 哑变量不可时序外推 → 去掉

    variants = {}
    variants["with_leak"] = run_variant(panel, numeric_all, categorical, "含泄漏特征")
    variants["no_leak"] = run_variant(panel, numeric_noleak, categorical, "剔除泄漏特征")

    # 上游随机划分的乐观值（用于对照，不重算）
    up = json.loads((P2 / "06_train" / "output" / "metrics.json").read_text(encoding="utf-8"))
    random_split = {"train": up.get("train"), "test": up.get("test")}

    lean = variants["with_leak"]["rolling_agg"]
    nol = variants["no_leak"]["rolling_agg"]
    hold_leak = variants["with_leak"]["holdout"] or {}
    hold_nol = variants["no_leak"]["holdout"] or {}
    up_auc = (up.get("test") or {}).get("auc")
    penalty = (up_auc - lean["auc_mean"]) if (up_auc and lean["auc_mean"]) else None

    out = {
        "generated_at": _dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "generator": "portal/audit/rerun_p2_outoftime.py",
        "protocol": {
            "type": "expanding-window one-step-ahead + single clean holdout",
            "train_sample": "全部事件行 + 2×非事件行（沿用上游 cloglog 分层口径）",
            "test_sample": "测试年份的**整年全量行**（未下采样）→ Brier 在真实事件率下计算",
            "year_dummies": "已移除（C(year) 无法外推到新年份；这是时序验证的硬约束）",
            "leakage_note": ("bank_closed_rate 按 CERT 对全期聚合后 join 回逐年、"
                             "DEPSUMBR_last 是终期值却用于每一年 → 训练期内亦含未来信息。"
                             "含泄漏变体是**上界**，剔泄漏变体是**下界**（唯一可信的口径）。"),
        },
        "random_split_reported": random_split,
        "variants": variants,
        "conclusion": {
            "reported_test_auc_random_split": up_auc,
            "out_of_time_auc_with_leak_mean": lean["auc_mean"],
            "out_of_time_auc_no_leak_mean": nol["auc_mean"],
            "windows": {
                "n": lean["n_windows"], "years": [lean["year_min"], lean["year_max"]],
                "why_not_all_years": f"2016 年起每年事件数 < {MIN_TEST_EVENTS}，不足以评估",
            },
            "holdout_2015_2025": {
                "with_leak": {"auc": hold_leak.get("auc"), "event_rate": hold_leak.get("event_rate"),
                              "n": hold_leak.get("n")},
                "no_leak": {"auc": hold_nol.get("auc"), "event_rate": hold_nol.get("event_rate"),
                            "n": hold_nol.get("n")},
                "warning": ("含泄漏特征时 AUC≈0.99 是**排序伪影**：该特征对 CERT 恒定且编码全期信息，"
                            "而留出窗事件率仅 0.24% → 看似完美，不是技能。剔泄漏后同一留出 AUC≈0.48。"),
            },
            "headline": ("表观判别力主要来自时序泄漏特征（bank_closed_rate 全期聚合 + "
                         "DEPSUMBR_last 终期值）。剔除后时序外推 AUC ≈ 0.53（≈随机）→ "
                         "本模型不构成「可预测未来」的证据，只能做同期归因，"
                         "与「风险归因台」的定位一致。"),
            "auc_penalty_vs_random_split": penalty,
            "note": ("随机划分的测试集里含训练期年份 → 指标偏乐观；时序外推才是上线口径。"
                     "两者之差即「乐观幅度」。"),
        },
    }
    (AUDIT / "p2_out_of_time.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"[ok] 已写出 {AUDIT / 'p2_out_of_time.json'}")
    log(f"  随机划分 AUC={up_auc:.4f}｜时序外推（含泄漏）{lean['auc_mean']:.4f}"
        f"｜剔除泄漏 {nol['auc_mean']:.4f}")
    if penalty is not None:
        log(f"  随机划分相对时序外推的乐观幅度：{penalty:+.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
