# -*- coding: utf-8 -*-
"""08_conclude —— ⑧ 结论（扩展阶段，规范 §8 / §8.5）。

入口文件与目录同名（``08_conclude.py``），必须暴露 ``run(project) -> dict``。
**只读**上游 ``06_estimate/output/`` 与 ``07_visualize/output/``，产物只进本阶段 ``output/``。

按指导图⑦ 输出：

    · 短论口径（精简 Markdown，给非技术阅读）
    · 技术报告（distill 风格 Markdown + 嵌入式图表）
    · conclusion.md（结论 + 已知限制 / 止损条件）+ conclusion_report.json

约束：遵循 ``churn_methodology_handbook.html`` 的 §10 落地清单 + §12 陷阱速查：
    · 直接效应、spillover、total 分开报告
    · 必须交代 bootstrap CI / 敏感性 / 是否有空间自相关
    · 主动承认 ~ 一条：        — 流失 ≠ ROI/干预阈值（成本参数缺失）
    · 不承诺 ROI / 不承诺干预阈值
    · 报告所有 CI
"""

from __future__ import annotations

import datetime as _dt
import json
import warnings
from pathlib import Path
from textwrap import dedent

import numpy as np
import pandas as pd

import datakit as dk

STAGE = "08_conclude"
TITLE = "⑧ 结论（短论 + 技术报告 + 已知限制）"

ROOT = Path(__file__).resolve().parent.parent
OUT = Path(__file__).resolve().parent / "output"
IN_EST = ROOT / "06_estimate" / "output"        # 只读 ⑥ 的估计结果
IN_VIZ = ROOT / "07_visualize" / "output"       # 只读 ⑦ 的图清单
REP_DIR = OUT
SHORT = OUT / "short_essay.md"
LOGS = ROOT / "logs"
for _d in (OUT, LOGS):
    _d.mkdir(parents=True, exist_ok=True)


def log(msg: str) -> None:
    print(msg, flush=True)
    with (LOGS / "pipeline.log").open("a", encoding="utf-8") as f:
        f.write(msg + "\n")


warnings.filterwarnings("ignore")


# --------------------------------------------------------------------------- #
# 工具
# --------------------------------------------------------------------------- #
def _fmt_p(p: float) -> str:
    """p 值展示：极小时报 "<0.001"，避免浮点下溢打印成 "0"。"""
    if p is None:
        return "n/a"
    try:
        if np.isnan(float(p)):
            return "n/a"
    except (TypeError, ValueError):
        return str(p)
    if float(p) < 0.001:
        return "p<0.001"
    if float(p) < 0.05:
        return f"p={p:.3g}*"
    return f"p={p:.3g}"


def _fmt_coef(beta: float, se: float = None, p: float = None,
               n: int = None, ci: tuple = None) -> str:
    s = f"{beta:+.4g}"
    if se is not None:
        if p is not None:
            s += f" (SE={se:.4g}, {_fmt_p(p)})"
        else:
            s += f" (SE={se:.4g})"
    elif ci:
        s += f" 95% CI [{ci[0]:.4g}, {ci[1]:.4g}]"
    if n is not None:
        s += f", n={n:,}"
    return s


def _read_estimate() -> dict:
    return json.loads((IN_EST / "estimate.json").read_text(encoding="utf-8"))


def _read_manifest() -> dict:
    p = IN_VIZ / "manifest.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# 1) 短论（≈ A4 一页）
