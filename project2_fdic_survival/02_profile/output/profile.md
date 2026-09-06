# ② 画像报告 · fdic

- 源：`E:\workspace\workbuddy\project\data_use\data_raw\fdic`（只读）
- 行数列数：**2,822,977 行 × 10 列**；年份 1994–2025
- 空单元格：3,458,580（整体缺失率 12.25%）
- 异常值（iqr，阈值 3.0）：506,766 条

## 关键发现：寿命追踪主键是 UNINUMBR，不是 BRNUM

- UNINUMBR 是跨年稳定的寿命追踪主键；BRNUM 是银行内序号，同年即大量重复且会跨年重编号
- 1994 年 81,297 行里，BRNUM 唯一值仅 1,531 个（重复 79,766 行），UNINUMBR 唯一值 73,469 个。
- 全期看，152,538 个可追踪网点中有 76,440 个 BRNUM 发生过变化（50.11%）→ BRNUM 不能作跨年连接键。

## 生存字段缺失率（缺失语义优先于缺失率）

| 字段 | 缺失率 | 语义 |
| --- | --- | --- |
| SIMS_ESTABLISHED_DATE（出生，缺失=左截断候选） | 35.81% | — |
| SIMS_ACQUIRED_DATE（死亡，缺失=右删失，禁止填充） | 66.36% | — |
| SIMS_LATITUDE/SIMS_LONGITUDE（缺失=无法入网格） | 8.04% | — |
| DEPSUMBR | 0.00% | — |
| BKCLASS | 0.00% | — |

## 等级分布

| 等级 | 字段数 |
| --- | --- |
| important | 5 |
| required | 4 |
| ignore | 1 |

## 字段清单（角色 / 等级 / 缺失 / 唯一值）

| 字段 | 类型 | 角色 | 等级 | 非空 | 缺失率 | 唯一值 | 备注 |
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

## 极端值 / 异常值（统计意义）

- 检测方法：`iqr`（阈值 3.0）

| 字段 | 异常数 | 占比 | 下界 | 上界 |
| --- | --- | --- | --- | --- |
| BRNUM | 336,298 | 11.91% | -2089 | 2797 |
| CERT | 13,056 | 0.46% | -5.41e+04 | 8.121e+04 |
| DEPSUMBR | 110,465 | 3.91% | -1.541e+05 | 2.426e+05 |
| SIMS_LATITUDE | 1,422 | 0.05% | 12.18 | 63.48 |
| SIMS_LONGITUDE | 11,291 | 0.40% | -145.3 | -30.83 |
| UNINUMBR | 34,234 | 1.21% | -1.168e+05 | 5.96e+05 |

## 规则违规（业务意义）

| 字段 | 等级 | 严重度 | 规则 | 违规数 | 占比 | 样本 |
| --- | --- | --- | --- | --- | --- | --- |
| UNINUMBR | required | P0 | not_null | 120,261 | 4.26% | nan, nan, nan |
| UNINUMBR | required | P0 | unique(fields=['UNINUMBR', 'YEAR']) | 120,261 | 4.26% | nan, nan, nan |
| SIMS_LATITUDE | important | P1 | geo_lat | 5 | 0.00% | 138.097, 158.227518485, 158.227518485 |
