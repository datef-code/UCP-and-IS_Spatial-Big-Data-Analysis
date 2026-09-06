# 06_visualize · ⑥ 可视化（扩展阶段）

> 项目：[project6_spatial_teaching](../README.md)　|　规范：`datakit/PROJECT_STRUCTURE.md` §8.2 / §8.5 / §8.8

- **kind**：`visualization`　**depends_on**：`05_map`　**requires**：`ladder_report.json`、`L2_spatial_lag.csv`
- **extras**：`geo`（h3 + matplotlib）　**blocking**：false（失败只降级告警，不阻断五阶段）

## 本阶段做什么

为**开源电子书 / 知乎专栏 / B站视频课**生成静态素材：只读上游 `05_map` 的 L0→L3 产物，
不引入任何新算法、不做新建模（本方案是「放大器」）。

| 图 | 文件（`output/<dataset>/figures/`） | 回答的问题 |
| --- | --- | --- |
| L0 格值集中度 | `01-L0-cell-value-ecdf.png` | 格值是均匀分布还是高度集中？ |
| L2 Moran 散点 | `02-L2-moran-scatter.png` | 格值与邻居均值是否同向变化？ |
| L3 距离环溢出 | `03-L3-ring-spillover.png` | 热点周边溢出是否随距离衰减？ |
| 全局对比 | `output/figures/01-global-ladder-comparison.png` | 四个数据集的规模与自相关差多少？ |

每张图同时出 **PNG（看）+ PDF（进文档）**，并登记进 `manifest.json`（标题 / alt_text / 口径 /
来源产物 / n / 单位 / 脚注）。

## 运行

```powershell
python main.py --stage 06
```

## 出图规范（§8.8）

- 标题写**结论**不写字段名；副标题放口径与 `n=`；轴标签带单位；脚注标来源产物与生成时间。
- 配色 Okabe–Ito / viridis，六边形分箱处理 > 5k 点，despine，只留 y 轴浅灰网格。
- 中文字体：Microsoft YaHei 优先（`axes.unicode_minus=False`，PDF 内嵌 TrueType）。
- 禁止：红绿同现、jet 彩虹、3D、双 Y 轴、旋转 45° 刻度、全图数值标签。
