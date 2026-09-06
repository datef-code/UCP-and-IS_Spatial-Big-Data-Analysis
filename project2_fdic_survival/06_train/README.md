# 06_train · ⑥ 训练 / 估计（离散时间生存模型）

> 项目：[project2_fdic_survival](../README.md)　|　规范：`datakit/PROJECT_STRUCTURE.md` §8 扩展阶段（插件）

## 定位

**扩展阶段（插件）**：课题专属下游动作，不属于 datakit 内核五阶段（`01`–`05`）。
与内置阶段同构（与目录同名入口 `.py` + `run(project)` + `README.md` + `output/`）。

| 登记项 | 值 |
| --- | --- |
| `stage` | `06_train` |
| `kind` | `modeling` |
| `depends_on` | `05_map` |
| `requires` | `branch_panel.csv`, `bank_fragility.csv` |
| `extras` | `modeling`（statsmodels / scikit-learn / shap / matplotlib） |
| `blocking` | `false`（失败不阻断五阶段，但写进 `SUMMARY.md`） |

## 本阶段做什么

重构「网点-年」长表 → 拟合 **logit**（SGD，稀疏 one-hot）与 **cloglog**（GLM）离散时间风险模型 →
**SHAP** 解释 → **残差 Moran's I** 空间诊断。

## 输入 / 输出

- **输入**：只读 `05_map/output/data/{branch_panel.csv, bank_fragility.csv}`
- **输出**（本阶段 `output/`）：

| 产物 | 内容 |
| --- | --- |
| `metrics.json` | 训练 / 测试的 AUC、C-index、Brier、log-loss、事件率 |
| `replication_manifest.json` | 版本 / 参数 / 随机种子 / 输入指纹（§8.5 必交） |
| `train_report.md` | 人读训练报告（指标 + cloglog + SHAP 排名 + Moran） |
| `logit_pipeline.pkl` | 可复现推理的流水线（对新网点-年行直接 `predict_proba`） |
| `logit_coefficients.csv` | logit 系数（含年份效应） |
| `cloglog_coefficients.csv` / `cloglog_summary.txt` | cloglog 系数 + 95% CI / 完整 summary |
| `shap_values.csv` / `shap_importance.csv` | 逐样本 SHAP 值 / 聚合回原始特征的重要性 |
| `moran_i.json` | 残差空间自相关 + 置换检验 p 值 |
| `test_predictions.csv`、`data/branch_year_panel.parquet` | 测试集预测、面板过程数据 |

## 硬约束

- 只能**读**上游阶段的 `output/`，**禁止回写**；自身产物只进本阶段 `output/`。

## 本阶段口径要点（本次运行）

- 面板 **1,667,283** 网点-年观测（事件率 4.13%），剔除事件早于首次观测的 11,787 个网点（左截断）。
- logit：保留全部事件行的分层下采样 50 万（训练 40 万 / 测试 10 万）→
  **测试 AUC 0.881、C-index 0.810、Brier 0.161**。
- cloglog：206,724 行含全部 68,908 个事件，McFadden 伪 R² 0.387，显著正 / 负因子 25 / 8。
- SHAP：year（宏观 / 监管周期）> 银行层因素（脆弱性、历史关闭率）> 网点规模。
- 残差 **Moran's I = 0.141（p = 0.005，k=8 近邻 + 199 次置换）** → 本地市场因素仍未进入模型。
