# 08_conclude · ⑧ 结论

> 项目：[project2_fdic_survival](../README.md)　|　规范：`datakit/PROJECT_STRUCTURE.md` §8 / §8.5

## 定位

| 登记项 | 值 |
| --- | --- |
| `stage` | `08_conclude` |
| `kind` | `conclusion` |
| `depends_on` | `06_train`, `07_visualize` |
| `requires` | `metrics.json` |
| `blocking` | `false` |

## 本阶段做什么

把 ①–⑦ 的产物收敛为**一句话交付**：结论 + 关键数字 + 三条可操作结论 +
**已知限制** + **止损条件**（结论必须带约束）。

## 输入 / 输出

- **输入**：只读 `05_map/output/map.yaml`、`06_train/output/{metrics.json, moran_i.json,
  shap_importance.csv, replication_manifest.json}`、`07_visualize/output/manifest.json`
- **输出**（本阶段 `output/`）：

| 产物 | 内容 |
| --- | --- |
| `conclusion.md` | 人读：一句话结论、关键数字、可操作结论、已知限制、止损条件 |
| `conclusion_report.json` | 机读：同上 + `conclusion` 字段（供 `SUMMARY.md` 引用） |

## 本阶段口径要点

- 数字全部**从上游产物读取**（不硬编码），换数据重跑后报告自动更新。
- 已知限制写 8 条（左截断、死亡年口径、CERT 归属、右删失比例、事件率与抽样、
  残差空间自相关、非因果、坐标缺失）。
- 止损条件写 5 条：读成因果、换算 ROI / 干预阈值、跨口径比 AUC、解读早年年份效应、用 KM 尾部下结论。
