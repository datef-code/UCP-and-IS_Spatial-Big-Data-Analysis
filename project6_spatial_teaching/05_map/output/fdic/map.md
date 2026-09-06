# ⑤ 映射报告 · fdic

> 生成时间：2026-09-06T21:00:22　教学主线：H3 网格化 → 空间权重矩阵 → 空间滞后 → 距离环溢出

- 形状：148,137 行 × 3 列 → 70,456 行 × 6 列（点 → 格）

## 操作明细

| 操作 | 对象 | 结果 | 原因 |
| --- | --- | --- | --- |
| `geocode` | lat,lon | h3_cell（res=8） | L0 网格化 |
| `aggregate` | value by h3_cell | value（求和） | 点值聚合到格 |
| `spatial_weights` | h3 邻接 | W（n=70456，行标准化） | L1 空间权重矩阵 |
| `derive` | Wx | spatial_lag | L2 空间滞后 |
| `derive` | moran(value, W) | moran_i=0.133109 | L2 Moran's I |
| `aggregate` | top-100 热点 × 4 环 | L3_ring_spillover.csv | L3 距离环溢出 |

## L0→L3 四阶结果

| 层 | 章节 | 关键指标 |
| --- | --- | --- |
| L0 | H3 网格化 | 148,137 点 → 70,456 格（R8） |
| L1 | 空间权重矩阵 | n=70,456，平均邻居 1.41，孤岛 19786 |
| L2 | 空间滞后 | Moran's I = 0.1331，lag 相关 0.2163 |
| L3 | 距离环溢出 | 100 圆心 × 4 环 |

## 距离环均值溢出

| 环（km） | 平均溢出值（求和） | 溢出密度（环内格均摊） |
| --- | ---: | ---: |
| spill_0_1km | 42.26 | 7.62 |
| spill_1_3km | 31.57 | 2.13 |
| spill_3_5km | 42.45 | 1.72 |
| spill_5_10km | 128.52 | 1.64 |

## 映射阶段断言

| 断言 | 严重度 | 结果 | 实际 |
| --- | --- | --- | --- |
| h3_cell_not_null | P1 | PASS | 0 |
| weights_row_standardized | P1 | PASS | 孤岛 19786 |
| moran_i_in_range | P2 | PASS | 0.133109 |

> 字段血缘见 `lineage.csv`；映射后字段数据报告见 `fields.csv`。
