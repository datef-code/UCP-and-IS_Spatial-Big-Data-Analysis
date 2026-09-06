# 03_clean · ③ 清洗

> 规范：`datakit/PROJECT_STRUCTURE.md` §2-③。入口：`03_clean.py`。

## 做什么

回答「动了哪些数据、为什么动、动了多少」：形状变化、缺失单元格前后、
**按字段影响**（填充 / 越界置空 / 替换 / 因该字段删除的行数 / 类型转换）、按操作影响，
以及逐条可审计的决策日志。

## 输入

- `../02_profile/output/raw_long.parquet`（优先；不存在时回退到只读源数据重跑）

## 口径

全部来自 `config/clean_plan.yaml`（**改口径不改代码**）：

1. `drop_na(UNINUMBR)` —— 追踪主键缺失无法定位网点；
2. `drop_duplicates(UNINUMBR × YEAR, keep=last)` —— 面板主键唯一；
3. `clip(SIMS_LATITUDE / SIMS_LONGITUDE, on_violation=to_null)` —— 越界坐标**置空而非截断**（截断会伪造位置）；
4. `clip(DEPSUMBR, lower=0, to_null)` —— 存款不能为负；
5. `astype` 年份 / 事件日期。

明令禁止的动作（`clean_plan.forbidden`）：**不得填充** `SIMS_ACQUIRED_DATE`
（缺失=右删失）、经纬度（会伪造空间位置）、`BRNUM`。④ 会复核是否真的没被执行。

## 输出

| 文件 | 说明 |
| --- | --- |
| `output/clean_report.md` | 清洗报告（**先看这份**：形状变化 + 决策 + 影响） |
| `output/decisions.yaml` / `decisions.md` | 决策日志（步骤 / 动作 / 字段 / 原因 / 影响行 / 可逆性） |
| `output/impact.yaml` | 按操作 / 按字段的影响 |
| `output/filled_by_field.csv` | 填充 / 置空 / 截断 / 替换 按字段统计 |
| `output/dropped_by_field.csv` | 因该字段删除的行数 + 类型前后 |
| `output/cleaned.csv` / `cleaned.parquet` | 过程数据（可重建），下游 ④⑤ 的输入 |

## 怎么跑

```powershell
python main.py --stage 03
```
