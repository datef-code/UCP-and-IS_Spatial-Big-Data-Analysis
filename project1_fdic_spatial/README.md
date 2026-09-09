# project1_fdic_spatial · FDIC 网点关闭对周边同业的空间溢出

按 `datakit/PROJECT_STRUCTURE.md` 规范运行的**八阶段数据产品项目**：

内置五阶段（采集 → 画像 → 清洗 → 校验 → 映射）产出 exposure 数据底座，
扩展阶段（⑥ 估计 / ⑦ 可视化 / ⑧ 结论）回答「网点关闭对周边同业存款的空间溢出」。

数据源：FDIC Summary of Deposits（SOD）1994–2025，32 个年度文件 × 81 列，
约 1.6 GB，**只读**。追踪主键是 **UNINUMBR 而非 BRNUM**（前置验证③）。

## 运行

```powershell
cd E:\workspace\workbuddy\project\data_use\datakit

.\.venv\Scripts\python.exe ..\project1_fdic_spatial\main.py          # 全流程 01→08
.\.venv\Scripts\python.exe ..\project1_fdic_spatial\main.py --stage 03   # 单阶段
.\.venv\Scripts\python.exe ..\project1_fdic_spatial\main.py --list       # 列阶段
```

依赖：`pandas / numpy / pyyaml / h3 / matplotlib / scipy / statsmodels /
linearmodels / libpysal / esda / spreg`（datakit 主依赖 + `geo` / `modeling` 可选组）。

## 目录结构（规范 §1 / §8）

```text
project1_fdic_spatial/
├── README.md / SUMMARY.md / datakit.yaml / main.py
├── config/                 # 口径外置：schema / clean_plan / mapping / assertions
├── data_raw/README.md      # 数据说明（实际数据在仓库根 data_raw/fdic，只读共享）
├── logs/pipeline.log
├── 01_discover/ … 05_map/  # 内置五阶段：与目录同名入口 .py + README.md + output/
├── 06_estimate/            # 扩展阶段 §8：DID / 事件研究 / 空间计量
├── 07_visualize/           # 扩展阶段：Kepler 地图 + 报告图表
└── 08_conclude/            # 扩展阶段：短论 / 技术报告 / 结论与限制
```

数据流向：`data_raw/` → ① 扫描 → ② 画像（落 `raw_long.parquet`）→ ③ 清洗（`cleaned.csv`）
→ ④ 校验 → ⑤ 映射（`mapped.csv` + `data/`）→ ⑥⑦⑧（只读上游，产物各归各阶段）。

## 交互展示（先打开这个）

静态图是「死的」——不能 hover、不能播放、不能切换口径。
⑨ 阶段把它们升级为可戳的交互件（**只读上游产物，不重算任何模型**）：

| 打开 | 看什么 |
| --- | --- |
| **`09_interactive/output/index.html`** | 证据链叙事：结论 → 机制 → 证据 → 空间 → 限制 → 复现 |
| `07_visualize/output/kepler/kepler_map.html` | Kepler 交互地图（需联网加载 Kepler CDN） |
| `09_interactive/output/event_study.html` | 事件研究 τ 系数 + 95% CI，hover 看数值与 p 值 |
| `09_interactive/output/attenuation.html` | 距离衰减，可切「标准环 / 合并环」×「计数 / 密度」 |
| `09_interactive/output/spacetime.html` | 1994–2015 关闭事件在全国的级联扩散（**mp4 内嵌**，可拖进度条 / 倍速 / 下载） |
| `09_interactive/output/kepler_timeline.html` | Kepler 时间轴版（可逐帧播放 / 拖进度条定格任意年份；需联网加载 Kepler CDN） |

全部为**单文件自包含**（plotly 内联 / mp4 以 base64 内嵌），离线可开、挪动不丢图。

## 八个阶段在做什么

