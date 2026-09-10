# SUMMARY.md · project6_spatial_teaching

> 空间结构化教学管线 · L0→L3 四阶认知阶梯（多数据集）
> 自动生成于 2026-09-10T12:35:03；规范见 `datakit/PROJECT_STRUCTURE.md`。

## 阶段摘要

| 阶段 | 状态 | 关键指标 |
| --- | --- | --- |
| 01_discover | ✅ | dataset_count=4；file_count=24975；total_size_human=31.1 GB |
| 02_profile | ✅ | datasets={'fdic': 152538, 'sz_bike': 8572465, 'snap_brightkite': 4747287, 'snap_gowalla': 6442892}；rows=19915182；violations=7 |
| 03_clean | ✅ | rows_before=19915182；rows_after=19910637；removed_rate=0.000228；datasets={'fdic': 148137, 'sz_bike': 8572465, 'snap_brightkite': 4747172, 'snap_gowalla': 6442863} |
| 04_validate | ✅ | checks_pass=28；checks_total=28 |
| 05_map | ✅ | cells=604173；datasets={'fdic': {'cells': 70456, 'moran_i': '0.1331'}, 'sz_bike': {'cells': 2661, 'moran_i': '0.7077'}, 'snap_brightkite': {'cells': 228476, 'moran_i': '0.0132'}, 'snap_gowalla': {'cells': 302580, 'mora… |
| 06_visualize | ✅ | figures=13；datasets=4 |
| 07_conclude | ✅ | datasets=4；conclusion=sz_bike 空间聚集最强（Moran's I=0.7077），snap_brightkite 最弱（0.0132）——空间权重矩阵定义对结论敏感 |
| 08_interactive | ✅ | figures=9；datasets=4 |

## 一句话结论

> sz_bike 空间聚集最强（Moran's I=0.7077），snap_brightkite 最弱（0.0132）——空间权重矩阵定义对结论敏感
