# 项目6 空间结构化教学管线 · L0→L3 四阶认知阶梯

按 datakit v2 规范（`datakit/PROJECT_STRUCTURE.md`）组织的**多数据集**项目：
内置五阶段（①采集 → ②画像 → ③清洗 → ④校验 → ⑤映射）+ 两个扩展阶段
（⑥可视化 / ⑦结论），阶段内按 `<dataset>/` 分目录。

教学主线（h3 · libpysal）：**L0 H3 网格化 → L1 空间权重矩阵 → L2 空间滞后 →
L3 距离环溢出**。四个数据集各自独立产出，内容全部来自本管线实际跑通的结果
（不写没跑过的内容），所有代码块随数据集版本冻结、可按章节顺序复现。

## 运行

```powershell
# 推荐方式（datakit 虚拟环境，含 h3 / matplotlib / libpysal）
cd E:\workspace\workbuddy\project\data_use\datakit
uv run --extra geo python ..\project6_spatial_teaching\main.py

# 或直接用 venv 的 python
E:\workspace\workbuddy\project\data_use\datakit\.venv\Scripts\python.exe main.py

# 单阶段 / 数据集子集
python main.py --stage 05
python main.py --stage 02 --datasets fdic,sz_bike
```

依赖：`uv sync --extra geo`（含 `h3` 与 `matplotlib`）；再 `uv pip install libpysal`（W 矩阵）。

## 数据集与许可状态（每章开头标注，不许可说明不使用）

| 数据集 | 角色 | 许可状态 | 限制说明 |
| --- | --- | --- | --- |
| `fdic` | **主示例** | 公共领域（美国联邦政府数据），可商用 | 示例可自由分发 |
| `sz_bike` | 辅助示例 | 研究用途 | **源标注数据源已停更**（最后数据 2021-08） |
| `snap_brightkite` | 辅助示例 | 仅限研究用途（SNAP） | 不允许商用；**数据年代 2010–2013**（实测 2008-03 ~ 2010-10，见 version_lock） |
| `snap_gowalla` | 辅助示例 | 仅限研究用途（SNAP） | 不允许商用；**数据年代 2010–2013**（实测 2009-02 ~ 2010-10，见 version_lock） |

## 各数据集实测结果（L0→L3，2026-09-06 全流程重跑）

| 数据集 | 清洗后点数 | L0 格数(R8) | L1 平均邻居(孤岛) | L2 Moran's I | L3 溢出密度 0–1→5–10 km |
| --- | ---: | ---: | ---: | ---: | --- |
| fdic（网点关闭 0/1 聚合） | 148,137 | 70,456 | 1.41（19,786） | 0.1331 | 7.6 → 1.6，单调衰减 |
| sz_bike（抽样日起点活跃度） | 8,572,465 | 2,661 | 5.07（121） | 0.7077 | 24,612 → 6,867，单调衰减 |
| snap_brightkite（签到次数） | 4,747,172 | 228,476 | 2.01（67,189） | 0.0132 | 3,006 → 65，单调衰减 |
| snap_gowalla（签到次数） | 6,442,863 | 302,580 | 2.40（66,069） | 0.5090 | 4,024 → 124，单调衰减 |

解读：sz_bike（同城密集骑行）空间自相关最强；fdic 全国稀疏网点最弱；
brightkite 全球签到稀疏导致近邻格错配，Moran's I 偏低——本身就是
「空间权重矩阵定义对结论敏感」的活教材。
L3 注意：**求和口径不衰减**（环面积随距离增大），按环内格均摊的**溢出密度**才呈距离衰减
——聚合口径影响结论，本身就是教材。

## 目录结构（datakit v2 规范，已落地）

