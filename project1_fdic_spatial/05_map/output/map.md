# ⑤ 映射报告（空间结构化）

- 映射时间：2026-09-06T19:21:10
- H3：v4.5.0，res=8，grid_disk k=23
- 形状：面板 2,702,716 行；网点维度 152,538 行；exposure 27,018 行 × 15 列
- H3 网格数：70,109

## 操作明细

| 操作 | 结果 | 原因 |
| --- | --- | --- |
| `geocode` | 新增列 h3 (res=8)；5483 行坐标缺失，h3 置空 | R8 平均边长 ≈ 0.46 km，匹配 0–1 km 细环 |
| `derive` | 新增列 event_type | 区分并购关闭 / 仍存活（右删失）/ 数据缺失 |
| `derive` | 新增列 left_truncated | 设立年份早于观测起点 → 左截断标记 |
| `derive` | 长表新增列 dep_chg / dep_chg_rate | 存款年度变动额 / 变动率（结果变量） |
| `aggregate` | 关闭事件 × 距离环 exposure（27,018 行） | 处理组强度 = 各环内同 BKCLASS 网点数；对照 = 同 MSABR 存活网点 |

## 事件判定分布

| 事件类型 | 网点数 |
| --- | --- |
| alive_censored | 76,097 |
| attrition_missing | 46,828 |
| closed_ma | 29,613 |

## 各环同业网点数均值（距离衰减）

| 距离环 | 均值 |
| --- | --- |
| same_ind_ring_0_1km | 5.01 |
| same_ind_ring_1_3km | 8.47 |
| same_ind_ring_3_5km | 11.86 |
| same_ind_ring_5_10km | 40.38 |
| same_ind_ring_0_2km | 8.81 |
| same_ind_ring_2_5km | 16.54 |

## 字段血缘

| 输出字段 | 来源字段 | 表达式 / 方式 | 操作 |
| --- | --- | --- | --- |
| dep_chg | DEPSUMBR | DEPSUMBR - DEPSUMBR.shift(1) over (UNINUMBR order by YEAR) | derive |
| dep_chg_rate | DEPSUMBR | dep_chg / DEPSUMBR.shift(1) | derive |
| acq_year | SIMS_ACQUIRED_DATE | year(SIMS_ACQUIRED_DATE) | derive |
| h3 | SIMS_LATITUDE, SIMS_LONGITUDE | h3.latlng_to_cell(lat, lng, 8) | geocode |
| event_type | SIMS_ACQUIRED_DATE, YEAR | closed_ma if acq_year notnull else (alive_censored if last_year == max_year else attrition_missing) | derive |
| left_truncated | SIMS_ESTABLISHED_DATE | int(est_year < first_observed_year) | derive |
| n_same_ind_10km | h3, BKCLASS | count(同 BKCLASS 网点, haversine <= 10km, grid_disk(k=23)) | aggregate |
| same_ind_ring_<a>_<b>km | h3, BKCLASS | count(同 BKCLASS 网点, a <= d < b km) | aggregate |
| BRNUM | BRNUM | —（跨年不稳定，不进入下游） | drop |

## 映射后字段数据报告（exposure）

| 字段 | 类型 | 非空 | 缺失率 | 唯一值 | 关键统计 |
| --- | --- | --- | --- | --- | --- |
| UNINUMBR | int64 | 27,018 | 0.00% | 27,018 | mean=2.282e+05, median=2.36e+05, max=5.506e+05 |
| acq_year | float64 | 27,018 | 0.00% | 46 | mean=1999, median=1999, max=2015 |
| CERT | int64 | 27,018 | 0.00% | 2,324 | mean=1.379e+04, median=8273, max=9.139e+04 |
| BKCLASS | str | 27,018 | 0.00% | 6 | N(15935), SM(4897), NM(4729) |
| MSABR | str | 27,018 | 0.00% | 389 | 0(3765), 35620(1810), 16980(798) |
| lat | float64 | 27,018 | 0.00% | 26,451 | mean=37.47, median=38.91, max=64.84 |
| lng | float64 | 27,018 | 0.00% | 26,465 | mean=-88.56, median=-84.26, max=0 |
| h3 | str | 27,018 | 0.00% | 20,771 | 88283082a3fffff(34), 882a100d67fffff(30), 882a134d69fffff(21) |
| n_same_ind_10km | int64 | 27,018 | 0.00% | 1,148 | mean=174.8, median=71, max=2296 |
| same_ind_ring_0_1km | int64 | 27,018 | 0.00% | 150 | mean=5.01, median=3, max=243 |
| same_ind_ring_1_3km | int64 | 27,018 | 0.00% | 215 | mean=8.472, median=4, max=467 |
| same_ind_ring_3_5km | int64 | 27,018 | 0.00% | 231 | mean=11.86, median=5, max=528 |
| same_ind_ring_5_10km | int64 | 27,018 | 0.00% | 479 | mean=40.38, median=17, max=1025 |
| same_ind_ring_0_2km | int64 | 27,018 | 0.00% | 203 | mean=8.81, median=5, max=413 |
| same_ind_ring_2_5km | int64 | 27,018 | 0.00% | 289 | mean=16.54, median=8, max=614 |

## exposure 结构与设计取向

- 处理组：各环内同业（同 BKCLASS）网点数 = 处理组强度
- 对照组：同 MSABR 存活网点（远环 / 同城对照，见 04_validate control_coverage）
- L1 设计取向：空间特征（距离环强度列）而非区域 one-hot
