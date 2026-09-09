# data_raw/

> **本目录不存放数据**，只登记口径。源数据实际位置由 `datakit.yaml` 的
> `source_root: '../data_raw'` 指向仓库根 `E:\workspace\workbuddy\project\data_use\data_raw\`
> （四个数据集共享，不在本项目内重复存放）。
>
> 本文件的所有规模 / 时间范围数字均为 **2026-09-08 本地实测**，并与官方来源交叉核实；
> 与官方不一致处已单列「口径差异」。

## 数据集与许可（每章开头必须标注，不许可说明不使用）

| 数据集 | 角色 | 许可状态 | 限制说明 | 官方来源 |
| --- | --- | --- | --- | --- |
| `fdic` | **主示例** | 公共领域（美国联邦政府数据），可商用 | 示例可自由分发 | 下载 <https://www.fdic.gov/bank-data-guide/data-downloads>（Data Downloads → Branch Office Deposits - SOD）；BankFind <https://banks.data.fdic.gov/bankfind-suite/SOD> |
| `sz_bike` | 辅助示例 | 研究用途 | **数据源已停更**（实测最后日期 2021-08-31）；本地存档，无公开引用 | 本地存档，未见可核实的公开来源 |
| `snap_brightkite` | 辅助示例 | 仅限研究用途（SNAP） | 不允许商用、不再分发原始文件 | <https://snap.stanford.edu/data/loc-brightkite.html> |
| `snap_gowalla` | 辅助示例 | 仅限研究用途（SNAP） | 不允许商用、不再分发原始文件 | <https://snap.stanford.edu/data/loc-gowalla.html> |

**SNAP 两数据集的引用（官方要求，教学材料必须给出）**

> E. Cho, S. A. Myers, J. Leskovec. *Friendship and Mobility: User Movement in
> Location-Based Social Networks*. ACM SIGKDD International Conference on Knowledge
> Discovery and Data Mining (KDD), 2011.

## 口径（`config/schema.yaml` 的 `per_dataset`，改口径不改代码）

| 数据集 | 源路径（**实测**） | 统一字段 | 度量语义 |
| --- | --- | --- | --- |
| `fdic` | `fdic/fdic_sod_*.csv`（32 个文件，1.57 GiB；优先复用 `project1_fdic_spatial/05_map/output/data/branch_dim.csv`） | `lat, lon, value` | 网点是否关闭（0/1，按 UNINUMBR 聚合） |
| `sz_bike` | `sz_bike/bike_<YYYYMMDD>_p<NNNNN>.csv`（**实测命名模式**；管线按「每月 15 日」筛日期，共 20 个抽样日） | `lat, lon, value` | 抽样日起点骑行次数（每次计 1） |
| `snap_brightkite` | `snap_brightkite/loc-brightkite_totalCheckins.txt.gz`（60.0 MB） | `lat, lon, value` | 签到次数（每次计 1） |
| `snap_gowalla` | `snap_gowalla/loc-gowalla_totalCheckins.txt.gz`（105.5 MB） | `lat, lon, value` | 签到次数（每次计 1） |

## 实测规模与时间范围（覆盖 / 精度 / 偏差，规范 §9.3）

| 数据集 | 实测文件数 | 实测体积 | 实测行数 | 实测时间范围 | 官方口径 | 差异说明 |
| --- | ---: | ---: | ---: | --- | --- | --- |
| `fdic` | 32 | 1.57 GiB | 2,822,977（网点-年） | 1994–2025 | 1994–2025 | 一致 |
| `sz_bike` | 24,939 个 CSV + 4 个采集元数据文件 | **31.49 GB** | — | **2020-01-01 ~ 2021-08-31（609 天）** | — | 原写「30 GB / 24,939 个文件」，体积实测 31.49 GB |
| `snap_brightkite` | 1 | 60.0 MB | **4,747,287** | **2008-03-21 ~ 2010-10-18** | 4,491,143 check-ins，Apr 2008 – Oct 2010 | 见下 |
| `snap_gowalla` | 1 | 105.5 MB | **6,442,892** | **2009-02-04 ~ 2010-10-23** | 6,442,890 check-ins，Feb 2009 – Oct 2010 | 多 2 行（疑似空/尾行），可忽略 |

### 必须知悉的两处口径差异

1. **`snap_brightkite` 行数比官方多 256,144 行（+5.7%）**：本地文件 4,747,287 行，
   官方数据集页写 4,491,143 check-ins。实测**没有空行、全部 5 个字段**（无格式损坏），
   但有 **6 行时间戳异常**（时间字段为空或非标准格式）与 **109 行坐标越界/不可解析**。
   即：差异不是解析错误，而是**原始文件本身比官方统计口径多出的记录**。
   → 教学材料中引用 Brightkite 计数时，必须说明「本地文件行数」而非官方 check-in 数，
   或先按官方口径清洗后再引用。
2. **SNAP 数据年代不是 2010–2013**：README 旧版写的「2010–2013」是**错的**。
   官方与本地实测一致：Brightkite **2008-04 ~ 2010-10**（本地实测 2008-03-21 起），
   Gowalla **2009-02 ~ 2010-10**。两者都在 **2010 年**结束。
   教学讲解「签到数据的时代背景」时须按 2008–2010 表述。

### 其它已知偏差

- **`sz_bike` 的坐标含飞点与空岛**：05_map 的 `mapped.csv`（2,661 格）里，
  `lat` 最小 −0.0018、`lon` 最小 −0.0027（**(0,0) 空岛**），最大 `lat=47.66 / lon=132.54`
  （远在黑龙江一带，不是深圳）。因为 `geo_lat` / `geo_lon` 断言只查 `[-90,90]` / `[-180,180]`，
  这两个值都「合法」所以没被清洗掉。中位数（22.67°N / 114.07°E）才是深圳本体。
  → 出图时按深圳 bbox（22.35–23.05°N / 113.65–114.75°E）裁切；
  本质是**加一条业务范围的合理性规则**，而不是只靠经纬度的几何范围断言。
- `snap_brightkite` 与 `snap_gowalla` 都是**社交签到数据**，空间分布高度偏斜
  （少量热点贡献绝大多数签到），因此 L0 格值 ECDF 呈长尾、L1 权重下孤岛格占比高
  （Brightkite 67,189 / 228,476）——这是**数据性质**，不是管线错误。
- `sz_bike` 全量 31.49 GB 覆盖 609 天，管线只取每月 15 日共 20 天作抽样
  （**合成抽样参数**，非真实业务口径），故绝对量级不可外推到全年。
- `fdic` 在 `project1` 产物缺失时从原始 CSV 重建，口径为「按 `UNINUMBR` 取最后一年坐标，
  `value=1` 表示 `SIMS_ACQUIRED_DATE` 非空」；注意 SOD 的 `UNINUMBR` 在 1994–2010 有
  120,261 行缺失（4.26%），早年样本系统性不可追踪。

## 通用约束

- **只读**：任何脚本都不得写入本目录（`dk.scan` 只做只读探测）。
- **不再分发原始文件**：SNAP 数据仅本地研究使用。
- 跨数据集的口径、抽样与成本参数均为**合成参数**，见根 `README.md`「版本冻结与合成参数」。
