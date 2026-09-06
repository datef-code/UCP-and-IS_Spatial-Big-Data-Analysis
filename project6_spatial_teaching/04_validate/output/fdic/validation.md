# ④ 校验报告 · fdic

> 生成时间：2026-09-06T20:55:19　断言口径：`config/assertions.yaml`

- 通过 7 / 7
- 阻断项（P0 未过）：**无**

| 断言 | 严重度 | 结果 | 实际 | 期望 | 说明 |
| --- | --- | --- | --- | --- | --- |
| lat_in_range | P0 | PASS | 0 | 0 | 字段 lat 越界 0 个 |
| lon_in_range | P0 | PASS | 0 | 0 | 字段 lon 越界 0 个 |
| lat_not_null | P0 | PASS | 0.0 | <= 0.0 | 字段 lat 缺失率 0.0000% |
| lon_not_null | P0 | PASS | 0.0 | <= 0.0 | 字段 lon 缺失率 0.0000% |
| rows_after_clean | P0 | PASS | 148137 | >= 1 |  |
| value_non_negative | P1 | PASS | 0 | 0 | 字段 value 负值 0 个 |
| version_lock_reproducible | P1 | PASS | 首次冻结（无历史版本可比对） | version_lock.json 中的库版本与本次运行一致 | 教学代码随版本冻结，版本漂移须重新出图 |
