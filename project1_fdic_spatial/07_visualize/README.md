# 07_visualize · ⑦ 可视化（扩展阶段 · visualization）

> 规范：`datakit/PROJECT_STRUCTURE.md` §8 / §8.8。入口：`07_visualize.py`。
> `blocking: false`。

## 做什么

出两类图：**交互式**（Kepler.gl 自包含 HTML，关闭事件 + H3 R8 存款增长分层渲染）与
**报告图表**（事件研究、TWFE 系数、衰减曲线、空间模型对比、残差 Moran's I、τ 衰减）。

## 输入（**只读**上游）

- `../05_map/output/data/{branch_year_panel.parquet, branch_dim.csv, closure_exposure.csv}`
- `../06_estimate/output/{estimate.json, data/spatial_cross_section.parquet, data/did_event_long.parquet}`

## 输出

| 文件 | 说明 |
| --- | --- |
| `output/manifest.json` | **图清单**（§8.8.5）：文件名 → 标题 → 口径 → 来源 → alt_text（README 直接引用，不手写第二份） |
| `output/figures/*.png` + `*.pdf` | 每张图双格式：PNG 看、PDF 进文档 |
| `output/kepler/kepler_map.html` | 浏览器自包含地图（CSV 以 base64 内嵌，离线可开） |
| `output/data/cell_year.csv` | H3 cell × 年聚合（Kepler 图层数据） |

## 出图约定（§8.8）

- 中文：注册微软雅黑，`axes.unicode_minus=False`，PDF 嵌入 TrueType；
- 标题写**结论**不写字段名；轴标签带单位；脚注标数据来源；
- 色板 Okabe–Ito / viridis，禁止红绿同现、jet 彩虹、3D、双 Y 轴；
- 每张图必带：结论标题、单位、样本量/时空范围、口径、来源路径、生成脚本+版本+时间、alt_text。

## 怎么跑

```powershell
python main.py --stage 07
```