# --------------------------------------------------------------------------- #
def write_short_essay(est: dict) -> Path:
    log("  [7.1] M0 短论（≤ A4 一页）")

    twfe = est["twfe"]
    twfe_params = twfe.get("params", {})
    twfe_p = twfe.get("pvalues", {})
    spatial = est["spatial_fits"]
    decomp = est["spatial_effect_decomposition"]
    mi = spatial.get("residuals_morans_i", {})
    sens = est.get("sensitivity", {})
    n_twfe = int(twfe.get("n_obs", 0))

    beta = twfe_params.get("post_x_strength", float("nan"))
    se = twfe["std_err"]["post_x_strength"]
    p = twfe_p["post_x_strength"]

    sar = spatial.get("sar", {})
    sar_decomp = decomp.get("sar_approx", {})
    slx = spatial.get("slx", {})

    # 预先解析 SLX 子项，避免 f-string 中 dict literal 冲突
    slx_params = slx.get("params", {}) or {}
    slx_pvalues = slx.get("pvalues", {}) or {}
    w_treat = slx_params.get("W_treat_strength", 0.0)
    w_treat_p = slx_pvalues.get("W_treat_strength", 1.0)
    sar_rho = sar.get("rho", 0.0)
    sar_direct = sar_decomp.get("direct_effect", 0.0)
    sar_spill = sar_decomp.get("spillover_effect", 0.0)
    sar_total = sar_decomp.get("total_effect", 0.0)
    mi_I = mi.get("I", 0.0)
    mi_p = mi.get("p_sim", 1.0)

    # 事件研究 ATT（窗口内平均），用于叙事
    es_table = est.get("event_study", {}).get("table", [])
    es_post = [r["dynamic_effect"] for r in es_table if r["rel_year"] >= 0]
    es_post_avg = float(np.mean(es_post)) if es_post else float("nan")
    es_t4 = next((r["dynamic_effect"] for r in es_table if r["rel_year"] == 4), float("nan"))
    es_t0 = next((r["dynamic_effect"] for r in es_table if r["rel_year"] == 0), float("nan"))
    es_t3 = next((r["dynamic_effect"] for r in es_table if r["rel_year"] == -3), float("nan"))
    es_t2 = next((r["dynamic_effect"] for r in es_table if r["rel_year"] == -2), float("nan"))
    es_p3 = next((r["pvalue"] for r in es_table if r["rel_year"] == -3), float("nan"))
    post_beta = twfe_params.get("post", float("nan"))

    text = f"""# FDIC 网点关闭对周边同业存款增量：因果与空间效应（M0 短论）

**研究设计（重要修正）**

处理组 = **存续网点（alive_censored）中，首次在其生命周期内 10 km 处发生
同业（同 BKCLASS）关闭事件**的网点（35,785 / 76,097；KDTree+haversine
配对 330,691 对）；对照组 = 其余从未被辐射的存续网点。
关闭网点自身不作为 outcome（其在关闭后无观测，避免把"死亡"当效应）。
双固定效应 + UNINUMBR 聚类稳健 SE；TWFE 与事件研究均限定
treated 网点在 rel ∈ [−3,+4] 窗口内，对照组全样本。

**事件研究（首选动态证据）**

    · 事件前：τ=-3 效应 {es_t3 * 100:+.3g} pp（p={es_p3:.2g}，不显著）；
      τ=-2 效应 {es_t2 * 100:+.3g} pp（显著但量级约为 post 的 1/8）——
      平行趋势近似成立，无正向预期。
    · 事件后：τ=0 {es_t0 * 100:+.3g} pp → τ=4 {es_t4 * 100:+.3g} pp，
      逐年显著为负且加深；窗口内平均处理效应 ≈
      {es_post_avg * 100:+.3g} pp/年。
    · **结论：周边同业关闭事件后，被辐射存活网点的存款增速显著下降，
      且随事件后年限加深（至第 4 年约 {es_t4 * 100:.3g} pp）**——支持
      "关闭事件释放的存款并未留在原地理邻域"的负溢出叙事。

**TWFE（平均效应，n={n_twfe:,}）**

    · post 主效应 = {_fmt_coef(post_beta, twfe['std_err'].get('post'), twfe_p.get('post'))}：
      事件后存款增速平均显著下行（≈ {post_beta * 100:.3g} pp/年）。
    · post × strength 交互 = {_fmt_coef(beta, se, p)}：处理强度
      （环加权同业关闭数）越高的网点，负效应越缓和——与"强度 = 更多竞争者
      退出 → 更多存款回流本网点"的再配置边际一致。

**空间截面（2010→2014，H3 R8）**

    · SLX：W_treat_strength = {w_treat:.4g} (p={w_treat_p:.3g}) →
      邻 cell 处理强度与本 cell 存款增长正相关（聚合层的正溢出信号）；
    · SAR 一阶近似 direct={sar_direct:.4g} / spill={sar_spill:.4g} /
      total={sar_total:.4g}（ρ={sar_rho:.4g}，数值不稳仅参考）；
    · 残差 Moran's I={mi_I:.4g}（p_sim={mi_p:.3g}）→ OLS 残差仍有空间自相关。
    · **网点层负 ATT 与聚合层正 W_treat 并不矛盾**：前者是存活网点个体的
      存款流失轨迹，后者是存量份额在 cell 间的再配置，两者度量不同对象。

**关键的不确定性（必须如实交代）**

    ① 事件研究 pre 期并非完全零（τ=-2 轻微负），且被辐射区域本身可能
       处于衰退走廊——**共同区域冲击**可能贡献部分 post 下降；
       TWFE/事件研究点估计是"关闭与周边网点存款衰退"的关联证据，
       严格因果仍需 IV/匹配或 Callaway–Sant'Anna 类估计。
    ② 存款转移 ≠ 区域净增：网点层负 ATT 只说明存款**没有留在原地理邻域**，
       聚合层正 spillover 提示更广尺度的再配置；两者均不能外推区域存款
       总量或任何 ROI（成本参数缺失，不承诺 ROI/干预阈值）。
    ③ 关闭网点自身客户流失与获客成本（CAC）未建模。

**结论一个句子**

> 1994–2015 FDIC SOD 显示：10 km 内同业关闭事件发生后，被辐射存活网点
> 的存款增速平均下降约 {abs(es_post_avg) * 100:.3g} pp/年（τ=0 起
> {es_t0 * 100:.3g} pp，至 τ=4 加深到 {es_t4 * 100:.3g} pp）；TWFE 平均
> post 效应 {post_beta * 100:.3g} pp。聚合 cell 层 SLX 给出正 spillover，
> 提示存款在**更广地理尺度上再配置**，而非留在关闭事件原邻域。两套识别
> 均**不可读成严格因果或 ROI**（τ=-2 轻微趋势 + 区域共同冲击 +
> 成本参数缺失），仅供方向性结论。
"""

    p = SHORT
    p.write_text(text, encoding="utf-8")
    log(f"    saved → {p}")
    return p


