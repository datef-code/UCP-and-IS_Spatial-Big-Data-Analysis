# 02_profile · ② 画像

> 项目：[project6_spatial_teaching](../README.md)　|　规范：`datakit/PROJECT_STRUCTURE.md` §2-②

## 本阶段做什么

回答「字段有哪些、哪些必需、数据质量有多差」：字段等级、空值语义、描述性统计、
**极端值**（统计意义）与**规则违规**（业务意义，两者分开列）。

源数据由同目录 `loaders.py` 统一读成 `points(lat, lon, value)` —— 与阶段 3 共用同一份加载口径，
**不落盘过程数据**（规范数据流向：`data_raw → 03_clean`，阶段 3 自己重读）。

## 输入 / 输出

- **输入**：`../data_raw/<dataset>/`（只读）+ `config/schema.yaml`（等级 / 角色 / 规则 / 抽样日）
- **输出**（`output/<dataset>/`）：

| 路径 | 内容 |
| --- | --- |
| `profile.yaml` / `profile.md` | 机读 + 人读报告（含许可状态、源数据指纹、等级分布） |
| `fields.csv` | 字段清单：类型 / 角色 / **等级** / 非空 / 缺失率 / 唯一值 / 说明 |
| `nulls.csv` | 空值表：按角色解释语义（主键缺失=缺陷、坐标缺失=需处理） |
| `outliers.csv` | 极端值明细（IQR；明细截断 2 万条，总数见 `profile.yaml`） |
| `violations.csv` | 规则违规表：字段 / 等级 / 严重度 / 规则 / 违规数 / 样本 |

## 运行

```powershell
python main.py --stage 02
```

## 口径要点

- 四个数据集统一为三个字段：`lat`（纬度）、`lon`（经度）、`value`（度量值）。
- 等级来自 `config/schema.yaml`：`lat` / `lon` / `value` 均为 `required`（无坐标无法网格化）。
- 异常值方法 `iqr`（`datakit.yaml` 的 `options.outlier_method`）。
- 深圳单车只取**抽样日**（`config/schema.yaml` 的 `sample_day`，默认每月 15 日，共 20 天）；
  全量 30 GB 不做全量载入 —— 这是**合成抽样参数**，结论仅对抽样日成立。
