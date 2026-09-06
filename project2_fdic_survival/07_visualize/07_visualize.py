# -*- coding: utf-8 -*-
"""07_visualize —— ⑦ 可视化（扩展阶段，规范 §8 / §8.8）。

入口文件与目录同名（``07_visualize.py``），必须暴露 ``run(project) -> dict``。
**只读**上游 ``05_map/output/data/``（网点维度表 / 银行脆弱性）与 ``06_train/output/``
（系数、SHAP、测试集预测、Moran's I），产物只进本阶段 ``output/``。

出图遵循 §8.8：

* 先选对图型（生存 → KM 阶梯；模型结果 → ROC / 校准 / 系数森林图；空间 → hexbin 密度）；
* 标题写**结论**不写字段名；轴标签带单位；副标题放口径与样本量；
* **禁止双 Y 轴**：基准风险图改为上下两格小倍数；
* 中文用微软雅黑（字形缺失才是乱码主因，不是编码）；
* 双格式落盘 ``figures/*.png`` + ``*.pdf``，全部登记进 ``manifest.json``。
"""
from __future__ import annotations

import datetime as _dt
import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

import datakit as dk

STAGE = "07_visualize"
TITLE = "⑦ 可视化（基准风险 / KM / SHAP / ROC 校准 / 森林图 / 空间）"

ROOT = Path(__file__).resolve().parent.parent
OUT = Path(__file__).resolve().parent / "output"
FIG = OUT / "figures"
IN_MAP = ROOT / "05_map" / "output" / "data"
IN_TRAIN = ROOT / "06_train" / "output"
for _d in (OUT, FIG):
    _d.mkdir(parents=True, exist_ok=True)

warnings.filterwarnings("ignore")

FONT = "Microsoft YaHei"
PALETTE = ["#4C72B0", "#DD8452", "#55A868", "#C44E52", "#8172B3", "#937860", "#DA8BC3", "#8C8C8C"]

# 每张图的登记信息（§8.8.5 manifest）：文件名 → (标题=结论, 回答的问题, alt_text, 口径, 单位)
_FIGURE_META = {
    "01-baseline-hazard-by-year.png": (
        "危机后整合窗口，网点关闭率翻倍",
        "网点关闭风险随日历年份如何变化？",
        "上格年关闭率在 2009–2014 抬升至两倍量级，下格模型年份效应同向",
        "按年关闭数 / 当年风险集；logit 年份虚拟变量相对 1994 的 exp(β)",
        "x=日历年，y=关闭率 或 相对风险"),
    "02-km-by-group.png": (
        "银行越脆弱，网点存活率越低",
        "不同银行脆弱性 / 类别 / 历史关闭率分层的网点存活曲线是否有差异？",
        "三格 KM 曲线：L2 地理分散银行与高历史关闭率银行的网点存活率最低",
        "Kaplan–Meier，右删失计入风险集，左截断样本已剔除",
        "x=进入风险集后年数，y=存活率"),
    "03-shap-importance.png": (
        "年份之后，银行层因素最强",
        "哪些特征驱动网点的关闭风险？",
        "条形图显示 year 之后为银行脆弱性与历史关闭率、网点规模",
        "LinearExplainer，变换后特征空间，聚合回原始特征",
        "x=mean |SHAP|"),
    "04-roc-calibration.png": (
        "区分度良好，高危段概率略低估",
        "离散时间风险模型在测试集上的区分度与校准如何？",
        "左 ROC 明显优于对角，右校准曲线低中风险贴合、高风险略低于对角",
        "测试集按 event 分层划分；校准按预测风险 10 分位分箱",
        "x=预测概率 / 假阳性率，y=实际关闭率 / 真阳性率"),
    "05-cloglog-forest.png": (
        "规模是护城河，地理分散更易被整合",
        "非时间因素里，哪些延长、哪些缩短网点寿命？",
        "森林图显示银行历史关闭率与地理分散为正，存款规模为负",
        "cloglog GLM，剔年份虚拟与完美分离项，仅保留显著项",
        "x=cloglog 系数（>0 缩短寿命）"),
    "06-spatial-closures.png": (
        "残差仍有空间聚集，本地因素未进模型",
        "控制银行与年份后，关闭风险是否仍有空间结构？",
        "左右两格密度图分布相近，但残差 Moran's I 显著为正",
        "hexbin 密度（120 网格）；Moran's I 用 k=8 近邻 + 置换检验",
        "x=经度，y=纬度，色=网点数/格"),
}

