# -*- coding: utf-8 -*-
"""06_train —— ⑥ 训练 / 估计（扩展阶段，规范 §8）。

入口文件与目录同名（``06_train.py``），必须暴露 ``run(project) -> dict``。
**只读**上游 ``05_map/output/data/{branch_panel.csv, bank_fragility.csv}``，
产物只进本阶段 ``output/``；失败不阻断五阶段（``blocking: false``）。

做什么：

* 重构「网点-年」长表（向量化展开），剔除事件早于首次观测的网点（左截断）；
* **离散时间 logit 风险模型**（SGD，稀疏 one-hot + 分层抽样）→ AUC / C-index / Brier；
* **cloglog 风险模型**（statsmodels GLM）→ 系数 + 95% CI（风险比方向的机制解释）；
* **SHAP**（LinearExplainer，变换后特征空间）→ 逐样本值 + 聚合重要性；
* **残差空间自相关** Moran's I（k 近邻 + 置换检验，不构造 n×n 稠密矩阵）。

必交产物（规范 §8.5）：``metrics.json`` + ``replication_manifest.json``（版本 / 参数 /
随机种子 / 输入指纹）—— 没有 manifest = 不可复现 = 不算产出。
"""
from __future__ import annotations

import datetime as _dt
import json
import pickle
import platform
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import scipy.stats as st
from scipy.spatial import cKDTree
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import SGDClassifier
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
import statsmodels.api as sm
import statsmodels.formula.api as smf

import datakit as dk

STAGE = "06_train"
TITLE = "⑥ 训练（离散时间 logit / cloglog + SHAP + 残差 Moran's I）"

ROOT = Path(__file__).resolve().parent.parent
OUT = Path(__file__).resolve().parent / "output"
DATA = OUT / "data"
IN_MAP = ROOT / "05_map" / "output" / "data"      # 只读 ⑤ 的交付数据

RANDOM_STATE = 42
MAX_TOTAL = 500_000          # logit 分层抽样上限（保留全部事件行）
SHAP_SAMPLE_N = 2000
MORAN_K = 8
MORAN_N_PERM = 199

warnings.filterwarnings("ignore", category=FutureWarning)


# --------------------------------------------------------------------------- #
# 1. 面板重构
# --------------------------------------------------------------------------- #
def load_and_build_panel(project) -> pd.DataFrame:
    """网点维度表 + 银行脆弱性 →「网点-年」长表（向量化展开）。"""
    branch = pd.read_csv(IN_MAP / "branch_panel.csv", low_memory=False)
    bank = pd.read_csv(IN_MAP / "bank_fragility.csv", low_memory=False)

    keep = ["CERT", "n_branches", "n_closed", "fragility_tier", "bank_closed_rate"]
    branch = branch.merge(bank[[c for c in keep if c in bank.columns]], on="CERT", how="left")

    # 出生年缺失 → 用首次观测年代理
    branch["est_year"] = branch["est_year"].fillna(branch["first_year"]).astype(int)
    branch["first_year"] = branch["first_year"].astype(int)
    branch["obs_end"] = branch["obs_end"].fillna(
        branch["acq_year"].fillna(branch["last_year"])).astype(int)

    # 事件早于首次观测 → 不在风险集内，剔除（左截断样本）
    before_window = branch["acq_year"].notna() & (branch["acq_year"] < branch["first_year"])
    n_drop = int(before_window.sum())
    if n_drop:
        project.log(f"    [⑥] 剔除事件早于首次观测的网点：{n_drop:,}")
    branch = branch[~before_window].copy()

    branch["span"] = (branch["obs_end"] - branch["first_year"] + 1).clip(lower=1).astype(int)

    # 向量化展开：每条网点-年一行
    panel = branch.loc[branch.index.repeat(branch["span"])].copy()
    panel["year"] = panel.groupby(level=0).cumcount() + panel["first_year"].to_numpy()
    panel["age"] = panel["year"] - panel["est_year"].to_numpy()
    panel["event"] = ((panel["event"] == "closed") & (panel["year"] == panel["acq_year"])).astype(int)
    panel["right_censored"] = ((panel["right_censored"] == 1)
                               & (panel["year"] == panel["obs_end"])
                               & (panel["event"] == 0)).astype(int)

    # 特征工程
    panel["log_depsumbr"] = np.log1p(panel["DEPSUMBR_last"])
    panel["neighbor_count"] = panel["neighbor_count"].fillna(0).astype(int)
    panel["BKCLASS"] = panel["BKCLASS"].fillna("MISSING").astype("category")
    panel["fragility_tier"] = panel["fragility_tier"].fillna("L0_单网点").astype("category")
    panel["n_branches"] = panel["n_branches"].fillna(1).astype(int)
    panel["bank_closed_rate"] = panel["bank_closed_rate"].fillna(0.0)
    panel["year"] = panel["year"].astype(int)

    panel = panel[[
        "UNINUMBR", "CERT", "year", "age", "event", "right_censored", "left_truncated",
        "log_depsumbr", "neighbor_count", "lat", "lng",
        "BKCLASS", "fragility_tier", "n_branches", "bank_closed_rate",
    ]].reset_index(drop=True)
    return panel


