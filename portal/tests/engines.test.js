/* 计算引擎单元测试（node 原生 test runner，零依赖）
 * 运行：node --test portal/tests/engines.test.js
 *
 * 为什么必须有：engines.js 是整个产品里唯一"会算错"的地方 ——
 * 页面可以丑，但数字不能错。
 */
'use strict';
const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

const ROOT = path.resolve(__dirname, '..');
const ctx = { console, Math, JSON, Date, isFinite, parseInt };
ctx.window = ctx;
ctx.globalThis = ctx;
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(path.join(ROOT, 'data/portal_data.js'), 'utf8'), ctx, { filename: 'portal_data.js' });
vm.runInContext(fs.readFileSync(path.join(ROOT, 'assets/engines.js'), 'utf8'), ctx, { filename: 'engines.js' });
vm.runInContext(fs.readFileSync(path.join(ROOT, 'data/tools.js'), 'utf8'), ctx, { filename: 'tools.js' });

const E = ctx.SDP_ENGINE;
const D = ctx.SDP_DATA;
const T = ctx.SDP_TOOLS;

test('数据层已加载且无缺失登记', () => {
  assert.ok(D, 'SDP_DATA 未挂载');
  assert.ok(D.impact && D.risk && D.teaching && D.datakit);
  assert.strictEqual((D.missing || []).length, 0, '存在缺失项：' + JSON.stringify(D.missing));
});

test('normCdf / pFromT 数值正确', () => {
  assert.ok(Math.abs(E.normCdf(0) - 0.5) < 1e-6, 'normCdf(0) 应为 0.5');
  assert.ok(Math.abs(E.normCdf(1.96) - 0.975) < 1e-3, 'normCdf(1.96) 应≈0.975');
  const p = E.pFromT(1.96);
  assert.ok(Math.abs(p - 0.05) < 1e-2, 'pFromT(1.96) 应≈0.05，实得 ' + p);
  assert.strictEqual(E.pFromT(null), null);
});

test('结论强度评级：外生+无前趋势 → A', () => {
  const g = E.gradeEvidence({ exogenous: true, preTrendMaxAbsT: 0.5, ringsVerified: true, bootstrapCI: true, outOfTime: true });
  assert.strictEqual(g.level, 'A');
});

test('结论强度评级：前趋势显著 → 至少降一级', () => {
  const g = E.gradeEvidence({ exogenous: true, preTrendMaxAbsT: 4.12 });
  assert.notStrictEqual(g.level, 'A');
  assert.ok(g.reasons.join(' ').includes('平行趋势'));
});

test('结论强度评级：前趋势量级接近 post → 降到 C', () => {
  const g = E.gradeEvidence({ exogenous: true, preTrendMaxAbsT: 4.12, preTrendRatio: 0.8 });
  assert.strictEqual(g.level, 'C');
});

test('结论强度评级：内生事件 → C（一票到底）', () => {
  const g = E.gradeEvidence({ exogenous: false, preTrendMaxAbsT: 0.1 });
  assert.strictEqual(g.level, 'C');
});

test('准入体检：全优 → Go，且带出结论等级上限', () => {
  const r = E.intake({
    stableId: true, idMatchRate: 0.95, coordNullRate: 0.05, outcomeLevel: 'store',
    years: 10, eventDefined: true, exogenous: true,
  });
  assert.strictEqual(r.ok, true);
  assert.strictEqual(r.hardFail, false);
  assert.strictEqual(r.go, true);
  assert.strictEqual(r.scorePct, 1);
  assert.ok(r.weeks[0] > 0 && r.weeks[1] >= r.weeks[0], '工期区间不合法');
  assert.ok(r.caveats.length > 0, '必须带使用边界');
});

test('准入体检：无稳定主键 → 一票否决', () => {
  const r = E.intake({ stableId: false, coordNullRate: 0.05, outcomeLevel: 'store', years: 10, eventDefined: true, exogenous: true });
  assert.strictEqual(r.hardFail, true);
  assert.strictEqual(r.go, false);
  assert.ok(r.blockers.length >= 1);
  assert.ok(r.blockers.join(' ').includes('稳定实体 ID'));
});

