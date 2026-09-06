# ④ 清洗前后对比

| 项 | 前 | 后 |
| --- | --- | --- |
| 行数 | 2,822,977 | 2,702,716 |
| 空单元格 | 3,681,987 | 2,974,055 |

## 逐字段对比

| 字段 | 等级 | 缺失率 前→后 | 变化 | 唯一值 前→后 | 均值 前→后 | 类型 前→后 |
| --- | --- | --- | --- | --- | --- | --- |
| UNINUMBR | required | 4.26% → 0.00% | -4.26% | 152,538 → 152,538 | 2.419e+05 → 2.419e+05 | float64 → float64 |
| BRNUM | ignore | 0.00% → 0.00% | +0.00% | 10,437 → 10,437 | 934.1 → 964.9 | int64 → int64 |
| CERT | required | 0.00% → 0.00% | +0.00% | 15,505 → 15,505 | 1.533e+04 → 1.467e+04 | int64 → int64 |
| YEAR | required | 0.00% → 0.00% | +0.00% | 32 → 32 | 2009 → 2010 | Int64 → Int64 |
| SIMS_ESTABLISHED_DATE | important | 35.81% → 32.97% | -2.84% | 24,382 → 24,382 | — | datetime64[us] → datetime64[ns] |
| SIMS_ACQUIRED_DATE | important | 66.36% → 64.87% | -1.50% | 5,832 → 5,832 | — | datetime64[us] → datetime64[ns] |
| DEPSUMBR | required | 0.00% → 0.00% | +0.00% | 312,301 → 310,041 | 1.009e+05 → 1.032e+05 | int64 → int64 |
| SIMS_LATITUDE | important | 8.04% → 4.19% | -3.85% | 500,715 → 500,713 | 37.91 → 37.91 | float64 → float64 |
| SIMS_LONGITUDE | important | 8.04% → 4.19% | -3.85% | 514,256 → 514,256 | -90.02 → -90.03 | float64 → float64 |
| BKCLASS | important | 0.00% → 0.00% | +0.00% | 7 → 7 | — | string → string |
| MSABR | optional | 0.00% → 0.00% | +0.00% | 411 → 411 | — | string → string |
| METROBR | optional | 3.25% → 3.40% | +0.14% | 2 → 2 | 0.7816 → 0.7777 | float64 → float64 |
| SIMS_PROJECTION | optional | 4.66% → 0.42% | -4.24% | 840 → 840 | — | string → string |

## 清洗效果评估

- 清洗幅度可控，可进入 ⑤ 映射
- 删除行比例：4.26%
- 填充单元格：707,932
- 违反禁止动作：无
