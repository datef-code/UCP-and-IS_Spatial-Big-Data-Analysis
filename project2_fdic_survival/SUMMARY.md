# SUMMARY.md · project2_fdic_survival

> FDIC 网点寿命生存模型（离散时间 logit / cloglog + SHAP + 空间残差）
> 自动生成于 2026-09-06T19:59:34；规范见 `datakit/PROJECT_STRUCTURE.md`。

## 阶段摘要

| 阶段 | 状态 | 关键指标 |
| --- | --- | --- |
| 01_discover | ✅ | file_count=32；group_count=1；total_size_human=1.58 GB；columns_consistent=True |
| 02_profile | ✅ | rows=2822977；columns=10；year_range=1994-2025；level_distribution={'important': 5, 'required': 4, 'ignore': 1}；outliers=506766；violation_kinds=3；tracking_key=UNINUMBR |
| 03_clean | ✅ | rows_before=2822977；rows_after=2702716；removed_rate=4.26%；steps=6 |
| 04_validate | ✅ | checks=9；passed=8；recommendations=2；right_censored_rate=0.471 |
| 05_map | ✅ | branches=152538；banks=15505；closed_rate=0.529；right_censored_rate=0.471；geo_method=h3_r7 |
| 06_train | ✅ | panel_rows=1667283；test_auc=0.8814；test_c_index=0.8096；test_brier=0.1609；moran_i=0.1412；top_shap_feature=year |
| 07_visualize | ✅ | figures=6；branches=140751 |
| 08_conclude | ✅ | conclusion=网点不是「老死」而是「被关」——谁家的网点（银行层脆弱性）与什么时候（危机后 2009–2014 整合窗口，关闭率翻倍）比网点自身年龄更能解释生死；规模是护城河（存款越大越长寿），多网点且地理分散的银行其网点是行业重组的首选裁撤对象。模型测试 AUC 0.881 / C-index 0.810；残差 Moran's I 0.141（p=0.005）说明本地市场因素仍未进入模型。；test_auc=0.8814… |

## 一句话结论

> 网点不是「老死」而是「被关」——谁家的网点（银行层脆弱性）与什么时候（危机后 2009–2014 整合窗口，关闭率翻倍）比网点自身年龄更能解释生死；规模是护城河（存款越大越长寿），多网点且地理分散的银行其网点是行业重组的首选裁撤对象。模型测试 AUC 0.881 / C-index 0.810；残差 Moran's I 0.141（p=0.005）说明本地市场因素仍未进入模型。