def feature_columns() -> tuple[list[str], list[str], list[str]]:
    """返回 (数值列, 类别列, 全部特征列)。"""
    numeric = ["age", "log_depsumbr", "neighbor_count", "lat", "lng", "bank_closed_rate"]
    categorical = ["year", "BKCLASS", "fragility_tier"]
    return numeric, categorical, numeric + categorical


# --------------------------------------------------------------------------- #
# 2. 离散时间 logit（SGD）
# --------------------------------------------------------------------------- #
def build_logit_pipeline(numeric: list[str], categorical: list[str]) -> Pipeline:
    # StandardScaler(with_mean=False) 保持稀疏矩阵，避免 densify 导致内存爆炸
    preprocessor = ColumnTransformer(
        transformers=[
            ("num", Pipeline([("imputer", SimpleImputer(strategy="median")),
                              ("scaler", StandardScaler(with_mean=False))]), numeric),
            ("cat", OneHotEncoder(drop="first", sparse_output=True, handle_unknown="ignore"), categorical),
        ],
        remainder="drop",
        sparse_threshold=0.3,
    )
    return Pipeline([
        ("prep", preprocessor),
        ("clf", SGDClassifier(
            loss="log_loss", penalty="l2", alpha=1e-4, class_weight="balanced",
            max_iter=500, tol=1e-3, random_state=RANDOM_STATE, n_jobs=-1, verbose=0,
        )),
    ])


class _Fenwick:
    """树状数组，支持 O(log n) 前缀计数。"""

    def __init__(self, n: int):
        self.n = n
        self.bit = [0] * (n + 1)

    def add(self, i: int, v: int = 1) -> None:
        i += 1
        bit, n = self.bit, self.n
        while i <= n:
            bit[i] += v
            i += i & -i

    def sum(self, i: int) -> int:
        s = 0
        bit = self.bit
        while i > 0:
            s += bit[i]
            i -= i & -i
        return s


def harrell_c_index(
    pred_risk: np.ndarray,
    durations: np.ndarray,
    events: np.ndarray,
    max_n: int = 120_000,
    seed: int = 0,
) -> float:
    """Harrell's C-index，O(n log n) 实现（Fenwick 树，不再 O(n²)）。"""
    valid = ~(np.isnan(pred_risk) | np.isnan(durations) | np.isnan(events))
    pred_risk, durations, events = pred_risk[valid], durations[valid], events[valid].astype(bool)
    n = len(durations)
    if n == 0 or events.sum() == 0:
        return float("nan")

    if n > max_n:
        rng = np.random.default_rng(seed)
        idx = rng.choice(n, size=max_n, replace=False)
        pred_risk, durations, events = pred_risk[idx], durations[idx], events[idx]
        n = max_n
        if events.sum() == 0:
            return float("nan")

    risk_rank = (st.rankdata(pred_risk, method="min") - 1).astype(int)
    order = np.argsort(durations, kind="mergesort")[::-1]
    fenw = _Fenwick(n)
    conc = 0.0
    total = 0
    i = 0
    while i < n:
        t = durations[order[i]]
        j = i
        while j < n and durations[order[j]] == t:
            j += 1
        grp = order[i:j]
        for ii in grp:                       # 与「更晚存活」的已插入样本比较
            if events[ii]:
                total += fenw.sum(n)
                conc += fenw.sum(int(risk_rank[ii]))
        for ii in grp:
            fenw.add(int(risk_rank[ii]))
        i = j
    return conc / total if total else float("nan")