_TIER_MAP = {
    "L0_单网点": "L0 单网点银行",
    "L1_多网点高集中": "L1 多网点·地理集中",
    "L2_多网点地理分散": "L2 多网点·地理分散",
}
_BK_MAP = {"N": "N 国家银行", "SM": "SM 州会员", "NM": "NM 非会员",
           "SB": "SB 州非会员", "SA": "SA 储蓄协会"}


# --------------------------------------------------------------------------- #
# 字体与落盘
# --------------------------------------------------------------------------- #
def _setup_style() -> None:
    """中文字体（§8.8.3）：先注册字体文件，再设 rcParams。"""
    import matplotlib
    from matplotlib import font_manager
    import matplotlib.pyplot as plt

    for p in (r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\msyhbd.ttc",
              r"C:\Windows\Fonts\simhei.ttf"):
        if Path(p).exists():
            try:
                font_manager.fontManager.addfont(p)
            except Exception:
                pass
    matplotlib.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["Microsoft YaHei", "SimHei", "Noto Sans CJK SC",
                            "Noto Sans SC", "SimSun", "DejaVu Sans"],
        "axes.unicode_minus": False,
        "pdf.fonttype": 42, "ps.fonttype": 42,
        "figure.dpi": 110, "savefig.dpi": 200,
        "figure.facecolor": "white", "savefig.facecolor": "white",
        "axes.titlesize": 13, "axes.labelsize": 11,
        "xtick.labelsize": 9, "ytick.labelsize": 9,
    })
    plt.switch_backend("Agg")


def _save(fig, name: str) -> Path:
    """统一落盘：PNG（看）+ PDF（矢量，进文档），位置 ``output/figures/``。"""
    p = FIG / name
    fig.tight_layout()
    fig.savefig(p, dpi=200, bbox_inches="tight", pad_inches=0.1, facecolor="white")
    fig.savefig(p.with_suffix(".pdf"), bbox_inches="tight", pad_inches=0.1, facecolor="white")
    return p


def _footnote(fig, source: str) -> None:
    """右下角脚注：数据来源产物路径 + 生成时间（§8.8.2）。"""
    fig.text(0.995, 0.005,
             f"来源：{source}　生成：{_dt.datetime.now():%Y-%m-%d %H:%M}",
             ha="right", va="bottom", fontsize=8, color="#666666")


def _despine(ax) -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(alpha=0.3, axis="y", color="#CCCCCC")


# --------------------------------------------------------------------------- #
# 数据
# --------------------------------------------------------------------------- #
def load_branch_data() -> pd.DataFrame:
    """网点维度表 + 银行脆弱性，仅保留「进入风险集」的网点（与 ⑥ 同口径）。"""
    branch = pd.read_csv(IN_MAP / "branch_panel.csv", low_memory=False)
    bank = pd.read_csv(IN_MAP / "bank_fragility.csv", low_memory=False)
    cols = [c for c in ["CERT", "n_branches", "n_closed", "fragility_tier",
                        "bank_closed_rate"] if c in bank.columns]
    branch = branch.merge(bank[cols], on="CERT", how="left")

    before = branch["acq_year"].notna() & (branch["acq_year"] < branch["first_year"])
    branch = branch[~before].copy()
    branch["est_year"] = branch["est_year"].fillna(branch["first_year"])
    branch["duration"] = branch["duration"].astype(int)
    branch["censored"] = (branch["event"] == "alive").astype(int)
    branch["bank_closed_rate"] = branch["bank_closed_rate"].fillna(0.0)
    branch["BKCLASS"] = branch["BKCLASS"].fillna("MISSING")
    branch["fragility_tier"] = branch["fragility_tier"].fillna("L0_单网点")
    return branch.reset_index(drop=True)


