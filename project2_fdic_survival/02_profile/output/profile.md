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

## 字段清单（角色 / 等级 / 缺失 / 唯一值 / 问题数）

| 字段 | 类型 | 角色 | 等级 | 非空 | 缺失率 | 唯一值 | 问题数 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| UNINUMBR | float64 | key | required | 2,702,716 | 4.26% | 152,538 | 3 |  |
| BRNUM | int64 | ignore | ignore | 2,822,977 | 0.00% | 10,437 | 1 |  |
| CERT | int64 | key | required | 2,822,977 | 0.00% | 15,505 | 1 |  |
| YEAR | Int64 | key | required | 2,822,977 | 0.00% | 32 | 0 |  |
| SIMS_ESTABLISHED_DATE | datetime64[us] | event | important | 1,811,989 | 35.81% | 24,382 | 1 |  |
| SIMS_ACQUIRED_DATE | datetime64[us] | event | important | 949,516 | 66.36% | 5,832 | 1 |  |
| DEPSUMBR | int64 | time_varying | required | 2,822,977 | 0.00% | 312,301 | 1 |  |
| SIMS_LATITUDE | float64 | spatial | important | 2,596,045 | 8.04% | 500,715 | 3 |  |
| SIMS_LONGITUDE | float64 | spatial | important | 2,596,039 | 8.04% | 514,256 | 2 |  |
| BKCLASS | string | categorical | important | 2,822,977 | 0.00% | 7 | 0 |  |

## 字段角色 / 等级判定依据（规范 §3.5）

| 字段 | 角色 / 等级 | 说明 | 判定依据 |
| --- | --- | --- | --- |
| `UNINUMBR` | key / required | 跨年唯一网点号；本项目唯一追踪主键 | 判为 key+required：① 唯一性——非空后唯一值 = 网点数（152,538）；② 非空性——2011 年起零缺失； ③ 稳定性——跨年不重分配；④ 业务标识——对应真实网点。 对照 BRNUM：观测 ≥2 年的 146,396 个网点中 52.19% 首末年变化，唯一≠稳定 → 弃用。 缺它则寿命追踪无从建立 → required，缺失即 drop_na。 |
| `BRNUM` | ignore / ignore | 银行内网点序号 | 判为 ignore：实测观测 ≥2 年网点中 52.19% 首末年变化（与 CERT 52.17% 同步， 因 BRNUM 是银行内序号，CERT 一变必然重编）→ 违反主键判据第 3 条「稳定性」， 唯一≠稳定，已弃用为追踪主键。 |
| `CERT` | key / required | 银行（机构）编号，用于银行层聚合；并购后网点会改挂新 CERT，本项目按首次观测归属 | 判为 key+required：银行层脆弱性分层（bank_fragility）的唯一分组键，缺它核心协变量不可得。 已知偏差：52.17% 的网点首末年 CERT 变化（并购改挂），因此只作分组键、不作跨年追踪键； 归属口径取「首次观测」（改按末次则测试 AUC 0.881 → 0.812）。 |
| `YEAR` | key / required | 数据年份 | 判为 key+required：离散时间风险模型的「期」；与 UNINUMBR 组成复合主键 （唯一性断言即 UNINUMBR × YEAR）。缺它无法构造 duration 与风险集。 |
| `SIMS_ESTABLISHED_DATE` | event / important | 网点设立（出生）日期 | 判为 event+important：出生时间决定「网点年龄」与左截断判定，直接影响 duration， 但不决定记录能否定位，故 important 而非 required。缺失 35.81% → 按左截断处理，不填充。 |
| `SIMS_ACQUIRED_DATE` | event / important | 网点被并购 / 关闭（死亡）日期 | 判为 event+important：生存分析的事件指示（有值 = 死亡，缺失 = 右删失）。 缺失率 66.36%，但缺失本身携带「仍存活」的信息 → **明令禁止 fill** （填充会摧毁生存信息），level 只到 important。 |
| `DEPSUMBR` | time_varying / required | 网点存款余额（美元）；结果变量来源 | 判为 time_varying+required：核心协变量 log_depsumbr 的来源，缺它样本无法进入估计。 实测无缺失、无负值（负值规则作护栏）。 |
| `SIMS_LATITUDE` | spatial / important | 网点纬度 | 判为 spatial+important：承担空间结构（H3 R7 网格化 → neighbor_count → 残差 Moran's I）。 缺失 8.04%（97.8% 落在 1994–2010，时间结构化缺失）；坐标列**禁止 fill**， 越界值 `to_null` 而非截断（截断会伪造位置）。无坐标网点不进网格，neighbor_count 记 0。 |
| `SIMS_LONGITUDE` | spatial / important | 网点经度 | 同 SIMS_LATITUDE。另需注意：全期有 572 条落在 (0, 0) 空岛，不被范围断言捕获。 |
| `BKCLASS` | categorical / important | 银行类别；直接进入模型的类别协变量 | 判为 categorical+important：模型类别特征之一，无缺失；不直接决定样本能否进入估计， 故不到 required。 |

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
