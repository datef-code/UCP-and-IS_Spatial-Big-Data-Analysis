# 网点决策台 · 空间决策证据工作台（v2）

> **这是什么**：把 `project1_fdic_spatial`（空间溢出）、`project2_fdic_survival`（寿命风险）、
> `project6_spatial_teaching`（空间口径）与 `datakit`（工程底座）整合成**一个可操作的产品**：
> 输入参数 → 真实计算 → 可交付输出（报告 + JSON）。
>
> **边界**：本目录**只读**上游产物，**不修改任何已有文件**，不改动工作区外环境。
> 源数据（FDIC 1.58 GB / 教学 31.1 GB）不在版本库内——本产品只依赖**已入库的聚合产物**。

---

## 一、快速开始

### 形态 A · 静态（默认，零依赖）

**双击 `index.html`**。离线可用、无需服务器、无需安装、无任何 CDN 依赖（图表为手写 SVG）。

可用模块：① 数据准入体检（问卷模式）· ② 冲击评估 · ③ 风险归因 · ④ 口径实验室 · ⑤ 评估报告

### 形态 B · 本地服务（可选增强）

```powershell
cd <仓库根>
./.venv/Scripts/python.exe portal/serve.py        # 默认 http://127.0.0.1:8765，自动开浏览器
./.venv/Scripts/python.exe portal/serve.py --port 9000 --no-browser
```

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

1. **纯函数**：`assets/engines.js` 不碰 DOM，可被 `node --test` 直接单测（当前 **26 项**）。
2. **护栏是一等公民**：每个返回值都带 `caveats[]`（使用边界）与 `source[]`（血缘），调用方不得丢弃。
3. **取不到就拒绝，不猜**：系数缺失 → `ok:false` + 原因；年份超出适用域 → 拒绝打分并解释。

```powershell
node --test portal/tests/engines.test.js     # 26 项：数值正确性 / 护栏行为 / 报告降级路径
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
├── serve.py                # 可选本地服务（仅标准库 + datakit/pandas）
├── build_data.py           # 数据层构建：真实产物 → data/portal_data.js
├── DESIGN.md               # v2 设计稿（含三视角审查发现的硬伤清单）
├── README.md               # 本文件
├── assets/
│   ├── style.css           # 主题 / 布局 / 表单 / 打印（报告打印自动隐藏表单）
│   ├── charts.js           # 手写 SVG 图表（折线+置信带 / 曲线+支撑域 / 条形 / 柱状 / 环形）
│   ├── engines.js          # ★ 计算引擎层（纯函数，26 项单测覆盖）
│   └── app.js              # 路由 / 九个页面 / 表单 / 报告渲染
├── data/
│   ├── portal_data.js      # 【自动生成】事实层，勿手改
│   ├── portal_data.json    # 【自动生成】同内容，供外部程序读取
│   ├── content.js          # 【手写】说明页叙事（不含数字）
│   └── tools.js            # 【手写】表单定义 / 选项 / 示例 / 修补看板 / 变更日志
└── tests/
    └── engines.test.js     # 引擎单测（node 原生 test runner）
```

### 重建

```powershell
./.venv/Scripts/python.exe portal/build_data.py     # 重建事实层（终端会打印缺失登记）
node --test portal/tests/engines.test.js            # 26 项引擎单测
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

## 八、已知限制

1. **静态优先，无多租户**：不做用户系统、计费、持久化客户数据（后者反而是合规优势）。
   要产品化为订阅/API（商业化路径 M3）需补服务层。
2. **商业数字仍为占位**：TAM/SAM/SOM、客单价、人日均一律标注「待填」——业务数字不臆测。
3. **六项 P0 修补未完成**：详见「证据与边界 → 修补看板」；受影响的模块已在页面上强制披露，
   而非隐藏。其中 P0-1/2/4 需要**重跑管线**，而源数据不在本机，因此当前无法完成。
4. **口径不一致待修**：`project1/08_conclude/output/technical_report.md` 的 SLX `W_treat` 写作
   `0.0073 (p=0.009)`，`estimate.json` 为 `0.008986 (p≈0.0013)`。本产品全程以 `estimate.json` 为准。
5. **页码与可视化未做视觉验收**：改动后请用 `window.SDP_APP.render('<pageId>')` 在控制台逐页渲染，
   或直接点检；引擎逻辑请以 `node --test` 为准。