def kaplan_meier(time: np.ndarray, event: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Kaplan–Meier 阶梯（样本已按进入风险集条件化）。"""
    df = pd.DataFrame({"t": time, "e": event}).sort_values("t")
    t_all, e_all = df["t"].to_numpy(), df["e"].to_numpy()
    times, surv, n, pos = [0.0], [1.0], len(df), 0
    while pos < n:
        t = t_all[pos]
        end = pos
        while end < n and t_all[end] == t:
            end += 1
        at_risk = n - pos
        n_events = int(e_all[pos:end].sum())
        if at_risk > 0 and n_events > 0:
            surv.append(surv[-1] * (1 - n_events / at_risk))
            times.append(float(t))
        pos = end
    return np.asarray(times), np.asarray(surv)


# --------------------------------------------------------------------------- #
# 各图
# --------------------------------------------------------------------------- #
def fig_baseline_hazard(branch: pd.DataFrame) -> dict:
    """图1：基准风险随年份（上=数据关闭率，下=模型年份效应；禁止双 Y 轴）。"""
    import matplotlib.pyplot as plt
    _setup_style()

    obs_end = branch["acq_year"].fillna(branch["last_year"])
    years = np.arange(int(branch["first_year"].min()), int(obs_end.max()) + 1)
    first = branch["first_year"].to_numpy()[:, None]
    end = obs_end.to_numpy()[:, None]
    at_risk = ((first <= years) & (end >= years)).sum(axis=0)
    closed_year = branch["acq_year"].fillna(branch["first_year"]).to_numpy()
    is_closed = (branch["event"] == "closed").to_numpy()
    n_closed = np.asarray([int(((closed_year == y) & is_closed).sum()) for y in years])
    with np.errstate(divide="ignore", invalid="ignore"):
        raw_rate = np.where(at_risk > 0, n_closed / np.maximum(at_risk, 1), np.nan)

    coef = pd.read_csv(IN_TRAIN / "logit_coefficients.csv")
    yr = coef[coef["feature"].astype(str).str.startswith("year_")].copy()
    yr["year"] = yr["feature"].astype(str).str.replace("year_", "", regex=False).astype(int)
    yr["exp_coef"] = np.exp(yr["coef"])
    yr = yr.sort_values("year")

    fig, axes = plt.subplots(2, 1, figsize=(10, 7), sharex=True)
    ax = axes[0]
    ax.plot(years, raw_rate, color=PALETTE[0], marker="o", ms=3, lw=1.6)
    ax.axvspan(2008, 2015, color=PALETTE[3], alpha=0.10)
    ax.set_ylabel("网点年关闭率")
    ax.set_ylim(0, float(np.nanmax(raw_rate)) * 1.25)
    ax.set_title("危机后行业整合窗口，年关闭率抬升至两倍量级", loc="left")
    _despine(ax)

    ax = axes[1]
    ax.plot([1994] + yr["year"].tolist(), [1.0] + yr["exp_coef"].tolist(),
            color=PALETTE[3], marker="s", ms=3, lw=2)
    ax.axvspan(2008, 2015, color=PALETTE[3], alpha=0.10)
    ax.axhline(1.0, color="#999999", lw=0.8, ls="--")
    ax.set_xlabel("日历年份")
    ax.set_ylabel("相对风险 exp(β)（参照 1994）")
    ax.set_ylim(0, max([1.0] + yr["exp_coef"].tolist()) * 1.15)
    ax.set_title("模型年份效应与数据同向：2010 / 2014 为关闭高峰", loc="left")
    _despine(ax)

    fig.suptitle("离散风险的基准形状（上：数据；下：logit 年份效应）", fontsize=14)
    _footnote(fig, "05_map/output/data/branch_panel.csv + 06_train/output/logit_coefficients.csv")
    _save(fig, "01-baseline-hazard-by-year.png")
    plt.close(fig)
    return {"peak_year": int(yr.loc[yr["exp_coef"].idxmax(), "year"]) if len(yr) else None}


def fig_km_groups(branch: pd.DataFrame) -> dict:
    """图2：分层 KM 生存曲线（脆弱性 / 银行类别 / 历史关闭率）。"""
    import matplotlib.pyplot as plt
    _setup_style()
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.6))

    def _panel(ax, df, col, name_map, title):
        for k, (name, g) in enumerate(df.groupby(col, observed=True)):
            t, s = kaplan_meier(g["duration"].to_numpy(), (1 - g["censored"]).to_numpy())
            ax.step(t, s, where="post", color=PALETTE[k % len(PALETTE)], lw=2,
                    label=name_map.get(name, str(name)))
        ax.set_xlabel("进入风险集后的年数")
        ax.set_ylabel("网点存活率")
        ax.set_ylim(0, 1.02)
        ax.set_title(title, fontsize=11, loc="left")
        ax.legend(frameon=False, fontsize=8, loc="upper right")
        _despine(ax)

    _panel(axes[0], branch[branch["fragility_tier"].isin(_TIER_MAP)],
           "fragility_tier", _TIER_MAP, "(a) 银行脆弱性")
    top_bk = branch["BKCLASS"].value_counts().head(4).index
    _panel(axes[1], branch[branch["BKCLASS"].isin(top_bk)],
           "BKCLASS", _BK_MAP, "(b) 银行类别")
    branch = branch.copy()
    branch["rate_grp"] = pd.cut(branch["bank_closed_rate"], bins=[-1e-9, 0.0, 0.25, 1.0],
                                labels=["0%（无历史关闭）", "0–25%", "≥25%"])
    _panel(axes[2], branch.dropna(subset=["rate_grp"]), "rate_grp", {},
           "(c) 所属银行历史关闭率")

    fig.suptitle("银行层共享脆弱性决定网点生死（Kaplan–Meier，右删失计入风险集）", fontsize=14)
    _footnote(fig, "05_map/output/data/branch_panel.csv + bank_fragility.csv")
    _save(fig, "02-km-by-group.png")
    plt.close(fig)
    return {"groups": 3}


def fig_shap_importance() -> dict:
    """图3：SHAP 聚合特征重要性（排序条形图）。"""
    import matplotlib.pyplot as plt
    _setup_style()
    imp = pd.read_csv(IN_TRAIN / "shap_importance.csv").sort_values("mean_abs_shap")
    fig, ax = plt.subplots(figsize=(9, 4.2))
    colors = [PALETTE[3] if i >= len(imp) - 2 else PALETTE[0] for i in range(len(imp))]
    ax.barh(imp["feature"], imp["mean_abs_shap"], color=colors, alpha=0.9)
    for i, (feat, v) in enumerate(zip(imp["feature"], imp["mean_abs_shap"])):
        ax.text(v * 1.01, i, f"{v:.2f}", va="center", fontsize=8, color="#444444")
    ax.set_xlabel("mean |SHAP|（对数几率尺度，正类 = 关闭）")
    ax.set_title("年份（宏观）之后，银行层因素主导网点关闭风险", loc="left")
    _despine(ax)
    _footnote(fig, "06_train/output/shap_importance.csv")
    _save(fig, "03-shap-importance.png")
    plt.close(fig)
    return {"top": str(imp.iloc[-1]["feature"])}


def fig_roc_calibration() -> dict:
    """图4：ROC + 校准曲线（测试集）。"""
    import matplotlib.pyplot as plt
    from sklearn.metrics import roc_auc_score, roc_curve
    _setup_style()
    pred = pd.read_csv(IN_TRAIN / "test_predictions.csv")
    y, risk = pred["event"].to_numpy(), pred["risk"].to_numpy()
    fpr, tpr, _ = roc_curve(y, risk)
    auc = roc_auc_score(y, risk)

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8))
    ax = axes[0]
    ax.plot(fpr, tpr, color=PALETTE[0], lw=2)
    ax.plot([0, 1], [0, 1], ls="--", color="#999999", lw=1)
    ax.set_xlabel("假阳性率")
    ax.set_ylabel("真阳性率")
    ax.set_title(f"区分度良好（AUC = {auc:.3f}）", loc="left")
    _despine(ax)

    ax = axes[1]
    q = pd.qcut(risk, q=10, duplicates="drop")
    cal = pd.DataFrame({"bin": q, "pred": risk, "obs": y}).groupby("bin", observed=True).agg(
        pred=("pred", "mean"), obs=("obs", "mean"))
    ax.plot([0, cal["pred"].max() * 1.05], [0, cal["pred"].max() * 1.05],
            ls="--", color="#999999", lw=1)
    ax.plot(cal["pred"], cal["obs"], marker="o", color=PALETTE[1], lw=2)
    ax.set_xlabel("预测关闭概率")
    ax.set_ylabel("实际关闭率")
    ax.set_title("低中风险段贴合对角，高风险段略低估", loc="left")
    _despine(ax)

    fig.suptitle("离散时间 logit 风险模型 · 测试集离线评估", fontsize=14)
    _footnote(fig, "06_train/output/test_predictions.csv")
    _save(fig, "04-roc-calibration.png")
    plt.close(fig)
    return {"auc": float(auc)}


def fig_coef_forest() -> dict:
    """图5：非时间因素 cloglog 系数森林图（点 + 95% CI）。"""
    import matplotlib.pyplot as plt
    _setup_style()
    coef = pd.read_csv(IN_TRAIN / "cloglog_coefficients.csv")
    coef.columns = [str(c).strip() for c in coef.columns]
    lo_col = [c for c in coef.columns if c.startswith("[0.025")]
    hi_col = [c for c in coef.columns if c.endswith("0.975]")]
    coef = coef.rename(columns={coef.columns[0]: "term"})
    coef["lo"], coef["hi"] = coef[lo_col[0]], coef[hi_col[0]]

    keep = (~coef["term"].astype(str).str.startswith("C(year)")
            & (coef["P>|z|"] < 0.05) & ((coef["hi"] - coef["lo"]) < 5))
    plot_df = coef[keep].sort_values("Coef.").tail(14)
    labels = {
        "bank_closed_rate": "所属银行历史关闭率",
        "log_depsumbr": "网点存款规模 log(存款)",
        "lat": "纬度", "lng": "经度", "age": "网点年龄",
        "neighbor_count": "同格竞争网点数",
    }
    names = []
    for t in plot_df["term"].astype(str):
        if t.startswith("C(BKCLASS)[T."):
            names.append("银行类别 " + t.split("[T.")[1].rstrip("]"))
        elif t.startswith("C(fragility_tier)[T."):
            names.append(t.split("[T.")[1].rstrip("]"))
        else:
            names.append(labels.get(t, t))
    plot_df = plot_df.assign(label=names)

    fig, ax = plt.subplots(figsize=(9.5, 5.5))
    ypos = np.arange(len(plot_df))
    err = [plot_df["Coef."] - plot_df["lo"], plot_df["hi"] - plot_df["Coef."]]
    ax.errorbar(plot_df["Coef."], ypos, xerr=err, fmt="none", ecolor="#999999",
                capsize=3, lw=1.2)
    ax.scatter(plot_df["Coef."], ypos,
               c=[PALETTE[3] if v > 0 else PALETTE[0] for v in plot_df["Coef."]],
               s=45, zorder=3)
    ax.axvline(0, color="#555555", lw=1)
    ax.set_yticks(ypos, labels=plot_df["label"])
    ax.set_xlabel("cloglog 系数（>0 缩短寿命，<0 延长寿命）")
    ax.set_title("规模大更长寿；银行历史关闭率高、地理分散更易被整合", loc="left")
    ax.grid(alpha=0.3, axis="x", color="#CCCCCC")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    _footnote(fig, "06_train/output/cloglog_coefficients.csv")
    _save(fig, "05-cloglog-forest.png")
    plt.close(fig)
    return {"terms": int(len(plot_df))}


def fig_spatial(branch: pd.DataFrame, moran: dict) -> dict:
    """图6：存活 / 关闭网点空间密度 + 残差 Moran's I 结论。"""
    import matplotlib.pyplot as plt
    _setup_style()
    closed = branch[(branch["event"] == "closed") & branch["lat"].notna()]
    alive = branch[(branch["event"] == "alive") & branch["lat"].notna()]

    fig, axes = plt.subplots(1, 2, figsize=(13, 5.6), sharex=True, sharey=True)
    for ax, df, title, cmap in [(axes[0], alive, "仍存活网点（右删失）密度", "Blues"),
                                (axes[1], closed, "已关闭网点密度", "Reds")]:
        hb = ax.hexbin(df["lng"], df["lat"], gridsize=120, cmap=cmap, mincnt=1, alpha=0.9)
        cb = fig.colorbar(hb, ax=ax, fraction=0.03, pad=0.02)
        cb.set_label("网点数 / 格")
        ax.set_xlabel("经度")
        ax.set_title(title, fontsize=11, loc="left")
        ax.set_xlim(-130, -60)
        ax.set_ylim(20, 55)
    axes[0].set_ylabel("纬度")

    mi = moran.get("moran_i")
    p = moran.get("p_value")
    txt = (f"残差 Moran's I = {mi:.3f}\n置换检验 p = {p:.3f}（n = {moran.get('n', 0):,}）\n"
           "→ 控制银行 / 年份后仍有弱而显著的正空间自相关，\n   本地市场条件未完全进入模型"
           if mi is not None else "残差 Moran's I 未能计算")
    axes[1].text(0.02, 0.02, txt, transform=axes[1].transAxes, fontsize=9,
                 va="bottom", ha="left",
                 bbox=dict(facecolor="white", alpha=0.85, boxstyle="round,pad=0.4"))
    fig.suptitle("网点关闭的空间分布：东西差异之外，本地市场因素仍未解释", fontsize=14)
    _footnote(fig, "05_map/output/data/branch_panel.csv + 06_train/output/moran_i.json")
    _save(fig, "06-spatial-closures.png")
    plt.close(fig)
    return {"moran_i": mi, "moran_p": p}


# --------------------------------------------------------------------------- #
# manifest
# --------------------------------------------------------------------------- #
def build_manifest(branch: pd.DataFrame) -> dict:
    """按规范 §8.8.5 生成 manifest.json。"""
    import matplotlib
    import sklearn

    figures = []
    for p in sorted(FIG.glob("*.png")):
        meta = _FIGURE_META.get(p.name)
        figures.append({
            "file": f"figures/{p.name}",
            "pdf": f"figures/{p.stem}.pdf",
            "title": meta[0] if meta else p.stem,
            "type": p.stem.split("-", 1)[-1],
            "question": meta[1] if meta else "",
            "alt_text": meta[2] if meta else "",
            "scope": meta[3] if meta else "",
            "unit": meta[4] if meta else "",
            "source": "05_map/output/data/ + 06_train/output/",
            "n": int(len(branch)),
            "range": f"{int(branch['first_year'].min())}–{int(branch['last_year'].max())}；"
                     f"右删失计入风险集；左截断已剔除",
        })
    return {
        "generated_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "generator": {
            "tool": "matplotlib", "version": matplotlib.__version__,
            "script": "07_visualize/07_visualize.py",
            "encoding": "utf-8", "font": FONT, "reproducible": True,
            "sklearn": sklearn.__version__,
        },
        "n_figures": len(figures),
        "figures": figures,
    }


def run(project) -> dict:
    """只读上游产物，产出 6 张图 + manifest.json。"""
    project.log(f"[{STAGE}] {TITLE}")
    branch = load_branch_data()
    moran = json.loads((IN_TRAIN / "moran_i.json").read_text(encoding="utf-8"))
    project.log(f"    [⑦] 风险集网点 {len(branch):,}；关闭率 {(branch['event'] == 'closed').mean():.1%}")

    fig_baseline_hazard(branch)
    fig_km_groups(branch)
    fig_shap_importance()
    fig_roc_calibration()
    fig_coef_forest()
    fig_spatial(branch, moran)

    manifest = build_manifest(branch)
    dk.write_json(OUT, "manifest", manifest)
    project.log(f"    [⑦] 出图 {manifest['n_figures']} 张 → 07_visualize/output/figures/")
    return {
        "stage": STAGE, "blocking": False,
        "figures": manifest["n_figures"],
        "branches": int(len(branch)),
        "artifacts": ["manifest.json", "figures/"],
    }


def main() -> None:
    project = dk.Project.load(ROOT)
    print(run(project))


if __name__ == "__main__":
    main()
