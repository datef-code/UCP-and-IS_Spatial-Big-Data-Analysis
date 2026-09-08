# ④ 校验报告

- 校验时间：2026-09-08T10:06:39
- 断言总数：8，通过：8，失败：0
- **是否存在阻断项（P0 失败）：否**

## 断言结果

| 名称 | 严重度 | 结果 | 实际 | 期望 | 说明 |
| --- | --- | --- | --- | --- | --- |
| uninumbr_not_null | P0 | PASS | 0.0 | <= 0.0 | 字段 UNINUMBR 缺失率 0.0000% |
| uninumbr_year_unique | P0 | PASS | 0 | 0 | 重复行 0 条 |
| lat_in_range | P1 | PASS | 0 | 0 | 字段 SIMS_LATITUDE 越界 0 个 |
| lon_in_range | P1 | PASS | 0 | 0 | 字段 SIMS_LONGITUDE 越界 0 个 |
| depsumbr_non_negative | P1 | PASS | 0 | 0 | 字段 DEPSUMBR 负值 0 个 |
| brnum_not_tracking_key | P1 | PASS | 0.724277 | > 0（存在重编号 → 必须用 UNINUMBR） | 并购关闭网点 29,613 家中 21,448 家 BRNUM 跨年变化（72.43%）→ 追踪主键固化为 UNINUMBR |
| coordinate_exact_ratio | P2 | PASS | 0.510508 | —（信息性断言） | 坐标最高精度占比 51.05%（全期混合口径 EXACT=45.45% / US_Rooftop=5.60%；最高精度（EXACT 或 US_Rooftop）合计 51.05%）→ <100%，<1 km 环有系统性失真，须同时产出合并环敏感性结果 |
| control_coverage | P1 | PASS | 0.983386 | >= 0.50 | 关闭事件 29,613 起，同城（同 MSABR）对照覆盖 98.34% |

## 必要字段核验

- required 字段：UNINUMBR, CERT, YEAR, DEPSUMBR
- 清洗后仍有缺失：无
- 能否进入下一步：**能**

## 平行趋势（数据侧准备）

- 口径：dep_chg_rate clip 到 ±50pp（与 ⑥ 估计同一口径）
- 处理组事件前增长：均值 0.0433 / 中位数 0.0170
- 对照组增长：均值 0.0705 / 中位数 0.0438
- 均值差：-0.0272

> 数据侧准备：事件前增长 vs 对照增长；正式平行趋势检验在 ⑥ 估计阶段做事件研究

## 建议清单

| 严重度 | 事项 | 证据 | 建议动作 |
| --- | --- | --- | --- |
| P2 | 坐标存在插值 | EXACT 占 51.05% | <1 km 环结果只作参考，主表用 5 km 中等环并始终给出合并环敏感性 |
