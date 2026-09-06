# 03_clean · ③ 清洗

> 项目：[project6_spatial_teaching](../README.md)　|　规范：`datakit/PROJECT_STRUCTURE.md` §2-③

## 本阶段做什么

回答「动了哪些数据、为什么动、动了多少」：按 `config/clean_plan.yaml` 的顺序动作执行清洗，
产出决策日志与按操作 / 按字段的影响汇总。

数据流向（规范 §1）：`data_raw/ → 03_clean`。与阶段 2 共用 `02_profile/loaders.py`
（数字前缀目录不能 `import`，用 `importlib` 按文件路径加载），保证画像与清洗基于同一口径。

## 输入 / 输出

- **输入**：`../data_raw/<dataset>/` + `config/clean_plan.yaml`
- **输出**（`output/<dataset>/`）：

| 路径 | 内容 |
| --- | --- |
| `cleaned.csv` | 过程数据（交付 04 / 05，坐标保留 6 位小数） |
| `clean_report.md` | 决策 + 结果汇总（形状变化 / 空单元格 / 影响 / 禁止项校验） |
| `decisions.yaml` / `decisions.md` | 决策日志：步骤 / 动作 / 字段 / 原因 / 影响行 / 可逆 |
| `impact.yaml` | 按操作、按字段的影响（填充 / 置空 / 截断 / 删除行 / 类型转换） |
| `filled_by_field.csv` / `dropped_by_field.csv` | 填充量与删除量的字段级明细 |

## 运行

```powershell
python main.py --stage 03
```

## 口径要点

- 越界坐标**置空而非截断**（`on_violation: to_null`）：截断会把越界点伪造到边界上。
- 无坐标点**删除**：无法进入 L0 网格化。
- `config/clean_plan.yaml` 的 `forbidden` 声明「坐标不得填充」—— 本阶段会反查计划并报告违规。
- `value` 统一转 `float64`。
