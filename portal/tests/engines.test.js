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

const E = ctx.SDP_ENGINE;
const D = ctx.SDP_DATA;

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

test('冲击评估：支撑域下界为 log1p(1)', () => {
  const r = E.impact({ strength: 0 }, D);
  assert.ok(Math.abs(r.supportLowerBound - Math.log1p(1)) < 1e-12);
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

test('冲击评估：必须携带合并环敏感性未验证的边界提示', () => {
  const r = E.impact({ strength: 1 }, D);
  assert.ok(r.caveats.join(' ').includes('合并环'), '缺少合并环敏感性未跑提示');
  assert.ok(r.caveats.join(' ').includes('log1p(n_same_ind_5km)'), '缺少文档/实现口径不一致提示');
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
