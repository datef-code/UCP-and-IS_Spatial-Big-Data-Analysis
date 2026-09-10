# 09_interactive · ⑨ 交互展示（扩展阶段）

> 项目：[project2_fdic_survival](../README.md)　|　规范：`datakit/PROJECT_STRUCTURE.md` §8.2 / §8.5 / §8.8
> 立项依据：`datakit/suggestions_for_projects_0908.md` §三 —— 产品 2 是
> **预测模型 / 可解释性产品型**，受众 = 分析师 + 风控 / 决策者，要点是**标注边界**。

- **kind**：`visualization`　**depends_on**：`05_map`、`06_train`
- **requires**：`metrics.json` / `cloglog_summary.txt` / `train_report.md` / `moran_i.json` /
  `conclusion_report.json`（**必需，均入库**）
  `logit_coefficients.csv` / `test_predictions.csv` / `branch_panel.csv`（**可选增强，不入库**）
- **extras**：`viz`（plotly）　**blocking**：false

## 本阶段做什么

让人**相信模型准（性能）、理解为什么（可解释）、能上手试（demo）**，并且把
「这是打分、不是命运」的边界写在页面上。⑨ 只读上游产物，不重训模型、不回写上游。

| 产物 | 回答什么 | 交互点 |
| --- | --- | --- |
| `output/index.html` | **决策驾驶舱**：值不值得信、能怎么用、边界在哪 | KPI（AUC/C-index/Brier/Moran's I）+ 一句话结论 + **王牌 demo 内嵌** + 年份效应图 + 产品矩阵 + 边界速览 + 复现清单 |
| `output/predict_demo.html` | 给定特征，这个网点明年关闭风险多少？（**王牌**） | 拖滑块 / 选档位 → 实时风险 + 逐特征贡献分解 + **单因素敏感性 tornado**（纯前端，离线可算） |
| `output/shap_force.html` | 模型凭什么说它风险高？ | 全局 SHAP 重要性（对数轴）+ 三个真实样本分解，红推高蓝压低 |
| `output/model_report.html` | 模型够不够用？ | **年份效应（带 95% CI）** + 非年份因子森林 + 性能指标 + 残差 Moran's I |
| `output/guardrails.html` | 什么情况下**不能**用？ | 8 条已知限制 + 5 条止损条件 + 正确/错误用法对照 |
| `output/km_roc.html` | 谁先死、模型分得开吗？ | KM 分层存活曲线 + 年度基准风险 + 测试集区分度 |
| `output/risk_evolution.html` | 关闭在时间上怎么分布？ | mp4 内嵌：年度关闭柱 + 风险分布同步推进，标出 2009–2014 整合窗口 |

## 代码结构（为什么要拆 3 个模块）

| 模块 | 职责 |
| --- | --- |
| `studio_data.py` | 数据层 + 降级策略（**头号问题：本阶段原本缺 CSV 会直接 FileNotFoundError**） |
| `studio_ui.py` | 设计令牌 + 组件（风控看板风格：KPI 卡 / 护栏卡 / 风险条） |
| `studio_figs.py` | 交互件 |
| `09_interactive.py` | 编排入口（规范要求与目录同名）+ logit 主模型路径 + 演化动图 |

## 关键口径与决策理由

1. **唯一入库权威源**：`metrics.json`、`moran_i.json`、`replication_manifest.json`、
   **`cloglog_summary.txt`（完整系数表，含 95% CI，可解析）**、
   **`train_report.md`（SHAP 重要性表，可解析）**、`shap_force.json`（3 个真实样本的
   SHAP 分解）、`08_conclude/output/conclusion_report.json`（8 限制 + 5 止损）、
   `07_visualize/output/figures/*.png`、`05_map/output/map.md`（**字段真实取值区间**）、
   `02_profile/output/profile.yaml`（min / std）。
