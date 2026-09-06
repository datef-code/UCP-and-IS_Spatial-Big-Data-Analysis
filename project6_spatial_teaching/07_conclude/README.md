# 07_conclude · ⑦ 结论（扩展阶段）

> 项目：[project6_spatial_teaching](../README.md)　|　规范：`datakit/PROJECT_STRUCTURE.md` §8.5「结论」

- **kind**：`conclusion`　**depends_on**：`06_visualize`　**requires**：`global_visual_report.json`
- **blocking**：false

## 本阶段做什么

把 ④ 校验 / ⑤ 映射 / ⑥ 可视化的产出收敛成一页结论：**结论 + 已知限制 / 止损条件**。
所有数字来自本流水线实际产出（`05_map` 的 `ladder_report.json`、`04_validate` 的
`version_lock.json`、`06_visualize` 的 `global_visual_report.json`），不写没跑过的内容。

## 输入 / 输出

- **输入**：`05_map/output/<dataset>/ladder_report.json`、`04_validate/output/<dataset>/version_lock.json`、
  `06_visualize/output/global_visual_report.json`
- **输出**（`output/`，全局，不分数据集）：

| 路径 | 内容 |
| --- | --- |
| `conclusion.md` | 人读结论：定位、实测结果表、核心结论、已知限制、可复现性、传播形态 |
| `conclusion_report.json` | 机读结论（含 findings / known_limits / reproducibility） |

## 运行

```powershell
python main.py --stage 07
```

## 口径要点

- 定位是**放大器不是主菜**；核心判据是「读者 `git clone` 后能否按章节顺序复现 L0→L3」。
- **止损条件**：若 ④⑤ 未做，本方向退化为官方文档翻译 —— 应直接砍掉。
- 结论必须带约束：合成参数、抽样口径、许可限制（SNAP 不得商用）逐条写明。