# --------------------------------------------------------------------------- #
# 2) 技术报告（distill 风格）
# --------------------------------------------------------------------------- #
def _upstream_facts() -> dict:
    """从上游阶段产物读取真实规模（避免报告里的行数硬编码漂移）。"""
    import yaml

    facts = {"panel_rows": 0, "branches": 0, "closure_events": 0, "h3_cells": 0,
             "cross_section_cells": 0, "did_panel_rows": 0, "event_dist": "—"}
    mp = ROOT / "05_map" / "output" / "map.yaml"
    if mp.exists():
        m = yaml.safe_load(mp.read_text(encoding="utf-8")) or {}
        sh = m.get("shape") or {}
        facts.update({
            "panel_rows": int(sh.get("panel_rows") or 0),
            "branches": int(sh.get("branch_dim_rows") or 0),
            "closure_events": int(sh.get("exposure_rows") or 0),
            "h3_cells": int(sh.get("h3_cells") or 0),
            "event_dist": "；".join(f"{k} {v:,}" for k, v in (m.get("event_type_dist") or {}).items()) or "—",
        })
    cs = IN_EST / "data" / "spatial_cross_section.parquet"
    if cs.exists():
        facts["cross_section_cells"] = int(len(pd.read_parquet(cs, columns=["h3"])))
    dp = IN_EST / "data" / "did_panel.parquet"
    if dp.exists():
        facts["did_panel_rows"] = int(len(pd.read_parquet(dp, columns=["UNINUMBR"])))
    return facts


