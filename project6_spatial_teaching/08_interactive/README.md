# 08_interactive · ⑧ 交互教材（扩展阶段）

> 项目：[project6_spatial_teaching](../README.md)　|　规范：`datakit/PROJECT_STRUCTURE.md` §8.2 / §8.5 / §8.8
> 立项依据：`datakit/suggestions_for_projects_0908.md` —— 产品 6 的主轴是**可复现交互教材**。

- **kind**：`teaching`　**depends_on**：`04_validate`、`05_map`
- **requires**：`ladder_report.json`（**必需**）　`L2_spatial_lag.csv` / `mapped.csv`（**可选增强**）
- **extras**：`geo`（h3 + libpysal）　**blocking**：false

## 本阶段做什么

教学产品最忌堆静态图 —— 学生看不懂逻辑链。本阶段把本教程最重要的一句判断
「**『邻居』怎么定义，决定你能看到什么结论**」做成能亲手拨的开关，
并把内容组织成一套**面向新人的产品矩阵**（而不是几张孤立的图）：

| 产物 | 回答什么 | 交互点 |
| --- | --- | --- |
| `output/index.html` | 从哪开始？ | Hero + L0→L3 学习路径 + 产品矩阵 + 四数据集结构表 + version_lock 复现表 |
| `output/ebook/index.html` | **教材主载体**：能一页页翻着读完吗？ | 15 页；常驻分组目录 + 关键词搜索 + 进度条/页码 + 深色模式 + 记住读到哪；每章「你将学到 / 章内交互 / 本章结论 / 最容易踩的坑 / 下一步」 |
| `output/moran_explorer.html` | Moran's I 怎么读、四个数据集差多少？ | I 对比条 + 四象限解读 + 公式；格级 CSV 在时可切数据集 × 权重 × 尺度的真交互散点 |
| `output/weight_lab.html` | 「邻居」是谁定的、孤岛有多致命？ | 切数据集看 L1 详情；六边形邻接 SVG；平均邻居 × I 气泡散点；孤岛率条 |
| `output/ring_decay.html` | 同一个数据，两种口径为什么相反？ | `updatemenus` 一键切「环内求和 / 溢出密度 / 归一化」 |
| `output/ladder_compare.html` | 四个数据集在每一层差多少？ | 8 个指标下拉切换 + 三层对数折线 + 完整数字表 |
| `output/method_atlas.html` | 这条管线用了哪些方法、各有什么坑？ | 方法卡可展开（输入/输出/参数/为什么/坑/代码位置），按 L0–L3 分层筛选 |
| `output/quiz.html` | 学完了吗？ | 12 题即时判分，**题目与答案由上游数字生成** |
| `output/ladder_evolution.html` | 四层怎么串成一条链？ | mp4 内嵌的四段演化动图（点 → 格 → 邻居 → 滞后 → 距离环） |

## 代码结构（为什么要拆 4 个模块）

单个 2000+ 行的脚本没法维护。按「数据 / 设计系统 / 交互件 / 电子书」切开：

| 模块 | 职责 |
| --- | --- |
| `studio_data.py` | 唯一权威数据源与降级策略（见下） |
| `studio_ui.py` | 设计令牌 + 组件 + 页面外壳。**改主色只动一处**，7 个页面风格才一致 |
| `studio_figs.py` | 7 个交互件 |
| `studio_ebook.py` | 电子书框架（15 页内容 + 导航/搜索/主题/进度） |
| `08_interactive.py` | 编排入口（规范要求与目录同名），负责 manifest 与降级日志 |

## 关键口径与决策理由

1. **唯一权威源 = `05_map/output/<ds>/ladder_report.json`**。
   格级 CSV（`L2_spatial_lag.csv` / `mapped.csv`）受仓库根 `.gitignore`
   约束**不入库**（`*/*/*/*.csv`），而重跑 ⑤ 映射又要 30 GB 原始数据。
   因此定了一条明确口径：**CSV 在 → 出可交互散点/动图；不在 → 相关面板降级为
   上游 ⑥ 阶段的真实静态图 + 显式披露**。本阶段 `blocking: false`，
   **绝不能因为缺 CSV 而整段失败**，也不能为了「好看」画一张编出来的图。
2. **I 与管线逐位对齐**：Queen + **原始格值**算出的 I 与
   `05_map/output/<ds>/ladder_report.json` 完全一致
   （fdic 0.1331 / sz_bike 0.7077 / brightkite 0.0132 / gowalla 0.5090）。
   这一点是标定出来的，不是碰巧 —— 曾用 log1p 得到另一组数值，与管线不符，
   已改为把「尺度」本身做成教学点（**Moran's I 依赖变量尺度**）。
