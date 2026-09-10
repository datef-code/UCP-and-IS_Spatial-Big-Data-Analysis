# 09_interactive · ⑨ 交互展示（扩展阶段）

> 项目：[project1_fdic_spatial](../README.md)　|　规范：`datakit/PROJECT_STRUCTURE.md` §8.2 / §8.5 / §8.8
> 立项依据：`datakit/suggestions_for_projects_0908.md` —— 产品 1 的主轴是**证据链叙事**。

- **kind**：`visualization`　**depends_on**：`05_map`、`06_estimate`、`07_visualize`
- **requires**：`estimate.json`、`mapped.csv`、`kepler/closed_events.csv`
- **extras**：`viz`（plotly）　**blocking**：false（失败只降级告警，不阻断五阶段）

## 本阶段做什么

⑦ 的 6 张静态图是「死的」：不能 hover、不能播放、不能切换口径，读者只能相信作者。
本阶段把它们升级为**可戳的**交互件——**只复用上游产物，不重跑任何模型**（硬约束：只读）。

| 产物 | 回答什么 | 交互点 |
| --- | --- | --- |
| `output/index.html` | 证据链能不能一眼看完？ | 叙事入口：结论 → 机制 → 证据 → 空间 → 限制 → 复现 |
| `output/event_study.html` | 处理效应随时间怎么走？平行趋势成立吗？ | hover 看每期系数 / 95% CI / p 值 |
| `output/attenuation.html` | 效应随距离衰减吗？换环宽结论还稳吗？ | 切换「标准环 / 合并环」×「计数 / 密度」 |
| `output/spacetime.html` | 关闭事件在空间上怎么扩散？ | mp4 内嵌：1994–2015 逐年扩散（进度条 / 倍速 / 可下载） |
| `output/spacetime.mp4` | 同上，单独文件 | 直接拖进 PPT / 汇报材料 |
| `output/kepler_timeline.html` | 能不能自己拖时间轴、定格任意年份？ | Kepler.gl 时间轴：逐帧播放关闭事件扩散（需联网加载 CDN） |

## 关键口径与决策理由

1. **为什么必须切「密度」口径**：环面积随距离平方增长，计数口径会随环变大而虚高。
   密度 = 环内同业均值 ÷ 环面积（π(r₂²−r₁²)），才是可比的距离衰减。
2. **为什么同时给「合并环」**：坐标精度分年代（2023–2025 EXACT 85.98%，
   1994–2022 屋顶级仅 16.37%）→ <1 km 环有系统性失真，主表用 5 km 中等环、
   并始终给出合并环敏感性（详见 `../data_raw/README.md`）。
3. **时空动画为什么是 mp4 而不是 plotly 帧**：`go.Frame` 会把每帧的点重复写进 HTML
   （27k 点 × 32 帧 → **6.3 MB** 且播放卡）；改成 **matplotlib FuncAnimation → mp4 →
   `<video>` base64 内嵌**后为 4.4 MB（mp4 本体 1.6 MB），浏览器原生解码、
   带进度条与倍速。代价是没有 hover 交互——那部分由 `event_study` / `attenuation` 承担。
4. **布局与节奏（按反馈定稿）**：
   * **上下布局**，不左右并排——并排会把地图压得很小、看不清扩散发生在哪。
     地图占上部约 55%（图幅 10.8×12.4 in @110 dpi = 1188×1364 px），统计图在下部同步推进。
   * **放慢**：每年 **4 个子帧**（新点淡入 + 柱子长高 + 累计线推进），fps=5
     → **每年 0.8 s、全程 17.6 s**（22 年）。最初每年只闪 0.2 s，根本来不及看清。
5. **图幅范围由事件数据本身决定，不写死**：取事件经纬度的 **1%–99% 分位数 + padding**
   （实测约 24.2–49.2°N / -125.4–-68.2°W）。此前写死 `-180..-60 / 15..72`，
   阿拉斯加把本土挤到画面右侧 1/3；写死范围也违背「口径来自数据」的原则。
   落在画幅外的点数（~180）会在副标题写明。
6. **底图＝州轮廓（只画线，不填色）**：`assets/us_states.geojson`（美国人口普查局衍生，
   **公共领域**，一次性下载后随项目走，**运行期不联网**）。此前没有底图，
   27k 个网点只能在深色背景上勾出隐约轮廓、看起来「很暗」。
   预解析成 `LineCollection` 后逐帧 `add_collection`，避免 128 帧重复解析地理数据。
7. **动画年份也由数据决定**：实测 `SIMS_ACQUIRED_DATE` 只到 **2015**，
   2016 起没有任何关闭事件——此前硬画到 2025，等于一半时长在放空气。
8. **为什么 plotly 内联**（`include_plotlyjs=True`）：保证单文件离线可开、挪动不丢图，
   代价是每页约 4–5 MB。