def write_technical_report(est: dict, manifest: dict) -> Path:
    log("  [8.2] 技术报告（distill 风格 Markdown）")

    _up = _upstream_facts()
    twfe = est["twfe"]
    event = est["event_study"]
    spatial = est["spatial_fits"]
    decomp = est["spatial_effect_decomposition"]
    sens = est.get("sensitivity", {})
    overview = est.get("model_overview", {})

    # 报告位于 08_conclude/output/，图片在 07_visualize/output/figures/ → 相对路径引用
    figs_dir = Path("..") / "07_visualize" / "output" / "figures"
    kepler_path = Path("..") / "07_visualize" / "output" / "kepler" / "kepler_map.html"

    # 事件研究表
    if "table" in event:
        ev_rows = event["table"]
        ev_md = "τ | dynamic effect\n---|---\n"
        for r in ev_rows:
            ev_md += f"{r['rel_year']:+d} | {r['dynamic_effect']:+.4g}\n"
    else:
        ev_md = "_event study unavailable_\n"

    # 空间模型对比
    sdm_table = "model | pseudo R² | n | 关键参数 | 备注\n---|---|---|---|---\n"
    for label, name in [("ols", "OLS"), ("sar", "SAR (GM_Lag)"),
                        ("sem", "SEM (GM_Error)"), ("slx", "SLX (OLS+W·X)")]:
        m = spatial.get(label)
        if not m:
            continue
        r2 = m.get("r2", m.get("pr2", float("nan")))
        n = m.get("n", "?")
        key = ""
        if label == "sar":
            key = f"rho={m.get('rho', 'n/a'):.4g}"
        elif label == "sem":
            key = f"lambda={m.get('lambda', 'n/a'):.4g}"
        elif label == "slx":
            w_treat = m.get("params", {}).get("W_treat_strength", float("nan"))
            key = f"W_treat={w_treat:.4g}"
        sdm_table += f"{name} | {r2:.4g} | {n} | {key} |\n"

    report = dedent(f"""
# 方案⑤⑥⑦·FDIC 网点关闭对周边存款增量的因果与空间效应 · 技术报告

> 项目：`project1_fdic_spatial` · 遵循 `docs/churn_methodology_handbook.html` (§3, §5, §7, §10, §12)

## 0. 摘要

数据集基础（来自上游 `05_map/output/data/` 与 `06_estimate/output/data/`）：

| artifact | rows |
|---|---|
| `branch_year_panel.parquet` | {_up["panel_rows"]:,} |
| `branch_dim.csv` | {_up["branches"]:,}（{_up["event_dist"]}）|
| `closure_exposure.csv` | {_up["closure_events"]:,} 起关闭事件（H3 cells {_up["h3_cells"]:,}）|
| `spatial_cross_section.parquet` | {_up["cross_section_cells"]:,} H3 R8 cells（2010→2014 截面）|
| `did_panel.parquet` | {_up["did_panel_rows"]:,} 存续网点-年 |

**识别说明（与早期草稿的重要修正）**

    · 处理组 = 存续网点（alive_censored）中首次被 10 km 内同业关闭事件
      辐射者（KDTree + haversine 空间配对，330,691 对）；
    · 关闭网点自身不做 outcome（关闭后无观测，避免把"死亡"当效应）；
    · post = YEAR ≥ first_event_year；强度 = 首次辐射年环加权同业关闭强度。

主结果一句话：**同业关闭事件发生后，被辐射存活网点的存款增速显著下行且逐年
加深（事件研究 τ=0 约 -4.4pp → τ=4 约 -10.1pp；TWFE post ≈ -0.053，
p<0.001）；post × strength 交互为正（+0.014），提示处理强度更高的网点
负效应更缓和。聚合 H3 cell 层 SLX 的 W_treat 为正 → 存款在更广地理尺度
再配置。事件前 τ=-2 轻微为负 + 区域共同冲击未排除 → 关联证据而非严格因果。**

## 1. 模型总览

```text
{json.dumps(overview, ensure_ascii=False, indent=2)}
```

## 2. TWFE + 事件研究

### 2.1 TWFE（linearmodels.PanelOLS）

**双向固定效应（UNINUMBR + YEAR）+ 聚类稳健 SE（cluster on UNINUMBR）。
y = dep_chg_rate（clip ±50pp）；回归量 post × strength。**
**Caution：平行趋势近似通过但 τ=-2 轻微为负，共同区域冲击未完全排除
→ 该 β 为关联证据，见 2.3。**

| 参数 | 系数 | SE | t | p |
|---|---|---|---|---|
""").strip() + "\n"
    if "params" in twfe:
        params = twfe["params"]
        se = twfe.get("std_err", {})
        tvals = twfe.get("tvalues", {})
        pvals = twfe.get("pvalues", {})
        for k in params:
            report += (f"| {k} | {params[k]:+.4g} | "
                       f"{se.get(k, float('nan')):.4g} | "
                       f"{tvals.get(k, float('nan')):.4g} | "
                       f"{_fmt_p(pvals.get(k))} |\n")

    report += dedent(f"""

n_obs = {twfe.get('n_obs', '?')}, n_entities = {twfe.get('n_entities', '?')}, n_times = {twfe.get('n_times', '?')}, R²_within = {twfe.get('r2_within', float('nan')):.4g}.

### 2.2 事件研究（网点级 event-time dummies，TWFE 同一识别框架）

事件研究结果表（baseline = τ=-1；τ<0 为事件前，应接近 0）：

{ev_md}

事件研究图：![event study]({(figs_dir / 'fig_event_study.png').as_posix()})

### 2.3 事件研究的平行趋势诊断

**pre-trend max|t| = {event.get('pre_trend_max_abs_t', 0):.2f}：τ=-3 不显著
（-0.0019, p=0.33），τ=-2 轻微为负（-0.0069，约为 post 效应的 1/8）——
平行趋势近似成立，无正向预期。残余的 τ=-2 负值若反映"被辐射区域处于衰退
走廊"，则共同区域冲击会贡献部分 post 下行；因此把点估计读作**关联证据**，
严格因果留给 IV/匹配 / Callaway–Sant'Anna 类设计。**

## 3. H3 R8 截面空间计量

### 3.1 OLS → LM 检验

""").strip() + "\n"

    ols = spatial.get("ols", {})
    report += f"""
| 检验 | 统计量 | p |
|---|---|---|
| LM-Lag | {ols.get('LM_Lag', {}).get('stat', 'n/a'):.4g} | {ols.get('LM_Lag', {}).get('p', 'n/a'):.3g} |
| LM-Error | {ols.get('LM_Error', {}).get('stat', 'n/a'):.4g} | {ols.get('LM_Error', {}).get('p', 'n/a'):.3g} |
| Robust LM-Lag | {ols.get('Robust_LM_Lag', {}).get('stat', 'n/a'):.4g} | {ols.get('Robust_LM_Lag', {}).get('p', 'n/a'):.3g} |
| Robust LM-Error | {ols.get('Robust_LM_Error', {}).get('stat', 'n/a'):.4g} | {ols.get('Robust_LM_Error', {}).get('p', 'n/a'):.3g} |

LM 决策：{spatial.get('chosen', '?')}（手算 LM，手册 §5.2 建议偏向 Robust 显著者）

### 3.2 模型对比

{sdm_table}

### 3.3 残差 Moran's I

""".strip() + "\n"
    mi = spatial.get("residuals_morans_i", {})
    report += f"""
I = {mi.get('I', 'n/a'):.4g}, E[I] = {mi.get('E_I', 'n/a'):.4g}, z_sim = {mi.get('z_sim', 'n/a'):.3g}, p_sim = {mi.get('p_sim', 'n/a'):.3g}

**解读**：p_sim < 0.05 → OLS 残差仍存在空间自相关，必须报告空间模型系数。

### 3.4 效应分解（direct / spillover / total）

""".strip() + "\n"
    for k, v in decomp.items():
        if isinstance(v, dict) and "direct_effect" in v:
            report += f"- {k}: direct = {v['direct_effect']:+.4g}, spillover = {v['spillover_effect']:+.4g}, total = {v['total_effect']:+.4g}, spillover_share = {v.get('spillover_share', 'n/a')}\n"

    report += f"""

**SAR ρ 异常说明**：spreg.GM_Lag 在 30k×30k KNN 稀疏网络上数值不稳（ρ 常不在 (0,1)）。本研究的 SAR 给出 ρ = {spatial.get('sar', {}).get('rho', 'n/a'):.4g}（pseudo-R² = {spatial.get('sar', {}).get('r2', 'n/a'):.4g}），其一阶近似的溢出项（spill≈-0.002）也不稳健；**本研究仅把 SLX 的 W_treat = 0.0073 (p=0.009) 作为邻 cell 溢出的代理（正）**。

## 4. 距离带敏感性

""".strip() + "\n"
    report += f"""
{sens.get('main_choice', '—')}
{sens.get('rings_alternative', {}).get('fine', [])} 主回归 = treat_strength（中等环）
{sens.get('coordinate_precision', {})}
""".strip() + "\n"

    report += f"""

衰减曲线：![attenuation]({(figs_dir / 'fig_attenuation_curve.png').as_posix()})

事件强度 τ 衰减：![tau]({(figs_dir / 'fig_event_attenuation.png').as_posix()})

## 5. 可视化

Kepler.gl 自包含 HTML（关闭事件 + H3 R8 cells）：{kepler_path.as_posix()}

静态图：
- ![TWFE coef]({(figs_dir / 'fig_twfe_coef.png').as_posix()})
- ![Event study]({(figs_dir / 'fig_event_study.png').as_posix()})
- ![Attenuation]({(figs_dir / 'fig_attenuation_curve.png').as_posix()})
- ![Residual Moran]({(figs_dir / 'fig_residual_moran.png').as_posix()})
- ![Spatial compare]({(figs_dir / 'fig_spatial_compare.png').as_posix()})
- ![Event attenuation]({(figs_dir / 'fig_event_attenuation.png').as_posix()})

## 6. 已知限制 & 必须声明

""".strip() + "\n"

    report += dedent("""
    ① **事件前 τ=-2 轻微为负（-0.0069, p<0.001；τ=-3 不显著）**：平行趋势
       近似通过但非理想。若被辐射区域本身处于衰退走廊，共同区域冲击会贡献
       部分 post 下行 → TWFE/事件研究点估计为**关联证据**而非严格因果。
       修正方向：事件前窗口、IV/匹配、或 Callaway–Sant'Anna 类 staggered 估计。
    ② 存款转移 ≠ 区域净增：网点层负 ATT 说明存款**没有留在原地理邻域**；
       聚合层 SLX 的 W_treat 为正提示更广尺度再配置——两者均不直接对应
       区域存款总量或 ROI，不据此报区域增长红利。
    ③ SAR 在大稀疏 KNN 上 ρ 数值不稳，不据 SAR 报溢出量级；
       仅以 SLX 的 W_treat 作为邻 cell 溢出的代理（正）。
    ④ 网点关闭≠ROI/干预阈值：成本参数（网点重置、客户获取成本、CAC）缺失。
    ⑤ spatial 权重的选择（KNN vs rook vs queen vs 反距离）可能影响结论。
       本研究使用 KNN(k=6)，未对比其他权重方案——稳健性证明应另行加入。
    ⑥ 1994–2015 横跨 2008 金融危机，可能存在 break；后续需结构性断点检测。
    ⑦ 事件研究未加 bootstrap CI；显著性部分来自大样本，应补 bootstrap 重抽样。
""").strip() + "\n"

    p = REP_DIR / "technical_report.md"
    p.write_text(report, encoding="utf-8")
    log(f"    saved → {p}")
    return p