test('准入体检：只有公司级结果变量 → 一票否决', () => {
  const r = E.intake({ stableId: true, idMatchRate: 0.95, coordNullRate: 0.05, outcomeLevel: 'company', years: 10, eventDefined: true, exogenous: true });
  assert.strictEqual(r.hardFail, true);
  assert.ok(r.blockers.join(' ').includes('门店级'));
});

test('准入体检：内生事件 → 上限降到 C 级', () => {
  const r = E.intake({ stableId: true, idMatchRate: 0.95, coordNullRate: 0.05, outcomeLevel: 'store', years: 10, eventDefined: true, exogenous: false });
  assert.strictEqual(r.hardFail, false);
  assert.strictEqual(r.ceiling, 'C');
});

test('冲击评估：结构完整、时间路径为 8 期、含事件前', () => {
  const r = E.impact({ strength: 1, eventYear: 2010 }, D);
  assert.strictEqual(r.ok, true);
  assert.strictEqual(r.byTau.length, 8);
  assert.ok(r.byTau.some(x => x.tau === -1 && x.effect === 0), '基线 τ=−1 应为 0');
  assert.ok(r.byTau.some(x => x.tau === 0));
  assert.ok(r.byTau.some(x => x.tau === 4));
});

test('冲击评估：强度=0 处的点估计等于 β_post（并标注为外推）', () => {
  const r = E.impact({ strength: 0 }, D);
  assert.ok(Math.abs(r.marginal.atZero.effect - D.impact.twfe.post) < 1e-12);
  assert.strictEqual(r.isExtrapolation, true, 'strength=0 必须被标记为观测支撑域外');
  assert.ok(r.caveats.join(' ').includes('未被观测'));
});

test('冲击评估：支撑域下界优先取审计实测值（无审计时退回 log1p(1)）', () => {
  const r = E.impact({ strength: 0 }, D);
  const br = D.impact.strength_support.branch_level;
  assert.ok(Math.abs(r.supportLowerBound - br.min) < 1e-12,
    '有审计产物时应取实测网点级最小值 ' + br.min + '，实得 ' + r.supportLowerBound);
  assert.strictEqual(r.isExtrapolation, true);
  const r2 = E.impact({ strength: 2 }, D);
  assert.strictEqual(r2.isExtrapolation, false);
});

test('冲击评估：零交叉点可由 β 反解，且与边际效应自洽', () => {
  const r = E.impact({ strength: 1 }, D);
  const zc = r.marginal.zeroCross;
  assert.ok(isFinite(zc) && zc > 0, '零交叉点应为正有限值');
  const atZc = r.marginal.beta0 + r.marginal.beta1 * zc;
  assert.ok(Math.abs(atZc) < 1e-9, '在零交叉点效应应为 0，实得 ' + atZc);
});

test('冲击评估：必须携带合并环与强度口径的边界提示', () => {
  const r = E.impact({ strength: 1 }, D);
  const txt = r.caveats.join(' ');
  assert.ok(txt.includes('合并环'), '缺少合并环敏感性提示');
  assert.ok(txt.includes('环加权和'), '缺少强度口径（环加权和）提示');
  assert.ok(!txt.includes('log1p(n_same_ind_5km)'), '不应再传播已过时的 log1p 计数口径');
});

test('冲击评估：空间分解存在且本地为负、邻域为正', () => {
  const r = E.impact({ strength: 1 }, D);
  assert.ok(r.spatial.direct < 0, '本地效应应为负');
  assert.ok(r.spatial.spillover > 0, '邻域效应应为正');
});

test('风险归因：正常输入 → η 自洽、风险落在 [0,1]', () => {
  const r = E.risk({
    age: 25, log_depsumbr: Math.log1p(39360), neighbor_count: 5, lat: 38.9, lng: -86.22,
    bank_closed_rate: 0.3, year: 2010, bkclass: 'N', fragility: 'L0_单网点',
  }, D);
  assert.strictEqual(r.ok, true);
  const sum = r.contributions.reduce((a, c) => a + c.value, 0);
  assert.ok(Math.abs(sum - r.eta) < 1e-9, '贡献之和应等于 η');
  assert.ok(r.hazard >= 0 && r.hazard <= 1, '风险必须在 [0,1]');
});

