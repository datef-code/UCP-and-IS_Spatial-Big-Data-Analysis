# 08_interactive · ⑧ 交互教材（扩展阶段）

> 项目：[project6_spatial_teaching](../README.md)　|　规范：`datakit/PROJECT_STRUCTURE.md` §8.2 / §8.5 / §8.8
> 立项依据：`datakit/suggestions_for_projects_0908.md` —— 产品 6 的主轴是**可复现交互教材**。

- **kind**：`teaching`　**depends_on**：`04_validate`、`05_map`
- **requires**：`L2_spatial_lag.csv`、`ladder_report.json`
- **extras**：`geo`（h3 + libpysal）　**blocking**：false

## 本阶段做什么

教学产品最忌堆静态图 —— 学生看不懂逻辑链。本阶段把本教程最重要的一句判断
「**『邻居』怎么定义，决定你能看到什么结论**」做成能亲手拨的开关。

| 产物 | 回答什么 | 交互点 |
| --- | --- | --- |
| `output/index.html` | 学习者能按阶梯看懂 / 能跑 / 能改吗？ | L0→L3 卡片 + 两件交互件 + version_lock 复现表 |
| `output/moran_explorer.html` | 权重方案怎么影响 Moran's I？ | 切数据集 × 权重 × 格值尺度，实时看散点 / 拟合线 / I |
| `output/ladder_evolution.html` | 网格化、权重、滞后、距离环怎么串成一条链？ | mp4 内嵌的四段演化动图（点 → 格 → 邻居 → 滞后 → 距离环） |
| `output/ladder_compare.html` | 四个数据集差多少？ | hover 看格数 / 平均邻居 / I |
| `output/ebook/index.html` | 内容能不能按阶梯一页页翻着读？ | **可翻页电子书骨架**：11 页（封面/目录/引言/L0–L3/对比/演化/结论/复现），左右箭头或键盘 ←/→ 翻页，TOC 跳转，进度条；每章嵌入对应交互图 |

## 关键口径与决策理由

1. **I 与管线逐位对齐**：本阶段 Queen + **原始格值**算出的 I 与
   `05_map/output/<ds>/ladder_report.json` **完全一致**
   （fdic 0.1331 / sz_bike 0.7077 / brightkite 0.0132 / gowalla 0.5090）。
   这一点是标定出来的，不是碰巧 —— 曾用 log1p 得到 0.0821 / 0.7892 / 0.2845 / 0.4004，
   与管线不符，已改为双尺度可切换并把差异本身做成教学点。
2. **「格值尺度」开关是本教材的第二个重点**：snap_brightkite 在原始格值下 I≈0.013，
   换 log1p 后 I≈0.285。**Moran's I 依赖变量尺度** —— 跨研究比较 I 必须同尺度、同权重、同网格。
3. **为什么权重在服务端算好**：30 万格 × 3 方案 × 2 尺度 × 4 数据集全塞进 HTML 会上百 MB，
   客户端也扛不住矩阵运算。因此权重与滞后由 h3 + libpysal 在服务端算（与 05_map 的
   ladder 算法同一套），前端只切换与重绘 —— **每个 I 都可复现，不是客户端近似**。
   散点最多传 15,000 个抽样点（页面已显式披露：拟合线是抽样的近似，精确值看左上角 I）。
4. **KNN 踩过的坑**：不能算 n×n 距离矩阵（30 万格直接爆内存）。改用 3D 直角坐标 +
   sklearn KD-tree —— 弦距与大圆距离单调同序，最近邻排序完全一致，但快几个数量级。
   另外 `libpysal.weights.W` 必须覆盖**全部格（含孤岛）**，否则 `w.n < n` 会让滞后维度对不上。
5. **动图的布局与节奏（按反馈定稿）**：
   * **上下布局**，不左右并排——并排会把地图压得很小看不清。
     地图占上部约 55%（图幅 10.8×12.4 in @110 dpi = 1188×1364 px），Moran 散点在下部同步长出。
   * **放慢**：4 段 × 45 帧、fps=6 → **30 s**（此前 4×40 帧 @16 fps 只有 10 s，
     快到看不清每段在做什么）。
6. **动图顺带发现的数据问题（已记入 `../data_raw/README.md`）**：`sz_bike` 的
   `05_map/output/sz_bike/mapped.csv` 里有 **(0,0) 空岛** 与 **lat=47.66 / lon=132.54 的飞点**。
   两者都「合法」（在 `[-90,90]` / `[-180,180]` 内），所以 ④ 的范围断言漏网。
   演化动图按深圳 bbox 裁切（副标题写明剔除多少格）；**根治需要在 schema 里加业务范围的
   合理性规则，而不是只靠经纬度的几何范围**——这本身就是一条好的教学素材。
7. **可复现显性化**：`index.html` 把四个数据集的 `version_lock.json`
   （冻结时间 / 行数 / 库版本）做成表格 —— 教学产品的信服度来自「你能重跑出同样的数」。

## 输入 / 输出

- **输入（只读）**：`05_map/output/<dataset>/{L2_spatial_lag.csv, ladder_report.json}`、
  `04_validate/output/<dataset>/version_lock.json`
- **输出**：`output/{index,moran_explorer,ladder_compare}.html` + `output/manifest.json`
- 三页均**内联 plotly**，单文件自包含、离线可开、挪动不丢图。

## 运行

```powershell
.\.venv\Scripts\python.exe ..\project6_spatial_teaching\main.py --stage 08
```