def eval_survival(y_true: np.ndarray, prob: np.ndarray,
                  durations: np.ndarray, events: np.ndarray) -> dict:
    """离线指标：AUC / Brier / log-loss / C-index / 事件率。"""
    return {
        "auc": float(roc_auc_score(y_true, prob)),
        "brier": float(brier_score_loss(y_true, prob)),
        "log_loss": float(log_loss(y_true, prob, labels=[0, 1])),
        "c_index": float(harrell_c_index(prob, durations, events)),
        "event_rate": float(y_true.mean()),
        "n": int(len(y_true)),
    }


def fit_logit(panel: pd.DataFrame, project) -> tuple[Pipeline, dict]:
    project.log("    [⑥] 训练离散时间 logit（SGD，稀疏 one-hot）")
    numeric, categorical, _ = feature_columns()
    X = panel[numeric + categorical].copy()
    y = panel["event"].to_numpy()
    durations = panel["age"].to_numpy(dtype=float)      # duration 代理
    events = panel["event"].to_numpy()

    if len(X) > MAX_TOTAL:
        event_idx = np.where(y == 1)[0]
        nonevent_idx = np.where(y == 0)[0]
        rng = np.random.default_rng(RANDOM_STATE)
        n_nonevent = min(MAX_TOTAL - len(event_idx), len(nonevent_idx))
        keep = np.concatenate([event_idx,
                               rng.choice(nonevent_idx, size=n_nonevent, replace=False)])
        X, y = X.iloc[keep].copy(), y[keep]
        durations, events = durations[keep], events[keep]
        project.log(f"      分层抽样至 {len(X):,} 条观测（保留全部事件行）")

    X_train, X_test, y_train, y_test, d_train, d_test, e_train, e_test = train_test_split(
        X, y, durations, events, test_size=0.2, stratify=y, random_state=RANDOM_STATE)
    project.log(f"      训练 {len(X_train):,} / 测试 {len(X_test):,}，事件率 {y.mean():.2%}")

    pipe = build_logit_pipeline(numeric, categorical)
    pipe.fit(X_train, y_train)
    prob_train = pipe.predict_proba(X_train)[:, 1]
    prob_test = pipe.predict_proba(X_test)[:, 1]

    metrics = {
        "model": "logit_discrete_time",
        "train": eval_survival(y_train, prob_train, d_train, e_train),
        "test": eval_survival(y_test, prob_test, d_test, e_test),
    }
    project.log(f"      测试 AUC={metrics['test']['auc']:.4f}，C-index={metrics['test']['c_index']:.4f}，"
                f"Brier={metrics['test']['brier']:.4f}")

    with open(OUT / "logit_pipeline.pkl", "wb") as f:
        pickle.dump(pipe, f)

    prep, clf = pipe.named_steps["prep"], pipe.named_steps["clf"]
    feature_names = list(prep.named_transformers_["num"].get_feature_names_out(numeric)) + \
                    list(prep.named_transformers_["cat"].get_feature_names_out(categorical))
    coef_df = pd.DataFrame({"feature": feature_names, "coef": clf.coef_[0],
                            "abs_coef": np.abs(clf.coef_[0])})
    coef_df.sort_values("abs_coef", ascending=False).to_csv(OUT / "logit_coefficients.csv", index=False)

    test_pred = X_test.copy()
    test_pred["risk"] = prob_test
    test_pred["event"] = y_test
    test_pred.to_csv(OUT / "test_predictions.csv", index=False)
    return pipe, metrics