| 阶段 | 输入 | 关键产出 | 一句话结论 |
| --- | --- | --- | --- |
| ① 采集 `01_discover` | `data_raw/fdic`（只读） | `catalog.yaml/md`、`files.csv` | 32 文件 / 1 个分组 / 1.58 GB，跨年列结构一致 |
| ② 画像 `02_profile` | 源数据（只读 13 列） | `profile.yaml/md`、`fields/nulls/outliers/violations.csv` | 2,822,977 行；13 字段（required 4 / important 5 / optional 3 / ignore 1） |
| ③ 清洗 `03_clean` | ② 的 `raw_long.parquet` | `clean_report.md`、`decisions.yaml`、`impact.yaml`、`cleaned.csv` | 2,822,977 → 2,702,716 行（删除 4.26%，仅剔主键缺失） |
| ④ 校验 `04_validate` | ③ 的 `cleaned` + ② 的 `fields.csv` | `validation.yaml/md`、`comparison.yaml/md`、`before_after.csv` | 8/8 断言通过，无 P0 阻断；同城对照覆盖 98.3% |
| ⑤ 映射 `05_map` | ③ 的 `cleaned` | `map.yaml/md`、`lineage.csv`、`mapped.csv`、`data/` | H3 R8 → 70,109 格；27,018 起关闭事件 × 距离环 exposure |
| ⑥ 估计 `06_estimate` | ⑤ 的 `data/`（只读） | `estimate.json`、`metrics.json`、`replication_manifest.json` | TWFE post ≈ -0.053（p<0.001）；τ=0 -4.4pp → τ=4 -10.1pp |
| ⑦ 可视化 `07_visualize` | ⑤⑥ 输出（只读） | `manifest.json`、`figures/*.png+pdf`、`kepler/kepler_map.html` | 6 张报告图 + 自包含 Kepler 地图 |
| ⑧ 结论 `08_conclude` | ⑥⑦ 输出（只读） | `conclusion.md`、`technical_report.md`、`short_essay.md` | 关联证据非严格因果；存款再配置而非区域净增 |
| ⑨ 交互 `09_interactive` | ⑤⑥⑦ 输出（只读） | `index.html`、`event_study/attenuation/spacetime/kepler_timeline.html`、`manifest.json` | 静态图 → 可 hover / 可播放 / 可切口径 |

各阶段的输入 / 输出 / 口径细节见对应目录下的 `README.md`。

## 立项六问（规范 §9.2）

1. **为什么做**：美国银行网点数自 2009 年峰值后持续收缩，但「一家网点关闭，周边同业的存款
   会怎么变」缺少网点级、长周期（1994–2025）的量化证据。本项目要回答的一句可证伪问题是：
   **在 10 km 内有同业网点被并购关闭后，存活网点的存款增速是否显著低于同城可比网点？**
2. **新在哪**：把「空间」从控制变量升级为**识别策略本身**——用 H3 R8 网格 + 距离环把每起
   关闭事件转成**连续的 exposure 强度**（而非「是否相邻」的 0/1 处理变量），因此可以同时
   估计**效应大小**与**距离衰减形状**；并用网点级面板做事件研究检验平行趋势，而非只用横截面。
3. **数据哪来、靠不靠谱**：FDIC Summary of Deposits（SOD）1994–2025 全量，81 列 × 32 年。
   **已实测的可信度边界**：① `UNINUMBR` 在 1994–2010 有 120,261 行缺失（占全期 4.26%、
   且**100% 集中在 2011 年之前**），2011 年起零缺失——早年样本系统性不可追踪；
   ② 坐标缺失率 8.04%（226,932/2,822,977）；③ 坐标精度编码体系 2023 年切换，
   2023–2025 屋顶级（EXACT）占 85.98%，而 1994–2022 屋顶级（US_Rooftop）只占 16.37%
   → **早年距离环误差显著大于近年**。详见 `data_raw/README.md` 的「可信度评估」。
4. **空间大数据起什么作用**：本课题的问题本身就是空间的——「周边同业」必须先定义「周边」。
   去掉空间维度，只剩「同城 / 同都会区」的粗对照，无法回答距离衰减，也无法区分
   「本地被吸走」与「区域整体下行」。空间结构（H3 网格聚合 + 距离环 + KNN 空间权重）
   同时承担三件事：构造 exposure、构造对照、检验残差空间自相关。
5. **做不做得了**：2,822,977 行网点-年面板、152,538 个可追踪网点、27,018 起关闭事件、
   H3 R8 70,109 个格——样本量足以支撑网点级固定效应与事件研究；核心依赖（pandas/h3/
   linearmodels/libpysal/esda）均已跑通，全流程 8 阶段约 26 分钟。
6. **怎么跑、结论、限制**：见下「运行」「一句话结论」「已知限制」。

## 关键口径（与方案原文的偏差）

1. **追踪主键 UNINUMBR，不是 BRNUM**。实测（按 UNINUMBR 追踪、观测 ≥2 年的 146,396 个
   网点）：**BRNUM 首末年变化 52.19%**，CERT 变化 52.17%（两者几乎同步——BRNUM 是「银行内
   网点序号」，CERT 一变必然重编号）；只看曾出现 `SIMS_ACQUIRED_DATE` 的并购/关闭网点，
   BRNUM 变化率升至 **86.80%**。→ BRNUM 唯一但不稳定，不能作跨年键（④ 阶段固化断言）。
