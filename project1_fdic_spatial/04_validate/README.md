# 04_validate · ④ 校验

> 规范：`datakit/PROJECT_STRUCTURE.md` §2-④。入口：`04_validate.py`。

## 做什么

回答「洗得对不对、能不能进下一步」：断言结果（P0 阻断 / P1 / P2）、整体与**逐字段前后对比**、
清洗效果评估、必要字段核验、**分级可操作建议清单**，外加本项目专属的四个校验
（前置验证③、坐标精度、归因对照覆盖、平行趋势数据侧准备）。

## 输入

- `../03_clean/output/cleaned.parquet`（回退 `cleaned.csv`）
- `../02_profile/output/fields.csv`（清洗前画像，用于前后对比）

## 口径

- 断言来自 `config/assertions.yaml`：`not_null` / `unique` / `geo_lat` / `geo_lon` / `non_negative`
  编译成 datakit 断言；`kind: custom` 的由本阶段实现。
- 建议规则（§3.4）：删除行比例 > 5% → P1；required 字段清洗后仍缺失 → P0；
  坐标最高精度 < 100% → P2（必须给合并环敏感性）。
  口径修正（2026-09-08）：`SIMS_PROJECTION` 词表 2023 年切换，按「EXACT ∪ US_Rooftop」
  计最高精度，并分年代报告（2023–2025 85.98% / 1994–2022 16.37%）。

## 输出

| 文件 | 说明 |
| --- | --- |
| `output/validation.yaml` / `validation.md` | 断言结果 + 必要字段核验 + 平行趋势准备 + 建议清单 |
| `output/comparison.yaml` / `comparison.md` | 整体 / 逐字段前后对比 + 清洗效果评估 |
| `output/before_after.csv` | 逐字段：缺失率、唯一值、均值/中位数、类型 前→后→变化 |

## 怎么跑

```powershell
python main.py --stage 04
```