test('风险归因：cloglog 链接可复算 h = 1 - exp(-exp(η))', () => {
  const r = E.risk({ age: 0, log_depsumbr: 0, neighbor_count: 0, lat: 0, lng: 0, bank_closed_rate: 0, year: 2000, bkclass: 'N', fragility: 'L0_单网点' }, D);
  assert.ok(Math.abs(r.hazard - (1 - Math.exp(-Math.exp(r.eta)))) < 1e-12);
});

test('风险归因：年份超出适用域 → 拒绝打分并说明原因', () => {
  const r = E.risk({ year: 2020, bkclass: 'N', age: 10, log_depsumbr: 10, neighbor_count: 5, lat: 38, lng: -86, bank_closed_rate: 0.2, fragility: 'L0_单网点' }, D);
  assert.strictEqual(r.ok, false);
  assert.ok(r.reason.includes('超出模型可用域'));
  assert.ok(r.detail.includes('完全分离'));
});

test('风险归因：退化类别 SL → 拒绝打分', () => {
  const r = E.risk({ year: 2010, bkclass: 'SL', age: 10, log_depsumbr: 10, neighbor_count: 5, lat: 38, lng: -86, bank_closed_rate: 0.2, fragility: 'L0_单网点' }, D);
  assert.strictEqual(r.ok, false);
  assert.ok(r.reason.includes('SL'));
});

test('风险归因：银行关闭率越高，风险越高（单调性）', () => {
  const base = { age: 20, log_depsumbr: 10, neighbor_count: 5, lat: 38, lng: -86, year: 2010, bkclass: 'N', fragility: 'L0_单网点' };
  const lo = E.risk({ ...base, bank_closed_rate: 0.1 }, D);
  const hi = E.risk({ ...base, bank_closed_rate: 0.8 }, D);
  assert.ok(hi.hazard > lo.hazard, '关闭率上升应提高风险');
});

test('风险归因：剔除泄漏特征后的保守值应低于全特征值', () => {
  const r = E.risk({ age: 25, log_depsumbr: 10, neighbor_count: 5, lat: 38, lng: -86, bank_closed_rate: 0.5, year: 2010, bkclass: 'N', fragility: 'L0_单网点' }, D);
  assert.ok(r.hazardConservative < r.hazard, '保守版本应更保守');
  assert.ok(r.caveats.join(' ').includes('目标泄漏'), '必须披露泄漏特征');
});

test('口径实验室：四个数据集齐全，Moran 值与产物一致', () => {
  const r = E.caliber({ dataset: 'fdic' }, D);
  assert.strictEqual(r.ok, true);
  assert.strictEqual(r.all.length, 4);
  const fdic = D.teaching.datasets.find(x => x.dataset === 'fdic');
  assert.ok(Math.abs(r.moranI - fdic.moran_i) < 1e-12);
  assert.ok(r.rings.length === 4, '距离环应为 4 段');
});

test('口径实验室：必须披露 SNAP 商用限制', () => {
  const r = E.caliber({ dataset: 'snap_brightkite' }, D);
  assert.ok(r.caveats.join(' ').includes('仅限研究用途'));
});

test('报告生成：包含关键章节、无渲染泄漏', () => {
  const proj = {
    name: '测试项目', client: '某连锁', industry: '零售', decision: '评估竞对关店的溢出',
    intake: E.intake({ stableId: true, idMatchRate: 0.95, coordNullRate: 0.05, outcomeLevel: 'store', years: 10, eventDefined: true, exogenous: true }),
    impact: E.impact({ strength: 1.5, eventYear: 2012 }, D),
    risk: E.risk({ age: 25, log_depsumbr: 10, neighbor_count: 5, lat: 38, lng: -86, bank_closed_rate: 0.4, year: 2010, bkclass: 'N', fragility: 'L0_单网点' }, D),
    grade: E.gradeEvidence({ exogenous: true, preTrendMaxAbsT: 4.12, ringsVerified: false, bootstrapCI: false, outOfTime: false }),
  };
  const md = E.buildReport(proj, D);
  ['# 空间影响评估报告', '## 一、数据准入体检', '## 二、冲击评估', '## 三、风险归因', '## 四、使用边界', '## 五、数据血缘']
    .forEach(h => assert.ok(md.includes(h), '缺少章节：' + h));
  assert.ok(!/undefined|\[object Object\]/.test(md), '报告存在渲染泄漏');
  assert.ok(md.includes('不得用于 ROI'), '缺少禁止用途');
});

