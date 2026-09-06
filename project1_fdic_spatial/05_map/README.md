# 05_map · ⑤ 映射（空间结构化）

> 规范：`datakit/PROJECT_STRUCTURE.md` §2-⑤。入口：`05_map.py`。

## 做什么

回答「原始字段怎么变成分析字段」：

1. **网点-年面板**：派生存款年度变动额 `dep_chg` / 变动率 `dep_chg_rate`（结果变量）；
2. **网点维度**：经纬度 → H3 R8 网格（`dk.MappingScheme.geocode`）+ 事件判定
   （`closed_ma` 并购关闭 / `alive_censored` 仍存活=右删失 / `attrition_missing` 数据缺失）；
3. **exposure 结构**：以关闭事件为圆心构造距离环，各环内**同 BKCLASS（同业）**网点数 = 处理组强度，
   同 MSABR 存活网点 = 对照。

L1 设计取向：直接用**空间特征**（各环强度列）进入模型，而非区域 one-hot。

## 输入

- `../03_clean/output/cleaned.parquet`（回退 `cleaned.csv`）

## 口径

来自 `config/mapping.yaml`（纯业务意图，全人写）：

- H3 分辨率 `res=8`（平均边长 ≈ 0.46 km，匹配 0–1 km 细环）；`grid_disk(k=23)` ≈ 10 km 半径；
- 标准环 `0–1 / 1–3 / 3–5 / 5–10 km`；
- **坐标精度敏感性合并环** `0–2 / 2–5 / 5–10 km`（EXACT 坐标占比 < 100%，<1 km 环有系统性失真，两套都要产出）。

## 输出

| 文件 | 说明 |
| --- | --- |
| `output/map.yaml` / `map.md` | 映射报告（**先看 md**：操作明细 + 血缘 + 字段数据报告） |
| `output/lineage.csv` | 字段血缘：输出字段 ← 来源字段 / 表达式 / 映射方式 |
| `output/fields.csv` | 映射后字段数据报告（类型 / 非空 / 缺失率 / 唯一值 / 统计） |
| `output/mapped.csv` | 过程数据（= exposure 表，交付下游） |
| `output/data/branch_year_panel.parquet` | 网点-年长表 |
| `output/data/branch_dim.csv` | 网点维度表（含 H3 与事件判定） |
| `output/data/closure_exposure.csv` | 关闭事件 × 距离环 exposure 表 |

## 怎么跑

```powershell
python main.py --stage 05
```