2. **样本级 CSV 不入库 → 必须降级，不能崩**。`logit_coefficients.csv` /
   `test_predictions.csv` / `branch_panel.csv` / `cloglog_coefficients.csv` 受仓库根
   `.gitignore` 的 `*/*/*/*.csv` 约束不入库，重跑 ⑤⑥ 又要 1.58 GB 原始数据。
   因此：
   * 打分台 → 用 **cloglog 真实系数**构造（区间来自 `map.md` 与 `profile.yaml`，**不猜**）；
   * KM/ROC/动图 → 降级为上游 ⑦ 静态图 + 显式披露；
   * 有 CSV 时自动升级为 logit 主模型 demo（含 **AUC 保真度自检**）。
3. **保真度自检（硬约束，仅 logit 路径）**：用测试集复算 AUC，与 `metrics.json` 的
   0.8814 对照，**差值 > 0.02 直接抛错拒绝产出**。实测复现 AUC = 0.8815（差 0.0000）。
4. **截距为什么是校准出来的**（logit 路径）：模型产物未保存截距（只导出了 feature/coef），
   因此用测试集事件率反解。自洽，因为 AUC 与排序无关，校准只影响概率绝对值 —— 页面已标注。
5. **概率绝对值不能当业务概率**（cloglog 路径）：cloglog 拟合样本事件率 33.3%
   （面板事件率只有 4.13%，训练做了分层下采样），所以页面明确写
   「只看方向与相对量级」。这是本项目一贯的克制，不能因为做了 demo 就丢掉。
6. **年份效应为什么单独出一张图**：本课题最反直觉的发现是「**什么时候**比**多老**更重要」。
   旧版把年份虚变量和其它因子混在 top-18 森林图里，这个结论被淹没了。
   现在年份做成带 CI 的时间序列图，2009–2014 的抬升一眼可见。
7. **森林图刻意剔除 `bank_closed_rate`**：它的系数 3.82 比其余（|coef| ≤ 0.87）
   大一个量级，混画会把其余压成一条线 —— 改为单独一张「主导因子」卡。
8. **贡献分解为什么等于 SHAP**：线性模型的 SHAP 就是 `coef × (标准化后的特征值)`，
   各项之和 + 截距 = 线性预测器。所以分解是**精确的**，不是近似。
9. **plotly.js 全站共享一份** `output/assets/vendor/plotly.min.js`：
   单份 4.3 MB，逐页内联 = 十几 MB；共享后可命中缓存（驾驶舱里嵌的 iframe 第二次打开是瞬时的）。
   代价：**自包含单元改为整个 `output/` 目录**（配图在 `output/assets/fig/`）。
10. **退化系数必须剔除**：`cloglog_summary.txt` 里 2016–2025 的年份虚变量是
    **完美分离**导致的数值伪影（系数 ≈ −26、标准误 ≈ 4e4、p ≈ 1），
    不剔除会毁掉森林图与 demo 的档位列表。

## 输入 / 输出

- **输入（只读）**：`06_train/output/{metrics,moran_i,replication_manifest}.json`、
  `cloglog_summary.txt`、`train_report.md`、`08_conclude/output/conclusion_report.json`、
  `07_visualize/output/figures/*.png`、`05_map/output/map.md`、
  `02_profile/output/profile.yaml`；可选 `06_train/output/{logit_coefficients,test_predictions}.csv`、
  `05_map/output/data/branch_panel.csv`
- **输出**：`output/{index, predict_demo, shap_force, model_report, guardrails, km_roc,
  risk_evolution}.html` + `output/assets/{fig,vendor}/` + `output/manifest.json`
- 所有页面共享一套设计令牌，离线可开；`output/` 整体可拷走。

## 运行

```powershell
.\.venv\Scripts\python.exe ..\project2_fdic_survival\main.py --stage 09
```

缺样本级 CSV 时日志会写
`缺样本级 CSV（4/4）… → 依赖它们的面板降级`，属**预期降级**，不是失败；
打分台会自动改用 cloglog 真系数（页面顶部标注所用模型）。