test('报告生成：数据层缺失时仍能出报告（显式降级而非崩溃）', () => {
  const md = E.buildReport({ name: '空项目' }, { meta: {} });
  assert.ok(md.includes('# 空间影响评估报告'));
  assert.ok(!/undefined|\[object Object\]/.test(md));
});

/* ================================================================== *
 * v2.1 回归网 —— 以下用例对应 REVIEW_20260911.md 的整改项
 * ================================================================== */

test('P0-1 回归：边际效应标准误必须取 post_x_strength_se（不得用系数冒充）', () => {
  const r = E.impact({ strength: 1.61 }, D);
  assert.strictEqual(r.marginal.beta1se, D.impact.twfe.post_x_strength_se, '引擎未使用数据层的交互项标准误');
  const exp = Math.sqrt(D.impact.twfe.post_se ** 2 + 1.61 ** 2 * D.impact.twfe.post_x_strength_se ** 2);
  assert.ok(Math.abs(r.marginal.atInput.se - exp) < 1e-12, '边际效应 SE 与公式不符：' + r.marginal.atInput.se);
  assert.ok(r.marginal.atInput.ci.hi < 0, '默认强度处 95% 区间不应跨 0（hi=' + r.marginal.atInput.ci.hi + '）');
});

test('P0-1 回归：必须给出"同号最坏情况"保守区间且不窄于近似区间', () => {
  const r = E.impact({ strength: 1.61 }, D);
  assert.ok(r.marginal.atInput.seWorst >= r.marginal.atInput.se, '保守 SE 不应小于近似 SE');
  assert.ok(r.marginal.atInput.ciWorst.lo <= r.marginal.atInput.ci.lo, '保守区间下界应更宽');
  assert.ok(r.marginal.atInput.ciWorst.hi >= r.marginal.atInput.ci.hi, '保守区间上界应更宽');
  assert.ok(r.caveats.join(' ').includes('协方差'), '必须披露区间为近似（忽略协方差）');
});

test('P0-1 回归：强度曲线由引擎产出且与边际效应自洽', () => {
  const r = E.impact({ strength: 1.61 }, D);
  assert.strictEqual(r.curve.length, 41, '强度曲线应有 41 个点（0..5，步长 0.125）');
  const near = r.curve.find(x => Math.abs(x.x - 1.5) < 1e-9);
  assert.ok(near, '曲线缺少 1.5 处的点');
  const ref = r.marginal.beta0 + r.marginal.beta1 * 1.5;
  assert.ok(Math.abs(near.y - ref) < 1e-9, '曲线点与 Δ(s) 公式不符');
  assert.ok(near.hi >= near.lo, '曲线区间上下界颠倒');
});

test('P1-1 回归：冲击评估的结论强度不再写死，传入 opts 后与评级器一致', () => {
  const esT = D.impact.event_study.pre_trend_max_abs_t;
  const audit = D.impact.sensitivity_audit || {};
  const r = E.impact({ strength: 1.61 }, D, { exogenous: true });
  const g = E.gradeEvidence({
    exogenous: true, preTrendMaxAbsT: esT, preTrendRatio: r.preTrendRatio,
    ringsVerified: !!audit.rings_alternative_has_coefficients, bootstrapCI: !!audit.bootstrap_ci,
  });
  assert.strictEqual(r.grade.level, g.level, '冲击评估与评级器等级不一致');
  assert.strictEqual(r.grade.level, 'B', '外生 + 前趋势显著 + 量级比<0.5 应为 B 级');
  assert.ok(r.preTrendRatio > 0 && r.preTrendRatio < 0.5, '前趋势量级比异常：' + r.preTrendRatio);
});

