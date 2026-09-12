# 网点决策台 · 空间决策证据工作台（v2.2）

> **这是什么**：把 `project1_fdic_spatial`（空间溢出）、`project2_fdic_survival`（寿命风险）、
> `project6_spatial_teaching`（空间口径）与 `datakit`（工程底座）整合成**一个可操作的产品**：
> 输入参数 → 真实计算 → 可交付输出（报告 + JSON）。
>
> **边界**：本目录**只读**上游产物，**不修改任何已有文件**，不改动工作区外环境。
> 源数据（FDIC 1.58 GB / 教学 31.1 GB）不在版本库内——本产品只依赖**已入库的聚合产物**。

---

## 一、快速开始

> 第一次用？先看 **`portal/使用说明书_*.md`**——里面有启动方式、六步流程逐页说明、
> 两个内置示例项目的完整参数与**实测预期结果**、真实数据样例 JSON 的逐字段解释。

### 形态 A · 静态（默认，零依赖）

**双击 `index.html`**。离线可用、无需服务器、无需安装、无任何 CDN 依赖（图表为手写 SVG）。

可用模块：① 数据准入体检（问卷模式）· ② 冲击评估 · ③ 风险归因 · ④ 口径实验室 · ⑤ 评估报告

### 形态 B · 本地服务（可选增强）

**一键启动（推荐）**：双击 `portal/start.bat`（Windows）。
脚本会自动找 Python → 检查依赖 → 挑一个没被占用的端口 → 起服务并打开浏览器；
Git Bash / macOS / Linux 用 `bash portal/start.sh`。

```powershell
# 手动方式（等价）
./.venv/Scripts/python.exe portal/serve.py        # 默认 http://127.0.0.1:8765，自动开浏览器
./.venv/Scripts/python.exe portal/serve.py --port 9000 --no-browser
```

> 两个脚本都会设置 `PYTHONUTF8=1`：Windows 上 Python 的输出被重定向时默认用本地编码（GBK），
> 不设置会与 UTF-8 终端混用导致中文乱码。`start.bat` 本身刻意保持**纯 ASCII**——
> cmd.exe 用 OEM 代码页（zh-CN 为 GBK）解析批处理文件，`.bat` 里的中文会截断整行。

解锁能力：**上传客户自己的 CSV/TSV → 在本机真实调用 datakit 跑五阶段体检** → 自动预填准入问卷，
并输出 7 条可复跑断言（含 `(实体, 年份) 唯一`，与 project1 固化的同款口径一致）。

合规设计：仅监听 `127.0.0.1`；上传文件落在 `portal/.tmp/<uuid>/`，**响应结束后立即整目录删除**，
不持久化客户数据。

---

## 二、产品结构

```
工作台（评估项目）
 ├─ ① 数据准入体检   ← 判断能不能做、能拿到什么等级
 ├─ ② 冲击评估       ← 影响多大 / 传多远 / 第几年最深
 ├─ ③ 风险归因       ← 哪些门店最可能出事、由什么决定
 ├─ ④ 口径实验室     ← 换权重 / 换尺度，结论会不会翻
 └─ ⑤ 评估报告       ← 合成一份带边界与血缘的交付物
```

说明页：产品说明 · 证据与边界（含 **P0 修补看板** 与**可复现性真实状态**）· 关于（开发者视角 / FAQ / 变更日志）。

项目状态（输入、结果）保存在浏览器 `localStorage`，**不上传任何服务器**；支持导出/导入项目 JSON。

---

## 三、计算引擎（本产品与企业级要求最相关的部分）

所有模型系数**全部来自入库产物**，引擎内部**没有任何硬编码的模型系数**：

| 模块 | 计算依据（产物） |
|---|---|
| 结论强度评级器 | 由 `estimate.json` 的 `event_study.pre_trend_max_abs_t` 与 τ=−2/τ=0 量级比自动判定 A/B/C，并把结论文档里的止损条件变成**可执行规则** |
| 冲击评估 | `twfe.params/std_err`、`event_study.table`、`spatial_fits.slx`、`spatial_fits.ols`、`sensitivity.coordinate_precision` |
| 风险归因 | `cloglog_summary.txt` 的 46 项完整系数（含 95% CI），cloglog 链接 `h = 1 − exp(−exp(η))` |
| 口径实验室 | `project6/05_map/output/<ds>/ladder_report.json` ×4 |