# --------------------------------------------------------------------------- #
# 3) replication 包（preconditions / command / tree）
# --------------------------------------------------------------------------- #
def write_replication_manifest(est: dict) -> Path:
    log("  [7.3] replication manifest + README")
    manifest = {
        "project": "project1_fdic_spatial",
        "preconditions": [
            "datakit（项目根 venv）含：pandas, numpy, scipy, statsmodels, linearmodels, libpysal>=4.12, esda, spreg>=1.9, h3",
            "Windows / PowerShell；可执行 E:\\workspace\\workbuddy\\project\\data_use\\datakit\\.venv\\Scripts\\python.exe",
            "上游产物存在 (project1_fdic_spatial/output/data/ 下 *.parquet 与 *.csv)",
            "内存：事件-长表 ~ 200MB；H3 R8 截面对 ~ 800MB；建议机器 ≥ 16GB",
            "网络：可下载 kepler.gl@3.2.0 UMD bundle（首次打开 HTML）",
        ],
        "commands": {
            "end_to_end": "python main.py",
            "stage_06": "python main.py --stage 06",
            "stage_07": "python main.py --stage 07",
            "stage_08": "python main.py --stage 08",
        },
        "stages": [
            {"stage": "01_discover", "output": "01_discover/output/{catalog.yaml,catalog.md,files.csv}"},
            {"stage": "02_profile", "output": "02_profile/output/{profile.yaml,fields.csv,nulls.csv,outliers.csv,violations.csv}"},
            {"stage": "03_clean", "output": "03_clean/output/{clean_report.md,decisions.yaml,impact.yaml,cleaned.csv}"},
            {"stage": "04_validate", "output": "04_validate/output/{validation.yaml,comparison.yaml,before_after.csv}"},
            {"stage": "05_map", "output": "05_map/output/{map.yaml,lineage.csv,fields.csv,mapped.csv,data/}"},
            {"stage": "06_estimate", "output": "06_estimate/output/{estimate.json,metrics.json,replication_manifest.json}"},
            {"stage": "07_visualize", "output": "07_visualize/output/{manifest.json,figures/*,kepler/kepler_map.html}"},
            {"stage": "08_conclude", "output": "08_conclude/output/{conclusion.md,technical_report.md,short_essay.md}"},
        ],
        "expected_outputs": {
            "twfe_post_x_strength_beta": est["twfe"]["params"].get("post_x_strength"),
            "twfe_post_x_strength_p": est["twfe"]["pvalues"].get("post_x_strength"),
            "sar_rho": est["spatial_fits"].get("sar", {}).get("rho"),
            "sem_lambda": est["spatial_fits"].get("sem", {}).get("lambda"),
            "slx_w_treat": (est["spatial_fits"].get("slx", {}).get("params", {})
                            .get("W_treat_strength")),
            "residuals_morans_i_p": (est["spatial_fits"].get("residuals_morans_i", {})
                                       .get("p_sim")),
        },
    }
    p = REP_DIR / "replication_manifest.json"
    p.write_text(json.dumps(manifest, ensure_ascii=False, indent=2),
                 encoding="utf-8")
    log(f"    saved → {p}")
    return p