test('P1-1 回归：gradeFromData 是唯一等级来源，与 impact(opts) 输出一致', () => {
  const a = E.gradeFromData(D, true);
  const b = E.impact({ strength: 1.61 }, D, { exogenous: true });
  assert.strictEqual(a.level, b.grade.level, 'gradeFromData 与 impact 等级不一致');
  assert.strictEqual(a.level, 'B');
  assert.strictEqual(E.gradeFromData(D, false).level, 'C', '内生事件应为 C 级');
  assert.strictEqual(E.gradeFromData(D, null).level, 'C', '未判定 + 前趋势显著 → 降级到 C');
});

test('P1-2 回归：示例项目的外生性字段必须是问卷枚举，且期望等级与描述一致', () => {
  const samples = ((T.workbench || {}).samples || []).map(s => s.project);
  assert.ok(samples.length >= 2, '示例数量不足');
  samples.forEach(s => assert.ok(['yes', 'no', 'unsure'].indexOf(s.intakeAnswers.exogenous) >= 0,
    '示例外生性字段类型错误：' + JSON.stringify(s.intakeAnswers.exogenous)));
  const A = E.intake(Object.assign({}, samples[0].intakeAnswers));
  const B = E.intake(Object.assign({}, samples[1].intakeAnswers));
  assert.strictEqual(A.hardFail, false, '示例 A 不应触发一票否决');
  assert.strictEqual(A.ceiling, 'B', '示例 A 结论上限应为 B');
  assert.strictEqual(B.hardFail, true, '示例 B 应触发一票否决（仅有公司级结果变量）');
});

test('P1-2 回归：引擎接受布尔外生性（旧项目 JSON 向后兼容）', () => {
  const r = E.intake({ stableId: true, idMatchRate: 0.95, coordNullRate: 0.05, outcomeLevel: 'store', years: 10, eventDefined: true, exogenous: true });
  assert.strictEqual(r.hardFail, false);
  assert.strictEqual(r.ceiling, 'B');
});

test('P2-2 回归：外生性未判定必须写成"未判定"，不得与"内生决策"混为一谈', () => {
  const r = E.intake({ stableId: true, idMatchRate: 0.95, coordNullRate: 0.05, outcomeLevel: 'store', years: 10, eventDefined: true, exogenous: 'unsure' });
  assert.strictEqual(r.ceiling, 'B', '未判定应给上限 B');
  const txt = r.gaps.concat(r.notes).concat(r.grade.reasons).join(' ');
  assert.ok(txt.includes('未判定'), '缺少"未判定"措辞');
  assert.ok(!r.gaps.join(' ').includes('内生决策'), '未判定被误写成内生决策');
});

