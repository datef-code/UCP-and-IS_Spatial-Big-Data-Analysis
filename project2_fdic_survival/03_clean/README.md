# 03_clean · ③ 清洗

> 项目：[project2_fdic_survival](../README.md)　|　规范：`datakit/PROJECT_STRUCTURE.md` §2-③

## 本阶段做什么

回答「动了哪些数据、为什么动、动了多少」：形状变化、缺失单元格前后、**按字段影响**
（填充 / 越界置空 / 因该字段删除的行数 / 类型转换）、按操作影响、逐条可审计的决策日志。

## 输入 / 输出

- **输入**：② 的过程数据 `02_profile/output/raw_long.parquet`（缺失时回退到只读源数据）
  + `config/clean_plan.yaml`
- **输出**（本阶段 `output/`）：

| 产物 | 内容 |
| --- | --- |
| `clean_report.md` / `clean_report.yaml` | 清洗报告：形状变化、缺失单元格、禁止动作复核 |
| `decisions.md` / `decisions.yaml` | 决策日志：步骤 / 动作 / 字段 / 原因 / 影响行 / 是否可逆 |
| `impact.yaml` | 按操作 + 按字段的影响汇总 |
| `filled_by_field.csv` / `dropped_by_field.csv` | 填充了多少、因哪些字段删了多少 |
| `cleaned.csv` / `cleaned.parquet` | 过程数据（可重建） |

## 实现

`03_clean.py::run(project)`：`dk.CleanPlan.from_spec(config)` → `dk.clean`；
**口径全在配置里**（改口径不改代码），代码只做报告拼装。

## 本阶段口径要点（本次运行）

- 2,822,977 → **2,702,716 行**（剔除 `UNINUMBR` 缺失 120,261 行，4.26%）；空单元格 3,458,580 → 2,870,909。
- 越界经纬度、负存款一律**置空不截断**；`UNINUMBR × YEAR` 去重。
- 生存口径红线（写在 `clean_plan.forbidden`，④ 复核）：
  **死亡日期（右删失）、出生日期（左截断）、经纬度一律禁止填充** —— 本次运行 0 条违反。
