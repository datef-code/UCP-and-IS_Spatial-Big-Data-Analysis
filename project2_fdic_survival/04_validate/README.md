# 04_validate · ④ 校验

> 项目：[project2_fdic_survival](../README.md)　|　规范：`datakit/PROJECT_STRUCTURE.md` §2-④

## 本阶段做什么

回答「洗得对不对、能不能进下一步」：断言结果（P0 阻断 / P1 / P2）、整体与**逐字段前后对比**
（② 画像 vs ③ 清洗后）、清洗效果评估、必要字段核验、**分级可操作建议清单**。

## 输入 / 输出

- **输入**：③ 的 `cleaned.parquet`、② 的 `fields.csv` / `profile.yaml` + `config/assertions.yaml`
- **输出**（本阶段 `output/`）：

| 产物 | 内容 |
| --- | --- |
| `validation.yaml` / `validation.md` | 断言结果（含严重度）+ 生存口径核验 + 建议清单 |
| `comparison.yaml` / `comparison.md` | 整体与逐字段前后对比 + 清洗效果评估 |
| `before_after.csv` | 逐字段：缺失率 / 唯一值 / 均值 / 中位数 / 类型 前→后 |

## 实现

`04_validate.py::run(project)`：`config/assertions.yaml` 编译为 `dk.validate` 断言，
`kind: custom` 的四条由本阶段实现（BRNUM 重编号、死亡不早于出生、右删失比例、事件是否落在窗口内）。

## 本阶段口径要点（本次运行）

- **9 条断言，8 条通过，无 P0 阻断**；唯一失败：`death_after_birth`——80,695 个有起止年份的网点中
  有 1 个死亡早于出生（P1，记入已知限制）。
- 必要字段（UNINUMBR / CERT / YEAR / DEPSUMBR）清洗后**无缺失** → 可进入 ⑤。
- 生存口径核验：网点 152,538；右删失 47.10%；左截断 51.76%（⑥ 建模时剔除事件早于首次观测的样本）；
  坐标缺失 4.19%。
- 死亡年取「该网点出现过的最晚 `SIMS_ACQUIRED_DATE`」—— 该字段只在并购当年及之后若干年出现，
  按末行取值会把已关闭网点误判为存活（右删失率会从 47% 虚高到 81%）。