### 三条工程原则

1. **纯函数**：`assets/engines.js` 不碰 DOM，可被 `node --test` 直接单测。
2. **护栏是一等公民**：每个返回值都带 `caveats[]`（使用边界）与 `source[]`（血缘），调用方不得丢弃。
3. **取不到就拒绝，不猜**：系数缺失 → `ok:false` + 原因；年份超出适用域 → 拒绝打分并解释。

```powershell
node --test portal/tests/engines.test.js     # 数值正确性 / 护栏行为 / 回归网（P0-1 SE 对拍、等级一致性、示例等级、报告降级）
```

---

## 四、产品如何对待"已知缺陷"

v2 的核心设计选择：**把限制做成产品功能，而不是写进免责声明**。

| 已知问题 | 产品中的对应行为 |
|---|---|
| β_post 是强度 0 处的外推，该点未被观测 | 结果页强制标注**观测支撑域下界**（log1p(1)=0.693）；输入落在外推区时弹红色警告；同时给出**零交叉点**（效应由负转正的强度） |
| 合并环敏感性实际未跑（只有标签） | 每次结果都强制披露"未验证"，并列入 P0 修补看板 |
| `bank_closed_rate` 目标泄漏 | 同时给出**全特征值**与**剔除泄漏特征后的保守值**，并说明二者必须一起看 |
| 2016+ 年份系数退化（完全分离） | 适用域守门：**拒绝**为超域年份打分，并解释原因 |
| 无时序外推验证、测试集事件率被富集 | 模型卡强制披露，明确"不可用于预测未来" |
| 结论强度争议（B 级还是 C 级） | 评级器按可执行阈值自动判定，判定依据逐条展示 |
| 可复现承诺不可验证 | 「证据与边界」页公开真实状态（无 `.git`、绝对路径、`.pkl` 不入库）与 34 条产物血缘 |

---

## 五、目录结构

```text
portal/
├── index.html              # 应用外壳（离线可开）
├── start.bat               # ★ 一键启动本地服务（Windows：双击即可）
├── start.sh                # ★ 一键启动本地服务（Git Bash / macOS / Linux）
├── serve.py                # 本地服务：上传体检 + 泛化接入 + 现场重估（仅标准库 + datakit/pandas）
├── build_data.py           # 数据层构建：真实产物 → data/portal_data.js
├── ingest.py               # ★ 泛化接入内核（多文件 / 内容级角色推断 / 形态路由 / 映射模板）
├── refit.py                # ★ 重估内核（用客户自己的数据现场拟合 TWFE/事件研究/空间/cloglog）
├── DESIGN.md               # v2 设计稿（含三视角审查发现的硬伤清单）
├── README.md               # 本文件
├── 使用说明书_*.md          # ★ 面向使用者的说明书：怎么用 + 内置样例逐条详解
├── assets/
│   ├── style.css           # 主题 / 布局 / 表单 / 打印（报告打印自动隐藏表单）
│   ├── charts.js           # 手写 SVG 图表（折线+置信带 / 曲线+支撑域 / 条形 / 柱状 / 环形）
│   ├── engines.js          # ★ 计算引擎层（纯函数，node --test 覆盖）
│   └── app.js              # 路由 / 页面 / 表单 / 数据接入页 / 报告渲染
├── data/
│   ├── portal_data.js      # 【自动生成】事实层，勿手改
│   ├── portal_data.json    # 【自动生成】同内容，供外部程序读取
│   ├── content.js          # 【手写】说明页叙事（不含数字）
│   └── tools.js            # 【手写】表单定义 / 选项 / 示例 / 修补看板 / 变更日志
├── samples/                # 可直接导入的项目 JSON 样例
├── .templates/             # 【运行时生成】字段映射模板（复用）
└── tests/
    ├── engines.test.js     # 引擎单测（node 原生 test runner）
    ├── test_ingest.py      # 泛化接入单测
    └── test_serve.py       # 旧体检规则单测
```

### 重建

```powershell
./.venv/Scripts/python.exe portal/build_data.py     # 重建事实层（终端会打印缺失登记）
node --test portal/tests/engines.test.js            # 引擎单测（含 P0-1 等回归网）
```

---

## 六、数据来源（血缘）