# --------------------------------------------------------------------------- #
# 3. cloglog（statsmodels GLM）
# --------------------------------------------------------------------------- #
def fit_cloglog(panel: pd.DataFrame, project):
    project.log("    [⑥] 拟合 cloglog 风险模型（statsmodels GLM）")
    event_idx = panel.index[panel["event"] == 1]
    nonevent_pool = panel.index[panel["event"] == 0]
    n_nonevent = min(len(event_idx) * 2, len(nonevent_pool))
    nonevent_idx = nonevent_pool.to_series().sample(n=n_nonevent, random_state=RANDOM_STATE).index
    sample = panel.loc[event_idx.union(nonevent_idx)].copy()
    project.log(f"      分层样本 {len(sample):,} 条（事件 {int(sample['event'].sum()):,}）")

    numeric, categorical, _ = feature_columns()
    for col in numeric:
        sample[col] = sample[col].fillna(sample[col].median())
    formula = "event ~ " + " + ".join(numeric + [f"C({c})" for c in categorical])
    try:
        model = smf.glm(formula=formula, data=sample,
                        family=sm.families.Binomial(link=sm.families.links.CLogLog()))
        result = model.fit(disp=False)
    except Exception as exc:                     # pragma: no cover
        project.log(f"      cloglog 拟合失败：{exc}")
        return None

    summary = result.summary2().tables[1].reset_index()
    summary.to_csv(OUT / "cloglog_coefficients.csv", index=False)
    (OUT / "cloglog_summary.txt").write_text(str(result.summary()), encoding="utf-8")

    sig = result.params[result.pvalues < 0.05]
    stats = {
        "pseudo_r2_mcfadden": float(result.pseudo_rsquared()),
        "aic": float(result.aic),
        "n": int(len(sample)),
        "n_events": int(sample["event"].sum()),
        "significant_positive": int((sig > 0).sum()),
        "significant_negative": int((sig < 0).sum()),
    }
    project.log(f"      McFadden 伪 R²={stats['pseudo_r2_mcfadden']:.4f}；"
                f"显著正/负因子 {stats['significant_positive']}/{stats['significant_negative']}")
    return stats


# --------------------------------------------------------------------------- #
# 4. SHAP
# --------------------------------------------------------------------------- #
def compute_shap(pipe: Pipeline, panel: pd.DataFrame, project) -> dict | None:
    project.log("    [⑥] SHAP 可解释性（LinearExplainer，变换后特征空间）")
    try:
        import shap
    except ImportError:                          # pragma: no cover
        project.log("      shap 未安装，跳过（uv pip install shap）")
        return None

    numeric, categorical, _ = feature_columns()
    X = panel[numeric + categorical].copy()
    prep, clf = pipe.named_steps["prep"], pipe.named_steps["clf"]
    Z = prep.transform(X)
    feature_names = list(prep.named_transformers_["num"].get_feature_names_out(numeric)) + \
                    list(prep.named_transformers_["cat"].get_feature_names_out(categorical))

    rng = np.random.default_rng(RANDOM_STATE)
    idx = rng.choice(Z.shape[0], size=min(SHAP_SAMPLE_N, Z.shape[0]), replace=False)
    bg_idx = rng.choice(Z.shape[0], size=min(200, Z.shape[0]), replace=False)
    Z_sample = np.asarray(Z[idx].todense())
    Z_bg = np.asarray(Z[bg_idx].todense())

    explainer = shap.LinearExplainer(clf, Z_bg)
    shap_values = explainer.shap_values(Z_sample)
    if isinstance(shap_values, list):
        shap_values = shap_values[1]

    pd.DataFrame(shap_values, columns=feature_names).to_csv(OUT / "shap_values.csv", index=False)
    importance = pd.DataFrame({"feature": feature_names,
                               "mean_abs_shap": np.abs(shap_values).mean(axis=0)})

    aggregated = []
    for col in numeric:
        aggregated.append({"feature": col,
                           "mean_abs_shap": float(importance.loc[importance["feature"] == col,
                                                                 "mean_abs_shap"].sum())})
    for col in categorical:
        agg = float(importance.loc[importance["feature"].str.startswith(f"{col}_"),
                                   "mean_abs_shap"].sum())
        aggregated.append({"feature": col, "mean_abs_shap": agg})
    agg_importance = pd.DataFrame(aggregated).sort_values("mean_abs_shap", ascending=False)
    agg_importance.to_csv(OUT / "shap_importance.csv", index=False)
    project.log(f"      最重要特征：{agg_importance.iloc[0]['feature']}"
                f"（{agg_importance.iloc[0]['mean_abs_shap']:.4f}）")
    return {"top_feature": str(agg_importance.iloc[0]["feature"]),
            "ranking": agg_importance.to_dict("records")}


# --------------------------------------------------------------------------- #
# 5. 残差空间自相关（Moran's I）
# --------------------------------------------------------------------------- #
def _moran_from_z(z: np.ndarray, neighbors: np.ndarray) -> float:
    if len(z) < 3 or np.allclose(z, 0):
        return np.nan
    nb_sum = z[neighbors].sum(axis=1) / neighbors.shape[1]
    denominator = float((z * z).sum())
    if denominator <= 0:
        return np.nan
    return float((z * nb_sum).sum() / denominator)