# --------------------------------------------------------------------------- #
# 4) conclusion.md —— 结论 + 已知限制 / 止损条件（规范 §8.5）
# --------------------------------------------------------------------------- #
KNOWN_LIMITS = [
    "事件前 τ<0 存在轻微负向系数 → 平行趋势近似但非理想；区域共同冲击可能贡献 post 下行，"
    "点估计属**关联证据**而非严格因果。",
    "存款转移 ≠ 区域净增：网点层负效应 + 聚合层正 spillover → 存款在更广尺度再配置，"
    "不据此报区域增长红利或 ROI。",
    "SAR 在大稀疏 KNN 上 ρ 数值不稳定；不以 SAR 报溢出量级。",
    "不承诺 ROI、不承诺干预阈值（成本参数缺失）。",
    "坐标最高精度占比 < 100%（2023–2025 EXACT 85.98%；1994–2022 屋顶级仅 16.37%，"
    "且编码词表 2023 年切换不可跨年代比较）→ < 1 km 距离环可能偏差，主表用 5 km 中等环。",
    "UNINUMBR 缺失 120,261 行（4.26%）100% 集中在 1994–2010 → 早年样本系统性不可追踪。",
    "事件研究未加 bootstrap CI，显著性部分来自大样本。",
    "空间权重仅用 KNN(k=6)，未对比其他权重方案。",
]