test('P2-1 回归：报告数据血缘表按模块归组，首列不再是占位符', () => {
  const proj = {
    name: '血缘测试',
    intake: E.intake({ stableId: true, idMatchRate: 0.95, coordNullRate: 0.05, outcomeLevel: 'store', years: 10, eventDefined: true, exogenous: 'yes' }),
    impact: E.impact({ strength: 1.61 }, D, { exogenous: true }),
  };
  const md = E.buildReport(proj, D);
  assert.ok(!/\|\s*—\s*\|\s*`/.test(md), '血缘表仍存在空模块列');
  assert.ok(md.includes('| 准入体检 |') || md.includes('| 冲击评估 |'), '血缘表未按模块归组');
});

test('P2-3 回归：保守风险值必须标注"未重拟合 / 仅用于相对排序"', () => {
  const r = E.risk({ age: 25, log_depsumbr: 10, neighbor_count: 5, lat: 38, lng: -86, bank_closed_rate: 0.5, year: 2010, bkclass: 'N', fragility: 'L0_单网点' }, D);
  assert.ok(r.caveats.join(' ').includes('相对排序'), '缺少保守值口径披露');
});

test('P2-4 回归：有审计产物时支撑域必须用实测最小值，并在均值处报效应', () => {
  const r = E.impact({ strength: 1.61 }, D);
  const br = D.impact.strength_support.branch_level;
  assert.strictEqual(r.supportLowerBound, br.min, '支撑域下界应取实测网点级最小值');
  assert.ok(r.supportMeasured, '应标记为实测');
  assert.ok(r.caveats.join(' ').includes('实测'), '缺少实测来源披露');
  assert.ok(r.marginal.atMean, '缺少均值处边际效应');
  const exp = D.impact.marginal_at_support.at_mean;
  assert.ok(Math.abs(r.marginal.atMean.effect - exp.effect) < 1e-12, '均值处效应对不上审计产物');
  assert.strictEqual(r.marginal.atMean.s, br.mean);
});

test('P2-4 回归：审计产物缺失时退回"由变量定义反推"并如实标注', () => {
  const bare = JSON.parse(JSON.stringify(D));
  delete bare.impact.strength_support;
  const r = E.impact({ strength: 1.61 }, bare);
  assert.strictEqual(r.supportMeasured, false);
  assert.ok(Math.abs(r.supportLowerBound - Math.log1p(1)) < 1e-12);
  assert.ok(r.caveats.join(' ').includes('反推'), '缺审计产物时应标注为反推');
  assert.strictEqual(r.marginal.atMean, null);
});

test('P0-2 回归：合并环敏感性必须带真实系数，且细环与权威产物一致', () => {
  const r = E.impact({ strength: 1.61 }, D);
  const rs = r.ringsSensitivity;
  assert.ok(rs && rs.fine && rs.coarse_rebin && rs.coarse_linear, '缺少三种距离环口径');
  assert.strictEqual(rs.fine.coef, D.impact.twfe.post_x_strength, '细环系数应等于权威产物');
  ['fine', 'coarse_rebin', 'coarse_linear'].forEach(k => {
    assert.ok(isFinite(rs[k].se) && rs[k].se > 0, k + ' 缺标准误');
    assert.ok(rs[k].p < 0.05, k + ' 应显著');
    assert.ok(rs[k].coef > 0, k + ' 应与细环同号（正）');
  });
  assert.ok(r.ringsCross && isFinite(r.ringsCross.slope_spread_pct), '缺少跨口径可比性');
  assert.ok(r.ringsCross.slope_spread_pct < 10, '跨口径斜率差异应很小');
  assert.ok(r.caveats.join(' ').includes('合并环'), '结果披露缺少合并环提示');
});

test('P0-3 回归：风险归因必须披露时序外推结果（替代随机划分乐观值）', () => {
  const r = E.risk({
    age: 25, log_depsumbr: 10, neighbor_count: 5, lat: 38, lng: -86,
    bank_closed_rate: 0.4, year: 2010, bkclass: 'N', fragility: 'L0_单网点',
  }, D);
  const c = D.risk.out_of_time.conclusion;
  const txt = r.caveats.join(' ');
  assert.ok(txt.includes('时序外推'), '缺少时序外推披露');
  assert.ok(txt.includes(String(Number(c.out_of_time_auc_no_leak_mean).toFixed(4))), '剔泄漏 AUC 未出现');
  assert.ok(D.risk.model_card.out_of_time_validated === true, '模型卡应标记已做时序外推');
  assert.ok(c.out_of_time_auc_no_leak_mean < 0.6, '剔泄漏后应接近随机（<0.6）');
});

test('看板自动核对：必须由产物反推 P0-1~P0-6 状态，且与静态文案解耦', () => {
  const p = (D.audit || {}).patches || {};
  ['P0-1', 'P0-2', 'P0-3', 'P0-4', 'P0-5', 'P0-6'].forEach(k => {
    assert.ok(p[k] && p[k].auto_status && p[k].evidence, k + ' 缺少自动核对结论');
  });
  assert.ok(/已修/.test(p['P0-1'].auto_status));
  assert.ok(/已补跑/.test(p['P0-2'].auto_status));
  assert.ok(/已补跑/.test(p['P0-3'].auto_status));
  assert.ok(/一致/.test(p['P0-4'].auto_status), 'P0-4 应报口径一致：' + p['P0-4'].auto_status);
  assert.ok(/已修/.test(p['P0-5'].auto_status), 'P0-5 应报全链路重建通过：' + p['P0-5'].auto_status);
});

test('上游口径核对：SLX W_treat 在四处产物 + 正文必须一致（P0-4 已修）', () => {
  const wc = (D.audit || {}).wtreat_consistency;
  assert.ok(wc, '缺少 W_treat 一致性核对');
  assert.strictEqual(wc.consistent, true, '上游取值应一致；不一致处：' + JSON.stringify(wc.mismatches));
  assert.strictEqual(wc.mismatches.length, 0,
    '不应再有不一致项：' + JSON.stringify(wc.mismatches));
  assert.ok(wc.observed.length >= 4, '必须核对到 estimate.json / metrics.json / conclusion_report.json / manifest');
  const texts = wc.observed.filter(o => o.kind === 'text');
  assert.ok(texts.length >= 2, '必须核对正文里的印刷值');
  texts.forEach(o => {
    assert.ok(Math.abs(o.value - wc.authoritative) <= 2e-3 * wc.authoritative,
      `正文印刷值 ${o.value} 与权威值 ${wc.authoritative} 不符（${o.where}）`);
    assert.ok(Math.abs(o.value - wc.ols_treat_strength_for_reference) > 1e-4,
      `正文仍把 OLS 的 treat_strength 当成 SLX 的 W_treat（${o.where}）`);
  });
});

test('P0-5 回归：从原始 CSV 的全链路重建必须逐阶段对上（行数 + 最大绝对差）', () => {
  const fc = (D.audit || {}).full_chain;
  assert.ok(fc, '缺少全链路重建核对');
  assert.strictEqual(fc.verdict, '通过', '全链路重建未通过：' + JSON.stringify(fc.conclusion));
  assert.strictEqual(fc.checks_passed, fc.checks_total, '存在未通过的对拍项');
  assert.ok(fc.checks_total >= 8, '对拍项过少：' + fc.checks_total);
  assert.ok(fc.protocol.raw_files >= 32, '原始文件数异常');
  const h = fc.headline || {};
  assert.ok(h.did_panel_rows, '缺少 did_panel 行数对拍');
  assert.strictEqual(h.did_panel_rows.upstream, h.did_panel_rows.sandbox);
  assert.strictEqual(h.strength_t0_max_abs_diff, 0, 'strength_t0 未逐网点一致');
  assert.strictEqual(h.dep_chg_rate_max_abs_diff, 0, 'dep_chg_rate 未逐行一致');
  assert.strictEqual(h.estimate_ok, true, '头条系数未对上');
});

test('P2-5 回归：必须披露格级 OLS 混合值与 SLX 本地效应异号、不可混用', () => {
  const r = E.impact({ strength: 1.61 }, D);
  assert.ok(r.caveats.join(' ').includes('口径不同'), '缺少 OLS/SLX 口径冲突披露');
});

test('报告生成：模块缺失时对应章节应消失（而非输出空章节）', () => {
  const onlyIntake = E.buildReport({
    name: '只有准入',
    intake: E.intake({ stableId: true, idMatchRate: 0.95, coordNullRate: 0.05, outcomeLevel: 'store', years: 10, eventDefined: true, exogenous: 'yes' }),
  }, D);
  assert.ok(onlyIntake.includes('## 一、数据准入体检'));
  assert.ok(!onlyIntake.includes('## 二、冲击评估'));
  assert.ok(!onlyIntake.includes('## 三、风险归因'));
});

test('报告生成：必须带非加密报告指纹，且同输入同指纹', () => {
  const proj = {
    name: '指纹测试',
    intake: E.intake({ stableId: true, idMatchRate: 0.95, coordNullRate: 0.05, outcomeLevel: 'store', years: 10, eventDefined: true, exogenous: 'yes' }),
    impact: E.impact({ strength: 1.61 }, D, { exogenous: true }),
  };
  const re = /报告指纹\*\*：`([0-9a-f]{8})`/;
  const m1 = E.buildReport(proj, D).match(re);
  const m2 = E.buildReport(proj, D).match(re);
  assert.ok(m1, '缺少报告指纹或格式不正确');
  assert.strictEqual(m1[1], m2[1], '相同输入的指纹应稳定（不随生成时间漂移）');
  const other = E.buildReport(Object.assign({}, proj, { impact: E.impact({ strength: 2.4 }, D, { exogenous: true }) }), D).match(re);
  assert.notStrictEqual(m1[1], other[1], '不同输入的指纹应不同');
});
