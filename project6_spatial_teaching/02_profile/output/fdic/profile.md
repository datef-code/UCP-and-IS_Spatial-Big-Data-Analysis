# ② 画像报告 · fdic

> 生成时间：2026-09-08T10:18:38　异常值方法：`iqr`

**许可状态**：公共领域（美国联邦政府数据），可商用　限制：示例可自由分发
　**度量语义**：网点是否关闭（0/1，按 UNINUMBR 聚合）

## 概要

- 行数 152,538　列数 3　空单元格 8,798（1.92%）
- 极端值 8,964　规则违规 3
- 等级分布：required 3

## 字段清单（含等级 / 问题数）

| 字段 | 类型 | 角色 | 等级 | 非空 | 缺失率 | 唯一值 | 问题数 | 说明 |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| lat | float64 | spatial | required | 148,139 | 2.88% | 143,947 | 3 | 纬度（清洗后统一命名，源字段 lat / SIMS_LATITUDE / START_LAT） |
| lon | float64 | spatial | required | 148,139 | 2.88% | 144,164 | 3 | 经度（清洗后统一命名，源字段 lng / SIMS_LONGITUDE / START_LNG） |
| value | int64 | numeric | required | 152,538 | 0.00% | 2 | 0 | 聚合到格的度量值（各数据集语义不同，见 per_dataset） |

## 字段角色 / 等级判定依据（规范 §3.5）

| 字段 | 角色 / 等级 | 说明 | 判定依据 |
| --- | --- | --- | --- |
| `lat` | spatial / required | 纬度（清洗后统一命名，源字段 lat / SIMS_LATITUDE / START_LAT） | 同 lon：承担全部空间结构，required；禁止填充，越界置空。 |
| `lon` | spatial / required | 经度（清洗后统一命名，源字段 lng / SIMS_LONGITUDE / START_LNG） | 判为 spatial+required：本教程的全部内容（L0 网格化 → L1 权重 → L2 滞后 → L3 距离环） 都以坐标为起点，缺它整条主线无法启动。故 not_null 是 P0， 越界值 `to_null` 而非截断、且**明令禁止 fill**（填充会伪造位置）。 |
| `value` | numeric / required | 聚合到格的度量值（各数据集语义不同，见 per_dataset） | 判为 numeric+required：格值是 L0 聚合、L2 空间滞后、L3 溢出密度的唯一输入， 缺它所有指标不可得。语义随数据集变化（0/1 关闭标记 vs 骑行/签到计数）， 因此统一命名但语义必须查 per_dataset——这是本项目「一套流程跑 N 个数据集」的关键约定。 |

## 空值语义（按角色）

| 字段 | 空值数 | 缺失率 | 角色 | 语义 |
| --- | ---: | ---: | --- | --- |

## 极端值（统计意义）

| 字段 | 异常数 |
| --- | ---: |
| lon | 7,612 |
| lat | 1,352 |

> 明细见 `outliers.csv`（截断 20,000 条）。

## 规则违规（业务意义）

| 字段 | 等级 | 严重度 | 规则 | 违规数 | 占比 | 样本 |
| --- | --- | --- | --- | ---: | ---: | --- |
| lon | required | P0 | not_null | 4,399 | 2.8839% | [nan, nan, nan, nan, nan] |
| lat | required | P0 | geo_lat | 2 | 0.0013% | ['158.227518485', '138.097'] |
| lat | required | P0 | not_null | 4,399 | 2.8839% | [nan, nan, nan, nan, nan] |
