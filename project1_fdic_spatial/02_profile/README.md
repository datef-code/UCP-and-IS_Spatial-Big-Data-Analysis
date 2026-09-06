# 02_profile · ② 画像

> 规范：`datakit/PROJECT_STRUCTURE.md` §2-②。入口：`02_profile.py`。

## 做什么

回答「字段有哪些、哪些必需、数据质量有多差」：字段清单（含 `schema.yaml` 的等级）、
等级分布、空值分析（按角色解释语义）、描述性统计、极端值 / 异常值（**统计意义**）、
规则违规（**业务意义**，由 `datakit.schema` 检验人的口径）。

## 输入

- `../data_raw/fdic/*.csv`（只读）

## 输出

| 文件 | 说明 |
| --- | --- |
| `output/profile.yaml` / `profile.md` | 画像报告（**先看 md**） |
| `output/fields.csv` | 字段清单：类型 / 角色 / 等级 / 缺失率 / 唯一值 / 描述统计 |
| `output/nulls.csv` | 空值表（含按角色解释的语义：主键缺失=缺陷，事件缺失=右删失） |
| `output/outliers.csv` | 极端值逐字段汇总（方法 + 上下界 + 异常数） |
| `output/violations.csv` | 规则违规表：字段 / 等级 / 严重度 / 规则 / 违规数 / 样本 |
| `output/raw_long.parquet` | **过程数据**：导入后的长表，供 ③ 复用（避免 1.6 GB 二次 IO） |

## 口径

- 等级（required / important / optional / ignore）来自 `config/schema.yaml`；
  角色回灌给画像，决定空值语义。
- 异常值方法 `iqr`，可在 `datakit.yaml` 的 `options.outlier_method` 切换。

## 怎么跑

```powershell
python main.py --stage 02
```
