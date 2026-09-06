# 02_profile · ② 画像

> 项目：[project2_fdic_survival](../README.md)　|　规范：`datakit/PROJECT_STRUCTURE.md` §2-②

## 本阶段做什么

回答「字段有哪些、哪些必需、数据质量有多差」：字段清单（含 `schema.yaml` 等级）、
空值分析（按角色解释语义）、描述性统计、极端值 / 异常值、**规则违规**，
外加本项目的**关键发现：寿命追踪主键到底是 UNINUMBR 还是 BRNUM**。

## 输入 / 输出

- **输入**：`data_raw/fdic`（只读）+ `config/schema.yaml`（角色 / 等级 / 规则）
- **输出**（本阶段 `output/`）：

| 产物 | 内容 |
| --- | --- |
| `profile.yaml` / `profile.md` | 画像报告（机读 / 人读），含 `key_findings` |
| `fields.csv` | 字段清单：类型 / 角色 / 等级 / 非空 / 缺失率 / 唯一值 |
| `nulls.csv` | 空值表 + 按角色解释的语义（主键缺失=缺陷，事件缺失=右删失） |
| `outliers.csv` | 极端值汇总（逐字段异常数 / 上下界 / 占比） |
| `violations.csv` | 规则违规表（业务意义上的不合法值） |
| `raw_long.parquet` | 过程数据：全量长表，供 ③ 清洗复用（避免 1.7 GB 二次全量 IO） |

## 实现

`02_profile.py::run(project)`：逐年只读 10 个核心列（含 `BRNUM` 用于主键验证）→ 拼长表 →
`dk.profile`（roles 来自 `dk.schema_roles`）+ `dk.violations` / `dk.missing_fields` / `dk.unregistered_fields`。

## 本阶段口径要点（本次运行）

- 长表 **2,822,977 行 × 10 列**（1994–2025）；等级分布：required 4 / important 5 / ignore 1。
- **追踪主键**：1994 年 81,297 行里 `BRNUM` 唯一值仅 1,531 个，`UNINUMBR` 唯一值 73,469 个；
  全期 152,538 个可追踪网点中 76,440 个（**50.11%**）BRNUM 跨年变化 → **BRNUM 不可用，UNINUMBR 才是主键**。
- 缺失语义优先于缺失率：出生日期 35.81%（左截断候选）、死亡日期 66.36%（**右删失，禁止填充**）、
  经纬度 8.04%、存款与银行类别 0%。
- 异常值 506,766 条（IQR × 3.0）；规则违规 3 类（主键缺失、主键×年份重复、日期越界类）。