9. **时间轴为什么放 ⑨ 而不放 ⑦**：⑦ 是核心可视化阶段，产出固定的静态 Kepler 地图；
   时间轴是**交互增强**（§8.8 扩展可视化），应留在扩展阶段、不能反向污染核心阶段。
   `kepler_timeline.html` 只读 ⑦ 的 `closed_events.csv / h3_cells.csv / kepler_config.json`，
   注入 `timeRange` 过滤 + `animationConfig` 生成，**不重算、不改写 ⑦ 的产物**。
   它与 mp4 互补：mp4 是「自动讲一遍」，Kepler 时间轴是「自己拖进度条戳」。
10. **时间轴起点对齐 mp4**：`SIMS_ACQUIRED_DATE` 里有 4,612 起（17%）早于 1994 的历史并购
   （SOD 首年之前的存量），直接纳入会让时间轴前 24 年大段空白；故与 `anim_spacetime`
   一致，只保留 `acq_year >= 1994`。
11. **守住克制**：`index.html` 顶部与「限制」段反复标注**关联证据非严格因果**，
   并原样带上 `08_conclude` 的止损条件——这是本产品的可信度来源，不是减分项。

## 依赖与离线：Kepler UMD 的正确加载方式（踩坑记录）

`kepler_timeline.html` 是四件产物里唯一依赖外部 JS 的一件。曾在 Kepler.gl 3.x 的 UMD 包上
连踩五个坑，逐个实证（无头浏览器实测）后定稿如下：

| 坑 | 现象 | 现在的做法 |
| --- | --- | --- |
| **UMD 挂的全局名是 `KeplerGl`，不是 `KeplerGL`** | `typeof KeplerGL === "undefined"` **恒为真**，页面必报 "KeplerGL undefined" | `window.KeplerGl \|\| window.KeplerGL` 兜底 |
| UMD 把 react / react-dom / redux / react-redux / styled-components 列为 **externals** | 只挂 keplergl 一个 `<script>` → 加载即 `Cannot find module 'react'` | 按序先挂这 5 个全局，再挂 keplergl |
| 3.x 的 `default` 导出是 `React.memo` 对象（不是构造函数） | `new KeplerGL.default(...)` → `Ctor is not a constructor` | 官方 UMD 模式：`Redux.createStore` + `ReactRedux.Provider` + `KeplerGl.KeplerGl` |
| UMD **没有** `app.csvDataset()` 这个 API | `app.csvDataset is not a function` | `KeplerGl.processCsvData()` 解析 → `store.dispatch(KeplerGl.addDataToMap(...))` |
| **未挂载就 dispatch** | `ADD_DATA_TO_MAP` 被**静默丢弃**（datasets=0、无任何报错） | 显式等容器挂载（`[class*=kepler-gl]` 出现）后再灌数据 |

**为什么锁 React 18.3.1**：React ≥19 不再提供 UMD 构建，只能用 18.x 的 `umd/` 目录；
redux 取 4.2.1、react-redux 取 8.1.3（5.x / 9.x 同样没有 UMD 构建）；
styled-components 取 6.1.8（与 kepler.gl 3.2.0 的 peerDependency 一致）。

**离线**：默认 CDN（unpkg → jsdelivr → npmmirror 依次回退）。想完全断网打开，把 6 个依赖
放进 `09_interactive/assets/kepler/`（文件名见 `09_interactive.py` 的 `_KEPLER_DEPS_JS`）：

```powershell
cd project1_fdic_spatial
mkdir -p 09_interactive/assets/kepler
$b = "https://unpkg.com"; $d = "09_interactive/assets/kepler"
curl -L -o "$d/react.production.min.js"     "$b/react@18.3.1/umd/react.production.min.js"
curl -L -o "$d/react-dom.production.min.js" "$b/react-dom@18.3.1/umd/react-dom.production.min.js"
curl -L -o "$d/redux.min.js"                "$b/redux@4.2.1/dist/redux.min.js"
curl -L -o "$d/react-redux.min.js"          "$b/react-redux@8.1.3/dist/react-redux.min.js"
curl -L -o "$d/styled-components.min.js"    "$b/styled-components@6.1.8/dist/styled-components.min.js"
curl -L -o "$d/keplergl.min.js"             "$b/kepler.gl@3.2.0/umd/keplergl.min.js"   # 约 15 MB
```

放好后加 `?local=1` 强制优先读本地（浏览器报告离线时也会自动优先本地）。
**没有 Mapbox token 时底图为空白，但 Hexagon / Point 图层照常渲染**；要用官方底图就
`kepler_timeline.html?mapbox=你的token`。

## 输入 / 输出

- **输入（只读）**：`06_estimate/output/estimate.json`、`05_map/output/mapped.csv`、
  `07_visualize/output/kepler/{closed_events.csv, h3_cells.csv, kepler_config.json}`
- **输出**：`output/{index,event_study,attenuation,spacetime,kepler_timeline}.html` +
  `output/manifest.json` + 审计附件 `kepler_timeline_{events.csv, config.json}`
  （§8.8.5 结构：每图带 question / alt_text / source / n / scope / unit）

## 运行

```powershell
cd E:\workspace\workbuddy\project\data_use\datakit
.\.venv\Scripts\python.exe ..\project1_fdic_spatial\main.py --stage 09
```

打开 `output/index.html` 即可（离线可用，无需起服务）。
