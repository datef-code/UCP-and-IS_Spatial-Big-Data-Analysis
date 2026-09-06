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

各阶段的输入 / 输出 / 口径细节见对应目录下的 `README.md`。

## 关键口径（与方案原文的偏差）

1. **追踪主键 UNINUMBR，不是 BRNUM**。前置验证③实测：29,613 家并购关闭网点中
   BRNUM 跨年发生变化（④ 阶段固化断言）——BRNUM 不能作跨年键。
2. **CBSA_METRO 早年 SOD 不存在**，用 `MSABR`（都会统计区）+ `METROBR` 作同城 / 同都会区对照的代理口径。
3. **坐标精度敏感性**：`SIMS_PROJECTION=EXACT` 占比 < 100%（坐标存在插值）→ <1 km 距离环有系统性失真，
   除标准环（0–1/1–3/3–5/5–10 km）外同时产出**合并环**（0–2/2–5/5–10 km），两套结论需对比。
4. **归因对照**：每起关闭事件的对照 = 同 MSABR 存活网点（吸收同城共同冲击），覆盖率 98.3%。
5. **处理组取存续网点**：关闭网点自身不做 outcome（关闭后无观测，避免把"死亡"当效应）。
6. **L1 设计取向**：直接用**空间特征**（各环强度列）进入模型，而非区域 one-hot。
7. 各环同业均值呈距离衰减：0–1 km 5.01 / 1–3 km 8.47 / 3–5 km 11.86 / 5–10 km 40.38。

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
5. EXACT 坐标占比 < 100% → 主表用 5 km 中等环，<1 km 环只作参考。
6. 事件研究未加 bootstrap CI，显著性部分来自大样本。
7. 空间权重仅用 KNN(k=6)，未对比其他权重方案。

完整的**止损条件**见 `08_conclude/output/conclusion.md`。

## 许可与约束

- FDIC SOD：美国联邦政府公共数据，可商用；仅本地开发使用，源数据只读。
- 扩展阶段（⑥⑦⑧）`blocking: false`：失败降级为告警并写入 `SUMMARY.md`，不阻断五阶段。
- 硬约束：扩展阶段**禁止回写上游阶段的 `output/`**，只读。