def morans_i(residuals: np.ndarray, coords: np.ndarray,
             k: int = MORAN_K, n_perm: int = MORAN_N_PERM, seed: int = 0) -> dict:
    """k 近邻 + 行标准化权重的 Moran's I，条件置换检验给 p 值（不构造 n×n 稠密矩阵）。"""
    mask = ~np.isnan(coords).any(axis=1)
    z = residuals[mask].astype(float)
    xy = coords[mask].astype(float)
    n = len(z)
    if n < k + 2:
        return {"moran_i": None, "p_value": None, "n": n}
    kk = min(k, n - 1)
    tree = cKDTree(xy)
    _, idx = tree.query(xy, k=kk + 1)
    neighbors = idx[:, 1:]
    z_c = z - z.mean()

    observed = _moran_from_z(z_c, neighbors)
    if np.isnan(observed):
        return {"moran_i": None, "p_value": None, "n": n}
    rng = np.random.default_rng(seed)
    count = 0
    for _ in range(n_perm):
        if observed <= _moran_from_z(z_c[rng.permutation(n)], neighbors):
            count += 1
    return {
        "moran_i": float(observed),
        "p_value": float((count + 1) / (n_perm + 1)),
        "n": int(n),
        "k_neighbors": int(kk),
        "permutations": int(n_perm),
    }


def spatial_residual_check(panel: pd.DataFrame, pipe: Pipeline, project) -> dict:
    project.log("    [⑥] 残差空间自相关（Moran's I，k 近邻 + 置换检验）")
    event_idx = panel.index[panel["event"] == 1]
    nonevent_pool = panel.index[panel["event"] == 0]
    n_nonevent = min(len(event_idx) * 4, len(nonevent_pool))
    nonevent_idx = nonevent_pool.to_series().sample(n=n_nonevent, random_state=RANDOM_STATE).index
    sample = panel.loc[event_idx.union(nonevent_idx)].copy()

    numeric, categorical, _ = feature_columns()
    X = sample[numeric + categorical].copy()
    y = sample["event"].to_numpy()
    prob = pipe.predict_proba(X)[:, 1]
    residuals = y - prob
    coords = sample[["lat", "lng"]].to_numpy(dtype=float)

    result = morans_i(residuals, coords)
    (OUT / "moran_i.json").write_text(json.dumps(result, ensure_ascii=False, indent=2),
                                      encoding="utf-8")
    project.log(f"      Moran's I={result['moran_i']:.4f}，p={result['p_value']:.3g}，n={result['n']:,}")
    return result


# --------------------------------------------------------------------------- #
# 报告
# --------------------------------------------------------------------------- #
def _file_fingerprint(p: Path) -> dict:
    st_ = p.stat()
    return {"file": p.name, "size": int(st_.st_size),
            "mtime": _dt.datetime.fromtimestamp(st_.st_mtime).isoformat(timespec="seconds")}


