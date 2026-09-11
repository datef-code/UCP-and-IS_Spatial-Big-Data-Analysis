# MEMORY（长期记忆）

## 项目概况
- 仓库根含 `datakit/`（SDK + 规范，规范文档为 `datakit/PROJECT_STRUCTURE.md`）+ 三个数据产品项目：
  - `project1_fdic_spatial`：FDIC 网点关闭对周边同业的空间溢出（DID/事件研究/空间计量）。
  - `project2_fdic_survival`：FDIC 网点寿命生存模型（KM/SHAP/ROC）。
  - `project6_spatial_teaching`：空间结构化教学管线（L0 H3 → L1 权重 → L2 滞后 → L3 距离环，4 数据集）。
- 三项目均按 datakit v2 规范组织（01_discover ~ 05_map 内置五阶段 + 06 起扩展阶段）。
- 数据源：FDIC SOD 1994–2025（约 1.58 GB，只读）；追踪主键为 UNINUMBR（非 BRNUM）。

## 用户偏好 / 约定
- **只改被指定的文件**：用户强调「仅对此文件修改、项目内容暂不修改」时，严格限定改动范围。
- **展现形式观**：用户认为单一静态图片不足以支撑产品展示与信服度，倾向交互式（Plotly/Kepler/可下钻）、动画、一键复现（Binder/CI）等更「产品化」的展示；并要求**按产品差异化设计展现形式**（不同产品需求不同）。
- 文档/规范类修改需补「为什么」（字段语义、决策理由、血缘理由、可信度等），不要只写「是什么」。
- **教学/展示类产品的期望**：要「框架感 + 产品矩阵」，不是几张孤立图 —— 要有导航、目录、搜索、
  进度、深色模式、可下钻的方法卡、自测题；缺数据时**显式披露并降级**，不要画编出来的图。
- **仓库清理的边界（2026-09-10 用户拍板）**：「清理」= 只删**未追踪 / 已被 .gitignore 忽略**的
  缓存与中间文件（`__pycache__/`、`*.pyc`、`logs/pipeline.log`、gitignored 中间 CSV）。
  **已入库的产物一律保留**，即使体积大或可重建 —— 包括 `project6/output_legacy_v1/`、
  vendored `plotly.min.js`（8.3 MB）、交互阶段 `assets/fig/` 重复 PNG、大型 HTML/MP4。
  且**不改 `.gitignore`**。除非用户另行指定，不要提议删除这些。

## 工程环境（2026-09-10 建）
- 仓库根 `.venv`：`uv venv .venv --python 3.12` +
  `uv pip install --python .venv/Scripts/python.exe -e "./datakit[geo,viz]" libpysal scikit-learn`。
  跑任何项目脚本前先确认该 venv 存在（原本仓库没有 venv，全局 python 无任何包）。
- 本机 node 不在 PATH，可用 `C:/Users/fdate/.workbuddy/binaries/node/versions/22.22.2-2/node.exe`
  （用于校验生成页面里的内联 JS 语法）。
- **格级 CSV 不入库**：仓库根 `.gitignore` 的 `*/*/*/*.csv` 会排除
  `projectX/0X_stage/output/**/*.csv`。因此任何展示阶段都必须以**入库的 JSON 报告**
  （如 `ladder_report.json`）为权威源，CSV 只作可选增强。
- **入库的富矿不只是 JSON**：`cloglog_summary.txt`（statsmodels 完整系数表）、
  `train_report.md`（SHAP 表）、`map.md`（字段真实区间）、`profile.yaml`（min/std）都能正则解析。
  缺 CSV 时优先从这些文本产物里挖真实数字，**不要猜、不要编**。

## 已产出文件
- `datakit/suggestions_for_projects_0908.md`：三产品展现形式升级建议（2026-09-08）。
- `portal/`（2026-09-11 新建，v1 门户 → **v2 计算型工作台**）：「网点决策台 SDP」，
  把 p1/p2/p6 + datakit 整合成一条决策链上的产品（首页=工作台，四模块 + 报告导出：
  ① 数据准入体检 ② 冲击评估 ③ 风险归因 ④ 口径实验室 ⑤ 评估报告）。
  **只读上游产物，不改任何既有文件**。离线自包含（双击 `index.html` 即开，图表为手写 SVG，
  不引第三方 CDN）；`python portal/serve.py` 可选解锁「上传 CSV → 真调 datakit 五阶段体检」。
  - 分层：`build_data.py` → `data/portal_data.js`（自动生成事实层，**勿手改**；同名 `.json` 为
    对外程序可读副本，**两者都保留**）；`data/content.js`（手写叙事层，**不含数字**）；
    `assets/engines.js`（计算层，**零硬编码系数**）+ `tests/engines.test.js`（26 项单测）；`assets/*`（表现层）。
  - 缺数据一律显示「缺失 · 已降级」，不填估算值。
  - **当前状态：能演示、不能交付**，必修项见 `portal/REVIEW_20260911.md`（P0：`engines.js:183`
    把交互项系数当标准误，导致默认强度处 CI 跨 0）。