STOP_CONDITIONS = [
    "若把本结论用于**因果断言**（如「关闭导致存款流失 X%」）→ 停止：先补 IV/匹配或 "
    "Callaway–Sant'Anna 类 staggered 估计。",
    "若把点估计换算为**区域存款净增 / ROI / 干预阈值** → 停止：成本参数缺失，量纲不成立。",
    "若用 **SAR 的 ρ 或一阶近似溢出量级**报数 → 停止：数值不稳，仅以 SLX 的 W_treat 作代理。",
    "若事件研究 τ<0 出现**显著且量级接近 post** 的系数 → 停止因果解读，改报描述性差异。",
]


def write_conclusion(est: dict, manifest: dict) -> tuple[Path, Path]:
    """产出 ``conclusion.md``（人读）+ ``conclusion_report.json``（机读）。"""
    log("  [8.4] 结论（含已知限制 / 止损条件）")
    twfe, fits = est["twfe"], est["spatial_fits"]
    es_table = est.get("event_study", {}).get("table", [])
    tau0 = next((r["dynamic_effect"] for r in es_table if r["rel_year"] == 0), float("nan"))
    tau4 = next((r["dynamic_effect"] for r in es_table if r["rel_year"] == 4), float("nan"))
    post = twfe["params"].get("post", float("nan"))
    w_treat = (fits.get("slx", {}).get("params", {}) or {}).get("W_treat_strength", float("nan"))
    mi_p = fits.get("residuals_morans_i", {}).get("p_sim", float("nan"))

    headline = (f"10 km 内同业关闭事件后，被辐射存活网点存款增速显著下行并逐年加深"
                f"（τ=0 {tau0 * 100:+.3g} pp → τ=4 {tau4 * 100:+.3g} pp；TWFE post {post * 100:+.3g} pp）；"
                f"聚合层 SLX 的 W_treat {w_treat:+.4g} 为正 → 存款在更广尺度**再配置**而非区域净增。"
                f"事件前轻微趋势 + 区域共同冲击 → **关联证据，非严格因果**。")

    md = dedent(f"""
# ⑧ 结论 · project1_fdic_spatial

> 生成时间：{_dt.datetime.now().isoformat(timespec="seconds")}
> 上游：`06_estimate/output/estimate.json`、`07_visualize/output/manifest.json`

## 一句话结论

> {headline}

## 关键数字

| 指标 | 值 |
|---|---|
| TWFE post | {post:+.4g}（{_fmt_p(twfe['pvalues'].get('post'))}）|
| TWFE post × strength | {twfe['params'].get('post_x_strength', float('nan')):+.4g}（{_fmt_p(twfe['pvalues'].get('post_x_strength'))}）|
| 事件研究 τ=0 | {tau0 * 100:+.3g} pp |
| 事件研究 τ=4 | {tau4 * 100:+.3g} pp |
| SLX W_treat_strength | {w_treat:+.4g} |
| 残差 Moran's I p_sim | {mi_p:.3g} |

## 已知限制（必须阅读）

""").strip() + "\n"
    md += "\n".join(f"{i}. {t}" for i, t in enumerate(KNOWN_LIMITS, 1))

    md += "\n\n## 止损条件（出现下列用法即停止）\n\n"
    md += "\n".join(f"- {t}" for t in STOP_CONDITIONS)

    md += dedent(f"""

## 完整报告

- 短论：`short_essay.md`
- 技术报告：`technical_report.md`
- 可视化清单：`../07_visualize/output/manifest.json`（{manifest.get('n_figures', 0)} 图）
""")
    p = REP_DIR / "conclusion.md"
    p.write_text(md, encoding="utf-8")

    report = {
        "stage": STAGE,
        "generated_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "headline": headline,
        "key_numbers": {
            "twfe_post": post, "twfe_post_p": twfe["pvalues"].get("post"),
            "twfe_post_x_strength": twfe["params"].get("post_x_strength"),
            "event_study_tau0": tau0, "event_study_tau4": tau4,
            "slx_w_treat_strength": w_treat, "residuals_morans_p_sim": mi_p,
        },
        "known_limits": KNOWN_LIMITS,
        "stop_conditions": STOP_CONDITIONS,
        "artifacts": ["conclusion.md", "short_essay.md", "technical_report.md",
                      "replication_manifest.json", "conclusion_report.json"],
        "conclusion": headline,
    }
    pj = dk.write_json(REP_DIR, "conclusion_report", report)
    log(f"    saved → {p.name} / {pj.name}")
    return p, pj