2. **都会区口径：SOD 全期（1994–2025，81 列）没有 `CBSA_METRO` 字段**。实测 32 个年度文件
   全部只有 `MSABR`（MSA 代码）、`METROBR`（都会区标志）、`MICROBR`、`CSABR`、
   `CBSA_DIV_NAMB`。因此同城 / 同都会区对照用 **`MSABR` + `METROBR`** 构造，**这不是
   「早年缺失的权宜之计」，而是 SOD 全期的唯一可用口径**。
3. **坐标精度敏感性（口径已修正）**：`SIMS_PROJECTION` 是地理编码方式字段，但**取值词表在
   1994–2025 间至少换过两轮**：1994–2022 用 `US_Rooftop`/`US_Streets`/`US_Zipcode`/`0`/
   `100`，2023–2025 才改用 `EXACT`/`StreetAddress`/`PointAddress`/`Postal`。因此
   **不能用单一「EXACT 占比」衡量全期精度**。分年代实测（分母 = 网点-年行）：
   2023–2025 EXACT = **85.98%**；
   1994–2022 US_Rooftop = **16.37%**、US_Streets = **31.57%**、US_Zipcode = **4.97%**。
   （④ 断言里那个 51.05% 是**另一分母**——按「每个网点最后观测年」的 152,538 个网点维度计，
   EXACT 45.45% + US_Rooftop 5.60%，两者不可混用。）
   → 早年坐标多为街道级/邮编级插值，<1 km 距离环有系统性失真；除标准环
   （0–1/1–3/3–5/5–10 km）外同时产出**合并环**（0–2/2–5/5–10 km），两套结论需对比。
4. **归因对照**：每起关闭事件的对照 = 同 MSABR 存活网点（吸收同城共同冲击），覆盖率 98.3%。
5. **处理组取存续网点**：关闭网点自身不做 outcome（关闭后无观测，避免把"死亡"当效应）。
6. **L1 设计取向**：直接用**空间特征**（各环强度列）进入模型，而非区域 one-hot。
7. 各环同业均值呈距离衰减：0–1 km 5.01 / 1–3 km 8.47 / 3–5 km 11.86 / 5–10 km 40.38。
8. **10 km 环的构造方式**：`grid_disk(k=23)` 只是**候选窗口**（实测最大半径 21.7 km、
   平均 13.0 km），真正的 10 km 由 haversine 距离过滤实现，因此不存在「环形被放大」的问题。
   H3 R8 实测（h3 4.5.0）：平均单元面积 0.737328 km²、平均边长 0.531414 km。

## 一句话结论

> 10 km 内同业关闭事件后，被辐射存活网点存款增速显著下行并逐年加深
> （τ=0 −4.4pp → τ=4 −10.1pp；TWFE post ≈ −5.3pp，p<0.001）；post × strength
> 交互为正，聚合层 SLX 的 W_treat 为正 → 存款在更广地理尺度**再配置**而非区域净增。
> 事件前 τ=−2 轻微为负 + 区域共同冲击 → **关联证据，非严格因果**。

## 已知限制（必须阅读）

1. 事件前 τ=−2 轻微为负 → 平行趋势近似但非理想；区域共同冲击可能贡献 post 下行。
2. 存款转移 ≠ 区域净增：不据此报区域增长红利或 ROI。
3. SAR 在大稀疏 KNN 上 ρ 数值不稳 → 不以 SAR 报溢出量级，仅以 SLX 的 W_treat 作代理。
4. 不承诺 ROI、不承诺干预阈值（成本参数缺失）。
5. 坐标精度分年代：2023–2025 EXACT 85.98%，1994–2022 屋顶级仅 16.37%（其余多为街道级/
   邮编级插值）→ 早年距离环误差大，主表用 5 km 中等环，<1 km 环只作参考。
6. 事件研究未加 bootstrap CI，显著性部分来自大样本。
7. 空间权重仅用 KNN(k=6)，未对比其他权重方案。
8. **缺失非随机**：③ 清洗删除的 120,261 行（4.26%）**全部**来自 1994–2010 的 `UNINUMBR`
   缺失，2011 年起零缺失。即早年样本系统性不可追踪，事件研究的早期年份代表性弱于近 15 年。

完整的**止损条件**见 `08_conclude/output/conclusion.md`。

## 许可与约束

- FDIC SOD：美国联邦政府公共数据，可商用；仅本地开发使用，源数据只读。
- 扩展阶段（⑥⑦⑧）`blocking: false`：失败降级为告警并写入 `SUMMARY.md`，不阻断五阶段。
- 硬约束：扩展阶段**禁止回写上游阶段的 `output/`**，只读。
