# ⑤ 映射报告（生存分析数据底座）

- 映射时间：2026-09-06T19:59:13
- 面板范围：1994–2025
- 形状：长表 2,702,716 行 → 网点维度表 152,538 行 × 20 列；银行层 15,505 行
- 空间方法：`h3_r7`（网格数 43,099）

## 操作明细

| 操作 | 结果 | 原因 |
| --- | --- | --- |
| `geocode` | 新增列 h3 (res=7)；4399 行坐标缺失，h3 置空 | H3 R7（平均边长 ≈ 0.46 km）作空间聚合单元 |
| `derive` | 新增列 obs_end | 观察期终点：死亡年；仍存活则用最后一次出现年 |
| `derive` | 新增列 duration | 风险集内的存活年数（离散时间风险模型的 duration） |
| `derive` | 新增列 right_censored | 右删失标记：无死亡年 = 仍存活 |
| `derive` | 新增列 event | 事件类型（closed / alive） |
| `derive` | 新增列 left_truncated | 左截断：出生早于面板首期（出生年缺失按左截断处理） |
| `derive` | 新增列 age | 网点年龄（末次观测年 − 出生年；出生年缺失用首次出现年代替） |
| `derive` | 新增列 alive_years | 在面板中出现的年数 |
| `derive` | 新增列 neighbor_count（同网格网点数，含自身） | 本地竞争强度代理 |
| `aggregate` | 长表 → 网点维度表（按 UNINUMBR 聚合） | 离散时间生存模型的风险集骨架：每网点一行 |
| `aggregate` | 银行脆弱性分层（按 CERT，15,505 家） | 银行层共享脆弱性：L0/L1/L2 |

## 生存口径分布

| 项 | 值 |
| --- | --- |
| 关闭率（事件） | 52.90% |
| 右删失率（仍存活） | 47.10% |
| 左截断率 | 51.76% |
| event=closed | 80,695 |
| event=alive | 71,843 |

## 银行脆弱性分层

| 分层 | 银行数 |
| --- | --- |
| L2_多网点地理分散 | 6,028 |
| L1_多网点高集中 | 5,918 |
| L0_单网点 | 3,559 |

## 字段血缘

| 输出字段 | 来源字段 | 表达式 / 方式 | 操作 |
| --- | --- | --- | --- |
| est_year | SIMS_ESTABLISHED_DATE | min(year(SIMS_ESTABLISHED_DATE)) over UNINUMBR | aggregate |
| acq_year | SIMS_ACQUIRED_DATE | max(year(SIMS_ACQUIRED_DATE)) over UNINUMBR（该字段只在并购当年及之后若干年出现，取 max 而非末行，否则会把已关闭网点误判为存活） | aggregate |
| first_year / last_year | YEAR | min(YEAR) / max(YEAR) over UNINUMBR | aggregate |
| obs_end | acq_year, last_year | acq_year.fillna(last_year) | derive |
| duration | obs_end, first_year | (obs_end - first_year + 1).clip(lower=1) | derive |
| event | acq_year | closed if acq_year notnull else alive | derive |
| right_censored | acq_year | int(acq_year is null) | derive |
| left_truncated | est_year | int(est_year < 首期年份)；出生年缺失记为 1 | derive |
| age | last_year, est_year, first_year | last_year - est_year.fillna(first_year) | derive |
| spatial_key | SIMS_LATITUDE, SIMS_LONGITUDE | h3.latlng_to_cell(lat, lng, 7) | geocode |
| CERT | CERT | first(CERT) over UNINUMBR（基线所属银行；并购后不追溯重标） | aggregate |
| neighbor_count | spatial_key, UNINUMBR | groupby(spatial_key)[UNINUMBR].transform(count)（无坐标记 0） | derive |
| n_branches / n_closed / bank_closed_rate | UNINUMBR, event | groupby(CERT) 聚合 | aggregate |
| fragility_tier | n_branches, geo_spread | L0 单网点 / L1 多网点高集中 / L2 多网点地理分散（以多网点银行 geo_spread 中位数分界） | aggregate |
| BRNUM | BRNUM | —（跨年重编号，不进入下游） | drop |

## 映射后字段数据报告（网点维度表）

| 字段 | 类型 | 非空 | 缺失率 | 唯一值 | 关键统计 |
| --- | --- | --- | --- | --- | --- |
| UNINUMBR | int64 | 152,538 | 0.00% | 152,538 | mean=2.92e+05, median=2.558e+05, max=6.868e+05 |
| CERT | int64 | 152,538 | 0.00% | 15,505 | mean=1.692e+04, median=1.487e+04, max=9.139e+04 |
| BKCLASS | string | 152,538 | 0.00% | 7 | N(62247), NM(50657), SM(18951) |
| first_year | Int64 | 152,538 | 0.00% | 32 | mean=2000, median=1995, max=2025 |
| last_year | Int64 | 152,538 | 0.00% | 32 | mean=2017, median=2024, max=2025 |
| est_year | float64 | 141,335 | 7.34% | 221 | mean=1977, median=1989, max=2015 |
| acq_year | float64 | 80,695 | 47.10% | 46 | mean=2002, median=2004, max=2015 |
| DEPSUMBR_last | int64 | 152,538 | 0.00% | 93,025 | mean=1.513e+05, median=3.936e+04, max=7.272e+08 |
| lat | float64 | 148,139 | 2.88% | 143,946 | mean=37.65, median=38.9, max=71.29 |
| lng | float64 | 148,139 | 2.88% | 144,164 | mean=-89.95, median=-86.22, max=163 |
| h3 | str | 148,139 | 2.88% | 43,099 | 872a100d6ffffff(415), 872a100d2ffffff(231), 87283082affffff(187) |
| obs_end | float64 | 152,538 | 0.00% | 56 | mean=2010, median=2009, max=2025 |
| duration | int64 | 152,538 | 0.00% | 32 | mean=11.01, median=8, max=32 |
| right_censored | int64 | 152,538 | 0.00% | 2 | mean=0.471, median=0, max=1 |
| event | str | 152,538 | 0.00% | 2 | closed(80695), alive(71843) |
| left_truncated | int64 | 152,538 | 0.00% | 2 | mean=0.5176, median=1, max=1 |
| age | Float64 | 152,538 | 0.00% | 229 | mean=37.35, median=25, max=241 |
| alive_years | Int64 | 152,538 | 0.00% | 32 | mean=17.97, median=18, max=32 |
| spatial_key | str | 148,139 | 2.88% | 43,099 | 872a100d6ffffff(415), 872a100d2ffffff(231), 87283082affffff(187) |
| neighbor_count | int64 | 152,538 | 0.00% | 82 | mean=10.61, median=5, max=415 |
