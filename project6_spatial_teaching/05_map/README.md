# 05_map · ⑤ 映射（教学主线 L0→L3）

> 项目：[project6_spatial_teaching](../README.md)　|　规范：`datakit/PROJECT_STRUCTURE.md` §2-⑤ / §8.7

## 本阶段做什么

回答「原始字段怎么变成分析字段」：把清洗后的**点**映射为**格**上的空间结构化数据，
形成教学主线 **L0 → L1 → L2 → L3** 四阶认知阶梯。

| 层 | 内容 | 实现 |
| --- | --- | --- |
| L0 | H3 网格化 + 聚合（点 → R8 格 ≈ 0.46 km） | datakit 内核（`MappingScheme.geocode` / `aggregate`） |
| L1 | 空间权重矩阵：H3 邻接 → `libpysal` W，行标准化，孤岛标记 | 本阶段 `spatial_ladder.py` |
| L2 | 空间滞后 `Wx` + Moran's I | 本阶段 `spatial_ladder.py` |
| L3 | 距离环溢出：Top-N 热点为圆心，0–1 / 1–3 / 3–5 / 5–10 km | 本阶段 `spatial_ladder.py` |

> L1–L3 属于课题专属算法，尚未沉淀进 datakit 内核（规范 §8.7：被 ≥2 个项目复用后才升级）。

## 输入 / 输出

- **输入**：`03_clean/output/<dataset>/cleaned.csv` + `config/mapping.yaml`（分辨率 / 热点数 / 距离环）
- **输出**（`output/<dataset>/`）：

| 路径 | 内容 |
| --- | --- |
| `map.yaml` / `map.md` | 操作明细 + L0→L3 结果 + 映射阶段断言 |
| `lineage.csv` | 字段血缘：输出字段 ← 来源字段 / 表达式 / 引擎 |
| `fields.csv` | 映射后字段数据报告（类型 / 来源 / 非空 / 缺失率 / 唯一值 / 统计） |
| `mapped.csv` | 过程数据：`h3_cell, lat, lon, value, spatial_lag, isolate` |
| `L2_spatial_lag.csv` | L2 教学表：格值 + 空间滞后 |
| `L3_ring_spillover.csv` | L3 教学表：热点圆心 × 距离环溢出 |
| `ladder_report.json` | L0→L3 主线报告（扩展阶段 06/07 依赖） |

## 运行

```powershell
python main.py --stage 05
```

## 口径要点（全部来自 `config/`，改口径不改代码）

- `h3_res = 8`（`config/mapping.yaml`）、`hot_top_n = 100`、距离环 `[0,1] [1,3] [3,5] [5,10]` km
  —— 均为**合成参数，非真实业务数据**。
- 断言（`config/assertions.yaml` 的 `when: 05_map`）：`h3_cell` 非空、W 行标准化（孤岛除外）、
  Moran's I ∈ [-1, 1]。
- 孤岛格（无邻居）会被标记并在日志中告警 —— 占比高说明该分辨率对该数据集过细。
