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

## 字段清单（角色 / 等级 / 缺失 / 唯一值 / 问题数）

| 字段 | 类型 | 角色 | 等级 | 非空 | 缺失率 | 唯一值 | 问题数 | 登记 |
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
| MSABR | string | categorical | optional | 2,822,977 | 0.00% | 411 | 0 |  |
| METROBR | float64 | categorical | optional | 2,731,143 | 3.25% | 2 | 2 |  |
| SIMS_PROJECTION | string | categorical | optional | 2,691,404 | 4.66% | 840 | 1 |  |

## 字段角色 / 等级判定依据（规范 §3.5）

| 字段 | 角色 / 等级 | 说明 | 判定依据 |
| --- | --- | --- | --- |
| `UNINUMBR` | key / required | 跨年唯一网点号；本项目唯一追踪主键 | 判为 key+required：① 唯一性——非空后 UNINUMBR 唯一值 = 网点数（152,538）； ② 稳定性——跨年不重分配；③ 业务标识——对应真实网点实体。 对照：BRNUM 观测≥2 年网点中 52.19% 首末年变化，唯一≠稳定，故弃用。 缺它则记录无法定位、无法跨年 join → required，缺失即 drop_na。 |
| `BRNUM` | ignore / ignore | 银行内网点序号 | 跨年不稳定（观测≥2 年网点中 52.19% 首末年变化），已弃用为追踪主键 |
| `CERT` | key / required | 银行（机构）编号，用于银行层聚合 | 判为 key+required：与 UNINUMBR 同属「记录定位」层，银行层聚合（脆弱性、关闭率）的 唯一分组键。注意 CERT 会随并购改挂（52.17% 的网点首末年 CERT 变化）， 只作分组键、不作跨年追踪键。 |
| `YEAR` | key / required | 数据年份 | 判为 key+required：面板的时间维，与 UNINUMBR 组成复合主键（唯一性断言即 UNINUMBR × YEAR）。缺它无法定位事件时间与构造 event-time。 |
| `SIMS_ESTABLISHED_DATE` | event / important | 网点设立（出生）日期 | 判为 event+important：出生时间是「网点年龄」协变量与左截断判定的来源， 影响结论但不决定记录能否定位，故 important 而非 required；缺失按左截断处理，不填充。 |
| `SIMS_ACQUIRED_DATE` | event / important | 网点被并购 / 关闭（死亡）日期 | 判为 event+important：本课题「处理」的来源——有值才构成一起关闭事件。 缺失率全期 66.36%，但缺失本身 = 右删失（仍存活），是有意义信息， 因此 level 只到 important 且**明令禁止 fill**（填充会摧毁事件信息）。 |
| `DEPSUMBR` | time_varying / required | 网点存款余额（美元）；结果变量来源 | 判为 time_varying+required：本课题的结果变量 Y（存款增速）唯一来源。 缺它结论完全不可得 → required；实测无负值、无缺失（负值规则作护栏）。 |
| `SIMS_LATITUDE` | spatial / important | 网点纬度 | 判为 spatial+important：承担空间结构（H3 网格化、距离环、KNN 权重）。 缺它则该观测失去空间位置 → 坐标列**明令禁止 fill**（填充会伪造位置）， 越界值置空（to_null）而非截断。实测缺失 8.04%，早年更严重。 |
| `SIMS_LONGITUDE` | spatial / important | 网点经度 | 同 SIMS_LATITUDE：承担空间结构，禁止填充，越界置空。另需注意 (0,0) 空岛（全期 572 条）不被范围断言捕获。 |
| `BKCLASS` | categorical / important | 银行类别；用于「同业」判定（处理组强度按同 BKCLASS 计数） | 判为 categorical+important：本课题「同业」的定义本身由它决定（同 BKCLASS 才计入 各环 exposure 强度），直接决定 exposure 口径 → important。无缺失、7 个取值。 |
| `MSABR` | categorical / optional | 都会统计区（MSA）编号；与 METROBR 共同构成同城 / 同都会区对照口径 | 实测 1994–2025 全部 32 个年度文件（81 列）均不含 CBSA_METRO，故这是 SOD 全期唯一可用口径，非权宜替代 |
| `METROBR` | categorical / optional | 都会区标识，与 MSABR 共同构成对照口径 | 判为 optional：只用于辅助同城对照分组（主口径是 MSABR），缺失约 3.25% 不影响主结论，故不升到 important。 |
| `SIMS_PROJECTION` | categorical / optional | 地理编码方式；取值词表在 1994–2025 间换过两轮，不可跨年代直接比较 | 精度口径（本地全量实测）：1994–2022 用 US_Rooftop / US_Streets / US_Zipcode / 0 / 100， 屋顶级仅 16.37%；2023–2025 改用 EXACT / StreetAddress / PointAddress / Postal， EXACT 占 85.98%。早年多为插值坐标 → < 1 km 距离环有系统性失真，须做环宽敏感性。 旧口径「EXACT 占 45.45%」已作废：它把编码体系切换与样本退出时间混为一谈。 |

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
