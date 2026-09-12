# 方案⑤⑥⑦·FDIC 网点关闭对周边存款增量的因果与空间效应 · 技术报告

> 项目：`project1_fdic_spatial` · 遵循 `docs/churn_methodology_handbook.html` (§3, §5, §7, §10, §12)

## 0. 摘要

数据集基础（来自上游 `05_map/output/data/` 与 `06_estimate/output/data/`）：

| artifact | rows |
|---|---|
| `branch_year_panel.parquet` | 2,702,716 |
| `branch_dim.csv` | 152,538（alive_censored 76,097；attrition_missing 46,828；closed_ma 29,613）|
| `closure_exposure.csv` | 27,018 起关闭事件（H3 cells 70,109）|
| `spatial_cross_section.parquet` | 51,251 H3 R8 cells（2010→2014 截面）|
| `did_panel.parquet` | 1,814,985 存续网点-年 |

**识别说明（与早期草稿的重要修正）**

    · 处理组 = 存续网点（alive_censored）中首次被 10 km 内同业关闭事件
      辐射者（KDTree + haversine 空间配对，330,691 对）；
    · 关闭网点自身不做 outcome（关闭后无观测，避免把"死亡"当效应）；
    · post = YEAR ≥ first_event_year；强度 = 首次辐射年环加权同业关闭强度。

主结果一句话：**同业关闭事件发生后，被辐射存活网点的存款增速显著下行且逐年
加深（事件研究 τ=0 约 -4.4pp → τ=4 约 -10.1pp；TWFE post ≈ -0.053，
p<0.001）；post × strength 交互为正（+0.014），提示处理强度更高的网点
负效应更缓和。聚合 H3 cell 层 SLX 的 W_treat 为正 → 存款在更广地理尺度
再配置。事件前 τ=-2 显著为负 + 区域共同冲击未排除 → 关联证据而非严格因果。**

## 1. 模型总览

```text
{
  "primary": "TWFE (entity + time FE) post × treat_strength；处理组 = 10km 内同业关闭事件辐射的存续网点",
  "event_study": "branch-level event-time dummies (within entity+time demean + cluster)",
  "spatial": [
    "OLS",
    "SAR (GM_Lag)",
    "SEM (GM_Error)",
    "SLX (OLS + W·X)"
  ],
  "model_selection": "Robust LM-Lag vs LM-Error + 都显著时升 SDM（手册 §5.2 / §7.3 建议）；SAR 不稳时以 SLX 的 W·X 代理溢出",
  "thresholds": [
    "POST_WINDOW = 4 年（事件后窗口）",
    "PRE_WINDOW = 3 年（事件前窗口，预期效应检查）",
    "COHORT ∈ [1994, 2020]（留 5 年 post 余量）",
    "SPATIAL_T=2010→2014；处理源 = (2007, 2010)",
    "KNN_K = 6"
  ]
}
```

## 2. TWFE + 事件研究

### 2.1 TWFE（linearmodels.PanelOLS）

**双向固定效应（UNINUMBR + YEAR）+ 聚类稳健 SE（cluster on UNINUMBR）。
y = dep_chg_rate（clip ±50pp）；回归量 post × strength。**
**Caution：平行趋势近似通过但 τ=-2 显著为负，共同区域冲击未完全排除
→ 该 β 为关联证据，见 2.3。**

| 参数 | 系数 | SE | t | p |
|---|---|---|---|---|
| post_x_strength | +0.01382 | 0.001712 | 8.075 | p<0.001 |
| post | -0.05259 | 0.001643 | -32.01 | p<0.001 |
n_obs = 955025, n_entities = 73324, n_times = 31, R²_within = 0.003054.

### 2.2 事件研究（网点级 event-time dummies，TWFE 同一识别框架）

事件研究结果表（baseline = τ=-1；τ<0 为事件前，应接近 0）：

τ | dynamic effect
---|---
-3 | -0.001891
-2 | -0.006882
-1 | +0
+0 | -0.0438
+1 | -0.04304
+2 | -0.0736
+3 | -0.08929
+4 | -0.1007


事件研究图：![event study](../07_visualize/output/figures/fig_event_study.png)

### 2.3 事件研究的平行趋势诊断

