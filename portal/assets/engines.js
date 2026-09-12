/* ============================================================================
 * 网点决策台 · 计算引擎层
 * ----------------------------------------------------------------------------
 * 设计原则（三条，缺一不可）：
 *   1. 纯函数：不碰 DOM、不读全局以外的状态 → 可被 tests/engines.test.js 直接单测。
 *   2. 系数全部来自 window.SDP_DATA（由 build_data.py 从入库产物抽取），
 *      **引擎内部不出现任何硬编码的模型系数**；取不到就返回 ok:false + 原因。
 *   3. 每个返回值都带 caveats[]（使用边界）与 source[]（血缘），
 *      调用方不得丢弃 —— 这是本产品与"又一个计算器"的区别。
 * ========================================================================== */
(function (global) {
  'use strict';

  /* ------------------------------------------------------------------ *
   * 0. 基础统计工具
   * ------------------------------------------------------------------ */

  /** 标准正态 CDF（Zelen & Severo 近似，绝对误差 < 7.5e-8） */
  function normCdf(x) {
    const t = 1 / (1 + 0.2316419 * Math.abs(x));
    const d = 0.3989422804014327 * Math.exp(-x * x / 2);
    const p = d * t * (0.319381530 + t * (-0.356563782 + t * (1.781477937 + t * (-1.821255978 + t * 1.330274429))));
    return x >= 0 ? 1 - p : p;
  }
  /** 双侧 p 值 */
  const pFromT = (t) => (t == null || !isFinite(t)) ? null : 2 * (1 - normCdf(Math.abs(t)));
  const isNum = (v) => typeof v === 'number' && isFinite(v);

  /** 一致性：负向效应下取更保守（更接近 0）的一侧 */
  function ci(c, se, z) {
    if (!isNum(c)) return null;
    const w = isNum(se) ? (z == null ? 1.96 : z) * se : null;
    return w == null ? { lo: null, hi: null } : { lo: c - w, hi: c + w };
  }

  /* ------------------------------------------------------------------ *
   * 1. 结论强度评级器（贯穿所有模块的护栏核心）
   * ------------------------------------------------------------------ */

  const GRADES = {
    A: { level: 'A', name: '准因果', use: '可用于对外披露、政策论证', price: '高', color: 'var(--ok)' },
    B: { level: 'B', name: '关联', use: '可用于内部决策参考，不得对外宣称因果', price: '中', color: 'var(--accent)' },
    C: { level: 'C', name: '描述性', use: '只报差异，停止因果解读；建议转为描述性评估交付', price: '低', color: 'var(--danger)' },
  };

  /**
   * 评级规则：本项目自己的止损条件（08_conclude/output/conclusion.md）为
   *   「若事件研究 τ<0 出现显著且量级接近 post 的系数 → 停止因果解读，改报描述性差异」。
   * 引擎把这条"人读的规则"变成"可执行的判定"：
   *   - preTrendMaxAbsT ≥ 1.96（显著） → 至少降一级
   *   - 前趋势量级 / post 量级 ≥ 0.5（产品默认阈值，可配置） → 再降一级至 C
   */
  function gradeEvidence(opt) {
    const o = opt || {};
    const reasons = [];
    const t = o.preTrendMaxAbsT, ratio = o.preTrendRatio;
    let level = 'A';

    if (o.exogenous === false) { level = 'C'; reasons.push('处理事件为内生决策（非外生冲击）→ 平行趋势前提不成立'); }
    else if (o.exogenous == null) { level = 'B'; reasons.push('处理事件外生性未判定 → 按默认上限 B 处理'); }
    else reasons.push('处理事件被判定为外生冲击 → 具备准因果前提');

    if (isNum(t) && t >= 1.96) {
      reasons.push(`事件前 τ 系数显著（|t| = ${t.toFixed(2)} ≥ 1.96）→ 平行趋势不理想，降一级`);
      level = level === 'A' ? 'B' : 'C';
    } else if (isNum(t)) {
      reasons.push(`事件前 τ 系数不显著（|t| = ${t.toFixed(2)} < 1.96）→ 平行趋势可接受`);
    } else {
      reasons.push('事件前 τ 的 |t| 不可得 → 无法验证平行趋势，按 B 处理');
      if (level === 'A') level = 'B';
    }

    if (isNum(ratio) && ratio >= 0.5) {
      reasons.push(`前趋势量级与 post 量级之比 ${ratio.toFixed(2)} ≥ 0.5 → 触及"量级接近"止损条件，再降一级`);
      level = 'C';
    }

    if (o.ringsVerified === false) { reasons.push('合并环敏感性未产出系数（仅有标签）→ 口径稳健性未验证'); }
    if (o.outOfTime === false) { reasons.push('无时序外推验证（随机划分）→ 模型不可用于预测未来'); }
    if (o.bootstrapCI === false) { reasons.push('未加 bootstrap CI → 显著性部分来自大样本'); }

    return { ...GRADES[level], reasons };
  }

  /**
   * 从数据层 + 外生性答案直接导出结论强度。
   * 这是「工作台 / 冲击评估 / 评估报告」三处等级的唯一来源 ——
   * 任何一处自行拼装评级参数都会造成 P1-1 式的自相矛盾。
   */
  function gradeFromData(D, exogenous, opts) {
    const d = (D || global.SDP_DATA || {});
    const I = d.impact || {};
    const es = I.event_study || {};
    const tbl = es.table || [];
    const t0 = (tbl.find(r => r.tau === 0) || {}).effect;
    const tm2 = (tbl.find(r => r.tau === -2) || {}).effect;
    const ratio = (isNum(t0) && t0 !== 0 && isNum(tm2)) ? Math.abs(tm2 / t0) : null;
    const audit = I.sensitivity_audit || {};
    const o = opts || {};
    return gradeEvidence({
      exogenous: exogenous === undefined ? null : exogenous,
      preTrendMaxAbsT: es.pre_trend_max_abs_t,
      preTrendRatio: ratio,
      ringsVerified: !!audit.rings_alternative_has_coefficients,
      bootstrapCI: !!audit.bootstrap_ci,
      outOfTime: o.outOfTime === undefined ? false : o.outOfTime,
    });
  }

  /* ------------------------------------------------------------------ *
   * 2. 数据准入体检引擎
   * ------------------------------------------------------------------ */

  // 工期模型（来源：商业化文档 §4.1 分层难度表）
  const WORK_WEEKS = { show: [1, 1], eng: [1, 2], space: [1, 2], ident: [2, 4], data: [3, 6] };

  function intake(a) {
    const ans = a || {};
    const gaps = [], blockers = [], notes = [];
    let score = 0, total = 0;
    const add = (ok, weight, gapText) => { total += weight; if (ok) score += weight; else if (gapText) gaps.push(gapText); };

    // ① 稳定实体 ID（一票否决级）
    add(ans.stableId === true, 30, '缺少可跨年追踪的稳定实体 ID：需先做主键重建（名称+地址+坐标模糊匹配），这是最不可压缩的工作量');
    if (ans.stableId === false) blockers.push('无稳定实体 ID → 无法构造面板 → 事件研究与 DID 均不成立');

    // ② ID 匹配准确率
    add(isNum(ans.idMatchRate) && ans.idMatchRate >= 0.9, 12,
      `主键匹配准确率不足（${isNum(ans.idMatchRate) ? (ans.idMatchRate * 100).toFixed(0) + '%' : '未提供'}，阈值 90%）→ 面板存在系统性错配风险`);

    // ③ 坐标可用性
    add(isNum(ans.coordNullRate) && ans.coordNullRate <= 0.2, 15,
      `坐标缺失率过高（${isNum(ans.coordNullRate) ? (ans.coordNullRate * 100).toFixed(1) + '%' : '未提供'}，阈值 ≤20%）→ 距离环与暴露强度不可靠`);
    if (isNum(ans.coordNullRate) && ans.coordNullRate > 0.2) blockers.push('坐标缺失率 > 20% → 空间口径不可用');

    // ④ 结果变量层级（一票否决级）
    add(ans.outcomeLevel === 'store', 18,
      '结果变量不是门店级（或只有公司级汇总）→ 无法构造门店级 outcome，识别策略退化为描述性');
    if (ans.outcomeLevel !== 'store') {
      blockers.push('结果变量非门店级 → 无法构造门店级 outcome，DID 与事件研究均不成立');
    }

    // ⑤ 时间跨度
    add(isNum(ans.years) && ans.years >= 5, 10,
      `时间跨度不足（${isNum(ans.years) ? ans.years + ' 年' : '未提供'}，需 ≥5 年）→ 无法做事件前后窗口`);

    // ⑥ 事件可定义性与外生性（三态：yes 外生 / no 内生 / unsure 或未填 → 未判定）
    add(ans.eventDefined === true, 8, '无明确、可观测的进入/退出时点 → 无法定义处理事件');
    const exo = (ans.exogenous === true || ans.exogenous === 'yes') ? true
      : ((ans.exogenous === false || ans.exogenous === 'no') ? false : null);
    add(exo === true, 7,
      exo === true ? null
        : exo === false ? '处理事件为内生决策 → 结论强度上限降为 C 级（描述性）'
          : '处理事件外生性尚未判定 → 结论强度上限按 B 级处理，须先补外生性论证');

    const pct = total ? score / total : 0;
    const hardFail = blockers.length > 0;

    // 工期：基线为结构相似数据（4–6 周），按缺口累加
    let wmin = WORK_WEEKS.show[0] + WORK_WEEKS.eng[0] + WORK_WEEKS.space[0] + WORK_WEEKS.ident[0] + WORK_WEEKS.data[0];
    let wmax = WORK_WEEKS.show[1] + WORK_WEEKS.eng[1] + WORK_WEEKS.space[1] + WORK_WEEKS.ident[1] + WORK_WEEKS.data[1];
    if (!isNum(ans.years) || ans.years < 5) { wmin += 2; wmax += 5; notes.push('面板不足 → 需外购历史快照，工期上调'); }
    if (ans.stableId === false) { wmin += 2; wmax += 4; notes.push('需自建实体匹配 → 工期上调'); }
    if (exo === false) notes.push('内生性偏强 → 需补匹配/合成控制等更重的识别设计，且结论仍可能只能到 C 级');
    else if (exo === null) notes.push('外生性未判定 → 需先在方案阶段论证事件外生性，否则结论上限只能到 B 级');

    const grade = gradeEvidence({
      exogenous: exo,
      preTrendMaxAbsT: null,
      ringsVerified: false,
      outOfTime: false,
      bootstrapCI: false,
    });

    return {
      ok: true,
      go: !hardFail && pct >= 0.5,
      scorePct: pct,
      hardFail,
      blockers,
      gaps,
      notes,
      weeks: [wmin, wmax],
      ceiling: hardFail ? null : grade.level,
      grade,
      source: ['商业化文档 §4.1 分层难度表', '商业化文档 §4.5 准入清单（原文档阈值以 XX 占位，本产品设定为可配置默认值）'],
      caveats: [
        '准入清单原文档中 3 个阈值（ID 匹配准确率 / 坐标缺失率 / 样本量）以 XX 占位，本工具使用产品默认阈值，可在报告中标明来源与调整依据。',
        '"可行性等级"是数据条件的技术判定，不等于客户一定会买单——需要真实 POC 验证。',
      ],
    };
  }

  /* ------------------------------------------------------------------ *
   * 3. 冲击评估引擎（project1）
   * ------------------------------------------------------------------ */

  function impact(input, D, opts) {
    const opt = opts || {};
    const d = (D || global.SDP_DATA || {});
    const I = d.impact || {};
    const es = I.event_study || {};
    const tw = I.twfe || {};
    const sp = I.spatial || {};
    const slx = sp.slx || {};
    const ols = I.ols_cell || {};
    const caveats = [], source = [];

    if (tw.post == null) return { ok: false, reason: '未取到 TWFE 系数（estimate.json 不可用）', caveats, source };

    const inp = input || {};
    const s = isNum(inp.strength) ? inp.strength : 0;
    const ringsSensAvailable = !!(I.rings_sensitivity && Object.keys(I.rings_sensitivity).length);
    const beta0 = tw.post, b0se = tw.post_se;
    // ⚠ 标准误字段名必须是 *_se；曾误用系数本身当 SE，导致默认强度处区间跨 0（见 REVIEW P0-1）
    const b1 = tw.post_x_strength, b1se = tw.post_x_strength_se;

    // (a) 时间路径：平均处理效应（直接来自事件研究表，未做强度调整）
    const byTau = (es.table || []).map(r => ({
      tau: r.tau, effect: r.effect, se: r.se, p: r.p,
      lo: isNum(r.se) ? r.effect - 1.96 * r.se : null,
      hi: isNum(r.se) ? r.effect + 1.96 * r.se : null,
    }));
    source.push('impact.event_study.table ← 06_estimate/output/estimate.json');

    // 前趋势量级比（|τ=−2| / |τ=0|）：评级器的输入，必须与 computeGrade 用同一算法
    const rowT0 = (es.table || []).find(r => r.tau === 0);
    const rowTm2 = (es.table || []).find(r => r.tau === -2);
    const preTrendRatio = (rowT0 && rowTm2 && isNum(rowT0.effect) && rowT0.effect !== 0 && isNum(rowTm2.effect))
      ? Math.abs(rowTm2.effect / rowT0.effect) : null;
    const ratioUsed = isNum(opt.preTrendRatio) ? opt.preTrendRatio : preTrendRatio;

    // (b) 强度维度：Δ(s) = β_post + β_int × s
    //     ⚠ β_post 是 s=0 处的反事实外推 —— 处理组强度恒 > 0，该点从未被观测。
    //     支撑域下界优先取「审计重跑实测的网点级最小值」（真实分布），取不到才退回定义反推。
    const supAll = I.strength_support || {};
    const supBr = supAll.branch_level || {};
    const supportMeasured = isNum(supBr.min);
    const S_LOWER_BOUND = supportMeasured ? Number(supBr.min) : Math.log1p(1);
    const supportMean = isNum(supBr.mean) ? Number(supBr.mean) : null;
    if (!isNum(b1se)) caveats.push('数据层缺少交互项标准误（post_x_strength_se）→ 边际效应的置信区间不可信，请勿引用区间。');
    const effectAt = (sv) => {
      const c = beta0 + b1 * sv;
      // 近似：忽略 β_post 与 β_int 的协方差。二者符号通常相反（截距更负、斜率更正），
      // 忽略会使区间偏窄 —— 方向未定，因此同时给出「同号最坏情况」的保守区间 ciWorst。
      const se = (isNum(b0se) && isNum(b1se))
        ? Math.sqrt(Math.pow(b0se, 2) + Math.pow(sv, 2) * Math.pow(b1se, 2)) : null;
      const seWorst = (isNum(b0se) && isNum(b1se)) ? (Math.abs(b0se) + Math.abs(sv) * Math.abs(b1se)) : null;
      const t = (isNum(se) && se > 0) ? c / se : null;
      return {
        s: sv, effect: c, se,
        ci: se == null ? { lo: null, hi: null } : { lo: c - 1.96 * se, hi: c + 1.96 * se },
        seWorst,
        ciWorst: seWorst == null ? { lo: null, hi: null } : { lo: c - 1.96 * seWorst, hi: c + 1.96 * seWorst },
        t, p: t == null ? null : pFromT(t),
      };
    };
    const atZero = effectAt(0);
    const atInput = effectAt(s);
    const atMean = supportMean != null ? effectAt(supportMean) : null;
    const zeroCross = (b1 !== 0) ? -beta0 / b1 : null;   // 效应由负转正的强度
    source.push('impact.twfe.params / std_err ← estimate.json');

    // 强度曲线：由引擎统一生成，避免视图层复算 SE 公式造成口径漂移
    const curve = [];
    for (let sv = 0; sv <= 5 + 1e-9; sv += 0.125) {
      const e = effectAt(Number(sv.toFixed(6)));
      curve.push({ x: Number(sv.toFixed(6)), y: e.effect, lo: e.ci.lo, hi: e.ci.hi, loWorst: e.ciWorst.lo, hiWorst: e.ciWorst.hi });
    }

    // (c) 空间分解：本地 vs 邻域（方向相反的才是关键）
    const spatial = {
      direct: slx.direct, directSe: slx.direct_se, directP: slx.direct_p,
      spillover: slx.spillover, spilloverSe: slx.spillover_se, spilloverP: slx.spillover_p,
      r2: slx.r2,
      note: 'SLX 把效应拆为本地项与空间滞后项；两者方向相反 → 存款在更大尺度再配置，而非区域净增',
    };
    if (slx.direct != null) source.push('impact.spatial.slx ← estimate.json → spatial_fits.slx');

    // (d) 格级方程（唯一可直接代入的多元回归式）
    const cellEq = (ols.terms || []).length ? {
      terms: ols.terms, n: ols.n, r2: ols.r2,
      predict: (t) => {
        const m = {}; ols.terms.forEach(x => m[x.name] = x.coef);
        let y = m.const || 0;
        if (isNum(t.strength)) y += (m.treat_strength || 0) * t.strength;
        if (isNum(t.logDep)) y += (m.log_dep_t0 || 0) * t.logDep;
        if (isNum(t.nBranches)) y += (m.n_branches || 0) * t.nBranches;
        return y;
      },
    } : null;

    // (e) 精度折扣（按事件年份）
    const cp = I.coordinate_precision || {};
    const era = cp.top_precision_pct_by_era || {};
    const year = inp.eventYear;
    let precision = null;
    if (isNum(year)) {
      if (year >= 2023) precision = { tier: '高', pct: era['2023-2025_EXACT'], note: '屋顶级地理编码占 85.98%' };
      else precision = { tier: '低', pct: era['1994-2022_US_Rooftop'], note: '屋顶级仅 16.37%，其余多为街道级/邮编级插值 → <1 km 环存在系统性失真' };
    }

    // 结论强度：走与工作台/报告完全相同的入口（gradeFromData），杜绝三处等级不一致。
    // 不传 opts.exogenous 时按"外生性未判定"处理，不写死任何假设。
    const gradeObj = gradeFromData(d, opt.exogenous === undefined ? null : opt.exogenous, { outOfTime: opt.outOfTime });

    // ---- 必须随结果一起展示的边界 ----
    caveats.push('β_post（' + (beta0 * 100).toFixed(2) + 'pp）是暴露强度 = 0 处的截距外推，而样本中处理组强度 ≥ ' + S_LOWER_BOUND.toFixed(3) + '，该点从未被观测 → 不能单独引用。');
    if (supportMeasured) {
      const isRefit = /refit/i.test(((I._src || {}).from) || '');
      caveats.push('支撑域下界 ' + S_LOWER_BOUND + ' 与均值 ' + supportMean.toFixed(4)
        + (isRefit ? ' 取自本次重估现场计算的处理组强度分布（'
          : ' 取自审计重跑实测的网点级 strength_t0 分布（')
        + (supBr.distinct_values || '?')
        + ' 个离散取值，中位 ' + supBr.median + '，p95 ' + supBr.p95 + '，最大 ' + supBr.max
        + '）' + (isRefit ? '。' : '；该分布在复算中与上游 did_panel.parquet 逐网点完全一致（最大绝对差 0）。'));
      if (isNum(supBr.max) && supBr.max > 5) {
        caveats.push('实测强度最大值 ' + supBr.max + ' 超出本页滑杆上限 5 —— 滑杆区间只覆盖支撑域的一部分，高暴露网点无法在本页表达。');
      }
    } else {
      caveats.push('支撑域下界 ' + S_LOWER_BOUND.toFixed(3) + ' 由变量定义反推，并未用 strength_t0 的真实分布实测验证（审计产物缺失）—— 重跑 portal/audit/rerun_p1_strength.py 后须替换。');
    }
    if (isNum(b1) && b1 > 0) {
      const tInt = (I.strength_disclosure || {}).interaction_t;
      const toward = (isNum(beta0) && beta0 < 0) ? '负效应越小' : '正效应越大';
      caveats.push(`交互项显著为正（${b1.toFixed(6)}${isNum(tInt) ? '，t = ' + tInt.toFixed(2) : ''}）→ 暴露强度越高，${toward}。`);
    }
    caveats.push('边际效应的 95% 区间用 √(SE_post² + s²·SE_int²) 近似（忽略两项协方差，方向未定），并同时给出"同号最坏情况"的更宽区间 —— 引用时以更宽者为准。');
    if (isNum(zeroCross) && zeroCross > 0) caveats.push(`按线性外推，强度超过 ${zeroCross.toFixed(2)} 时效应由负转正 —— 该点很可能超出观测支撑域，须重跑导出强度分布后确认。`);
    if (I.sensitivity_audit && I.sensitivity_audit.rings_alternative_has_coefficients === false) caveats.push('合并环敏感性未产出系数（仅有标签）→ 距离环口径的稳健性尚未验证。');
    caveats.push('强度口径：strength_t0 = Σ 环权重（0–1km 1.0 / 1–3km 0.6 / 3–5km 0.3 / 5–10km 0.1），即环加权和、不是 log1p 计数 —— 已由审计重跑逐网点复现（最大绝对差 0）；上游 06_estimate.py 的模块 docstring 写法已过时，以代码为准。');
    caveats.push('SAR 在 30k×30k 稀疏 KNN 上 ρ 越界且对数似然为 NaN → 不以 SAR 报溢出量级，仅以 SLX 的 W·X 作代理。');
    if ((ols.terms || []).length) caveats.push('格级 OLS 的 treat_strength 是混合值，与 SLX 拆出的本地效应口径不同、符号可相反（本项目实测二者异号）→ 两者不可混用，也不可互相印证。');
    const wc = (d.audit || {}).wtreat_consistency;
    if (wc && wc.consistent === false) {
      caveats.push('上游产物对该量（SLX 邻域溢出 W_treat）取值不一致：权威值 ' + wc.authoritative
        + '，但 ' + (wc.mismatches || []).map(m => m.where + ' = ' + m.value).join('、')
        + ' 实际写的是 OLS 的 treat_strength（口径不同、不可互换）→ 对外引用邻域溢出量级时以 estimate.json 为准。');
    }
    if (ringsSensAvailable) caveats.push('合并环敏感性已重跑（三种距离环口径，见结果卡）：三种口径下「单位相对暴露」的斜率差异在 5% 内 → 结论不依赖细环选择。');
    caveats.push(`结论强度为 ${gradeObj.level} 级（${gradeObj.name}），非严格因果：事件前 τ=−2 已显著。`);

    return {
      ok: true,
      strengthInput: s,
      supportLowerBound: S_LOWER_BOUND,
      isExtrapolation: s < S_LOWER_BOUND,
      byTau,
      curve,
      preTrendRatio: ratioUsed,
      support: supAll,
      supportMeasured,
      supportLowerBoundFromData: supportMeasured,
      ringsSensitivity: I.rings_sensitivity || null,
      ringsCross: I.rings_cross_comparison || null,
      ringsSource: I.audit_source || null,
      auditSource: I.audit_source || null,
      marginal: { atZero, atInput, atMean, zeroCross, beta0, b0se, beta1: b1, beta1se: b1se },
      spatial, cellEq, precision,
      twfeMeta: { nObs: tw.n_obs, nEntities: tw.n_entities, nTimes: tw.n_times, r2Within: tw.r2_within },
      eventStudyMeta: { baseline: es.baseline, nObs: es.n_obs, preTrendMaxAbsT: es.pre_trend_max_abs_t },
      grade: gradeObj,
      caveats, source,
    };
  }

  /* ------------------------------------------------------------------ *
   * 4. 风险归因引擎（project2）—— 历史归因，不是预测
   * ------------------------------------------------------------------ */

  /* 默认特征表（project2 cloglog）。**只是兜底**：
   * 若产物自带 risk.feature_spec（例如用客户自己数据重估出来的模型），则以产物为准 ——
   * 否则产品就又被"锁死"在 FDIC 的特征集上了。 */
  const DEFAULT_RISK_FEATURES = [
    { key: 'age', label: '网点年龄', unit: '年', kind: 'numeric' },
    { key: 'log_depsumbr', label: '存款规模（对数）', unit: 'log1p(美元)', kind: 'numeric' },
    { key: 'neighbor_count', label: '同格网点数', unit: '个', kind: 'numeric' },
    { key: 'lat', label: '纬度', unit: '°', kind: 'numeric' },
    { key: 'lng', label: '经度', unit: '°', kind: 'numeric' },
    { key: 'bank_closed_rate', label: '所属银行历史关闭率', unit: '', kind: 'numeric' },
  ];
  const DEFAULT_RISK_CATS = [
    { key: 'year', kind: 'year', label: '年份' },
    { key: 'bkclass', kind: 'bkclass', label: '银行类别' },
    { key: 'fragility', kind: 'fragility', label: '银行脆弱性' },
  ];

  function risk(input, D) {
    const d = (D || global.SDP_DATA || {});
    const R = d.risk || {};
    const card = R.model_card || {};
    const coefs = (R.cloglog || {}).coefficients || [];
    const caveats = [], source = [];

    if (!coefs.length) return { ok: false, reason: '未解析出 cloglog 系数 → 打分器不可用（不臆造系数）', caveats, source };

    const inp = input || {};
    const spec = R.feature_spec || {};
    const FEATS = (spec.numeric && spec.numeric.length) ? spec.numeric : DEFAULT_RISK_FEATURES;
    const CATS = (spec.categorical && spec.categorical.length) ? spec.categorical : DEFAULT_RISK_CATS;
    const year = parseInt(inp.year, 10);

    // ---- 适用域守门（护栏，不是缺陷）；只在产物声明了适用年份时才守门 ----
    const ys = card.year_supported || null;
    if (ys && ys.length >= 2) {
      const yMin = ys[0], yMax = ys[1];
      if (!isNum(year)) return { ok: false, reason: '未指定年份', caveats, source };
      if (year < yMin || year > yMax) {
        return {
          ok: false,
          reason: `年份 ${year} 超出模型可用域（${yMin}–${yMax}）`,
          detail: card.degenerate_why ||
            '该区间的哑变量系数已完全分离（数值伪影），不代表真实风险；本工具拒绝为该年份打分，而不是给一个看似合理的错数。',
          caveats, source,
        };
      }
    }
    const bk = inp.bkclass;
    if ((card.degenerate_levels || {}).bkclass && card.degenerate_levels.bkclass.indexOf(bk) >= 0) {
      return { ok: false, reason: `银行类别 ${bk} 的系数已退化（完全分离）→ 拒绝打分`, caveats, source };
    }

    const find = (kind, level) => coefs.find(c => c.kind === kind && String(c.level) === String(level));
    const contrib = [];
    let eta = (coefs.find(c => c.kind === 'intercept') || {}).coef || 0;
    contrib.push({ name: '截距（基线）', value: eta, kind: 'base' });

    // 数值项（口径与拟合产物一致；特征表由产物声明，缺省才用内置表）
    const numInput = {};
    FEATS.forEach(f => {
      const c = coefs.find(x => x.kind === 'numeric' && x.name === f.key);
      if (!c) return;
      const v = isNum(inp[f.key]) ? inp[f.key] : 0;
      numInput[f.key] = v;
      const val = c.coef * v;
      eta += val;
      contrib.push({ name: f.label, value: val, coef: c.coef, input: v, kind: 'numeric', key: f.key });
    });

    // 类别项：基准组 coefficient = 0
    const addCat = (kind, level, label) => {
      const c = find(kind, level);
      const val = c ? c.coef : 0;
      eta += val;
      contrib.push({ name: label + ' = ' + level + (c ? '' : '（基准组）'), value: val, coef: val, kind: 'categorical' });
    };
    CATS.forEach(cat => {
      const lv = (cat.key === 'year') ? (inp.year !== undefined ? year : null) : inp[cat.key];
      if (lv === undefined || lv === null || lv === '') return;
      addCat(cat.kind || cat.key, lv, cat.label || cat.key);
    });

    const hazard = 1 - Math.exp(-Math.exp(eta));

    // ---- 保守版本：剔除被标记为泄漏的特征 ----
    const leakKeys = (card.leakage_flags || []).map(f => f.feature);
    let etaCons = eta - contrib.filter(c => leakKeys.indexOf(c.key) >= 0).reduce((a, c) => a + c.value, 0);
    const hazardCons = 1 - Math.exp(-Math.exp(etaCons));

    caveats.push(...(card.leakage_flags || []).map(f =>
      `特征「${f.feature}」存在目标泄漏：${f.why}（系数 ${f.coef == null ? '—' : f.coef.toFixed(4)}，SHAP 排名第 ${f.shap_rank || '—'}）→ 全特征版本的风险分被系统性抬高。`));
    caveats.push(`本模型无时序外推验证（${card.split}）→ 只能做历史归因与情景分析，不能预测未来。`);
    caveats.push(`测试集事件率与真实面板事件率不一致（${card.event_rate_note}）→ Brier / log-loss 不可直接对外引用。`);
    caveats.push('残差 Moran\'s I = ' + (R.moran && R.moran.moran_i != null ? R.moran.moran_i.toFixed(4) : '—') +
      '（p = ' + (R.moran && R.moran.p_value != null ? R.moran.p_value : '—') + '）显著为正 → 本地市场因素未进入模型，点估计不等于"网点自身属性效应"。');
    caveats.push('「剔除泄漏特征后的保守值」= 仅减去该特征的贡献、保留其余系数与截距，并非重新拟合 → 只能用于同一输入下的相对排序，不能当作真实概率。');
    const otm = (d.risk || {}).out_of_time;
    if (otm && otm.conclusion) {
      const c = otm.conclusion;
      caveats.push('时序外推验证（本次补齐，替代随机划分的乐观值）：含泄漏特征 AUC '
        + fmtNum(c.out_of_time_auc_with_leak_mean, 4) + '、剔除泄漏特征 AUC '
        + fmtNum(c.out_of_time_auc_no_leak_mean, 4) + '（随机划分报的 '
        + fmtNum(c.reported_test_auc_random_split, 4)
        + '）→ 表观判别力主要来自时序泄漏特征，本模型不构成「可预测未来」的证据。');
      if (c.windows && c.windows.why_not_all_years) {
        caveats.push('时序外推只覆盖 ' + c.windows.years[0] + '–' + c.windows.years[1] + '（' + c.windows.n + ' 个窗口）：' + c.windows.why_not_all_years + '。');
      }
    }
    caveats.push('这是归因模型（无识别设计）→ 不承诺干预阈值与 ROI，也不宣称预测未来。');
    source.push('risk.cloglog.coefficients ← 06_train/output/cloglog_summary.txt');
    source.push('risk.model_card ← replication_manifest / metrics.json / 系数退化实测');
    source.push('risk.shap_force ← 09_interactive/output/shap_force.json');

    return {
      ok: true,
      eta, hazard, hazardConservative: hazardCons, etaConservative: etaCons,
      contributions: contrib,
      leakageKeys: leakKeys,
      baseValue: (R.shap_force || {}).base_value,
      outOfTime: (d.risk || {}).out_of_time || null,
      grade: gradeEvidence({ exogenous: null, outOfTime: false, bootstrapCI: false }),
      caveats, source,
    };
  }

  /* ------------------------------------------------------------------ *
   * 5. 口径实验室（project6）
   * ------------------------------------------------------------------ */

  function caliber(sel, D) {
    const d = (D || global.SDP_DATA || {});
    const sets = ((d.teaching || {}).datasets) || [];
    if (!sets.length) return { ok: false, reason: '未取到 ladder_report.json' };
    const s = sel || {};
    const ds = sets.find(x => x.dataset === (s.dataset || 'fdic')) || sets[0];

    const density = ds.spill_density_by_ring || {};
    const sum = ds.spill_sum_by_ring || {};
    const LABEL = { spillden_0_1km: '0–1 km', spillden_1_3km: '1–3 km', spillden_3_5km: '3–5 km', spillden_5_10km: '5–10 km' };
    const SLABEL = { spill_0_1km: '0–1 km', spill_1_3km: '1–3 km', spill_3_5km: '3–5 km', spill_5_10km: '5–10 km' };
    const rings = Object.keys(density).length
      ? Object.keys(density).map(k => ({ label: LABEL[k] || k, value: density[k] }))
      : Object.keys(sum).map(k => ({ label: SLABEL[k] || k, value: sum[k] }));

    return {
      ok: true,
      dataset: ds.dataset,
      all: sets.map(x => ({ dataset: x.dataset, cells: x.cells, points: x.points, moran: x.moran_i, neighbors: x.mean_neighbors, islands: x.islands })),
      cells: ds.cells, points: ds.points, h3Res: ds.h3_res,
      moranI: ds.moran_i, lagCorr: ds.lag_corr,
      meanNeighbors: ds.mean_neighbors, islands: ds.islands,
      rings, ringBasis: Object.keys(density).length ? 'density' : 'sum',
      ringNote: ds.note,
      caveats: [
        '「邻居」是人为定义，不是客观事实：换权重（Queen / KNN k=4 / k=8）或换格值尺度（原始 / log1p）都会改变 Moran\'s I。',
        '商用许可：SNAP 两个数据集（snap_brightkite / snap_gowalla）仅限研究用途、不允许商用；对外商业版本只保留 fdic 与 sz_bike。',
        '求和口径不随距离衰减（环面积随距离增大）；按环内格均摊的溢出密度才反映距离衰减 → 聚合口径影响结论。',
      ],
      source: ['teaching.datasets ← project6_spatial_teaching/05_map/output/<ds>/ladder_report.json'],
    };
  }

  /* ------------------------------------------------------------------ *
   * 6. 报告生成（统一交付物）
   * ------------------------------------------------------------------ */

  function fmtPct(v, d) { return isNum(v) ? (v * 100).toFixed(d == null ? 2 : d) + 'pp' : '—'; }
  function fmtNum(v, d) { return isNum(v) ? v.toFixed(d == null ? 4 : d) : '—'; }

  /** 非加密指纹（FNV-1a 32bit）：用于回答"这份报告对应哪一版数据层 / 哪一组输入"，不是安全用途。 */
  function fnv1a(str) {
    let h = 0x811c9dc5;
    for (let i = 0; i < str.length; i++) {
      h ^= str.charCodeAt(i);
      h = (h + ((h << 1) + (h << 4) + (h << 7) + (h << 8) + (h << 24))) >>> 0;
    }
    return ('0000000' + h.toString(16)).slice(-8);
  }
  function reportFingerprint(p, d) {
    const num = (v) => (isNum(v) ? Number(v).toFixed(6) : '—');
    const tw = (d.impact || {}).twfe || {};
    return fnv1a(JSON.stringify({
      n: p.name || '', ceil: (p.intake || {}).ceiling || '—',
      s: num((p.impact || {}).strengthInput), eta: num((p.risk || {}).eta),
      b0: num(tw.post), b1: num(tw.post_x_strength), gen: (d.meta || {}).generated_at || '—',
    }));
  }

  function buildReport(project, D) {
    const p = project || {};
    const d = (D || global.SDP_DATA || {});
    const L = [];
    const push = (s) => L.push(s);
    const meta = d.meta || {};

    push(`# 空间影响评估报告`);
    push('');
    push(`- **项目名称**：${p.name || '（未命名）'}`);
    push(`- **客户/行业**：${p.client || '—'} / ${p.industry || '—'}`);
    push(`- **目标决策**：${p.decision || '—'}`);
    push(`- **生成时间**：${new Date().toISOString().slice(0, 19).replace('T', ' ')}`);
    push(`- **生成工具**：网点决策台（SDP）· 计算引擎 v2`);
    push(`- **数据层生成时间**：${meta.generated_at || '—'}`);
    push(`- **报告指纹**：\`${reportFingerprint(p, d)}\`（非加密摘要，用于核对"这份报告对应哪版数据层 / 哪组输入"）`);
    push('');

    push(`## 〇、结论摘要`);
    push('');
    if (p.intake && p.intake.ok) {
      push(`- **数据可行性**：${p.intake.hardFail ? '**未通过（存在一票否决项）**' : (p.intake.go ? '通过' : '有条件通过')}` +
        `（评分 ${(p.intake.scorePct * 100).toFixed(0)}/100）`);
      if (p.intake.ceiling) push(`- **结论强度上限**：${p.intake.ceiling} 级`);
      push(`- **预估工期**：${p.intake.weeks[0]}–${p.intake.weeks[1]} 周`);
    } else push(`- 未执行数据准入体检`);
    if (p.impact && p.impact.ok) {
      push(`- **冲击评估**：暴露强度 ${p.impact.strengthInput} 下，效应点估计 ${fmtPct(p.impact.marginal.atInput.effect)}` +
        `（95% 近似区间 [${fmtPct(p.impact.marginal.atInput.ci.lo)}, ${fmtPct(p.impact.marginal.atInput.ci.hi)}]）`);
      push(`- **空间分解**：本地 ${fmtPct(p.impact.spatial.direct)}（p=${fmtNum(p.impact.spatial.directP, 4)}）/ ` +
        `邻域 ${fmtPct(p.impact.spatial.spillover)}（p=${fmtNum(p.impact.spatial.spilloverP, 4)}）`);
    }
    if (p.risk && p.risk.ok) {
      push(`- **风险归因**：全特征 ${(p.risk.hazard * 100).toFixed(2)}% / 剔除泄漏特征后 ${(p.risk.hazardConservative * 100).toFixed(2)}%`);
    }
    push('');
    push(`> **结论强度：${(p.grade || {}).level || '—'} 级 · ${(p.grade || {}).name || '—'}** —— ${(p.grade || {}).use || ''}`);
    push('');

    if (p.intake && p.intake.ok) {
      push(`## 一、数据准入体检`);
      push('');
      if (p.intake.blockers.length) { push(`**一票否决项：**`); p.intake.blockers.forEach(b => push(`- ⛔ ${b}`)); push(''); }
      if (p.intake.gaps.length) { push(`**数据缺口（需补齐）：**`); p.intake.gaps.forEach(b => push(`- ${b}`)); push(''); }
      if (p.intake.notes.length) { push(`**工期调整说明：**`); p.intake.notes.forEach(b => push(`- ${b}`)); push(''); }
      push(`**判定依据**：${p.intake.source.join('；')}`);
      push('');
    }

    if (p.impact && p.impact.ok) {
      push(`## 二、冲击评估`);
      push('');
      push(`### 2.1 事件后逐年动态效应（平均处理效应）`);
      push('');
      push(`| 事件后年数 τ | 效应 | 标准误 | p 值 |`);
      push(`| ---: | ---: | ---: | ---: |`);
      p.impact.byTau.filter(r => r.tau >= 0).forEach(r => {
        push(`| τ=${r.tau} | ${fmtPct(r.effect)} | ${r.se == null ? '—' : fmtPct(r.se)} | ${fmtNum(r.p, 6)} |`);
      });
      push('');
      push(`### 2.2 暴露强度与效应`);
      push('');
      push(`- 模型：Δ(s) = ${fmtPct(p.impact.marginal.beta0)} + ${fmtNum(p.impact.marginal.beta1, 6)} × s`);
      push(`- 强度 = 0 处：${fmtPct(p.impact.marginal.atZero.effect)}（**该点未被观测，不可单独引用**）`);
      push(`- 强度 = ${p.impact.strengthInput} 处：${fmtPct(p.impact.marginal.atInput.effect)}` +
        `；95% 近似区间 [${fmtPct(p.impact.marginal.atInput.ci.lo)}, ${fmtPct(p.impact.marginal.atInput.ci.hi)}]` +
        `，同号最坏情况 [${fmtPct(p.impact.marginal.atInput.ciWorst.lo)}, ${fmtPct(p.impact.marginal.atInput.ciWorst.hi)}]`);
      if (p.impact.marginal.atMean) {
        const am = p.impact.marginal.atMean;
        push(`- 处理组**均值强度** ${fmtNum(am.s, 4)} 处：${fmtPct(am.effect)}` +
          `（95% 近似区间 [${fmtPct(am.ci.lo)}, ${fmtPct(am.ci.hi)}]）—— 「典型网点」的效应，推荐对外引用这一个`);
      }
      if (isNum(p.impact.marginal.zeroCross)) push(`- 效应由负转正的强度阈值：${fmtNum(p.impact.marginal.zeroCross, 2)}（线性外推，需重跑确认是否在支撑域内）`);
      push('');
      push(`### 2.3 空间分解（本地 / 邻域）`);
      push('');
      push(`| 项 | 系数 | p 值 | 解读 |`);
      push(`| --- | ---: | ---: | --- |`);
      push(`| 本地效应 | ${fmtPct(p.impact.spatial.direct)} | ${fmtNum(p.impact.spatial.directP, 4)} | 显著为负 → 本地被吸走 |`);
      push(`| 邻域效应 W·X | ${fmtPct(p.impact.spatial.spillover)} | ${fmtNum(p.impact.spatial.spilloverP, 4)} | 显著为正 → 邻域补回 |`);
      push('');
      push(`> 两者方向相反 → 存款在更大地理尺度**再配置**，而非区域净增。`);
      push('');
      if (p.impact.ringsSensitivity) {
        push(`### 2.4 距离环口径敏感性（审计重跑）`);
        push('');
        push(`| 口径 | 距离环（km） | β_int | 标准误 | p 值 |`);
        push(`| --- | --- | ---: | ---: | ---: |`);
        Object.keys(p.impact.ringsSensitivity).forEach(k => {
          const v = p.impact.ringsSensitivity[k] || {};
          push(`| ${k} | ${(v.rings || []).map(z => z[0] + '–' + z[1]).join(' / ')} | ${fmtNum(v.coef, 6)} | ${fmtNum(v.se, 6)} | ${fmtNum(v.p, 3)} |`);
        });
        if (p.impact.ringsCross) {
          push('');
          push(`> 合并环改变强度刻度，直接比 β_int 无意义；按「单位相对暴露的斜率」比较，三种口径差异 ${fmtNum(p.impact.ringsCross.slope_spread_pct, 1)}% → 结论不依赖细环选择。`);
        }
        push('');
      }
    }

    if (p.risk && p.risk.ok) {
      push(`## 三、风险归因`);
      push('');
      push(`| 因子 | 输入 | 系数 | 对线性预测器的贡献 |`);
      push(`| --- | ---: | ---: | ---: |`);
      p.risk.contributions.forEach(c => {
        push(`| ${c.name} | ${c.input == null ? '—' : (isNum(c.input) ? c.input.toFixed(4) : c.input)} | ${c.coef == null ? '—' : fmtNum(c.coef, 4)} | ${fmtNum(c.value, 4)} |`);
      });
      push('');
      push(`- 线性预测器 η = ${fmtNum(p.risk.eta, 4)}`);
      push(`- 风险（cloglog 链接）= ${(p.risk.hazard * 100).toFixed(2)}%`);
      push(`- 剔除泄漏特征后的保守值 = ${(p.risk.hazardConservative * 100).toFixed(2)}%`);
      const otm = p.risk.outOfTime;
      if (otm && otm.conclusion) {
        const c = otm.conclusion;
        push(`- **时序外推**（替代随机划分的乐观值）：随机划分 AUC ${fmtNum(c.reported_test_auc_random_split, 4)}`
          + ` → 含泄漏特征 ${fmtNum(c.out_of_time_auc_with_leak_mean, 4)}`
          + ` → 剔除泄漏特征 ${fmtNum(c.out_of_time_auc_no_leak_mean, 4)}（≈随机）`);
        if (c.headline) push(`- 判读：${c.headline}`);
      }
      push('');
    }

    push(`## 四、使用边界（不可省略）`);
    push('');
    const allCav = []
      .concat((p.impact && p.impact.caveats) || [])
      .concat((p.risk && p.risk.caveats) || [])
      .concat((p.intake && p.intake.caveats) || []);
    allCav.forEach(c => push(`- ${c}`));
    push('');
    push(`**禁止用途**：`);
    push(`- 不得用于 ROI 测算或干预阈值决策（成本参数缺失，量纲不成立）；`);
    push(`- 不得对外作因果表述（结论强度 ${(p.grade || {}).level || '—'} 级）；`);
    push(`- 不得用于个人级 / 客流级分析（合规红线）。`);
    push('');

    push(`## 五、数据血缘`);
    push('');
    push(`| 模块 | 来源产物 |`);
    push(`| --- | --- |`);
    const srcGroups = [
      ['准入体检', (p.intake && p.intake.source) || []],
      ['冲击评估', (p.impact && p.impact.source) || []],
      ['风险归因', (p.risk && p.risk.source) || []],
    ];
    srcGroups.forEach(([mod, list]) => {
      Array.from(new Set(list)).forEach(s => push(`| ${mod} | \`${s}\` |`));
    });
    push('');
    push(`> 本报告全部数字由 \`portal/build_data.py\` 从上述入库产物抽取，取不到即显示"缺失·已降级"，**不填充任何估算值**。`);
    push(`> 源数据（FDIC SOD 1.58 GB / 教学数据 31.1 GB）不在版本库内：${meta.source_data_note || ''}`);

    return L.join('\n');
  }

  /* ------------------------------------------------------------------ *
   * 导出
   * ------------------------------------------------------------------ */
  global.SDP_ENGINE = {
    normCdf, pFromT,
    GRADES, gradeEvidence, gradeFromData,
    intake, WORK_WEEKS,
    impact, RISK_FEATURES: DEFAULT_RISK_FEATURES,
    risk, caliber, buildReport,
    _fmt: { fmtPct, fmtNum },
  };
})(typeof window !== 'undefined' ? window : globalThis);