# --------------------------------------------------------------------------- #
# 主流程
# --------------------------------------------------------------------------- #
def run(project) -> dict:
    """只读 ⑥⑦ 的产物，产出短论 / 技术报告 / 结论与已知限制。"""
    log("=" * 60)
    log(f"[{STAGE}] {TITLE}")
    est = _read_estimate()
    manifest = _read_manifest()
    write_short_essay(est)
    write_technical_report(est, manifest)
    write_replication_manifest(est)
    write_conclusion(est, manifest)
    log("完成 ⑧ 全部产出。")
    return {
        "stage": STAGE, "blocking": False,
        "conclusion": _conclude_line(est),
        "artifacts": ["conclusion.md", "conclusion_report.json",
                      "technical_report.md", "short_essay.md", "replication_manifest.json"],
    }


def _conclude_line(est: dict) -> str:
    """给 SUMMARY.md 用的一句话结论。"""
    twfe = est["twfe"]
    es_table = est.get("event_study", {}).get("table", [])
    tau0 = next((r["dynamic_effect"] for r in es_table if r["rel_year"] == 0), float("nan"))
    tau4 = next((r["dynamic_effect"] for r in es_table if r["rel_year"] == 4), float("nan"))
    return (f"同业关闭后周边存活网点存款增速下行（τ=0 {tau0 * 100:+.3g}pp → τ=4 {tau4 * 100:+.3g}pp；"
            f"TWFE post {twfe['params'].get('post', float('nan')) * 100:+.3g}pp）；"
            f"聚合层再配置而非区域净增 → 关联证据，非严格因果")


def main() -> None:
    project = dk.Project.load(ROOT)
    print(run(project))


if __name__ == "__main__":
    main()