def write_replication_manifest(panel: pd.DataFrame, metrics: dict, project) -> dict:
    """规范 §8.5：版本 / 参数 / 随机种子 / 输入指纹。"""
    import matplotlib
    import scipy
    import sklearn
    import statsmodels

    manifest = {
        "project": project.name,
        "stage": STAGE,
        "generated_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "pandas": pd.__version__, "numpy": np.__version__, "scipy": scipy.__version__,
            "scikit-learn": sklearn.__version__, "statsmodels": statsmodels.__version__,
            "matplotlib": matplotlib.__version__,
        },
        "params": {
            "random_state": RANDOM_STATE,
            "max_total_sample": MAX_TOTAL,
            "shap_sample_n": SHAP_SAMPLE_N,
            "moran_k": MORAN_K, "moran_n_perm": MORAN_N_PERM,
            "c_index_max_n": 120_000,
            "duration_proxy": "age（year − est_year）",
        },
        "features": {"numeric": feature_columns()[0], "categorical": feature_columns()[1]},
        "inputs": [_file_fingerprint(IN_MAP / "branch_panel.csv"),
                   _file_fingerprint(IN_MAP / "bank_fragility.csv")],
        "panel": {"rows": int(len(panel)), "branches": int(panel["UNINUMBR"].nunique()),
                  "event_rate": float(panel["event"].mean()),
                  "year_range": [int(panel["year"].min()), int(panel["year"].max())]},
        "test_metrics": metrics["test"],
        "commands": {
            "end_to_end": "python main.py",
            "stage_06": "python main.py --stage 06",
        },
    }
    (OUT / "replication_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def _md_report(metrics: dict, cloglog_stats, shap_info, moran, panel: pd.DataFrame) -> str:
    t = metrics["test"]
    lines = [
        "# ⑥ 训练报告 · 离散时间生存模型", "",
        f"- 面板：{len(panel):,} 网点-年观测（{int(panel['UNINUMBR'].nunique()):,} 网点），"
        f"事件率 {panel['event'].mean():.2%}",
        "",
        "## 离线指标（测试集）", "",
        "| 指标 | 值 |", "| --- | --- |",
        f"| AUC | {t['auc']:.4f} |",
        f"| C-index | {t['c_index']:.4f} |",
        f"| Brier | {t['brier']:.4f} |",
        f"| log-loss | {t['log_loss']:.4f} |",
        f"| 事件率 | {t['event_rate']:.2%}（n={t['n']:,}） |",
        "",
        "## cloglog（机制解释）", "",
    ]
    if cloglog_stats:
        lines += [f"- McFadden 伪 R²：{cloglog_stats['pseudo_r2_mcfadden']:.4f}"
                  f"（n={cloglog_stats['n']:,}，事件 {cloglog_stats['n_events']:,}）",
                  f"- 显著正向因子（缩短寿命）：{cloglog_stats['significant_positive']} 个；"
                  f"显著负向因子（延长寿命）：{cloglog_stats['significant_negative']} 个"]
    else:
        lines.append("- 未拟合（依赖缺失或拟合失败）")

    lines += ["", "## SHAP 特征重要性（聚合回原始特征）", ""]
    if shap_info:
        lines += ["| 排名 | 特征 | mean \\|SHAP\\| |", "| --- | --- | --- |"]
        for i, r in enumerate(shap_info["ranking"], 1):
            lines.append(f"| {i} | {r['feature']} | {r['mean_abs_shap']:.4f} |")
    else:
        lines.append("- shap 未安装，跳过")

    lines += ["", "## 残差空间自相关", ""]
    if moran and moran.get("moran_i") is not None:
        lines.append(f"- Moran's I = {moran['moran_i']:.4f}（p = {moran['p_value']:.3g}，"
                     f"k={moran['k_neighbors']}，置换 {moran['permutations']} 次，n={moran['n']:,}）")
        lines.append("- 显著为正 → 控制银行 / 年份后仍存在本地空间因素未进入模型")
    else:
        lines.append("- 未能计算")
    lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
def run(project) -> dict:
    """只读 ⑤ 的交付数据，产出模型、指标、SHAP 与空间诊断。"""
    project.log(f"[{STAGE}] {TITLE}")
    OUT.mkdir(parents=True, exist_ok=True)
    DATA.mkdir(parents=True, exist_ok=True)

    panel = load_and_build_panel(project)
    project.log(f"    [⑥] 面板重构完成：{len(panel):,} 网点-年观测，事件率 {panel['event'].mean():.2%}")
    panel.to_parquet(DATA / "branch_year_panel.parquet", index=False)

    pipe, metrics = fit_logit(panel, project)
    (OUT / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2),
                                      encoding="utf-8")
    cloglog_stats = fit_cloglog(panel, project)
    shap_info = compute_shap(pipe, panel, project)
    moran = spatial_residual_check(panel, pipe, project)

    manifest = write_replication_manifest(panel, metrics, project)
    dk.write_markdown(OUT, "train_report", _md_report(metrics, cloglog_stats, shap_info, moran, panel))

    return {
        "stage": STAGE, "blocking": False,
        "panel_rows": int(len(panel)),
        "test_auc": round(metrics["test"]["auc"], 4),
        "test_c_index": round(metrics["test"]["c_index"], 4),
        "test_brier": round(metrics["test"]["brier"], 4),
        "moran_i": round(moran["moran_i"], 4) if moran.get("moran_i") is not None else None,
        "top_shap_feature": (shap_info or {}).get("top_feature"),
        "artifacts": ["metrics.json", "replication_manifest.json", "logit_pipeline.pkl",
                      "logit_coefficients.csv", "cloglog_coefficients.csv",
                      "shap_importance.csv", "moran_i.json", "train_report.md"],
    }


def main() -> None:
    project = dk.Project.load(ROOT)
    print(run(project))


if __name__ == "__main__":
    main()