| 事实 | 来源产物 |
|---|---|
| 阶段指标与耗时 | `project{1,2,6}/logs/stage_summaries.json` |
| TWFE / 事件研究 / OLS·SAR·SEM·SLX / LM 检验 / 坐标精度 / 敏感性审计 | `project1/06_estimate/output/estimate.json`、`metrics.json` |
| cloglog 46 项系数、伪 R²、样本量 | `project2/06_train/output/cloglog_summary.txt`（正则解析） |
| 模型卡（泄漏标记 / 退化年份 / 事件率） | `replication_manifest.json`、`metrics.json` + 系数退化实测 |
| SHAP 特征重要性 | `project2/06_train/output/train_report.md` |
| 字段真实区间（滑块范围与默认值） | `project2/05_map/output/map.md`、`02_profile/output/profile.yaml` |
| L0→L3 阶梯（4 数据集） | `project6/05_map/output/<ds>/ladder_report.json` |
| SDK 行数 / 模块数 / 用例数 | `datakit/datakit/*.py`、`datakit/tests/*.py`（实测计数） |

> 为什么不用 CSV：仓库根 `.gitignore` 排除了 `*.csv` / `*.parquet` / `*/*/*/data`，
> 样本级明细不在版本库内。因此本产品一律以**入库的 JSON / MD / TXT / YAML** 为权威源，
> 取不到的指标显示「缺失 · 已降级」，**不画编出来的图**。

---

## 七、当前数据健康状态

`build_data.py` 末次运行（2026-09-11）实测：

- 阶段实例合计 **26**（9 + 9 + 8）
- datakit：13 模块 / **2,861 行** / 40 用例
- 缺失登记 **0 条**（所有图表均用真实数据绘制）
- 已登记产物血缘 **34 个文件**

---

## 七·五、v2.1 修复记录（对应 `REVIEW_20260911.md`）

| 级别 | 问题 | 状态 |
|---|---|---|
| **P0-1** | 边际效应标准误误用交互项系数（默认强度处 95% 区间跨 0） | **已修**：改用数据层 `post_x_strength_se`，并补「同号最坏情况」保守区间；新增公式对拍单测 |
| **P1-1** | 结论强度在「工作台 / 冲击页 / 报告」三处不一致 | **已修**：统一由同一评级器判定；冲击页不再把外生性写死为未判定 |
| **P1-2** | 示例项目外生性字段为布尔，与问卷枚举不一致 | **已修**：示例改为 `'yes'` / `'no'`；引擎三态归一并向后兼容旧项目 JSON |
| P2-1/5/6/7/8 | 血缘表空模块列、OLS 与 SLX 异号未披露、硬编码 p 值、打印样式未生效、Markdown 表头 | **已修** |
| C-1~C-7 | 内容层旧叙事（「预测台」/「轻微为负」/`v1.0`）、未渲染死字段、`tools.js` 硬编码模型统计 | **已修**：改名「归因」、口径对齐、产品页补渲染指标与价值主张、移除写死的模型统计 |
| 建议 A | 报告无法回答「这份 PDF 对应哪版数据层」 | **已做**：报告新增非加密指纹（输入 + 系数 + 数据层版本摘要），同输入同指纹 |
| P0-1/2/3 底层 | 导出强度分布、补跑合并环、expanding-window 重算 | **v2.2 已真实重跑**（见 §七·六），产物在 `portal/audit/` |
| P0-4 底层 | 统一 `W_treat` 取值 | **只读核对已定位**（`technical_report.md` 误用 OLS 系数）；修正需上游 `08_conclude.py` |

> 结论：**「能演示、不能交付」的三条阻塞已清除**——算错的数字、自相矛盾的等级、演示即错的示例。
> 剩余待办全部是「需要重跑管线」的方法论修补，刻意保留公开，而非隐藏。

## 七·六、v2.2：P0 底层重跑已完成（数据源在本机）

> v2.1 只做了展示层披露，底层一直挂着「待重跑」。v2.2 用仓库内的中间产物**真实重跑**了 P0-1/2/3，
> 产物落在 `portal/audit/`（**不覆盖任何上游文件**），并带复现校准。

