# ② 画像报告 · fdic

- 源：`E:\workspace\workbuddy\project\data_use\data_raw\fdic`（只读）
- 行数列数：**2,822,977 行 × 13 列**；年份 1994–2025
- 空单元格：3,681,987（整体缺失率 10.03%）
- 异常值（iqr）：2,383,023 条

## 等级分布

| 等级 | 字段数 |
| --- | --- |
| important | 5 |
| required | 4 |
| optional | 3 |
| ignore | 1 |

## 字段清单（角色 / 等级 / 缺失 / 唯一值）

| 字段 | 类型 | 角色 | 等级 | 非空 | 缺失率 | 唯一值 | 说明 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| UNINUMBR | float64 | key | required | 2,702,716 | 4.26% | 152,538 |  |
| BRNUM | int64 | ignore | ignore | 2,822,977 | 0.00% | 10,437 |  |
| CERT | int64 | key | required | 2,822,977 | 0.00% | 15,505 |  |
| YEAR | Int64 | key | required | 2,822,977 | 0.00% | 32 |  |
| SIMS_ESTABLISHED_DATE | datetime64[us] | event | important | 1,811,989 | 35.81% | 24,382 |  |
| SIMS_ACQUIRED_DATE | datetime64[us] | event | important | 949,516 | 66.36% | 5,832 |  |
| DEPSUMBR | int64 | time_varying | required | 2,822,977 | 0.00% | 312,301 |  |
| SIMS_LATITUDE | float64 | spatial | important | 2,596,045 | 8.04% | 500,715 |  |
| SIMS_LONGITUDE | float64 | spatial | important | 2,596,039 | 8.04% | 514,256 |  |
| BKCLASS | string | categorical | important | 2,822,977 | 0.00% | 7 |  |
| MSABR | string | categorical | optional | 2,822,977 | 0.00% | 411 |  |
| METROBR | float64 | categorical | optional | 2,731,143 | 3.25% | 2 |  |
| SIMS_PROJECTION | string | categorical | optional | 2,691,404 | 4.66% | 840 |  |

## 空值分析（按角色解释）

| 字段 | 缺失数 | 缺失率 | 角色 | 语义 |
| --- | --- | --- | --- | --- |
| UNINUMBR | 120,261 | 4.26% | key | 缺陷：主键缺失，通常需剔除 |
| BRNUM | 0 | 0.00% | ignore | 忽略 |
| CERT | 0 | 0.00% | key | 缺陷：主键缺失，通常需剔除 |
| YEAR | 0 | 0.00% | key | 缺陷：主键缺失，通常需剔除 |
| SIMS_ESTABLISHED_DATE | 1,010,988 | 35.81% | event | 信息：缺失常表示右删失/未发生，不当作脏数据 |
| SIMS_ACQUIRED_DATE | 1,873,461 | 66.36% | event | 信息：缺失常表示右删失/未发生，不当作脏数据 |
| DEPSUMBR | 0 | 0.00% | time_varying | 可选：缺失可标记或填充 |
| SIMS_LATITUDE | 226,932 | 8.04% | spatial | 需处理：缺失坐标影响映射，可近似或置空 |
| SIMS_LONGITUDE | 226,938 | 8.04% | spatial | 需处理：缺失坐标影响映射，可近似或置空 |
| BKCLASS | 0 | 0.00% | categorical | 可重编码：缺失可归入 UNKNOWN 类 |
| MSABR | 0 | 0.00% | categorical | 可重编码：缺失可归入 UNKNOWN 类 |
| METROBR | 91,834 | 3.25% | categorical | 可重编码：缺失可归入 UNKNOWN 类 |
| SIMS_PROJECTION | 131,573 | 4.66% | categorical | 可重编码：缺失可归入 UNKNOWN 类 |

## 极端值 / 异常值（统计意义）

- 检测方法：`iqr`

| 字段 | 异常数 | 占比 | 下界 | 上界 |
| --- | --- | --- | --- | --- |
| BRNUM | 460,550 | 16.31% | -1042 | 1750 |
| CERT | 108,571 | 3.85% | -2.51e+04 | 5.222e+04 |
| DEPSUMBR | 228,147 | 8.08% | -6.909e+04 | 1.576e+05 |
| METROBR | 596,498 | 21.13% | 1 | 1 |
| SIMS_LATITUDE | 22,251 | 0.79% | 23.17 | 52.49 |
| SIMS_LONGITUDE | 150,831 | 5.34% | -120.8 | -55.37 |
| UNINUMBR | 816,175 | 28.91% | 3.598e+04 | 4.433e+05 |

## 规则违规（业务意义）

| 字段 | 等级 | 严重度 | 规则 | 违规数 | 占比 | 样本 |
| --- | --- | --- | --- | --- | --- | --- |
| UNINUMBR | required | P0 | not_null | 120,261 | 4.26% | nan, nan, nan |
| UNINUMBR | required | P0 | unique(fields=['UNINUMBR', 'YEAR']) | 120,261 | 4.26% | nan, nan, nan |
| SIMS_LATITUDE | important | P1 | geo_lat | 5 | 0.00% | 138.097, 158.227518485, 158.227518485 |