3. **「格值尺度」与「权重方案」都是开关**：跨研究比较 I 必须同尺度、同权重、同网格。
4. **为什么权重在服务端算好**：30 万格 × 3 方案 × 2 尺度 × 4 数据集全塞进 HTML 会上百 MB，
   客户端也扛不住矩阵运算。权重与滞后由 h3 + libpysal 在服务端算
   （与 05_map 的 ladder 算法同一套），前端只切换与重绘 —— **每个 I 都可复现，不是客户端近似**。
   散点最多传 15,000 个抽样点（页面已显式披露：拟合线是抽样的近似，精确值看左上角 I）。
5. **KNN 踩过的坑**：不能算 n×n 距离矩阵（30 万格直接爆内存）。改用 3D 直角坐标 +
   sklearn KD-tree —— 弦距与大圆距离单调同序，最近邻排序完全一致，但快几个数量级。
   另外 `libpysal.weights.W` 必须覆盖**全部格（含孤岛）**，否则 `w.n < n` 会让滞后维度对不上。
6. **plotly.js 全站共享一份**（`output/assets/vendor/plotly.min.js`），不逐页内联。
   单份 plotly.min.js 就是 4.3 MB，7 页内联 = 30 MB；共享后产物目录从 ~22 MB 降到 ~11 MB，
   且电子书里多个 iframe 命中同一份缓存，翻页明显更快。
   代价：**自包含单元改为整个 `output/` 目录**（配图也在 `output/assets/fig/` 下），
   单独拷走一个 HTML 会丢图 —— 这正是前面「复制配图而不是相对引用」的原因。
7. **动图顺带发现的数据问题（已记入 `../data_raw/README.md`）**：`sz_bike` 的
   `05_map/output/sz_bike/mapped.csv` 里有 **(0,0) 空岛** 与
   **lat=47.66 / lon=132.54 的飞点**。两者都「合法」（在 `[-90,90]` / `[-180,180]` 内），
   所以 ④ 的范围断言漏网。演化动图按深圳 bbox 裁切（副标题写明剔除多少格）；
   **根治需要在 schema 里加业务范围的合理性规则，而不是只靠经纬度的几何范围** ——
   这本身就是一条好的教学素材（已收进电子书「常见误区 ⑦」）。
8. **可复现显性化**：`index.html` 把四个数据集的 `version_lock.json`
   （冻结时间 / 行数 / 库版本）做成表格 —— 教学产品的信服度来自「你能重跑出同样的数」。

## 电子书的「带新人」设计（为什么长这样）

| 设计点 | 解决什么 |
| --- | --- |
| 左侧**常驻分组目录**（入门 / L0–L3 / 综合 / 实践 / 收尾）+ 当前页高亮 | 新人不知道从哪开始、也不知道读到哪 |
| 每章**「你将学到」+ 章尾「下一步」** | 每一页都有明确目标和出口，不会迷路 |
| **关键词搜索**（按 `/` 聚焦） | 想回查某个概念时不用一页页翻 |
| **进度条 + 页码 + localStorage 记忆** | 分几次读完也能接上 |
| **深色模式**（随系统 + 手动切） | 投影用深色、自己看用浅色 |
| 每章**内嵌对应交互件**（iframe） | 「只读不做」学不会；翻到哪一章就能动手哪一章 |
| **常见误区 7 条 + 迁移清单** | 把散落各章的坑收拢；并给出「用到自己数据上」的检查清单 |
| **术语表** | 新人被术语卡住时有个地方查 |

## 输入 / 输出

- **输入（只读）**：`05_map/output/<dataset>/{ladder_report.json, L2_spatial_lag.csv?, mapped.csv?}`、
  `04_validate/output/<dataset>/version_lock.json`、`02_profile/output/<dataset>/profile.yaml`、
  `06_visualize/output/<dataset>/figures/*.png`
- **输出**：`output/{index, moran_explorer, weight_lab, ring_decay, ladder_compare,
  method_atlas, quiz, ladder_evolution}.html` + `output/ebook/index.html` +
  `output/assets/{fig/,vendor/}` + `output/manifest.json`
- 所有页面共享一套设计令牌，离线可开；`output/` 目录整体可拷走。

## 运行

```powershell
.\.venv\Scripts\python.exe ..\project6_spatial_teaching\main.py --stage 08
```

缺格级 CSV 时日志会写
`缺格级 CSV（4/4）→ 散点面板降级为上游静态图`，属**预期降级**，不是失败。
