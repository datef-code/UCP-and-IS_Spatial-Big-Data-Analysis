# SUMMARY.md · project1_fdic_spatial

> FDIC 网点关闭对周边同业的空间溢出（空间结构化 + DID/事件研究）
> 自动生成于 2026-09-06T19:26:16；规范见 `datakit/PROJECT_STRUCTURE.md`。

## 阶段摘要

| 阶段 | 状态 | 关键指标 |
| --- | --- | --- |
| 01_discover | ✅ | file_count=32；group_count=1；total_size_human=1.58 GB；columns_consistent=True |
| 02_profile | ✅ | rows=2822977；columns=13；year_range=1994-2025；level_distribution={'important': 5, 'required': 4, 'optional': 3, 'ignore': 1}；outliers=2383023；violation_kinds=3 |
| 03_clean | ✅ | rows_before=2822977；rows_after=2702716；removed_rate=4.26%；steps=8 |
| 04_validate | ✅ | checks=8；passed=8；recommendations=1；control_coverage=0.9834 |
| 05_map | ✅ | panel_rows=2702716；branches=152538；h3_cells=70109；closure_events=27018；event_type_dist={'alive_censored': 76097, 'attrition_missing': 46828, 'closed_ma': 29613} |
| 06_estimate | ✅ | twfe_post=-0.05259；twfe_post_x_strength=0.01382；twfe_p=0；event_study_tau0=-0.0438；resid_moran_p=0.001 |
| 07_visualize | ✅ | figures=6；h3_cells=51251；closure_events=27018 |
| 08_conclude | ✅ | conclusion=同业关闭后周边存活网点存款增速下行（τ=0 -4.38pp → τ=4 -10.1pp；TWFE post -5.26pp）；聚合层再配置而非区域净增 → 关联证据，非严格因果 |

## 一句话结论

> 同业关闭后周边存活网点存款增速下行（τ=0 -4.38pp → τ=4 -10.1pp；TWFE post -5.26pp）；聚合层再配置而非区域净增 → 关联证据，非严格因果