| 硬伤 | 重跑结果 | 产物 |
|---|---|---|
| **P0-1** 强度外推 | 实测处理组 `strength_t0 ∈ [0.1, 13.7]`（网点级均值 0.685、中位 0.5、148 个离散取值）。边际效应改在**均值处**报：**−4.31pp，95% CI [−4.71, −3.92]**；口径厘清为**环加权和**（不是 log1p 计数） | `audit/rerun_p1_strength.py` |
| **P0-2** 合并环 | 三种距离环口径全部跑出系数且同号显著：细环 `+0.013823` / 合并环(沿用权重值) `+0.008018` / 合并环(等差衰减) `+0.009103`。合并环改变强度刻度，故按「单位相对暴露的斜率」比较 —— 差异 < 5% → **结论不依赖细环选择** | 同上 |
| **P0-3** 时序外推 | 随机划分 AUC `0.8814` → **时序外推（含泄漏）`0.8096`** → **剔除泄漏 `0.5322`（≈随机）**。21 个滚动窗口 + 单次 2015–2025 留出 | `audit/rerun_p2_outoftime.py` |
| **P0-4** 文档口径 | 已改上游 `08_conclude.py`：SAR 说明段改为从 `spatial_fits.slx.params/pvalues` 取值（现渲染 `0.008986 / p=0.00126`），并加注说明它 ≠ OLS 的 `treat_strength`（0.007313）；同时把「轻微为负」统一为「显著为负（量级远小于 post）」。重跑 ⑧ 后**四处产物 + 正文取值一致** | 上游 `08_conclude.py` + `build_data.py` 自动核对 |
| **P0-5** 可复现 | **从 32 个原始 SOD CSV 起步全链路重建通过**（4.1 分钟）：`raw_long` 2,822,977 行 / `cleaned` 2,702,716 行 / `panel` 2,702,716 行 / `did_panel` **1,814,985 行**全部一致；`strength_t0`、`dep_chg_rate`、`post`、`treated` 最大绝对差均为 **0**；`estimate.json` 头条系数（含 SE）最大绝对差 **0**。做法：隔离沙箱里真实执行上游 01→06 代码，**上游文件不被写入** | `audit/rerun_p5_full_chain.py` |
| **P0-6** 阈值口径 | 阈值写死在评级器，三处同源 + 回归单测锁定 | `assets/engines.js` |

**复现校准（P0-1/P0-2 成立的前提）**：审计重算的细环 `strength_t0` 与上游 `did_panel.parquet`
逐网点最大绝对差 **0.0**、首事件年不一致 **0 行**；细环 TWFE 系数与 `estimate.json` **完全一致**。
不通过就不出数——宁可不出，也不出对不上的数。

**看板升级**：`build_data.py` 现在从产物反推每条硬伤的 `auto_status`，与人工登记状态**并列显示**——
「看板说待修、实际已修」不再可能。

重跑与验证命令：

```
datakit/.venv/Scripts/python.exe portal/audit/rerun_p1_strength.py     # P0-1 / P0-2 / P0-4
datakit/.venv/Scripts/python.exe portal/audit/rerun_p2_outoftime.py    # P0-3
PYTHONPATH=datakit datakit/.venv/Scripts/python.exe portal/audit/rerun_p5_full_chain.py  # P0-5：原始 CSV → 06 估计，约 4 分钟
datakit/.venv/Scripts/python.exe portal/build_data.py                  # 重建事实层
datakit/.venv/Scripts/python.exe portal/tests/test_serve.py            # 体检规则单测（6 项）
node --test portal/tests/engines.test.js                               # 引擎回归
```

## 七·七、v2.3：泛化数据接入 + 现场重估（不再锁死特定数据）

v2.2 之前，产品有一条结构性硬伤：**它只认 FDIC 的列名、只认「实体-年面板」这一种形态，
且系数全部来自三个上游项目** —— 换成客户自己的数据（多份文件、字段不同）就用不了。

v2.3 把「数据接入」与「模型系数」拆成两层：

```
泛化层（与数据无关）          ingest.py
  Source  多文件 / 目录 / 通配符（按列名并集纵向拼接，缺列留空并登记）
  Mapping 角色由**内容**推断（年份靠值域、坐标靠值域+成对、实体靠"期上重复"），可人工覆盖
  Shape   panel / repeated_panel / event_log / cross_section / time_series / network / unknown
  Health  按形态路由规则集（不再硬套面板口径）
  Template 映射可存为模板复用
──────────────────────────────────────────
模型层（显式绑定，不匹配就禁用）  refit.py
  impact   TWFE 双向固定效应 + 事件研究（within 去均值 + 实体聚类 SE）
  spatial  KNN 权重 + OLS/SLX + 残差 Moran's I
  risk     cloglog（**特征表来自实际列**，不是 FDIC 固定清单）
```