**pre-trend max|t| = 4.12：τ=-3 不显著
（-0.0019, p=0.33），τ=-2 显著为负（-0.0069，约为 post 效应的 1/8）——
平行趋势近似成立，无正向预期。残余的 τ=-2 负值若反映"被辐射区域处于衰退
走廊"，则共同区域冲击会贡献部分 post 下行；因此把点估计读作**关联证据**，
严格因果留给 IV/匹配 / Callaway–Sant'Anna 类设计。**

## 3. H3 R8 截面空间计量

### 3.1 OLS → LM 检验
| 检验 | 统计量 | p |
|---|---|---|
| LM-Lag | 38.95 | 4.34e-10 |
| LM-Error | 0.00149 | 0.969 |
| Robust LM-Lag | 0.07914 | 0.778 |
| Robust LM-Error | 0.07914 | 0.778 |

LM 决策：ols（手算 LM，手册 §5.2 建议偏向 Robust 显著者）

### 3.2 模型对比

model | pseudo R² | n | 关键参数 | 备注
---|---|---|---|---
OLS | 0.03091 | 30000 |  |
SAR (GM_Lag) | 0.01084 | 30000 | rho=-0.1701 |
SEM (GM_Error) | 0.03084 | 30000 | lambda=0.2001 |
SLX (OLS+W·X) | 0.03697 | 30000 | W_treat=0.008986 |


### 3.3 残差 Moran's I
I = 0.07033, E[I] = -3.333e-05, z_sim = 23.3, p_sim = 0.001

**解读**：p_sim < 0.05 → OLS 残差仍存在空间自相关，必须报告空间模型系数。

### 3.4 效应分解（direct / spillover / total）
- sar_approx: direct = +0.006739, spillover = -0.0009799, total = +0.005759, spillover_share = -0.1701324779388358
- sem: direct = +0.007131, spillover = +0, total = +0.007131, spillover_share = n/a
**SAR ρ 异常说明**：spreg.GM_Lag 在 30k×30k KNN 稀疏网络上数值不稳（ρ 常不在 (0,1)）。本研究的 SAR 给出 ρ = -0.1701（pseudo-R² = 0.01084），其一阶近似的溢出项（spill≈-0.002）也不稳健；**本研究仅把 SLX 的 W_treat = 0.008986（p=0.00126）作为邻 cell 溢出的代理（正）**。注意：`estimate.json` 里另有 OLS 的 `treat_strength`（≈0.00731，混合值），两者口径不同、不可互换 —— 早期版本曾把该 OLS 系数误写成本行的 SLX W_treat，现已改为从 `spatial_fits.slx.params` 直接取值。

## 4. 距离带敏感性
5 km 内关闭事件 cell 数；标准环与合并环两套口径见 06_visualize.py
['0_1', '1_3', '3_5', '5_10'] 主回归 = treat_strength（中等环）
{'top_precision_pct_by_era': {'2023-2025_EXACT': 0.8598, '1994-2022_US_Rooftop': 0.1637, '1994-2022_US_Streets': 0.3157, '1994-2022_US_Zipcode': 0.0497}, 'explanation': 'SIMS_PROJECTION 取值词表 2023 年切换，不可跨年代直接比较；早年多为插值坐标 → <1 km 距离环存在系统性失真；主表用 5 km 中等环。旧口径『EXACT 占 45.45%』已作废（混淆编码切换与样本退出时间）', 'supersedes': 'EXACT_pct_45.45'}
衰减曲线：![attenuation](../07_visualize/output/figures/fig_attenuation_curve.png)

事件强度 τ 衰减：![tau](../07_visualize/output/figures/fig_event_attenuation.png)

## 5. 可视化

Kepler.gl 自包含 HTML（关闭事件 + H3 R8 cells）：../07_visualize/output/kepler/kepler_map.html

静态图：
- ![TWFE coef](../07_visualize/output/figures/fig_twfe_coef.png)
- ![Event study](../07_visualize/output/figures/fig_event_study.png)
- ![Attenuation](../07_visualize/output/figures/fig_attenuation_curve.png)
- ![Residual Moran](../07_visualize/output/figures/fig_residual_moran.png)
- ![Spatial compare](../07_visualize/output/figures/fig_spatial_compare.png)
- ![Event attenuation](../07_visualize/output/figures/fig_event_attenuation.png)

## 6. 已知限制 & 必须声明
① **事件前 τ=-2 显著为负（-0.0069, p<0.001；τ=-3 不显著）**：平行趋势
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