## ⚠️ 已知硬伤（2026-09-11 三视角审查发现，对外前必须先处理）
> 来源：产品经理 / 业务 / 面试官三个 code-explorer agent 独立审查仓库。以下均为实锤，引用见 `portal/DESIGN.md` §六。
1. **TWFE −5.26pp 是 strength=0 处外推**：`06_estimate.py:217-220` 中 `post` 只在被处理网点取 1，
   而处理组 `strength_t0 ≥ log1p(1)=0.69`；交互项 `post_x_strength` **+0.0138 (t=8.07) 显著为正**
   → 强度越高负效应越小。且代码用 `log1p(n_same_ind_5km)` **单环**，README 却写"环加权" → 口径与实现不符。
   → 对外报数前必须给出 **mean(strength_t0) 处的边际效应 + CI**。
2. **`bank_closed_rate` 目标泄漏**：`groupby(CERT)` 对**全期 1994–2025** 聚合后 join 回每一年
   （`05_map.py` + `06_train.py:70-71`），系数 3.8156 (t=176.9)，SHAP 第 2。→ AUC 0.881 含金量存疑。
3. **风险模型预测不了未来**：SHAP 第一是 `year`；2016+ 年份系数退化（≈−26, SE≈4e4, p≈1）；
   随机划分无 out-of-time 验证；测试集事件率 13.78% vs 真实 4.13% → Brier 不可对外报。
4. **合并环敏感性没跑**：`estimate.json` 的 `sensitivity.rings_alternative` 只有两个标签数组，零系数。
5. **复现承诺当前不可验证**：仓库无 `.git`；`replication_manifest` 写死 `E:\...` 绝对路径；`.pkl`/CSV 不入库。
6. **SLX W_treat 三个文件三个值**：estimate.json 0.008986(p=0.0013) / conclusion.md 0.008986 /
   technical_report.md **0.0073(p=0.009)** → 需统一（以 estimate.json 为准）。
7. **平行趋势口径打架**：README 说"轻微为负"，实际 τ=−2 p=3.76e-05 显著（|t|=4.12）；
   按 `08_conclude` 自己的止损条件（显著**且**量级接近 post）可能该降 **C 级**而非 B 级。
8. **project6 规模叙事失真**：SNAP 两数据集（56.2%）禁商用、sz_bike（43%）仅研究用途 → 商用版只剩 fdic 0.74%。
9. **结构性商业矛盾**：最好卖的市场（连锁零售）关店高度内生 → 大概率只能交付 C 级结论。

## 简历 / 对外叙事（2026-09-11）
- 用户核心诉求：项目要「先符合是一个产品，再是一个项目，最后是我在其中的作用」。
- 已确认的产品定位：**卖引擎不卖结论**（FDIC 数据公开 → 结论无法独占）。
- 产品矩阵 = 一条决策链：project2 事前风险预测 → project1 事后影响评估 →
  project6 客户教育与信任 → datakit 交付底座。四者**不是四份作业**。
- 最值钱的两个数字（已从产物核实）：SLX 本地效应 −0.0059 (p=0.026) / 邻域效应 +0.0090 (p=0.0013)
  → 本地被吸走、邻域补回 = 再配置而非净增；只看 OLS 混合值 +0.0073 会得出相反结论。
- **主语转换**（企业叙事的根）：从「我做了什么」改成「谁的决策因此变了」。
- **产品边界三条**（写进交付物，主动不承诺）：不承诺 ROI（成本量纲不成立）/ 不做个体预测 /
  只报关联不报因果。结论强度分级 A/B/C 对应不同价格与用途。
- **迁移成本模型**：展示层 1 周 / 工程 1–2 周 / 空间 1–2 周 / 识别 2–4 周 / 数据层 3–6 周（最难）。
- 商业化文档里的业务数字**全是 `XX` 占位**，对外材料不得编造。
- 跨会话归档（诉求演化链、面试三追问、三条企业感表述）见 `.codebuddy/memory/CONVERSATIONS.md`。