```text
project6_spatial_teaching/
├── README.md / SUMMARY.md / datakit.yaml / main.py   # main.py = importlib 根编排（§4.3）
├── config/                 # 口径外置：schema / clean_plan / mapping / assertions
├── data_raw/README.md      # 源数据口径登记（实际数据在仓库根 data_raw/，共享只读）
├── 01_discover/            # ① 采集：output/<dataset>/catalog.* + files.csv（+全局 catalog.*）
├── 02_profile/             # ② 画像：profile.* / fields / nulls / outliers / violations
│   └── loaders.py          #    四数据集统一加载器（lat, lon, value + 指纹），③ 共用
├── 03_clean/               # ③ 清洗：cleaned.csv / clean_report.md / decisions.* / impact.yaml
├── 04_validate/            # ④ 校验：validation.* / comparison.* / before_after.csv / version_lock.json
├── 05_map/                 # ⑤ 映射：map.* / lineage.csv / fields.csv / mapped.csv
│   └── spatial_ladder.py   #    L1→L3 空间算法（h3 + libpysal，课题专属，未沉淀内核）
├── 06_visualize/           # ⑥ 扩展阶段：manifest.json + figures/*.png|pdf（每数据集 3 图 + 全局 1 图）
├── 07_conclude/            # ⑦ 扩展阶段：conclusion.md + conclusion_report.json
├── logs/                   # pipeline.log（每次运行的阶段摘要与时间戳）+ stage_summaries.json
└── output_legacy_v1/       # 旧脚本（单文件 main.py 时代）的产物存档，仅比对用，可删除
```

各阶段「做什么 / 输入什么 / 看哪份报告」见各阶段目录内 `README.md`。

## 版本冻结与合成参数（④ 口径）

- `04_validate/output/<dataset>/version_lock.json`：文件指纹（MD5 仅对小文件）、行数、
  时间范围、`python/pandas/numpy/h3/libpysal/datakit` 版本——`git clone` 后按序可复现；
  重跑时与上一份比对，库版本或行数漂移会被记为断言失败。
- **成本参数均为合成参数，非真实业务数据**：`h3_res=8`、`ring_km=[0-1,1-3,3-5,5-10]`、
  `hot_top_n=100`、深圳单车抽样日=每月 15 日（共 20 个抽样日，全量 30 GB 不做全量载入）。
  全部来自 `config/`（`mapping.yaml` + `schema.yaml`），改口径不改代码。
- fdic 优先复用 `project1_fdic_spatial/output/data/branch_dim.csv`（UNINUMBR 口径），
  缺失时从原始 CSV 轻量重建（`02_profile/loaders.py`）。

## 教学主线（⑤ 映射）

1. **L0 H3 网格化**：点 → R8 格（平均边长 ≈ 0.46 km），值聚合到格（datakit 内核）；
2. **L1 空间权重矩阵**：H3 邻接 → `libpysal.weights.W`，行标准化（孤岛自动标记）；
3. **L2 空间滞后**：`Wx` + Moran's I（对应「空间滞后」认知）；
4. **L3 距离环溢出**：Top-100 热点为圆心，0–1/1–3/3–5/5–10 km 环内溢出
   （报告**求和**与**密度**两种口径，对应「距圈溢出」，完成 L1→L2→L3 认知阶梯）。

## 方案⑥ 可视化：开源电子书 + 知乎专栏 + B站视频课

- 每数据集 `06_visualize/output/<dataset>/figures/` 出 **L0 格值 ECDF、L2 Moran 散点
  （六边形分箱）、L3 距离环溢出密度**三张图（PNG + PDF 双格式），并登记进 `manifest.json`
  （标题写结论、口径、n、来源产物、alt_text，规范 §8.8.5）。
- `06_visualize/output/figures/01-global-ladder-comparison.png` 提供跨数据集对比，
  用于导论章说明「空间权重矩阵定义对结论敏感」。
- 技术栈：**GitHub Pages / Jupyter Book / Quarto** 即可；Vue + Node.js 可支撑自建站，但不强求。

## 方案⑦ 结论：放大器，不是主菜

- 本方案是 **放大器**：让 ④ 校验与 ⑤ 映射的产出更易被理解传播；
  不以阅读量/付费转化为核心指标。
- **⑤ 不适用**：不引入任何新算法、不做新建模，全部复用上游已验证产出。
- **止损条件**：若 ④⑤ 未做，本方向退化为官方文档翻译——应直接砍掉。

详见 `07_conclude/output/conclusion.md`。

## 许可与约束

- 仅本地开发使用；源数据 `data_raw` 只读；SNAP 数据仅研究用途、不再分发原始文件。
