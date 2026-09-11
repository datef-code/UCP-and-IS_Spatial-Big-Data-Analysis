/* 产品工具层内容（手写）。
 * 只放"文案 / 表单定义 / 选项"，**不放任何数字**——数字一律来自 portal_data.js。 */
window.SDP_TOOLS = {

  /* ---------------- 工作台：评估项目向导 ---------------- */
  workbench: {
    intro: '一个「评估项目」把四个模块串成一条链：先判断数据能不能做，再算影响、评估风险、检验口径，最后出一份带边界的交付物。所有结果存在本机浏览器，不上传服务器。',
    steps: [
      { id: 'intake', no: '①', name: '数据准入体检', why: '先判断能不能做、能做到什么等级——避免把不合格需求做成一份好看但没用的报告。', required: true },
      { id: 'impact', no: '②', name: '冲击评估', why: '回答"影响多大、传多远、第几年最深"，输出带置信区间的点估计。', required: false },
      { id: 'risk', no: '③', name: '风险归因', why: '回答"哪些门店最可能出事、主要由什么决定"，含剔除泄漏特征的保守版本。', required: false },
      { id: 'caliber', no: '④', name: '口径实验室', why: '检验结论对口径的敏感性——换权重、换尺度、换聚合方式，结论会不会翻。', required: false },
      { id: 'report', no: '⑤', name: '生成评估报告', why: '把前四步的结果合成一份带结论强度、使用边界与数据血缘的交付物。', required: true },
    ],
    samples: [
      {
        name: '示例 A · 咨询机构的连锁零售客户（外生事件）',
        desc: '客户有 10 年门店级销售数据、坐标完整、事件为竞对破产清算（外生）。预期：通过准入，结论上限 B 级。',
        project: {
          name: '某连锁便利店 · 竞对退出影响评估（示例）',
          client: '某咨询机构（终客户：连锁便利店）',
          industry: '连锁零售 / 便利店',
          decision: '竞对破产清算后，我方 3 km 内门店的销售额影响有多大、传多远',
          intakeAnswers: {
            stableId: true, idMatchRate: 0.94, coordNullRate: 0.03, outcomeLevel: 'store',
            years: 10, eventDefined: true, exogenous: true,
          },
          impactInput: { strength: 1.2, eventYear: 2018 },
          riskInput: { age: 25, deposit: 39360, neighbor: 5, lat: 38.9, lng: -86.22, bankClosedRate: 0.25, year: 2012, bkclass: 'N', fragility: 'L0_单网点' },
          caliberInput: { dataset: 'fdic' },
        },
      },
      {
        name: '示例 B · 银行并购整合（内生性偏强）',
        desc: '只有公司级汇总指标、坐标缺失 28%。预期：触发一票否决，产品建议先补数而非硬做。',
        project: {
          name: '某银行 · 并购重叠网点取舍评估（示例）',
          client: '某城市商业银行',
          industry: '银行 / 网点网络规划',
          decision: '并购后重叠网点如何取舍、关掉 A 点会不会伤到 3 km 外的自家 B 点',
          intakeAnswers: {
            stableId: true, idMatchRate: 0.72, coordNullRate: 0.28, outcomeLevel: 'company',
            years: 4, eventDefined: true, exogenous: false,
          },
          impactInput: { strength: 1.0, eventYear: 2012 },
          riskInput: { age: 40, deposit: 120000, neighbor: 12, lat: 39.1, lng: -94.6, bankClosedRate: 0.5, year: 2009, bkclass: 'NM', fragility: 'L2_多网点地理分散' },
          caliberInput: { dataset: 'fdic' },
        },
      },
    ],
  },

  /* ---------------- ① 准入体检问卷 ---------------- */
  intake: {
    lead: '六项数据条件决定这个项目能不能做、能做到什么等级。全部来自真实项目的准入清单（见商业化文档 §4.5），其中阈值原文档以 XX 占位，本工具使用可配置的产品默认值。',
    questions: [
      {
        key: 'stableId', type: 'bool', label: '① 是否有可跨年追踪的稳定实体 ID？',
        help: '本项目实测：官方主键 BRNUM 在同一网点上跨年变化率 52.19%（并购子样本 86.80%）——唯一 ≠ 稳定。若只有一个候选键，需用「名称+地址+坐标」二次校验。',
        fatal: '无稳定实体 ID → 无法构造面板 → DID 与事件研究均不成立',
      },
      {
        key: 'idMatchRate', type: 'pct', label: '② 实体匹配准确率（若为二次匹配请填实测值）',
        help: '本工具无法自动推出该值（实体不跨全期是正常的开关店行为），必须由人工用二次校验后填写。产品默认阈值 90%。',
        threshold: '≥ 90%',
      },
      {
        key: 'coordNullRate', type: 'pct', label: '③ 坐标缺失率',
        help: '坐标是距离环与暴露强度的唯一前提。本项目实测坐标缺失 8.04%。',
        threshold: '≤ 20%',
      },
      {
        key: 'outcomeLevel', type: 'enum', label: '④ 结果变量层级',
        help: '必须是门店级连续指标（销售额/存款/单量）。只有公司级汇总则无法构造门店级 outcome。',
        options: [{ v: 'store', t: '门店级连续指标' }, { v: 'company', t: '仅公司级汇总' }, { v: 'binary', t: '仅 0/1 存活标记' }],
      },
      {
        key: 'years', type: 'num', label: '⑤ 时间跨度（年）',
        help: '事件研究需要事件前后各若干年窗口，跨度 ≥ 5 年才有意义。本项目用 τ ∈ [−3, +4]。',
        threshold: '≥ 5 年',
      },
      {
        key: 'eventDefined', type: 'bool', label: '⑥ 是否存在明确、可观测的退出/进入时点？',
        help: '处理事件必须可观测。无法定义事件则无法做影响评估。',
      },
      {
        key: 'exogenous', type: 'enum3', label: '⑦ 该事件是自主决策还是外生冲击？',
        help: '这是决定结论强度上限的关键。外生冲击（竞对破产清算、政策强制关停、租约集中到期）才能近似主张平行趋势；自主关店与商圈衰退高度相关，内生性显著更强。',
        options: [
          { v: 'yes', t: '外生冲击（可冲 A/B 级）' },
          { v: 'no', t: '自主决策（上限 C 级）' },
          { v: 'unsure', t: '不确定 / 需进一步论证' },
        ],
      },
    ],
  },

  /* ---------------- ② 冲击评估 ---------------- */
  impact: {
    lead: '用项目真实估计出来的系数做前向计算。请注意：模型给出的 β_post 是暴露强度 = 0 处的截距外推，而训练样本中处理组强度从未为 0 —— 这决定了它的引用方式。',
    taxNote: '「暴露强度」在本项目中的定义是 treat_strength = log1p(5 km 内同业关闭事件数)。因此强度 0.69 ≈ 1 起事件，1.61 ≈ 4 起，2.40 ≈ 10 起。',
    presets: [
      { name: '低暴露（约 1 起同业关闭）', strength: 0.69 },
      { name: '中暴露（约 4 起）', strength: 1.61 },
      { name: '高暴露（约 10 起）', strength: 2.40 },
      { name: '极高暴露（约 21 起）', strength: 3.09 },
    ],
    guards: [
      '不得用于 ROI 测算或干预阈值决策（成本参数缺失，量纲不成立）',
      '不得对外作因果表述（结论强度为关联级）',
      '不得跨年代直接比较坐标精度（编码词表 2023 年切换）',
    ],
  },

  /* ---------------- ③ 风险归因 ---------------- */
  risk: {
    lead: '把 cloglog 完整系数表还原成一个可交互的归因器：每一项贡献 = 系数 × 输入值，加总即线性预测器 η，再经 cloglog 链接得到风险概率。',
    notice: '本模块被刻意命名为「归因」而非「预测」：模型没有时序外推验证，且测试集为随机划分——它只能解释历史，不能预测未来。',
    presets: [
      { name: '低风险样本（SDP 真实 SHAP 样本档位）', note: '对应文档中真实样本档位 0.01%', v: { age: 5, deposit: 25000, neighbor: 1, lat: 40.7, lng: -74.0, bankClosedRate: 0.02, year: 1995, bkclass: 'N', fragility: 'L0_单网点' } },
      { name: '中位样本', note: '对应真实样本档位 2.86%', v: { age: 25, deposit: 39360, neighbor: 5, lat: 38.9, lng: -86.22, bankClosedRate: 0.15, year: 2003, bkclass: 'NM', fragility: 'L0_单网点' } },
      { name: '高风险样本（已被关闭）', note: '对应真实样本档位 82.71%', v: { age: 60, deposit: 8000, neighbor: 60, lat: 33.5, lng: -112.1, bankClosedRate: 0.95, year: 2010, bkclass: 'SM', fragility: 'L2_多网点地理分散' } },
    ],
    fields: [
      { key: 'bankClosedRate', label: '所属银行历史关闭率', unit: '', input: 'rate', hint: '本模型的第一主导因子（系数 3.8156，SHAP 排名第 2）——「谁家的网点」比「网点多老」重要得多。但请注意：该特征存在目标泄漏。' },
      { key: 'deposit', label: '存款规模', unit: '美元', input: 'logAmount', hint: '内部按 log1p 转换。规模是护城河：存款越大越长寿（系数 −0.0305）。' },
      { key: 'neighbor', label: '同格网点数（竞争强度）', unit: '个', input: 'int', hint: '同一 H3 R7 网格内网点数（含自身）。系数 +0.0004，影响极弱（SHAP 排名第 7）。' },
      { key: 'age', label: '网点年龄', unit: '年', input: 'int', hint: '系数 1.898e−05，SHAP 排名最后（0.0030）—— 「老网点更容易死」在本数据上几乎不成立。' },
      { key: 'lat', label: '纬度', unit: '°', input: 'float', hint: '仅作地理基线；模型未含本地市场变量。' },
      { key: 'lng', label: '经度', unit: '°', input: 'float', hint: '仅作地理基线；模型未含本地市场变量。' },
    ],
  },

  /* ---------------- P0 修补看板（把"已知限制"变成可追踪的工程项） ---------------- */
  patches: [
    { id: 'P0-1', title: 'TWFE 主系数是零强度处的外推', status: '待修',
      impact: '影响「冲击评估」的引用方式',
      detail: 'post 的系数（−5.26pp）是 treat_strength = 0 处的反事实外推；而训练样本中处理组 strength ≥ log1p(1) = 0.693，该点从未被观测。且交互项 +0.0138（t = 8.07）显著为正——强度越高负效应越小。',
      fix: '重跑 06 阶段导出 strength_t0 的均值与分位数 → 报均值处的边际效应与置信区间。本模块已用显式披露替代（标注支撑域下界与零交叉点）。' },
    { id: 'P0-2', title: '合并环敏感性实际未跑', status: '待修',
      impact: '影响口径稳健性结论',
      detail: 'sensitivity.rings_alternative 只有两个标签数组（fine / coarse），没有任何系数、标准误或 p 值——即"写了敏感性要求但没跑"。',
      fix: '补跑合并环（0–2/2–5/5–10 km）并写入 estimate.json。本模块已在每次结果中强制披露"未验证"。' },
    { id: 'P0-3', title: '风险模型存在目标泄漏且无时序外推验证', status: '待修',
      impact: '影响「风险归因」的数值解释',
      detail: 'bank_closed_rate 按 CERT 对全期 1994–2025 聚合后 join 回每一年，早年样本使用了未来信息；测试集为随机划分，事件率经分层下采样富集。',
      fix: '改为 expanding-window 重算并补 hold-out 末 5 年验证。本模块已提供"剔除泄漏特征后的保守值"作为过渡。' },
    { id: 'P0-4', title: 'SLX 溢出系数在不同产物中取值不一致', status: '待修',
      impact: '影响核心卖点数字',
      detail: 'estimate.json 为 0.008986（p ≈ 0.0013），而 technical_report.md 写作 0.0073（p = 0.009）。',
      fix: '统一为 estimate.json 并修订结论文档。本产品全程以 estimate.json 为准。' },
    { id: 'P0-5', title: '可复现承诺当前不可验证', status: '部分修',
      impact: '影响交付信任',
      detail: '仓库无 .git；replication_manifest 记录的是绝对路径 E:\\...；logit_pipeline.pkl 与样本级 CSV 受 .gitignore 约束不入库。',
      fix: 'manifest 改相对路径 + 明确"完整复现需自备源数据"；本产品已新增「可复现性」看板，把真实状态（含缺陷）公开。' },
    { id: 'P0-6', title: '平行趋势口径表述不一致', status: '待修',
      impact: '直接决定结论是 B 级还是 C 级',
      detail: 'README 表述为"轻微为负"，实测 τ=−2 的 p = 3.76e-05、|t| = 4.12（显著）。按结论文档自己的止损条件（显著**且**量级接近 post → 停止因果解读），等级应重新判定。',
      fix: '定一个可执行的阈值并写死。本产品已把该规则实现为可执行的评级器（见「结论强度」）。' },
  ],

  /* ---------------- 变更日志 ---------------- */
  changelog: [
    { v: 'v2.0', d: '2026-09-11', items: [
      '从"介绍型门户"改为"计算型工作台"：新增输入 → 计算 → 可交付输出的完整闭环。',
      '新增计算引擎层（engines.js）与 26 项单元测试；系数全部来自入库产物，引擎内无硬编码模型系数。',
      '新增「结论强度评级器」：把结论文档里的止损条件变成可执行的自动评级与阻断。',
      '新增本地服务（serve.py）：上传客户数据 → 真实调用 datakit 跑五阶段体检 → 自动预填准入问卷。',
      '新增「P0 修补看板」与「可复现性」披露：把已知缺陷从免责声明变成可追踪工程项。',
      '风险模块由「预测」改名为「归因」，并关闭超出适用域的输入（2016 年及以后）。',
    ] },
    { v: 'v1.0', d: '2026-09-11', items: [
      '首个版本：九个介绍型页面 + 由 build_data.py 生成的事实层。',
      '确立了"缺数据显式降级、不画编出来的图"的口径。',
    ] },
  ],
};