**关键设计**：产出的 artifact 与 `portal_data.js` 的 `impact`/`risk` 段**同构**，
前端整体替换（不是合并）当前数据层 → 四个模块立刻按新系数工作，
且仓库产物里的项目专属文案（`strength_disclosure`、环敏感性、坐标精度词表）不会串味。
顶部横幅明示「当前数据层来自现场重估」，一键可恢复仓库产物。

**能力判定是数据条件的函数，不是开关**（实测）：

| 数据 | 形态 | impact | spatial | risk |
|---|---|---|---|---|
| FDIC 单年（76,097 行） | panel | ✗ 无时间维 | ✓ | ✓ |
| FDIC 6 年（493,406 行） | repeated_panel | ✓ | ✓ | ✓ |
| sz_bike 行程 | event_log | ✗ 无期维 | — | ✓ |
| SNAP 边表 | network | ✗ | — | ✓ |

不满足条件的模块**明确显示 ✗ 并说明原因**，而不是硬套一套不适用的系数。

### 新增接口（`serve.py`）

| 接口 | 说明 |
|---|---|
| `POST /api/ingest` | 多文件上传（自定义分帧，上限 512 MB），响应后立即删除 |
| `POST /api/ingest_paths` | 本机路径 / 通配符（大数据免上传；`limit` 控文件数） |
| `POST /api/refit` | 现场重估（JSON 传 paths，或分帧重发文件）；`roles` / `options` 指定映射与处理定义 |
| `GET/POST /api/templates` | 映射模板存取 |

### 命令

```powershell
node --test portal/tests/engines.test.js                    # 引擎（46 项）
datakit/.venv/Scripts/python.exe portal/tests/test_ingest.py   # 泛化接入（6 项）
datakit/.venv/Scripts/python.exe portal/tests/test_serve.py    # 旧体检规则（6 项）

# 命令行直接接入 + 重估（不经浏览器）
datakit/.venv/Scripts/python.exe portal/ingest.py --paths "data_raw/fdic/*.csv" --limit 6
datakit/.venv/Scripts/python.exe portal/refit.py  --paths "data_raw/fdic/*.csv" --limit 6 --out artifact.json
```

### 仍未覆盖（刻意公开）

- 重估的空间样本是**实体级均值截面**（非格级），与 project1 的 H3 R8 格级截面口径不同；
- 重估不做距离环敏感性、不做时序外推验证 → 产物里 `rings_alternative_has_coefficients=false`、
  `out_of_time_validated=false`，评级器据此如实降级，不假装跑过；
- `refit.py` 不做变量筛选与共线性诊断，特征数上限 12，全凭输入列；
- 泛化层不做跨文件**实体对齐**（同名不同实体仍视为两个实体），需人工先清洗。

## 八、已知限制

1. **静态优先，无多租户**：不做用户系统、计费、持久化客户数据（后者反而是合规优势）。
   要产品化为订阅/API（商业化路径 M3）需补服务层。
2. **商业数字仍为占位**：TAM/SAM/SOM、客单价、人日均一律标注「待填」——业务数字不臆测。
3. **六项 P0 已全部闭环（v2.2）**：P0-1/2/3 已重跑并带复现校准；P0-4 已改上游
   `08_conclude.py`（④ 处产物 + 正文取值一致）；P0-5 已从 32 个原始 SOD CSV 起步
   **全链路重建通过**（行数与数值最大绝对差全部为 0）；P0-6 阈值口径写死并有单测。
   产物全部在 `portal/audit/`，详见「证据与边界 → 修补看板」（看板状态 vs 实检状态并列）。
   仍未覆盖：07_visualize / 08_conclude 的**图上产物**不在沙箱对拍范围内（本轮只对拍到 ⑥ 估计；
   ⑧ 的文本产物已用真实项目重跑并单独核对），以及 `09_interactive` 未重跑。
4. **口径不一致待修**：`project1/08_conclude/output/technical_report.md` 的 SLX `W_treat` 写作
   `0.0073 (p=0.009)`，`estimate.json` 为 `0.008986 (p≈0.0013)`。本产品全程以 `estimate.json` 为准。
5. **页码与可视化未做视觉验收**：改动后请用 `window.SDP_APP.render('<pageId>')` 在控制台逐页渲染，
   或直接点检；引擎逻辑请以 `node --test` 为准。
