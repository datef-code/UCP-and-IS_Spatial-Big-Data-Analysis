/* ============================================================================
 * 网点决策台 v2 · 应用层
 * 结构：工作台（评估项目）→ 数据接入 → ① 准入体检 → ② 冲击评估 → ③ 风险归因
 *       → ④ 口径实验室 → ⑤ 评估报告   ／   说明页：帮助 · 产品 · 证据与边界 · 关于
 * 事实数字一律取 window.SDP_DATA（由 build_data.py 从入库产物生成），
 * 取不到即显式降级，绝不填充估算值。
 * ========================================================================== */
(function () {
  'use strict';

  const D = window.SDP_DATA || {};
  const C = window.SDP_CONTENT || {};
  const T = window.SDP_TOOLS || {};
  const E = window.SDP_ENGINE;
  const CH = window.SDPCharts;
  const esc = CH.esc, nf = CH.nfmt;

  const $ = (s, r) => (r || document).querySelector(s);
  const $$ = (s, r) => Array.from((r || document).querySelectorAll(s));

  /* ================================================================== *
   * 0. 通用小工具
   * ================================================================== */
  const fmtPct = (v, d) => (v == null || !isFinite(v)) ? '—' : (v * 100).toFixed(d == null ? 2 : d) + 'pp';
  const fmtNum = (v, d) => (v == null || !isFinite(v)) ? '—' : Number(v).toFixed(d == null ? 4 : d);
  const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
  const expm1 = (x) => Math.expm1(x);
  /** 外生性三态归一：兼容布尔（旧项目 JSON / 历史示例）与问卷字符串（yes/no/unsure） */
  const toExo = (v) => (v === true || v === 'yes') ? true : ((v === false || v === 'no') ? false : null);
  function fmtUSD(v) {
    if (v == null || !isFinite(v)) return '—';
    if (v >= 1e8) return (v / 1e8).toFixed(2) + ' 亿美元';
    if (v >= 1e4) return (v / 1e4).toFixed(1) + ' 万美元';
    return Math.round(v).toLocaleString('en-US') + ' 美元';
  }

  function stat(k, v, sub, kind) {
    if (v == null || v === '' || v === '—') {
      return `<div class="stat missing"><div class="v">缺失 · 已降级</div><div class="k">${esc(k)}</div>
        <div class="s">产物未入库，不填充估算值</div></div>`;
    }
    return `<div class="stat ${kind || ''}"><div class="v">${v}</div><div class="k">${esc(k)}</div>${sub ? `<div class="s">${sub}</div>` : ''}</div>`;
  }
  /** 把内容层里的指标指针（如 risk.test.auc / #teaching.cells_total）解析成真实值；取不到返回 null → 显式降级 */
  const METRIC_DERIVED = {
    '#impact.tau0': () => { const t = (((D.impact || {}).event_study || {}).table || []).find(z => z.tau === 0); return t ? t.effect : null; },
    '#teaching.dataset_count': () => (((D.teaching || {}).datasets || []).length || null),
    '#teaching.cells_total': () => { const a = ((D.teaching || {}).datasets || []); return a.length ? a.reduce((s, x) => s + (x.cells || 0), 0) : null; },
    '#teaching.moran_range': () => {
      const v = ((D.teaching || {}).datasets || []).map(x => x.moran_i).filter(isFinite);
      if (!v.length) return null;
      const mn = Math.min.apply(null, v);
      return mn > 0 ? Math.max.apply(null, v) / mn : null;
    },
  };
  function fmtMetric(v) {
    if (v == null || (typeof v === 'number' && !isFinite(v))) return null;
    if (typeof v === 'number') return Math.abs(v) >= 100 ? nf(v, 0) : nf(v, 4);
    return String(v);
  }
  function resolveMetric(path) {
    if (Object.prototype.hasOwnProperty.call(METRIC_DERIVED, path)) return fmtMetric(METRIC_DERIVED[path]());
    const v = String(path).split('.').reduce((o, k) => (o == null ? null : o[k]), D);
    return fmtMetric(v);
  }
  function figure(cap, sub, svg, legend) {
    return `<div class="figure"><div class="cap">${esc(cap)}</div><div class="sub">${esc(sub || '')}</div>${svg}
      ${legend ? `<div class="legend">${legend}</div>` : ''}</div>`;
  }
  function gradeBadge(g) {
    if (!g) return '';
    return `<span class="tag" style="color:${g.color};border-color:${g.color}">结论强度 ${g.level} · ${esc(g.name)}</span>`;
  }
  function caveatBlock(list, title) {
    if (!list || !list.length) return '';
    return `<details class="drill" open><summary>${esc(title || '使用边界（不可省略）')} · ${list.length} 条</summary>
      <div class="body"><ul>${list.map(x => `<li>${esc(x)}</li>`).join('')}</ul></div></details>`;
  }
  function sourceBlock(list) {
    if (!list || !list.length) return '';
    return `<details class="drill"><summary>数据血缘 · ${list.length} 条</summary>
      <div class="body"><ul>${list.map(x => `<li><code>${esc(x)}</code></li>`).join('')}</ul></div></details>`;
  }

  /* ================================================================== *
   * 1. 项目状态（本机 localStorage，不上传）
   * ================================================================== */
  const KEY = 'sdp.project.v2';
  const Store = {
    p: null,
    blank() {
      return {
        id: 'p' + Date.now().toString(36),
        name: '', client: '', industry: '', decision: '',
        intakeAnswers: {}, impactInput: { strength: 1.61, eventYear: 2012 },
        riskInput: {}, caliberInput: { dataset: 'fdic' },
        updatedAt: new Date().toISOString(),
      };
    },
    load() {
      if (this.p) return this.p;
      try {
        const raw = localStorage.getItem(KEY);
        this.p = raw ? JSON.parse(raw) : this.blank();
      } catch (e) { this.p = this.blank(); }
      if (!this.p.id) this.p = this.blank();
      return this.p;
    },
    save() {
      this.p.updatedAt = new Date().toISOString();
      try { localStorage.setItem(KEY, JSON.stringify(this.p)); } catch (e) { /* 隐私模式下静默 */ }
    },
    reset() { this.p = this.blank(); this.save(); },
    set(obj) { Object.assign(this.load(), obj); this.save(); },
  };

  /* ================================================================== *
   * 1.5 重估数据层：用「客户自己的数据」现场拟合出的产物，覆盖仓库产物
   *     —— 这是产品不再被锁死在 FDIC/三个项目系数上的关键开关。
   * ================================================================== */
  const REFIT_KEY = 'sdp.refit.v1';
  const Refit = {
    raw() { try { return JSON.parse(localStorage.getItem(REFIT_KEY) || 'null'); } catch (e) { return null; } },
    save(o) { try { localStorage.setItem(REFIT_KEY, JSON.stringify(o)); } catch (e) { /* 隐私模式静默 */ } applyRefit(); },
    clear() { try { localStorage.removeItem(REFIT_KEY); } catch (e) { /* ignore */ } location.reload(); },
  };
  function applyRefit() {
    const r = Refit.raw();
    if (!r || !r.artifact) return;
    // 整体替换而非合并：否则仓库产物里的项目专属字段（如 strength_disclosure 的 t=8.07、
    // 环敏感性、坐标精度词表）会串到客户数据的结果里 —— 那正是"锁死特定数据"的一种表现。
    if (r.artifact.impact) D.impact = Object.assign({}, r.artifact.impact);
    if (r.artifact.risk) D.risk = Object.assign({}, r.artifact.risk);
    D._refit_active = true;
  }
  applyRefit();
  function refitBanner() {
    const r = Refit.raw();
    if (!r) return '';
    const caps = r.capabilities || {};
    const on = Object.keys(caps).filter(k => caps[k]);
    return `<div class="note warn"><b>当前数据层来自「数据接入」现场重估</b>（不是仓库入库产物）：
      拟合时间 ${esc(String(r.at || '').slice(0, 19).replace('T', ' '))}；
      可用模块 ${esc(on.join(' / ') || '无')}；样本 ${esc(String(((r.dataset || {}).rows) || '—'))} 行。
      <a href="#ingest">回到数据接入</a>
      <button class="btn ghost" id="refitDrop" style="margin-left:8px">恢复仓库产物</button></div>`;
  }

  /** 由真实产物推导的结论强度（不是手填的）；统一走引擎 gradeFromData，保证「工作台 / 冲击页 / 报告」三处一致 */
  function computeGrade(p) {
    const prj = p || Store.load();
    return E.gradeFromData(D, toExo((prj.intakeAnswers || {}).exogenous));
  }

  function stepStatus(id) {
    const p = Store.load();
    if (id === 'intake') return (p.intakeAnswers && p.intakeAnswers.exogenous) ? 'done' : 'todo';
    if (id === 'impact') return p.impactInput && p.impactInput.strength != null ? 'done' : 'todo';
    if (id === 'risk') return p.riskInput && p.riskInput.year ? 'done' : 'todo';
    if (id === 'caliber') return p.caliberInput && p.caliberInput.dataset ? 'done' : 'todo';
    if (id === 'report') return (stepStatus('intake') === 'done') ? 'ready' : 'blocked';
    return 'todo';
  }

  /* ================================================================== *
   * 2. 页面
   * ================================================================== */
  const PAGES = [];

  /* 导航分组：把 10 个平铺入口收敛成 3 组，减少"看一眼不知道从哪开始"的负担 */
  const NAV_SECTIONS = [
    ['分析流程', ['workbench', 'ingest', 'intake', 'impact', 'risk', 'caliber', 'report']],
    ['了解与帮助', ['help', 'product']],
    ['可信度', ['evidence', 'about']],
  ];

  /* 分析流程的单一事实来源：顺序、短名、一句话职责 */
  const FLOW = [
    ['ingest', '数据接入', '任何份数 / 任何字段 → 一份数据集'],
    ['intake', '准入体检', '能不能做、能做到什么等级'],
    ['impact', '冲击评估', '影响多大 / 传多远 / 第几年最深'],
    ['risk', '风险归因', '哪些门店最可能出事、由什么决定'],
    ['caliber', '口径实验室', '换权重 / 换尺度，结论会不会翻'],
    ['report', '评估报告', '合成一份带边界与血缘的交付物'],
  ];
  const FLOW_IDS = FLOW.map(s => s[0]);

  function stepBar(cur) {
    const i = FLOW_IDS.indexOf(cur);
    return `<div class="steps">${FLOW.map(([id, name, why], k) => `
      <a class="step ${id === cur ? 'on' : ''} ${k < i ? 'done' : ''}" href="#${id}" title="${esc(why)}">
        <i>${k + 1}</i><span>${esc(name)}</span></a>`).join('')}</div>`;
  }
  function flowDone(p) {
    return {
      ingest: false,                                   // 可选步骤，不阻塞流程
      intake: !!(p.intakeAnswers || {}).exogenous,
      impact: (p.impactInput || {}).strength != null,
      risk: !!(p.riskInput || {}).year,
      caliber: !!(p.caliberInput || {}).dataset,
    };
  }
  /** 工作台的「建议下一步」：只把当前最该做的一步推到最前面，其余收进折叠区 */
  function nextStepCard() {
    const p = Store.load();
    const done = flowDone(p);
    const idx = FLOW.findIndex(s => s[0] !== 'ingest' && !done[s[0]]);
    const target = idx >= 0 ? FLOW[idx] : FLOW[FLOW.length - 1];
    const allDone = idx < 0 && !!(p.intakeAnswers || {}).exogenous;
    return `<div class="card" style="display:flex;align-items:center;gap:14px;flex-wrap:wrap;border-left:3px solid var(--brand)">
      <div style="flex:1 1 260px">
        <h3 style="margin:0">${allDone ? '流程已完成' : '建议下一步'}：${esc(target[1])}</h3>
        <p style="margin:4px 0 0" class="mini">${esc(target[2])}</p>
      </div>
      <a class="btn" href="#${esc(target[0])}">${allDone ? '生成报告' : '进入'} →</a>
    </div>`;
  }

  /* ---------- 工作台 ---------- */
  PAGES.push({
    id: 'workbench', name: '工作台', render() {
      const p = Store.load();
      const g = computeGrade(p);
      const steps = (T.workbench || {}).steps || [];
      const stepsHtml = steps.map(s => {
        const st = stepStatus(s.id);
        const badge = st === 'done' ? '<span class="tag ok">已完成</span>'
          : st === 'ready' ? '<span class="tag brand">可生成</span>'
            : st === 'blocked' ? '<span class="tag warn">待前置</span>'
              : '<span class="tag">未开始</span>';
        return `<details class="drill" ${s.id === 'intake' ? 'open' : ''}>
          <summary>${esc(s.no)} ${esc(s.name)} ${badge}${s.required ? '<span class="tag danger">必需</span>' : ''}</summary>
          <div class="body">
            <p>${esc(s.why)}</p>
            <a class="btn" href="#${esc(s.id)}">进入 →</a>
          </div></details>`;
      }).join('');

      const samples = ((T.workbench || {}).samples || []).map((s, i) =>
        `<div class="card" style="margin:0"><h4 style="margin-top:0">${esc(s.name)}</h4>
          <p>${esc(s.desc)}</p>
          <button class="btn ghost" data-sample="${i}">载入这个示例</button></div>`).join('');

      return `
      <div class="page-head">
        <div class="kicker">WORKBENCH</div>
        <h1>工作台 · 空间影响评估项目</h1>
        <p>${esc((T.workbench || {}).intro || '')}</p>
      </div>

      ${refitBanner()}
      ${nextStepCard()}

      <div class="card">
        <h3>项目信息</h3>
        <div class="grid g2" style="gap:10px">
          <label class="fld"><span>项目名称</span><input id="pjName" type="text" value="${esc(p.name)}" placeholder="例：某连锁便利店 · 竞对退出影响评估"></label>
          <label class="fld"><span>客户 / 委托方</span><input id="pjClient" type="text" value="${esc(p.client)}" placeholder="例：某咨询机构（终客户：连锁便利店）"></label>
          <label class="fld"><span>行业</span><input id="pjIndustry" type="text" value="${esc(p.industry)}" placeholder="例：连锁零售 / 便利店"></label>
          <label class="fld"><span>要回答的决策问题</span><input id="pjDecision" type="text" value="${esc(p.decision)}" placeholder="例：竞对关店后，我方门店受多大影响、传多远"></label>
        </div>
        <div style="margin-top:10px;display:flex;gap:8px;flex-wrap:wrap">
          <button class="btn ghost" id="pjReset">清空项目</button>
          <button class="btn ghost" id="pjExport">导出项目 JSON</button>
          <label class="btn ghost" style="cursor:pointer">导入项目 JSON<input id="pjImport" type="file" accept=".json" style="display:none"></label>
        </div>
        <div class="mini" id="pjMeta" style="margin-top:8px"></div>
      </div>

      <div class="card">
        <h3>当前结论强度</h3>
        <div style="margin-bottom:8px">${gradeBadge(g)}</div>
        <ul style="margin:0">${(g.reasons || []).map(r => `<li>${esc(r)}</li>`).join('')}</ul>
        <div class="note">该等级由引擎依据<b>真实产物</b>自动判定（事件前 τ 的 |t|、前趋势/post 量级比、敏感性是否已跑、是否有时序外推验证），不是手填选项。</div>
      </div>

      <div class="card">
        <h3>评估流程（五步）</h3>
        ${stepsHtml}
      </div>

      <div class="page-head" style="margin-top:22px"><div class="kicker">SAMPLES</div><h1 style="font-size:19px">一键载入示例项目</h1>
        <p>不想从零填表？载入一个示例看完整流程。示例数据为<b>演示用构造数据</b>，参数取自本项目真实分布。</p></div>
      <div class="grid g2">${samples}</div>`;
    },
    bind() {
      const p = Store.load();
      const map = { pjName: 'name', pjClient: 'client', pjIndustry: 'industry', pjDecision: 'decision' };
      const drop = document.getElementById('refitDrop');
      if (drop) drop.addEventListener('click', () => { if (confirm('恢复到仓库入库产物（丢弃本次重估数据层）？')) Refit.clear(); });
      Object.keys(map).forEach(id => {
        const el = document.getElementById(id);
        if (!el) return;
        el.addEventListener('input', () => { Store.set({ [map[id]]: el.value }); });
      });
      const meta = document.getElementById('pjMeta');
      if (meta) meta.textContent = `项目 ID ${p.id}　·　最后更新 ${String(p.updatedAt).slice(0, 19).replace('T', ' ')}　·　数据层生成于 ${String((D.meta || {}).generated_at || '').slice(0, 19).replace('T', ' ')}`;

      $$('[data-sample]').forEach(btn => btn.addEventListener('click', () => {
        const s = ((T.workbench || {}).samples || [])[Number(btn.dataset.sample)];
        if (!s) return;
        const fresh = Object.assign(Store.blank(), s.project);
        Store.p = fresh; Store.save();
        render('#' + current());
      }));

      const r = document.getElementById('pjReset');
      if (r) r.addEventListener('click', () => {
        if (confirm('清空当前项目（含所有输入）？')) { Store.reset(); render('#' + current()); }
      });
      const ex = document.getElementById('pjExport');
      if (ex) ex.addEventListener('click', () => download(`sdp-project-${Store.load().id}.json`, JSON.stringify(Store.load(), null, 2), 'application/json'));
      const im = document.getElementById('pjImport');
      if (im) im.addEventListener('change', () => {
        const f = im.files && im.files[0]; if (!f) return;
        const fr = new FileReader();
        fr.onload = () => { try { Store.p = JSON.parse(fr.result); Store.save(); render('#' + current()); } catch (e) { alert('JSON 解析失败：' + e.message); } };
        fr.readAsText(f);
      });
    },
  });

  /* ---------- 数据接入（泛化：多源 / 任意字段 / 形态路由 / 现场重估） ---------- */
  const ING_ROLES = [
    ['entity', '实体 ID'], ['time', '时间（期）'], ['event_time', '事件时间'],
    ['lat', '纬度'], ['lon', '经度'], ['value', '结果变量'], ['group', '分组 / 行业'],
  ];
  const REFIT_OPTIONS = [
    ['treat_year_col', '处理年（实体开始受处理的年份列）'],
    ['treat_col', '处理标记（0/1 列）'],
    ['strength_col', '暴露强度（可选，数值列）'],
    ['exit_col', '退出目标（0/1 列，用于风险归因）'],
  ];
  let ING = null;           // 最近一次接入结果
  let ING_FILES = null;     // 上传的 File[]（重估时重发，服务端不落盘）
  let ING_SRC = null;       // {mode:'upload'|'paths', paths:[]}
  let ING_REFIT = null;     // 最近一次重估结果
  let ING_TPLS = [];

  function ingSel(id, cols, cur) {
    return ['<option value="">（未选用）</option>'].concat(cols.map(c =>
      `<option value="${esc(c)}" ${String(c) === String(cur == null ? '' : cur) ? 'selected' : ''}>${esc(c)}</option>`)).join('');
  }
  async function ingJSON(url, body) {
    const r = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    return r.json();
  }
  async function ingFramed(url, files, query) {
    const parts = [];
    for (const f of files) { parts.push(`#FILE ${encodeURIComponent(f.name)} ${f.size}\n`, f, '\n'); }
    parts.push('#END\n');
    const r = await fetch(url + (query ? ('?' + query) : ''), { method: 'POST', body: new Blob(parts) });
    return r.json();
  }
  function ingMappingFromUI() {
    const m = {};
    ING_ROLES.forEach(([k]) => { const el = document.getElementById('ing_' + k); m[k] = el ? (el.value || null) : null; });
    return m;
  }
  function ingRefitFromUI() {
    const o = {};
    REFIT_OPTIONS.forEach(([k]) => { const el = document.getElementById('rf_' + k); if (el && el.value) o[k] = el.value; });
    return o;
  }
  function ingHealthList() {
    if (!ING) return '';
    return (ING.health.checks || []).map(c => `<div style="padding:7px 0;border-bottom:1px solid var(--line,#e5e7eb)">
      <span class="tag ${c.level === 'ok' ? 'ok' : c.level === 'warn' ? 'warn' : 'danger'}">${esc(c.level.toUpperCase())}</span>
      <b>${esc(c.title)}</b>：${esc(c.value)}
      ${c.note ? `<div class="mini">${esc(c.note)}</div>` : ''}
      ${c.action ? `<div class="mini" style="color:#b45309">→ ${esc(c.action)}</div>` : ''}
    </div>`).join('');
  }

  PAGES.push({
    id: 'ingest', name: '数据接入', render() {
      const cols = ING ? ING.dataset.columns : [];
      const ds = ING ? ING.dataset : null;
      const shapeTag = ING ? `<span class="tag brand">形态：${esc(ING.shape.kind)}</span>` : '';
      const filesHtml = ds ? (ds.sources || []).map(s => `<tr>
          <td><code>${esc(s.name)}</code></td><td>${nf(s.rows, 0)}</td><td>${s.cols}</td>
          <td>${(s.bytes / 1048576).toFixed(1)} MB</td><td>${s.ok ? 'ok' : `<span style="color:#b91c1c">${esc(s.error || '失败')}</span>`}</td></tr>`).join('') : '';
      const diff = ds ? (ds.schema_diff || {}).partial_columns || [] : [];
      const refitCaps = ING_REFIT ? ING_REFIT.capabilities || {} : null;
      const tplOpts = ['<option value="">（选择已存模板）</option>'].concat(
        ING_TPLS.map((t, i) => `<option value="${i}">${esc(t.name)}</option>`)).join('');

      return `
      <div class="page-head"><div class="kicker">STEP 0 · INGEST</div>
        <h1>数据接入（泛化）</h1>
        <p>不假设列名、不假设形态：一次可导入<b>多份文件</b>（按列名并集拼接），角色由<b>内容</b>推断且可人工覆盖，
          识别面板 / 事件流 / 横截面 / 边表后路由到不同体检规则；确认后用<b>你自己的数据</b>现场重估系数。</p></div>

      <div class="note">需本地服务：<code>datakit/.venv/Scripts/python.exe portal/serve.py</code>。
        上传文件在响应后立即删除；本机路径模式不复制数据。<span class="ro" id="ingState">检测服务…</span></div>

      <div class="card">
        <h3>① 数据来源</h3>
        <div class="row" style="gap:8px;flex-wrap:wrap;align-items:center">
          <input type="file" id="ingFiles" multiple accept=".csv,.tsv,.txt,.json,.jsonl,.xlsx,.gz">
          <label class="btn ghost" style="cursor:pointer">选择文件夹<input type="file" id="ingDir" webkitdirectory directory multiple style="display:none"></label>
          <button class="btn" id="ingParseUp">解析上传</button>
        </div>
        <div class="row" style="gap:8px;margin-top:10px;align-items:center">
          <input type="text" id="ingPaths" style="flex:1;min-width:280px"
            placeholder="本机路径 / 通配符，分号分隔。例：data_raw/fdic/*.csv ；data_raw/snap_brightkite">
          <label class="mini" style="white-space:nowrap">文件上限
            <input type="number" id="ingLimit" value="12" min="1" max="500" style="width:74px"></label>
          <button class="btn" id="ingParsePath">解析本机路径</button>
        </div>
        <div class="mini" style="margin-top:6px">大数据走本机路径（不受 512MB 上传上限约束）；小数据直接上传，服务端不落盘。</div>
      </div>

      ${ds ? `
      <div class="card">
        <h3>② 数据集 <span class="mini">${ds.source_count} 个文件 → ${nf(ds.rows, 0)} 行 × ${cols.length} 列</span> ${shapeTag}</h3>
        <table style="width:100%;font-size:12px"><thead><tr><th align="left">文件</th><th>行数</th><th>列数</th><th>大小</th><th>状态</th></tr></thead>
          <tbody>${filesHtml}</tbody></table>
        ${diff.length ? `<div class="note warn" style="margin-top:8px">各文件列不一致，已按列名并集拼接，缺失处留空：
          ${diff.slice(0, 12).map(d => `<code>${esc(d.column)}</code>(${d.in_files}/${d.of_files})`).join('、')}
          ${diff.length > 12 ? ` 等 ${diff.length} 列` : ''}</div>` : ''}
        ${(ds.notes || []).length ? `<div class="mini">${ds.notes.map(esc).join('；')}</div>` : ''}
      </div>

      <div class="card">
        <h3>③ 字段映射 <span class="mini">自动推断可覆盖；不是靠列名，而是靠取值分布</span></h3>
        <div class="grid g2" style="gap:10px">
          ${ING_ROLES.map(([k, label]) => `<label class="fld"><span>${esc(label)}</span>
            <select id="ing_${k}">${ingSel('ing_' + k, cols, (ING.roles || {})[k])}</select></label>`).join('')}
        </div>
        <div class="row" style="gap:8px;margin-top:10px;flex-wrap:wrap;align-items:center">
          <button class="btn ghost" id="ingRecheck">按当前映射重算</button>
          <input type="text" id="ingTplName" placeholder="模板名（如：某客户·网点年）" style="min-width:200px">
          <button class="btn ghost" id="ingTplSave">存为映射模板</button>
          <select id="ingTplPick">${tplOpts}</select>
          <button class="btn ghost" id="ingTplLoad">载入模板</button>
        </div>
      </div>

      <div class="card">
        <h3>④ 体检结果 <span class="mini">按形态路由：${esc(ING.shape.note || '')}</span></h3>
        ${ingHealthList()}
      </div>

      <div class="card">
        <h3>⑤ 用这份数据重估系数</h3>
        <p>全部系数<b>现场拟合</b>（TWFE 双向固定效应 + 事件研究 + 空间 KNN/SLX/Moran + cloglog），
          <b>不含任何上游硬编码系数</b>。拟合完成后可作为当前数据层直接进入四个模块。</p>
        <div class="grid g2" style="gap:10px">
          ${REFIT_OPTIONS.map(([k, label]) => `<label class="fld"><span>${esc(label)}</span>
            <select id="rf_${k}">${ingSel('rf_' + k, cols, '')}</select></label>`).join('')}
        </div>
        <div class="mini" style="margin-top:6px">不选任何处理定义时：若数据有事件时间列，则自动以「首次事件年」为处理起点。</div>
        <div class="row" style="gap:8px;margin-top:10px;flex-wrap:wrap;align-items:center">
          <button class="btn" id="ingRefit">开始重估</button>
          <span class="ro" id="ingRefitState"></span>
        </div>
        ${refitCaps ? `<div class="note" style="margin-top:10px">
          能力判定：${Object.keys(refitCaps).map(k => `${esc(k)} ${refitCaps[k]
        ? '<b style="color:#047857">✓</b>' : '<b style="color:#b91c1c">✗</b>'}`).join(' · ')}
          ${(ING_REFIT.notes || []).length ? `<div class="mini">${ING_REFIT.notes.map(esc).join('；')}</div>` : ''}
          ${ING_REFIT.artifact && ING_REFIT.artifact.impact ? `<div class="mini">TWFE：post = ${
        fmtNum(ING_REFIT.artifact.impact.twfe.post, 4)}，post×强度 = ${
        fmtNum(ING_REFIT.artifact.impact.twfe.post_x_strength, 4)}（n = ${
        nf(ING_REFIT.artifact.impact.twfe.n_obs, 0)}）</div>` : ''}
          <div class="row" style="margin-top:8px"><button class="btn" id="ingApply">载入为当前数据层</button></div>
        </div>` : ''}
      </div>` : ''}
      <div id="ingPick" style="display:none"></div>`;
    },
    bind() {
      const st = document.getElementById('ingState');
      async function health() {
        try {
          const h = await (await fetch('/api/health')).json();
          st.textContent = h.ingest_available ? '服务可用（接入 + 重估）' : ('服务不可用：' + (h.ingest_error || h.datakit_error || '未知'));
        } catch (e) { st.textContent = '未启动本地服务（上传 / 重估不可用）'; }
      }
      health();
      fetch('/api/templates').then(r => r.json()).then(r => { ING_TPLS = r.templates || []; }).catch(() => {});

      const bindFile = (id, dir) => {
        const el = document.getElementById(id);
        if (!el) return;
        el.addEventListener('change', async () => {
          const files = Array.from(el.files || []);
          if (!files.length) return;
          st.textContent = `解析中：${files.length} 个文件…`;
          const res = await ingFramed('/api/ingest', files, '');
          if (!res.ok) { st.textContent = '失败：' + (res.error || '未知'); return; }
          ING = res; ING_FILES = files; ING_SRC = { mode: 'upload', paths: files.map(f => f.name) }; ING_REFIT = null;
          st.textContent = `已解析 ${files.length} 个文件`;
          render('#ingest');
        });
      };
      bindFile('ingFiles');
      bindFile('ingDir', true);
      const pu = document.getElementById('ingParseUp');
      if (pu) pu.addEventListener('click', () => document.getElementById('ingFiles').click());

      const pp = document.getElementById('ingParsePath');
      if (pp) pp.addEventListener('click', async () => {
        const raw = (document.getElementById('ingPaths').value || '').trim();
        if (!raw) { alert('请填写本机路径或通配符'); return; }
        const paths = raw.split(/[;\n]+/).map(s => s.trim()).filter(Boolean);
        const limEl = document.getElementById('ingLimit');
        const limit = limEl ? Math.max(1, Number(limEl.value) || 12) : 12;
        st.textContent = '解析中：' + paths.join(' / ');
        const res = await ingJSON('/api/ingest_paths', { paths, limit });
        if (!res.ok) { st.textContent = '失败：' + (res.error || '未知'); return; }
        ING = res; ING_FILES = null; ING_SRC = { mode: 'paths', paths, limit }; ING_REFIT = null;
        st.textContent = '已解析本机路径';
        render('#ingest');
      });

      const rk = document.getElementById('ingRecheck');
      if (rk) rk.addEventListener('click', async () => {
        const override = ingMappingFromUI();
        const body = ING_SRC.mode === 'paths' ? { paths: ING_SRC.paths, override }
          : { paths: ING_FILES ? ING_FILES.map(f => f.name) : [], override };
        if (ING_SRC.mode === 'paths') {
          const res = await ingJSON('/api/ingest_paths', body);
          if (!res.ok) { alert('失败：' + (res.error || '')); return; }
          ING = res; render('#ingest');
        } else {
          const res = await ingFramed('/api/ingest', ING_FILES || [], 'override=' + encodeURIComponent(JSON.stringify(override)));
          if (!res.ok) { alert('失败：' + (res.error || '')); return; }
          ING = res; render('#ingest');
        }
      });

      const ts = document.getElementById('ingTplSave');
      if (ts) ts.addEventListener('click', async () => {
        const name = (document.getElementById('ingTplName').value || '').trim();
        if (!name) { alert('请填写模板名'); return; }
        const r = await ingJSON('/api/templates', { name, mapping: ingMappingFromUI(), shape: ING.shape.kind, columns: (ING.dataset.columns || []) });
        if (!r.ok) { alert('保存失败：' + (r.error || '')); return; }
        ING_TPLS = r.templates || []; alert('已保存模板：' + r.saved); render('#ingest');
      });
      const tl = document.getElementById('ingTplLoad');
      if (tl) tl.addEventListener('click', () => {
        const i = document.getElementById('ingTplPick').value;
        if (i === '') { alert('请选择模板'); return; }
        const t = ING_TPLS[Number(i)];
        if (!t) return;
        Object.keys(t.mapping || {}).forEach(k => {
          const el = document.getElementById('ing_' + k);
          if (el && t.mapping[k]) el.value = t.mapping[k];
        });
        alert('已套用模板「' + t.name + '」，可点「按当前映射重算」生效');
      });

      const rb = document.getElementById('ingRefit');
      if (rb) rb.addEventListener('click', async () => {
        const state = document.getElementById('ingRefitState');
        const roles = ingMappingFromUI(), options = ingRefitFromUI();
        state.textContent = '正在拟合（大数据可能几十秒）…';
        let res;
        if (ING_SRC.mode === 'paths') {
          res = await ingJSON('/api/refit', { paths: ING_SRC.paths, limit: ING_SRC.limit, roles, options });
        } else {
          res = await ingFramed('/api/refit', ING_FILES || [],
            'roles=' + encodeURIComponent(JSON.stringify(roles)) + '&options=' + encodeURIComponent(JSON.stringify(options)));
        }
        if (!res.ok) { state.textContent = '失败：' + (res.error || '未知'); return; }
        ING_REFIT = res; state.textContent = '重估完成';
        render('#ingest');
      });
      const ap = document.getElementById('ingApply');
      if (ap) ap.addEventListener('click', () => {
        if (!ING_REFIT || !ING_REFIT.artifact) return;
        Refit.save({ artifact: ING_REFIT.artifact, capabilities: ING_REFIT.capabilities,
          spec: ING_REFIT.spec, dataset: ING_REFIT.dataset, at: new Date().toISOString() });
        alert('已载入为当前数据层。工作台 / 冲击评估 / 风险归因 / 评估报告 现在使用本次重估的系数。');
        location.hash = '#workbench';
      });
    },
  });

  /* ---------- ① 准入体检 ---------- */
  PAGES.push({
    id: 'intake', name: '数据准入体检', render() {
      const p = Store.load();
      const a = p.intakeAnswers || {};
      const qs = ((T.intake || {}).questions || []).map(q => {
        const v = a[q.key];
        let ctrl = '';
        if (q.type === 'bool') {
          ctrl = `<div class="seg" data-k="${q.key}">
            <button data-v="true" class="${v === true ? 'on' : ''}">是</button>
            <button data-v="false" class="${v === false ? 'on' : ''}">否</button></div>`;
        } else if (q.type === 'pct') {
          ctrl = `<div class="row"><input type="range" min="0" max="100" step="1" data-k="${q.key}" data-scale="pct" value="${v == null ? 0 : Math.round(v * 100)}">
            <span class="ro" data-ro="${q.key}">${v == null ? '未设置' : (v * 100).toFixed(1) + '%'}</span></div>`;
        } else if (q.type === 'num') {
          ctrl = `<div class="row"><input type="number" min="0" max="50" step="1" data-k="${q.key}" data-scale="num" value="${v == null ? 5 : v}">
            <span class="ro">年</span></div>`;
        } else if (q.type === 'enum') {
          ctrl = `<div class="seg" data-k="${q.key}">${q.options.map(o => `<button data-v="${esc(o.v)}" class="${v === o.v ? 'on' : ''}">${esc(o.t)}</button>`).join('')}</div>`;
        } else if (q.type === 'enum3') {
          ctrl = `<div class="seg" data-k="${q.key}">${q.options.map(o => `<button data-v="${esc(o.v)}" class="${v === o.v ? 'on' : ''}">${esc(o.t)}</button>`).join('')}</div>`;
        }
        return `<div class="qitem"><div class="ql">${esc(q.label)}${q.threshold ? ` <span class="tag brand">${esc(q.threshold)}</span>` : ''}</div>
          ${ctrl}<div class="qh">${esc(q.help || '')}</div></div>`;
      }).join('');

      return `
      <div class="page-head"><div class="kicker">STEP 1 · INTAKE</div>
        <h1>数据准入体检</h1><p>${esc((T.intake || {}).lead || '')}</p></div>

      <div class="card">
        <h3>上传数据自动体检（可选 · 需本地服务）</h3>
        <p>启动 <code>python portal/serve.py</code> 后，可直接上传客户的门店数据 CSV，
          <b>在本机真实调用 datakit 跑五阶段体检</b>，自动预填下面 ③⑥ 两项，并给出 7 条可复跑断言。
          文件在响应结束后立即删除，不落地存储。</p>
        <div class="row" style="gap:8px;flex-wrap:wrap;align-items:center">
          <input type="file" id="upFile" accept=".csv,.tsv,.txt">
          <button class="btn" id="upBtn">上传并体检</button>
          <span class="ro" id="upState">服务状态检测中…</span>
        </div>
        <div id="upResult" style="margin-top:12px"></div>
      </div>

      <div class="card">
        <h3>问卷</h3>
        ${qs}
        <div class="row" style="gap:8px;margin-top:6px">
          <button class="btn ghost" id="intakeFill">填入示例答案</button>
          <button class="btn ghost" id="intakeClear">清空</button>
        </div>
      </div>

      <div id="intakeResult"></div>`;
    },
    bind() {
      const a = () => Store.load().intakeAnswers || {};
      function commit(key, val) {
        const p = Store.load();
        p.intakeAnswers = Object.assign({}, p.intakeAnswers, { [key]: val });
        Store.save();
      }
      // 分段按钮
      $$('.seg').forEach(seg => {
        seg.addEventListener('click', ev => {
          const b = ev.target.closest('button'); if (!b) return;
          let v = b.dataset.v;
          if (v === 'true') v = true; else if (v === 'false') v = false;
          commit(seg.dataset.k, v);
          $$('button', seg).forEach(x => x.classList.toggle('on', x === b));
          paint();
        });
      });
      // 滑块 / 数字
      $$('[data-k][data-scale]').forEach(inp => {
        inp.addEventListener('input', () => {
          const k = inp.dataset.k, sc = inp.dataset.scale;
          let v = Number(inp.value);
          if (sc === 'pct') v = v / 100;
          commit(k, v);
          const ro = $(`[data-ro="${k}"]`);
          if (ro) ro.textContent = sc === 'pct' ? (v * 100).toFixed(1) + '%' : v;
          paint();
        });
      });
      const fill = document.getElementById('intakeFill');
      if (fill) fill.addEventListener('click', () => {
        Store.set({ intakeAnswers: { stableId: true, idMatchRate: 0.94, coordNullRate: 0.05, outcomeLevel: 'store', years: 10, eventDefined: true, exogenous: 'yes' } });
        render('#' + current());
      });
      const cl = document.getElementById('intakeClear');
      if (cl) cl.addEventListener('click', () => { Store.set({ intakeAnswers: {} }); render('#' + current()); });
      bindUpload();
      paint();
    },
  });

  /* ---------- ② 冲击评估 ---------- */
  PAGES.push({
    id: 'impact', name: '冲击评估', render() {
      const p = Store.load();
      const ip = p.impactInput || {};
      const presets = ((T.impact || {}).presets || []).map(x =>
        `<button class="chip" data-strength="${x.strength}">${esc(x.name)}</button>`).join('');
      return `
      <div class="page-head"><div class="kicker">STEP 2 · IMPACT</div>
        <h1>冲击评估</h1><p>${esc((T.impact || {}).lead || '')}</p></div>

      <div class="card">
        <h3>输入</h3>
        <div class="fld"><span>暴露强度（treat_strength = log1p(5 km 内同业关闭事件数)）</span>
          <div class="row"><input id="imStrength" type="range" min="0" max="5" step="0.01" value="${ip.strength == null ? 1.61 : ip.strength}">
          <span class="ro" id="imStrengthRo">${(ip.strength == null ? 1.61 : ip.strength).toFixed(2)}</span></div>
        </div>
        <div class="filters" style="margin:6px 0 12px">${presets}</div>
        <div class="mini" style="margin-bottom:12px">${esc((T.impact || {}).taxNote || '')}</div>
        <div class="fld"><span>事件年份（用于坐标精度折扣）</span>
          <div class="row"><input id="imYear" type="range" min="1994" max="2025" step="1" value="${ip.eventYear == null ? 2012 : ip.eventYear}">
          <span class="ro" id="imYearRo">${ip.eventYear == null ? 2012 : ip.eventYear}</span></div></div>
      </div>

      <div id="impactResult"></div>`;
    },
    bind() {
      const s = document.getElementById('imStrength'), y = document.getElementById('imYear');
      const commit = () => {
        const cur = Store.load().impactInput || {};
        Store.set({ impactInput: Object.assign({}, cur, {
          strength: Number(s.value), eventYear: Number(y.value),
        }) });
        document.getElementById('imStrengthRo').textContent = Number(s.value).toFixed(2);
        document.getElementById('imYearRo').textContent = y.value;
        paint();
      };
      if (s) s.addEventListener('input', commit);
      if (y) y.addEventListener('input', commit);
      $$('[data-strength]').forEach(b => b.addEventListener('click', () => {
        s.value = b.dataset.strength; commit();
      }));
      paint();
    },
  });

  /* ---------- ③ 风险归因 ---------- */
  const RISK_DEFAULT = { age: 25, deposit: 39360, neighbor: 5, lat: 38.9, lng: -86.22, bankClosedRate: 0.15, year: 2003, bkclass: 'N', fragility: 'L0_单网点' };

  function riskRanges() {
    const md = ((D.risk || {}).map_dist || {}).ranges || {};
    const pf = (D.risk || {}).ranges || {};
    const latR = pf.SIMS_LATITUDE || {}, lngR = pf.SIMS_LONGITUDE || {};
    const sig = (r) => (r.mean != null && r.std != null) ? [r.mean - 3 * r.std, r.mean + 3 * r.std] : [null, null];
    return {
      age: [0, Math.ceil((md.age || {}).max || 241)],
      deposit: [0, Math.ceil((md.DEPSUMBR_last || {}).max || 727200000)],
      neighbor: [0, Math.ceil((md.neighbor_count || {}).max || 415)],
      lat: sig(latR), lng: sig(lngR),
      year: ((D.risk || {}).model_card || {}).year_supported || [1994, 2015],
    };
  }

  PAGES.push({
    id: 'risk', name: '风险归因', render() {
      const p = Store.load();
      const v = Object.assign({}, RISK_DEFAULT, p.riskInput || {});
      const R = riskRanges();
      const mc = ((D.risk || {}).model_card || {});
      const [y0, y1] = R.year;
      const yearOpts = [];
      for (let y = y0; y <= y1; y++) yearOpts.push(y);
      const bks = ['N', 'NM', 'SA', 'SB', 'SM'];   // SL 已退化，剔除
      const frags = ['L0_单网点', 'L1_多网点高集中', 'L2_多网点地理分散'];
      const depMax = R.deposit[1];

      const flds = ((T.risk || {}).fields || []).map(f => {
        let ctrl = '';
        if (f.input === 'rate') {
          ctrl = `<div class="row"><input type="range" id="rk_${f.key}" min="0" max="1" step="0.01" value="${v[f.key] != null ? v[f.key] : 0.15}">
            <span class="ro" id="ro_${f.key}">${(v[f.key] != null ? v[f.key] : 0.15).toFixed(2)}</span></div>`;
        } else if (f.input === 'logAmount') {
          const t = depMax > 0 ? Math.log1p(v[f.key] || 1) / Math.log1p(depMax) : 0;
          ctrl = `<div class="row"><input type="range" id="rk_${f.key}" min="0" max="100" step="0.5" value="${(t * 100).toFixed(1)}">
            <span class="ro" id="ro_${f.key}">${fmtUSD(v[f.key])}</span></div>`;
        } else if (f.input === 'int') {
          ctrl = `<div class="row"><input type="range" id="rk_${f.key}" min="${R[f.key] ? R[f.key][0] : 0}" max="${R[f.key] ? R[f.key][1] : 100}" step="1" value="${v[f.key] != null ? v[f.key] : 0}">
            <span class="ro" id="ro_${f.key}">${v[f.key] != null ? v[f.key] : 0}</span></div>`;
        } else {
          const rr = R[f.key] || [-100, 100];
          ctrl = `<div class="row"><input type="range" id="rk_${f.key}" min="${rr[0]}" max="${rr[1]}" step="0.01" value="${v[f.key] != null ? v[f.key] : rr[0]}">
            <span class="ro" id="ro_${f.key}">${(v[f.key] != null ? v[f.key] : rr[0]).toFixed(2)}</span></div>`;
        }
        return `<div class="qitem"><div class="ql">${esc(f.label)} <span class="mini">${esc(f.unit || '')}</span></div>${ctrl}
          <div class="qh">${esc(f.hint || '')}</div></div>`;
      }).join('');

      return `
      <div class="page-head"><div class="kicker">STEP 3 · RISK</div>
        <h1>风险归因台</h1><p>${esc((T.risk || {}).lead || '')}</p></div>

      <div class="note warn"><b>本模块不是预测器。</b>${esc((T.risk || {}).notice || '')}</div>

      <div class="card">
        <h3>适用域守门</h3>
        <p>模型可用的年份区间为 <b>${y0}–${y1}</b>。
          ${(mc.degenerate_levels || {}).year ? `${(mc.degenerate_levels || {}).year.join('、')} 年的系数已退化，本工具会拒绝打分。` : ''}
          ${(mc.degenerate_levels || {}).bkclass ? `银行类别 ${(mc.degenerate_levels || {}).bkclass.join('、')} 同样被剔除。` : ''}</p>
        <p class="mini">${esc(mc.degenerate_why || '')}</p>
      </div>

      <div class="card">
        <h3>门店参数</h3>
        ${flds}
        <div class="grid g4" style="margin-top:10px">
          <label class="fld"><span>年份</span><select id="rk_year">${yearOpts.map(y => `<option value="${y}" ${String(y) === String(v.year) ? 'selected' : ''}>${y}</option>`).join('')}</select></label>
          <label class="fld"><span>银行类别</span><select id="rk_bkclass">${bks.map(b => `<option value="${b}" ${b === v.bkclass ? 'selected' : ''}>${b}</option>`).join('')}</select></label>
          <label class="fld"><span>银行脆弱性分层</span><select id="rk_fragility">${frags.map(b => `<option value="${b}" ${b === v.fragility ? 'selected' : ''}>${b}</option>`).join('')}</select></label>
        </div>
        <div class="filters" style="margin-top:10px">
          ${((T.risk || {}).presets || []).map((x, i) => `<button class="chip" data-riskpreset="${i}">${esc(x.name)}</button>`).join('')}
        </div>
      </div>

      <div id="riskResult"></div>`;
    },
    bind() {
      function commit() {
        const g = id => document.getElementById(id);
        const inp = {
          age: Number(g('rk_age').value),
          deposit: expm1(Number(g('rk_deposit').value) / 100 * Math.log1p(riskRanges().deposit[1])),
          neighbor: Number(g('rk_neighbor').value),
          lat: Number(g('rk_lat').value),
          lng: Number(g('rk_lng').value),
          bankClosedRate: Number(g('rk_bankClosedRate').value),
          year: Number(g('rk_year').value),
          bkclass: g('rk_bkclass').value,
          fragility: g('rk_fragility').value,
        };
        document.getElementById('ro_age').textContent = inp.age;
        document.getElementById('ro_neighbor').textContent = inp.neighbor;
        document.getElementById('ro_lat').textContent = inp.lat.toFixed(2);
        document.getElementById('ro_lng').textContent = inp.lng.toFixed(2);
        document.getElementById('ro_bankClosedRate').textContent = inp.bankClosedRate.toFixed(2);
        document.getElementById('ro_deposit').textContent = fmtUSD(inp.deposit);
        Store.set({ riskInput: inp });
        paint();
      }
      ['rk_age', 'rk_deposit', 'rk_neighbor', 'rk_lat', 'rk_lng', 'rk_bankClosedRate'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.addEventListener('input', commit);
      });
      ['rk_year', 'rk_bkclass', 'rk_fragility'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.addEventListener('change', commit);
      });
      $$('[data-riskpreset]').forEach(b => b.addEventListener('click', () => {
        const pr = ((T.risk || {}).presets || [])[Number(b.dataset.riskpreset)];
        if (!pr) return;
        Store.set({ riskInput: Object.assign({}, pr.v) });
        render('#' + current());
      }));
      paint();
    },
  });

  /* ---------- ④ 口径实验室 ---------- */
  PAGES.push({
    id: 'caliber', name: '口径实验室', render() {
      const p = Store.load();
      const sel = p.caliberInput || {};
      const sets = ((D.teaching || {}).datasets) || [];
      return `
      <div class="page-head"><div class="kicker">STEP 4 · CALIBER</div>
        <h1>口径实验室</h1>
        <p>「邻居」是人为定义，不是客观事实。同一份数据换一种空间权重或格值尺度，Moran's I 会变——
          这决定了你的结论有多依赖口径选择。</p></div>

      <div class="card">
        <h3>选择数据集</h3>
        <div class="seg" id="calSeg">
          ${sets.map(s => `<button data-ds="${esc(s.dataset)}" class="${(sel.dataset || 'fdic') === s.dataset ? 'on' : ''}">${esc(s.dataset)}</button>`).join('')}
        </div>
        <div class="mini" style="margin-top:8px">四个数据集来自 project6 的 L0→L3 实测阶梯；切换即可看到同一方法在不同数据分布下的差异。</div>
      </div>

      <div id="caliberResult"></div>`;
    },
    bind() {
      const seg = document.getElementById('calSeg');
      if (seg) seg.addEventListener('click', ev => {
        const b = ev.target.closest('button'); if (!b) return;
        $$('button', seg).forEach(x => x.classList.toggle('on', x === b));
        Store.set({ caliberInput: { dataset: b.dataset.ds } });
        paint();
      });
      paint();
    },
  });

  /* ---------- ⑤ 评估报告 ---------- */
  PAGES.push({
    id: 'report', name: '评估报告', render() {
      const p = Store.load();
      return `
      <div class="page-head"><div class="kicker">STEP 5 · DELIVERABLE</div>
        <h1>评估报告</h1>
        <p>把前四步的结果合成一份可交付物：含结论强度、使用边界、禁止用途与完整数据血缘。
          报告中的每个数字都可追溯到仓库内的产物文件。</p></div>

      <div class="card">
        <div class="row" style="gap:8px;flex-wrap:wrap">
          <button class="btn" id="rpBuild">生成 / 刷新报告</button>
          <button class="btn ghost" data-copy="rpMd">复制 Markdown</button>
          <button class="btn ghost" data-download="rpMd" data-filename="space-impact-report.md">下载 .md</button>
          <button class="btn ghost" id="rpJson">下载结果 JSON</button>
          <button class="btn ghost" data-print>打印 / 导出 PDF</button>
        </div>
        <div class="mini" style="margin-top:8px">打印时会自动隐藏导航与表单，只输出报告正文。</div>
      </div>
      <div class="card keep-print" id="rpOut"><div class="note">点击「生成 / 刷新报告」。</div></div>
      <pre id="rpMd" data-raw="" style="display:none"></pre>`;
    },
    bind() {
      const build = () => {
        const p = Store.load();
        const ia = p.intakeAnswers || {};
        const ans = {
          stableId: ia.stableId, idMatchRate: ia.idMatchRate, coordNullRate: ia.coordNullRate,
          outcomeLevel: ia.outcomeLevel, years: ia.years, eventDefined: ia.eventDefined,
          exogenous: toExo(ia.exogenous),
        };
        const hasIntake = Object.keys(ia).length > 0;
        const proj = {
          name: p.name, client: p.client, industry: p.industry, decision: p.decision,
          intake: hasIntake ? E.intake(ans) : null,
          impact: (p.impactInput && p.impactInput.strength != null)
            ? E.impact({ strength: p.impactInput.strength, eventYear: p.impactInput.eventYear }, D) : null,
          risk: (p.riskInput && p.riskInput.year)
            ? E.risk({
              age: p.riskInput.age, log_depsumbr: Math.log1p(p.riskInput.deposit || 0),
              neighbor_count: p.riskInput.neighbor, lat: p.riskInput.lat, lng: p.riskInput.lng,
              bank_closed_rate: p.riskInput.bankClosedRate, year: p.riskInput.year,
              bkclass: p.riskInput.bkclass, fragility: p.riskInput.fragility,
            }, D) : null,
          grade: computeGrade(p),
        };
        const md = E.buildReport(proj, D);
        const pre = document.getElementById('rpMd');
        pre.textContent = md; pre.dataset.raw = md;
        document.getElementById('rpOut').innerHTML = `<div class="report-body">${md2html(md)}</div>`;
        return proj;
      };
      const b = document.getElementById('rpBuild');
      if (b) b.addEventListener('click', build);
      const j = document.getElementById('rpJson');
      if (j) j.addEventListener('click', () => {
        const proj = build();
        const payload = { project: Store.load(), computed: proj, dataLayer: { generated_at: (D.meta || {}).generated_at, provenance: ((D.meta || {}).provenance || []).slice(0, 0) } };
        download('space-impact-result.json', JSON.stringify(payload, null, 2), 'application/json');
      });
      build();
    },
  });

  /* ---------- 帮助 ---------- */
  PAGES.push({
    id: 'help', name: '帮助', render() {
      const hasRefit = !!Refit.raw();
      const pathCard = (no, title, steps, cta) => `<div class="card hcard">
        <div class="hno">${no}</div><h3>${esc(title)}</h3>
        <ol class="hlist">${steps.map(s => `<li>${s}</li>`).join('')}</ol>
        ${cta || ''}</div>`;

      return `
      <div class="page-head"><div class="kicker">HELP</div>
        <h1>使用帮助</h1>
        <p>三条使用路径、六步流程、常见问题与术语。看完这一页就能上手；
           更细的边界与方法说明见「产品说明」与「证据与边界」。</p></div>

      ${hasRefit ? `<div class="note warn">你当前正在使用<b>现场重估的数据层</b>（不是仓库自带产物）。
        <a href="#ingest">回到数据接入</a> 或在工作台点「恢复仓库产物」。</div>` : ''}

      <h2 class="sect">选择你的路径</h2>
      <div class="grid g3">
        ${pathCard('A', '只想看看它能做什么', [
        '打开 <a href="#workbench">工作台</a>，在页面底部点一个<b>示例项目</b>',
        '按 <a href="#impact">② 冲击评估</a> → <a href="#risk">③ 风险归因</a> → <a href="#report">⑤ 评估报告</a> 顺序点一遍',
        '每个结果都自带「使用边界」，注意看那几行'],
        '<a class="btn ghost" href="#workbench">去工作台</a>')}
        ${pathCard('B', '要用我自己的数据', [
        '先启动本地服务：<b>双击 <code>portal/start.bat</code></b>（自动找 Python、挑空闲端口、开浏览器；Git Bash 用 <code>bash portal/start.sh</code>）',
        '打开 <a href="#ingest">数据接入</a>：上传多份文件，或填本机路径 / 通配符',
        '核对<b>字段映射</b>（自动推断可改；不对就改，可存成模板）',
        '点「<b>开始重估</b>」→ 看能力判定 → 点「<b>载入为当前数据层</b>」',
        '之后四个模块就用你自己的系数工作了'],
        '<a class="btn" href="#ingest">去数据接入</a>')}
        ${pathCard('C', '要交付给别人', [
        '走完 <a href="#ingest">数据接入</a> → <a href="#intake">准入体检</a> → 各分析模块',
        '到 <a href="#report">⑤ 评估报告</a>，含结论强度、禁止用途、完整数据血缘',
        '「打印 / 导出 PDF」只输出报告正文；也可下载 Markdown 与结果 JSON'],
        '<a class="btn ghost" href="#report">去评估报告</a>')}
      </div>

      <h2 class="sect">六步流程：每步做什么、产出什么</h2>
      <div class="card"><table>
        <thead><tr><th style="width:34px">#</th><th style="width:110px">步骤</th><th>你要做的</th><th>你会得到</th></tr></thead>
        <tbody>
          <tr><td>0</td><td><a href="#ingest">数据接入</a></td>
            <td>导入数据（多文件 / 本机路径），确认字段映射</td>
            <td>数据集概览、形态判定、体检结果；可选：用你的数据重估系数</td></tr>
          <tr><td>1</td><td><a href="#intake">准入体检</a></td>
            <td>回答 7 个问题（或上传 CSV 自动预填）</td>
            <td>能不能做（Go/No-Go）、结论强度上限 A/B/C、预计工期、补数清单</td></tr>
          <tr><td>2</td><td><a href="#impact">冲击评估</a></td>
            <td>拖两个滑杆：暴露强度、事件年份</td>
            <td>逐年影响曲线 + 置信带、本地/邻域分解、均值处边际效应</td></tr>
          <tr><td>3</td><td><a href="#risk">风险归因</a></td>
            <td>填一个门店的参数（或点预设样本）</td>
            <td>逐因子贡献瀑布、全特征 vs 剔除泄漏的保守版本</td></tr>
          <tr><td>4</td><td><a href="#caliber">口径实验室</a></td>
            <td>切换数据集，看不同口径下的差异</td>
            <td>同一方法在不同数据/口径下的 Moran's I 对比</td></tr>
          <tr><td>5</td><td><a href="#report">评估报告</a></td>
            <td>点「生成 / 刷新报告」</td>
            <td>可打印 PDF / 可复制 Markdown / 结果 JSON（带指纹与血缘）</td></tr>
        </tbody></table></div>

      <h2 class="sect">常见问题</h2>
      <div class="card">
        <details class="drill" open><summary>我的数据是很多份文件、字段还不一样，能直接用吗？</summary>
          <div class="body"><p>可以。在<a href="#ingest">数据接入</a>里：</p>
          <ul>
            <li><b>多份文件</b>：多选或拖入整个文件夹，系统按<b>列名并集</b>纵向拼接成一个数据集，缺列留空并登记。</li>
            <li><b>字段不同</b>：角色不靠列名认，而是靠<b>取值分布</b>（年份看值域、坐标看值域且成对、实体看"在期上是否重复"）。
              自动推断只是起点，下面有下拉框可以改，改完点「按当前映射重算」。</li>
            <li><b>想复用</b>：把映射存成模板，下次一键套用。</li>
          </ul></div></details>
        <details class="drill"><summary>我的数据会被上传到服务器吗？</summary>
          <div class="body"><p>不会离开你的机器。服务只监听 <code>127.0.0.1</code>；上传的文件落在临时目录，
            <b>响应结束后立即整目录删除</b>，不持久化。大数据建议直接用「本机路径」模式，连复制都不会发生。</p></div></details>
        <details class="drill"><summary>为什么某个模块显示 ✗（不可用）？</summary>
          <div class="body"><p>能力判定是<b>数据条件的函数</b>，不是开关。例如：</p>
          <ul>
            <li>只有单一年份 → 没有时间维，算不了 TWFE 与事件研究 → 冲击评估 ✗</li>
            <li>没有二元退出/目标列 → 拟合不了 cloglog → 风险归因 ✗</li>
            <li>没有经纬度 → 空间部分跳过（不是错误，是数据没有空间维度）</li>
          </ul>
          <p>产品不会硬套一套不适用的系数，而是<b>明说为什么做不了</b>。</p></div></details>
        <details class="drill"><summary>「结论强度 A / B / C」是什么意思？</summary>
          <div class="body"><p>它是<b>自动判定</b>的，不是手选：由外生性、事件前趋势的 |t|、前趋势与 post 的量级比、
            敏感性是否跑过、是否有时序外推验证共同决定。等级越低，可对外主张的力度越弱。
            工作台、冲击页、报告三处用的是同一个评级器，不会互相矛盾。</p></div></details>
        <details class="drill"><summary>「支撑域」和「止损条件」是什么？</summary>
          <div class="body"><p><b>支撑域</b>：模型只在观测到的暴露强度范围内可信。低于下界的取值是<b>外推</b>，
            页面上会用颜色标出，并单独报「均值处的边际效应」。<br>
            <b>止损条件</b>：写死在评级器里的红线（如事件前趋势已显著、无时序外推验证），
            命中就自动降级或阻断，避免把结论用在它支撑不了的地方。</p></div></details>
        <details class="drill"><summary>为什么模型反复强调「不能预测未来」？</summary>
          <div class="body"><p>因为风险模型用的是随机划分，且存在时序泄漏特征；剔除泄漏后时序外推 AUC ≈ 0.53（接近随机）。
            所以它被定位成<b>归因</b>（解释历史、做情景分析），不是预测器。这是模型的真实状态，不是免责话术。</p></div></details>
        <details class="drill"><summary>怎么把结果交给别人？</summary>
          <div class="body"><ul>
            <li><b>报告</b>：<a href="#report">评估报告</a> →「打印 / 导出 PDF」只输出正文，或「下载 .md」。</li>
            <li><b>数据</b>：同页「下载结果 JSON」，含所用系数与数据层指纹，可交给下游程序。</li>
            <li><b>项目存档</b>：<a href="#workbench">工作台</a> →「导出项目 JSON」，下次「导入项目 JSON」即可恢复全部输入。</li>
          </ul>
          <p>注意：「导出项目 JSON」和「下载结果 JSON」不是一回事，前者才能被导入回来。</p></div></details>
        <details class="drill"><summary>怎么恢复成仓库自带的数据？</summary>
          <div class="body"><p>如果载入过现场重估的数据层，<a href="#workbench">工作台</a>顶部会出现横幅，
            点<b>「恢复仓库产物」</b>即可；也可以回到<a href="#ingest">数据接入</a>重新解析。</p></div></details>
        <details class="drill"><summary>顶部的搜索框能搜什么？</summary>
          <div class="body"><p>搜的是全部页面正文（含帮助页）。试试「准入」「暴露强度」「泄漏」「结论强度」「再配置」。</p></div></details>
      </div>

      <h2 class="sect">术语速查</h2>
      <div class="card"><table>
        <thead><tr><th style="width:150px">术语</th><th>一句话解释</th></tr></thead>
        <tbody>
          <tr><td>暴露强度</td><td>门店被"事件"波及的程度（本项目中是周边同业关闭的环加权和）。</td></tr>
          <tr><td>均值处边际效应</td><td>不引用强度为 0 的外推点，改在实测均值处报效应，避免高估。</td></tr>
          <tr><td>平行趋势</td><td>事件发生前，处理组与对照组的走势是否已经不同；不同则因果主张要打折。</td></tr>
          <tr><td>目标泄漏</td><td>特征里混入了未来信息（如用全期关闭率回填每一年），会让指标虚高。</td></tr>
          <tr><td>口径</td><td>人为设定的定义（距离环、权重、栅格尺度）；换口径结论会不会翻，决定结论稳不稳。</td></tr>
          <tr><td>数据集 / 形态</td><td>由多份文件拼成的一份表；形态指 panel / 事件流 / 横截面 / 边表等结构。</td></tr>
      </tbody></table></div>

      <div class="card">
        <h3>还有问题？</h3>
        <p>方法与边界的完整说明在 <a href="#product">产品说明</a>；
          数据血缘、修补看板与可复现性真实状态在 <a href="#evidence">证据与边界</a>。</p>
      </div>`;
    },
  });

  /* ---------- 产品说明 ---------- */
  PAGES.push({
    id: 'product', name: '产品说明', render() {
      const pr = C.product || {};
      const items = (C.matrix || {}).items || [];
      const sc = C.scenarios || {};
      const mk = C.market || {};
      const tc = C.tech || {};

      const matrix = items.map(it => `<div class="card" style="margin:0">
        <div class="row" style="align-items:center;gap:8px;flex-wrap:wrap"><span class="tag brand">${esc(it.tag)}</span><h3 style="margin:0">${esc(it.name)}</h3><code>${esc(it.sub)}</code></div>
        <p style="margin-top:8px"><b>回答：</b>${esc(it.question)}</p>
        <p><b>使用者：</b>${esc(it.audience)}</p>
        <p class="mini"><b>形态：</b>${esc(it.form || '')}</p>
        ${(it.metrics || []).length ? `<div class="grid g4" style="margin:4px 0 10px">${it.metrics.map(m => stat(m.k, resolveMetric(m.p))).join('')}</div>` : ''}
        <details class="drill"><summary>核心做法</summary><div class="body"><ul>${(it.highlights || []).map(x => `<li>${esc(x)}</li>`).join('')}</ul></div></details>
        <details class="drill"><summary>护栏与限制</summary><div class="body"><ul>${(it.guardrails || []).map(x => `<li>${esc(x)}</li>`).join('')}</ul></div></details>
      </div>`).join('');

      const scen = (sc.items || []).map(x => `<tr><td class="num">${x.rank}</td>
        <td><b>${esc(x.name)}</b><div class="mini">${esc(x.note)}</div></td>
        <td>${esc(x.decision)}</td><td>${esc(x.who)}</td><td>${esc(x.fit)}</td></tr>`).join('');

      const seg = (mk.segments || []).map(x => `<tr><td><b>${esc(x.id)}</b></td><td>${esc(x.name)}</td>
        <td>${esc(x.motive)}</td><td>${esc(x.budget)}</td><td>${esc(x.will)}</td><td>${esc(x.friction)}</td></tr>`).join('');
      const mod = (mk.models || []).map(x => `<tr><td><b>${esc(x.id)}</b></td><td>${esc(x.name)}</td>
        <td>${esc(x.sell)}</td><td>${esc(x.cost)}</td><td>${esc(x.scale)}</td><td>${esc(x.advice)}</td></tr>`).join('');
      const pipe = (tc.pipeline || []).map(x => `<tr><td><code>${esc(x.s)}</code></td><td><b>${esc(x.name)}</b></td><td>${esc(x.do)}</td><td class="mini">${esc(x.out)}</td></tr>`).join('');

      return `
      <div class="page-head"><div class="kicker">PRODUCT</div>
        <h1>${esc(pr.name || '网点决策台')} <span class="mini">${esc(pr.codename || '')}</span></h1>
        <p>${esc(pr.oneLiner || '')}</p>
        <div style="margin-top:8px"><span class="tag brand">${esc(pr.category || '')}</span><span class="tag">${esc(pr.delivery || '')}</span></div>
      </div>

      <div class="card"><p style="font-size:17px;font-weight:600;color:var(--fg);margin:0">${esc(pr.tagline || '')}</p></div>

      <div class="page-head" style="margin-top:20px"><h1 style="font-size:19px">为什么做</h1></div>
      <div class="grid g2">${(pr.whyBuild || []).map(x => `<div class="card" style="margin:0"><h3>${esc(x.title)}</h3><p>${esc(x.body)}</p></div>`).join('')}</div>

      <div class="page-head" style="margin-top:20px"><h1 style="font-size:19px">产品给的四个不一样</h1>
        <p>与"再写一份 BI 报告"的差别在哪 —— 每一条都对应页面里一个具体功能。</p></div>
      <div class="grid g2">${(pr.valueProps || []).map(v => `<div class="card" style="margin:0">
        <h3>${esc(v.h)} <span class="tag ${v.kind === '已验证' ? 'ok' : 'warn'}">${esc(v.kind || '')}</span></h3>
        <p>${esc(v.p)}</p></div>`).join('')}</div>

      <div class="page-head" style="margin-top:20px"><h1 style="font-size:19px">产品矩阵（四个模块）</h1>
        <p>${esc((C.matrix || {}).intro || '')}</p></div>
      <div class="grid g2">${matrix}</div>

      <div class="page-head" style="margin-top:20px"><h1 style="font-size:19px">业务场景</h1><p>${esc(sc.intro || '')}</p></div>
      <div class="card"><table><thead><tr><th class="num">#</th><th>场景</th><th>决策问题</th><th>谁关心</th><th>可行性</th></tr></thead><tbody>${scen}</tbody></table>
        <div class="note warn"><b>为什么这份星级要谨慎引用：</b>可行性星级是「问题同构性」的<b>技术判断</b>，不是客户验证结果。目前没有任何付费客户。</div>
      </div>

      <div class="page-head" style="margin-top:20px"><h1 style="font-size:19px">市场需求与商业模式</h1>
        <p><b>${esc(mk.core || '')}</b> —— ${esc(mk.coreWhy || '')}</p></div>
      <div class="card"><h3>谁会付费</h3><table><thead><tr><th>#</th><th>客群</th><th>付费动机</th><th>预算来源</th><th>意愿</th><th>成交阻力</th></tr></thead><tbody>${seg}</tbody></table></div>
      <div class="card"><h3>商业模式：三级跳</h3><table><thead><tr><th>#</th><th>模式</th><th>卖什么</th><th>启动成本</th><th>可规模化</th><th>建议</th></tr></thead><tbody>${mod}</tbody></table></div>
      <div class="card"><h3>市场规模</h3>
        <div class="note warn">${esc((mk.marketSize || {}).disclaimer || '')}</div>
        <table><thead><tr><th>层级</th><th>定义</th><th>规模</th></tr></thead><tbody>
        ${((mk.marketSize || {}).items || []).map(x => `<tr><td><b>${esc(x.k)}</b></td><td>${esc(x.v)}</td><td><span class="tag warn">${esc(x.s)}</span></td></tr>`).join('')}
        </tbody></table>
        <p>${esc((mk.marketSize || {}).structure || '')}</p></div>
      <div class="card"><h3>竞争与差异化</h3><table><thead><tr><th>对手</th><th>他们做什么</th><th>我们的差异</th></tr></thead><tbody>
        ${(mk.competition || []).map(x => `<tr><td><b>${esc(x.who)}</b></td><td>${esc(x.they)}</td><td>${esc(x.us)}</td></tr>`).join('')}</tbody></table></div>

      <div class="page-head" style="margin-top:20px"><h1 style="font-size:19px">技术方案</h1></div>
      <div class="card"><table><thead><tr><th>#</th><th>阶段</th><th>做什么</th><th>产物</th></tr></thead><tbody>${pipe}</tbody></table></div>
      <div class="card"><h3>工程硬约束</h3><ul>${(tc.constraints || []).map(x => `<li>${esc(x)}</li>`).join('')}</ul>
        <h4>性能与算法取舍</h4><ul>${(tc.perf || []).map(x => `<li>${esc(x)}</li>`).join('')}</ul></div>
      <div class="grid g2">${Object.entries(tc.stack || {}).map(([g, l]) => `<div class="card" style="margin:0"><h3>${esc(g.toUpperCase())}</h3><ul>${l.map(x => `<li>${esc(x)}</li>`).join('')}</ul></div>`).join('')}</div>`;
    },
  });

  /* ---------- 证据与边界 ---------- */
  PAGES.push({
    id: 'evidence', name: '证据与边界', render() {
      const es = (D.impact || {}).event_study || {};
      const tm2e = (es.table || []).find(z => z.tau === -2) || {};
      const preNoteE = (isFinite(tm2e.p) ? '（p=' + Number(tm2e.p).toExponential(2) + '）' : '');
      const pts = (es.table || []).map(r => ({ x: r.tau, y: r.effect, lo: r.effect - 1.96 * (r.se || 0), hi: r.effect + 1.96 * (r.se || 0) }));
      const tauSvg = pts.length ? CH.curve({ points: pts, w: 740, h: 270, marks: [{ x: 0, y: (es.table.find(z => z.tau === 0) || {}).effect, label: 'τ=0', color: 'var(--brand)' }], fmtY: v => (v * 100).toFixed(1) + 'pp', fmtX: v => 'τ=' + v, aria: '事件研究' }) : '<div class="note">数据缺失，已降级。</div>';

      const dss = (D.teaching || {}).datasets || [];
      const moranSvg = dss.length ? CH.vbar({ items: dss.filter(d => d.moran_i != null).map(d => ({ label: d.dataset, value: d.moran_i, sub: nf(d.cells, 0) + ' 格' })), w: 740, h: 230, fmt: v => nf(v, 4), aria: "Moran's I" }) : '<div class="note">数据缺失，已降级。</div>';

      const rk = D.risk || {};
      const shapSvg = (rk.shap || []).length ? CH.hbar({ items: rk.shap.map(s => ({ label: s.feature, value: s.value })), w: 740, labelWidth: 160, fmt: v => nf(v, 4), aria: 'SHAP' }) : '<div class="note">数据缺失，已降级。</div>';

      const rs = C.risks || {};
      const risks = (rs.items || []).map(r => `<div class="risk-item lv-${esc(r.level)}">
        <div class="t"><span class="tag ${r.level === '高' ? 'danger' : r.level === '中' ? 'warn' : 'ok'}">${esc(r.cat)} · ${esc(r.level)}</span> ${esc(r.title)}</div>
        <div class="b">${esc(r.body)}</div><div class="m"><b>应对：</b>${esc(r.mitigate)}</div></div>`).join('');

      const autoP = ((D.audit || {}).patches) || {};
      const autoCls = (s) => /已修|已补跑|一致|已厘清/.test(s) ? 'ok'
        : /部分/.test(s) ? 'warn' : 'danger';
      const patches = (T.patches || []).map(p => {
        const cls = p.status === '待修' ? 'danger' : p.status === '部分修' ? 'warn' : 'ok';
        const a = autoP[p.id];
        return `<div class="risk-item" style="border-left-color:var(--${cls === 'danger' ? 'danger' : cls === 'warn' ? 'accent' : 'ok'})">
          <div class="t"><code>${esc(p.id)}</code> <span class="tag ${cls}">看板：${esc(p.status)}</span> ${a ? `<span class="tag ${autoCls(a.auto_status)}">实检：${esc(a.auto_status)}</span>` : '<span class="tag warn">实检：无自动核对</span>'} ${esc(p.title)}</div>
          <div class="b"><b>影响：</b>${esc(p.impact)}<br>${esc(p.detail)}${a ? `<br><b>自动核对（由产物反推，不采信文案）：</b>${esc(a.evidence)}` : ''}</div>
          <div class="m"><b>修复方案：</b>${esc(p.fix)}${a ? `<br><span class="mini">核对来源：<code>${esc(a.source || '—')}</code></span>` : ''}</div></div>`;
      }).join('');
      const wtc = ((D.audit || {}).wtreat_consistency) || null;

      const prov = ((D.meta || {}).provenance || []);
      const provRows = prov.slice(0, 14).map(x => `<tr><td class="mini"><code>${esc(x.file)}</code></td><td class="num mini">${nf(x.bytes / 1024, 1)} KB</td><td class="mini">${esc(String(x.mtime).replace('T', ' '))}</td></tr>`).join('');

      const tw = (D.impact || {}).twfe || {}, slx = ((D.impact || {}).spatial || {}).slx || {};
      const rt = rk.test || {}, clog = rk.cloglog || {};

      return `
      <div class="page-head"><div class="kicker">EVIDENCE &amp; LIMITS</div>
        <h1>证据与边界</h1>
        <p>每个数字都能追到仓库内的产物文件；每一处已知缺陷都公开在案。这一页是产品的信任基础，不是免责声明。</p></div>

      <div class="grid g4">
        ${stat('TWFE 平均效应', fmtPct(tw.post), 'p = ' + fmtNum(tw.post_p, 6))}
        ${stat('事件研究 τ=0', fmtPct((es.table || []).find(z => z.tau === 0) ? (es.table.find(z => z.tau === 0) || {}).effect : null), '|t| 前趋势 ' + fmtNum(es.pre_trend_max_abs_t, 2))}
        ${stat('SLX 邻域效应', fmtPct(slx.spillover), 'p = ' + fmtNum(slx.spillover_p, 4))}
        ${stat('风险模型 AUC', rt.auc == null ? null : nf(rt.auc, 4), 'C-index ' + nf(rt.c_index, 4))}
        ${stat('cloglog 伪 R²', clog.pseudo_r2 == null ? null : nf(clog.pseudo_r2, 4), 'n = ' + nf(clog.n, 0))}
        ${stat('残差 Moran\'s I', (rk.moran || {}).moran_i == null ? null : nf(rk.moran.moran_i, 4), 'p = ' + ((rk.moran || {}).p_value))}
        ${stat('SDK / 用例', (D.datakit || {}).src_lines + ' 行', (D.datakit || {}).module_count + ' 模块 / ' + (D.datakit || {}).test_cases + ' 用例')}
        ${stat('阶段实例', (D.meta || {}).stage_instance_total, '三个项目合计')}
      </div>

      <div class="grid g2" style="margin-top:14px">
        ${figure('事件研究：效应何时出现、逐年多深', 'τ=−2 显著为负' + preNoteE + ' → 平行趋势不完美，故结论降格为关联级', tauSvg)}
        ${figure("跨数据集 Moran's I", '同一方法在稀疏与密集数据上相差数十倍 → 空间结论强依赖数据分布与口径', moranSvg)}
      </div>
      <div style="margin-top:14px">${figure('SHAP 特征重要性（风险模型）', 'year 与 bank_closed_rate 远超其余；age（网点年龄）排名最后 → 「老网点更容易死」在本数据上几乎不成立', shapSvg)}</div>

      <div class="page-head" style="margin-top:22px"><div class="kicker">PATCH BOARD</div>
        <h1 style="font-size:19px">已知缺陷与修补看板</h1>
        <p>这些不是"以后再说"的待办，而是会影响结论解读的实质问题。产品选择公开它们，并在受影响的模块中强制披露。</p>
        <p class="mini">每条都带两个状态：<b>看板</b>是人工登记，<b>实检</b>由 <code>portal/audit/*.py</code> 重跑后的产物反推 —— 两者不一致时以实检为准，避免「看板说待修、实际已修」。</p></div>
      <div class="card">${patches}</div>

      ${wtc ? `<div class="card" style="margin-top:14px">
        <h3>上游产物内部一致性核对：${esc(wtc.quantity)}</h3>
        <div class="note ${wtc.consistent ? '' : 'danger'}">${wtc.consistent
          ? `<b>四处产物 + 正文取值一致：${wtc.authoritative}</b>（权威来源 <code>${esc(wtc.authoritative_source)}</code>）。`
          : `<b>发现 ${(wtc.mismatches || []).length} 处不一致：</b>${esc((wtc.mismatches || []).map(m => m.where + ' = ' + m.value).join('、'))}，而权威值（${esc(wtc.authoritative_source)}）是 <b>${wtc.authoritative}</b>。`}</div>
        ${wtc.consistent ? '' : `<p class="mini"><b>可能成因：</b>${esc(wtc.probable_cause || '')}</p>`}
        <p class="mini">参照值：OLS 的 <code>treat_strength</code> = ${wtc.ols_treat_strength_for_reference}（混合值，与 SLX 邻域溢出不是同一个量）。</p>
        <p class="mini">核对方式：每次重建数据层自动重扫这几处产物与正文字面值（正文容差 ±0.2%，因为印刷会四舍五入）。${esc(wtc.fix_note || '')}</p>
      </div>` : ''}

      ${((D.audit || {}).full_chain) ? `<div class="card" style="margin-top:14px">
        <h3>原始数据全链路重建核对（P0-5）</h3>
        <div class="note ${D.audit.full_chain.verdict === '通过' ? '' : 'danger'}"><b>${esc(D.audit.full_chain.verdict)}</b>：${esc(D.audit.full_chain.conclusion || '')}</div>
        <div class="grid g4" style="margin-top:8px">
          ${stat('对拍项通过', D.audit.full_chain.checks_passed + ' / ' + D.audit.full_chain.checks_total)}
          ${stat('原始文件', nf((D.audit.full_chain.protocol || {}).raw_files, 0) + ' 个')}
          ${stat('重建耗时', fmtNum((D.audit.full_chain.protocol || {}).elapsed_minutes, 1) + ' 分钟')}
          ${stat('did_panel 行数差', nf(Math.abs(((((D.audit.full_chain.headline || {}).did_panel_rows) || {}).upstream || 0) - ((((D.audit.full_chain.headline || {}).did_panel_rows) || {}).sandbox || 0)), 0))}
        </div>
        <div class="mini">方式：把阶段入口复制到隔离沙箱、<code>source_root</code> 指向真实只读源数据，然后<b>真实执行上游 01→06 的代码</b> —— 逻辑与上游逐字一致，产物只落沙箱，<b>上游文件不被写入</b>。随后逐阶段对拍行数与关键数值列的最大绝对差。</div>
        <table style="margin-top:8px"><thead><tr><th>对拍项</th><th class="num">上游行数</th><th class="num">沙箱行数</th><th class="num">最大绝对差</th><th>结论</th></tr></thead><tbody>
        ${(D.audit.full_chain.checks || []).map(c => {
          const r = c.rows || {};
          const d = c.max_abs_diff || {};
          const dv = Object.keys(d).length
            ? Object.keys(d).map(k => k + '=' + (d[k] === null ? '—' : d[k])).join(' / ') : '—';
          return `<tr><td>${esc(c.label)}</td><td class="num">${r.upstream != null ? nf(r.upstream, 0) : '—'}</td><td class="num">${r.sandbox != null ? nf(r.sandbox, 0) : '—'}</td><td class="num">${esc(dv)}</td><td>${c.ok ? '<span class="tag ok">通过</span>' : '<span class="tag danger">' + esc(c.error || '不通过') + '</span>'}</td></tr>`;
        }).join('')}
        </tbody></table>
      </div>` : ''}

      <div class="page-head" style="margin-top:22px"><div class="kicker">RISKS</div><h1 style="font-size:19px">风险与限制清单</h1>
        <p>${esc(rs.lead || '')}</p></div>
      <div class="card">${risks}</div>

      <div class="page-head" style="margin-top:22px"><div class="kicker">REPRODUCIBILITY</div><h1 style="font-size:19px">可复现性：真实状态</h1></div>
      <div class="card">
        <div class="note danger"><b>必须说清的现状：</b>仓库当前不含 <code>.git</code>；<code>replication_manifest</code> 记录的是绝对路径
          <code>E:\\...</code>；<code>logit_pipeline.pkl</code> 与样本级 CSV 受 <code>.gitignore</code> 约束不入库。
          因此「git clone 后重跑出同样的数」这句承诺<b>在当前状态下不可验证</b>。</div>
        <h4>本产品做得到的部分</h4>
        <ul>
          <li>页面上的每个数字都由 <code>build_data.py</code> 从入库产物抽取，缺失即显示「缺失 · 已降级」；</li>
          <li>已登记的产物血缘共 ${prov.length} 个文件，下表列出前 14 个（名称 / 体积 / 修改时间）；</li>
          <li>源数据（FDIC 1.58 GB、教学 31.1 GB）不在版本库内 —— 完整复现需自备源数据并重跑对应阶段。</li>
        </ul>
        <table><thead><tr><th>产物文件</th><th class="num">体积</th><th>修改时间</th></tr></thead><tbody>${provRows}</tbody></table>
        <h4>重建命令</h4>
        <pre class="code">./.venv/Scripts/python.exe portal/build_data.py     # 重建事实层
node --test portal/tests/engines.test.js            # 引擎单测（数量以命令输出为准）
./.venv/Scripts/python.exe portal/serve.py          # 可选：本地服务（上传数据体检）</pre>
      </div>`;
    },
  });

  /* ---------- 关于 ---------- */
  PAGES.push({
    id: 'about', name: '关于', render() {
      const dv = C.developer || {};
      const faq = C.faq || [];
      const cats = ['全部'].concat(Array.from(new Set(faq.map(x => x.cat))));
      return `
      <div class="page-head"><div class="kicker">ABOUT</div><h1>关于这个产品与开发者</h1></div>

      <div class="card">
        <h3>我的角色</h3>
        <p><b>${esc(dv.role || '')}</b></p>
        <p>${esc(dv.scope || '')}</p>
        <h4>业务理解（技术之外的判断）</h4>
        <ul>${(dv.businessUnderstanding || []).map(x => `<li>${esc(x)}</li>`).join('')}</ul>
      </div>

      <div class="card">
        <h3>十个关键决策（含主动放弃的部分）</h3>
        ${(dv.decisions || []).map((x, i) => `<details class="drill" ${i === 0 ? 'open' : ''}>
          <summary>${esc(x.q)}</summary><div class="body"><p>${esc(x.a)}</p></div></details>`).join('')}
      </div>

      <div class="page-head" style="margin-top:20px"><div class="kicker">Q&amp;A</div><h1 style="font-size:19px">面试 / 评审问答</h1>
        <p>按最可能被追问的顺序组织：为什么做 → 有什么用 → 市场需求 → 有哪些业务 → 存在哪些问题 → 你起了什么作用。</p></div>
      <div class="filters" id="faqFilters">${cats.map((c, i) => `<button class="chip ${i === 0 ? 'on' : ''}" data-cat="${esc(c)}">${esc(c)}</button>`).join('')}</div>
      <div class="card" id="faqList">
        ${faq.map(x => `<div class="risk-item" data-cat="${esc(x.cat)}" style="border-left-color:var(--brand)">
          <div class="t"><span class="tag brand">${esc(x.cat)}</span> ${esc(x.q)}</div>
          <div class="b">${esc(x.a)}</div></div>`).join('')}
      </div>

      <div class="card">
        <h3>变更日志</h3>
        ${(T.changelog || []).map(c => `<div style="margin-bottom:12px"><b>${esc(c.v)}</b> <span class="mini">${esc(c.d)}</span>
          <ul>${(c.items || []).map(i => `<li>${esc(i)}</li>`).join('')}</ul></div>`).join('')}
      </div>

      <div class="card">
        <h3>术语表</h3>
        <table><thead><tr><th>术语</th><th>含义</th></tr></thead><tbody>
        ${(C.glossary || []).map(g => `<tr><td><b>${esc(g.t)}</b></td><td>${esc(g.d)}</td></tr>`).join('')}</tbody></table>
      </div>

      <div class="card">
        <h3>引擎自检</h3>
        <p>计算引擎自带单元测试，覆盖数值正确性（正态近似、cloglog 链接、零交叉点、边际效应标准误对拍）、
          护栏行为（一票否决、适用域拒绝、退化类别拒绝、外生性三态）与报告生成（含缺章降级路径）。
          数量以命令输出为准，不在页面上写死。</p>
        <pre class="code">node --test portal/tests/engines.test.js</pre>
      </div>`;
    },
    bind() {
      const fb = document.getElementById('faqFilters'), lb = document.getElementById('faqList');
      if (!fb || !lb) return;
      fb.addEventListener('click', ev => {
        const btn = ev.target.closest('.chip'); if (!btn) return;
        $$('.chip', fb).forEach(c => c.classList.toggle('on', c === btn));
        const cat = btn.dataset.cat;
        $$('[data-cat]', lb).forEach(it => { it.style.display = (cat === '全部' || it.dataset.cat === cat) ? '' : 'none'; });
      });
    },
  });

  /* ================================================================== *
   * 3. 渲染结果（仅重绘结果区，保留表单状态）
   * ================================================================== */
  function paint() {
    const p = Store.load();
    const cur = current();

    if (cur === 'intake') {
      const box = document.getElementById('intakeResult');
      if (!box) return;
      const a = p.intakeAnswers || {};
      const ans = {
        stableId: a.stableId,
        idMatchRate: a.idMatchRate,
        coordNullRate: a.coordNullRate,
        outcomeLevel: a.outcomeLevel,
        years: a.years,
        eventDefined: a.eventDefined,
        exogenous: toExo(a.exogenous),
      };
      const untouched = Object.keys(a).length === 0;
      if (untouched) {
        box.innerHTML = `<div class="card"><div class="note">尚未填写问卷。填完后这里会实时给出可行性判定、一票否决项与工期估算。</div></div>`;
        return;
      }
      const r = E.intake(ans);
      const verdict = r.hardFail
        ? '<span class="tag danger">未通过 · 存在一票否决项</span>'
        : r.go ? '<span class="tag ok">通过 · 可进入建模</span>' : '<span class="tag warn">有条件通过 · 需先补数</span>';
      box.innerHTML = `
        <div class="card">
          <h3>体检结论</h3>
          <div style="margin-bottom:10px">${verdict} ${r.ceiling ? `<span class="tag brand">结论强度上限 ${esc(r.ceiling)} 级</span>` : ''}</div>
          <div class="grid g4">
            ${stat('综合评分', (r.scorePct * 100).toFixed(0) + ' / 100')}
            ${stat('预估工期', r.weeks[0] + '–' + r.weeks[1] + ' 周', '五层工作量合计')}
            ${stat('一票否决项', r.blockers.length + ' 项', r.blockers.length ? '必须先解决' : '无', r.blockers.length ? 'neg' : 'pos')}
            ${stat('需补数据缺口', r.gaps.length + ' 项')}
          </div>
          ${r.blockers.length ? `<div class="note danger"><b>一票否决项：</b><ul>${r.blockers.map(x => `<li>${esc(x)}</li>`).join('')}</ul></div>` : ''}
          ${r.gaps.length ? `<div class="note warn"><b>数据缺口：</b><ul>${r.gaps.map(x => `<li>${esc(x)}</li>`).join('')}</ul></div>` : ''}
          ${r.notes.length ? `<div class="note"><b>工期与方案调整说明：</b><ul>${r.notes.map(x => `<li>${esc(x)}</li>`).join('')}</ul></div>` : ''}
          <div class="note"><b>结论强度判定依据：</b><ul>${(computeGrade(p).reasons || []).map(x => `<li>${esc(x)}</li>`).join('')}</ul></div>
          ${sourceBlock(r.source)}
          ${caveatBlock(r.caveats, '使用边界')}
          <div style="margin-top:10px"><a class="btn" href="#report">生成评估报告 →</a></div>
        </div>`;
      return;
    }

    if (cur === 'impact') {
      const box = document.getElementById('impactResult');
      if (!box) return;
      const ip = p.impactInput || {};
      const r = E.impact({ strength: ip.strength, eventYear: ip.eventYear }, D,
        { exogenous: toExo((p.intakeAnswers || {}).exogenous) });
      if (!r.ok) { box.innerHTML = `<div class="card"><div class="note danger">${esc(r.reason)}</div></div>`; return; }

      // τ 曲线
      const tauPts = r.byTau.map(x => ({ x: x.tau, y: x.effect, lo: x.lo, hi: x.hi }));
      const tauSvg = CH.curve({
        points: tauPts, w: 760, h: 290, marks: [{ x: 0, y: (r.byTau.find(z => z.tau === 0) || {}).effect, label: 'τ=0', color: 'var(--brand)' }],
        fmtY: v => (v * 100).toFixed(1) + 'pp', fmtX: v => 'τ=' + v,
        xLabel: '事件相对年份 τ（基线 τ=−1）', yLabel: '对结果变量的影响', aria: '事件研究动态效应',
      });
      const tm2row = r.byTau.find(z => z.tau === -2) || {};
      const preNote = (isFinite(tm2row.p) ? 'τ=−2 显著为负（p=' + Number(tm2row.p).toExponential(2) + '）' : 'τ=−2 显著为负')
        + ' → 平行趋势不完美，故结论降格为关联级';
      // 强度曲线：由引擎生成，视图层不再复算 SE 公式（避免口径漂移）
      const sPts = (r.curve || []).map(pt => ({ x: pt.x, y: pt.y, lo: pt.lo, hi: pt.hi }));
      const sSvg = CH.curve({
        points: sPts, w: 760, h: 290,
        bands: [{ from: r.supportLowerBound, to: 5, label: '观测支撑域（强度 ≥ ' + r.supportLowerBound.toFixed(2) + '）', color: 'var(--ok)' }],
        marks: [{ x: ip.strength, y: r.marginal.atInput.effect, label: '你的输入', color: 'var(--accent)' }]
          .concat(isFinite(r.marginal.zeroCross) && r.marginal.zeroCross > 0 && r.marginal.zeroCross <= 5
            ? [{ x: r.marginal.zeroCross, y: 0, label: '由负转正', color: 'var(--danger)' }] : []),
        fmtY: v => (v * 100).toFixed(1) + 'pp', xLabel: '暴露强度 s', yLabel: '效应 Δ(s)', aria: '效应随暴露强度的变化',
      });
      const decItems = [
        { label: 'SLX 本地效应', value: r.spatial.direct, lo: r.spatial.direct - 1.96 * (r.spatial.directSe || 0), hi: r.spatial.direct + 1.96 * (r.spatial.directSe || 0) },
        { label: 'SLX 邻域效应 W·X', value: r.spatial.spillover, lo: r.spatial.spillover - 1.96 * (r.spatial.spilloverSe || 0), hi: r.spatial.spillover + 1.96 * (r.spatial.spilloverSe || 0) },
      ].filter(x => x.value != null);
      const decSvg = decItems.length ? CH.hbar({ items: decItems, w: 720, labelWidth: 150, fmt: v => (v * 100).toFixed(2), suffix: 'pp', zeroBased: false, axisNote: '误差线 = ±1.96·SE', aria: '空间效应分解' })
        : '<div class="note">数据缺失，已降级。</div>';
      const at = r.marginal.atInput;

      box.innerHTML = `
        <div class="card">
          <h3>点估计</h3>
          <div class="grid g4">
            ${stat('强度 ' + nf(ip.strength, 2) + ' 处效应', fmtPct(at.effect), '95% 近似区间 [' + fmtPct(at.ci.lo) + ', ' + fmtPct(at.ci.hi) + ']', at.effect < 0 ? 'neg' : 'pos')}
            ${stat('τ=0 效应', fmtPct((r.byTau.find(z => z.tau === 0) || {}).effect), 'p = ' + fmtNum((r.byTau.find(z => z.tau === 0) || {}).p, 6))}
            ${stat('τ=4 效应', fmtPct((r.byTau.find(z => z.tau === 4) || {}).effect), '第 4 年最深')}
            ${stat('事件前最大 |t|', fmtNum(r.eventStudyMeta.preTrendMaxAbsT, 2), '< 1.96 才算平行趋势可接受', r.eventStudyMeta.preTrendMaxAbsT >= 1.96 ? 'neg' : 'pos')}
            ${r.marginal.atMean ? stat('处理组均值强度 ' + nf((r.support.branch_level || {}).mean, 2) + ' 处效应', fmtPct(r.marginal.atMean.effect), '95% 近似区间 [' + fmtPct(r.marginal.atMean.ci.lo) + ', ' + fmtPct(r.marginal.atMean.ci.hi) + ']；这才是"典型网点"的效应', r.marginal.atMean.effect < 0 ? 'neg' : 'pos') : ''}
          </div>
          <div style="margin-top:10px">${gradeBadge(computeGrade(p))}</div>
          <div class="mini" style="margin-top:6px">该等级与工作台、评估报告同源（同一评级器 + 同一事件研究产物），三处必须一致。</div>
          <div class="mini" style="margin-top:6px">区间为近似值（忽略 β_post 与交互项协方差）；同号最坏情况区间为 [${fmtPct(at.ciWorst.lo)}, ${fmtPct(at.ciWorst.hi)}]，对外引用时以更宽者为准。</div>
          ${ip.strength != null && ip.strength < r.supportLowerBound
            ? `<div class="note danger"><b>你输入的强度落在外推区：</b>强度 ${nf(ip.strength, 2)} 小于实测处理组下界 ${r.supportLowerBound}（网点级 strength_t0 最小值，审计复算与上游逐网点一致）。该点未被观测，结果不可直接引用。</div>`
            : `<div class="note"><b>你输入的强度位于观测支撑域内</b>（实测下界 ${r.supportLowerBound}${r.supportMeasured ? '，均值 ' + nf((r.support.branch_level || {}).mean, 3) + '，中位 ' + (r.support.branch_level || {}).median + '，最大 ' + (r.support.branch_level || {}).max : ''}）。</div>`}
        </div>

        <div class="grid g2" style="margin-top:14px">
          ${figure('① 事件后逐年动态效应', '平均处理效应，阴影为 ±1.96·SE；' + preNote, tauSvg)}
          ${figure('② 效应随暴露强度的变化', '绿色为观测支撑域；请只在支撑域内解读。β_post 单独引用会高估效应', sSvg)}
        </div>

        <div class="card" style="margin-top:14px">
          <h3>逐 τ 明细</h3>
          <table><thead><tr><th class="num">τ</th><th class="num">效应</th><th class="num">标准误</th><th class="num">p 值</th><th>含义</th></tr></thead><tbody>
          ${r.byTau.map(x => `<tr><td class="num">τ=${x.tau}</td><td class="num">${fmtPct(x.effect)}</td>
            <td class="num">${x.se == null ? '—' : fmtPct(x.se)}</td><td class="num">${fmtNum(x.p, 6)}</td>
            <td>${x.tau < 0 ? '<span class="tag warn">事前（应≈0）</span>' : '<span class="tag brand">事后动态</span>'}</td></tr>`).join('')}
          </tbody></table></div>

        <div class="card" style="margin-top:14px">
          <h3>空间分解：本地被吸走，邻域补回</h3>
          ${decSvg}
          <table style="margin-top:10px"><thead><tr><th>项</th><th class="num">系数</th><th class="num">p 值</th><th>解读</th></tr></thead><tbody>
            <tr><td>SLX 本地效应</td><td class="num">${fmtPct(r.spatial.direct)}</td><td class="num">${fmtNum(r.spatial.directP, 4)}</td><td>显著为负 → <b>本地被吸走</b></td></tr>
            <tr><td>SLX 邻域效应 W·X</td><td class="num">${fmtPct(r.spatial.spillover)}</td><td class="num">${fmtNum(r.spatial.spilloverP, 4)}</td><td>显著为正 → <b>邻域补回</b></td></tr>
          </tbody></table>
          <div class="note">两者方向相反 → 结果是<b>再配置</b>而非区域净增。只看聚合值会得出相反结论，这是本产品最核心的一条判读。</div>
        </div>

        ${r.cellEq ? `<div class="card" style="margin-top:14px">
          <h3>格级方程（唯一可直接代入的多元回归式）</h3>
          <p><code>cell_growth = ${(r.cellEq.terms.find(t => t.name === 'const') || {}).coef.toFixed(6)}
            ${r.cellEq.terms.filter(t => t.name !== 'const').map(t => `+ (${t.coef.toFixed(6)}) × ${esc(t.name)}`).join(' ')}</code></p>
          <div class="mini">n = ${nf(r.cellEq.n, 0)}，R² = ${fmtNum(r.cellEq.r2, 4)}（空间截面样本）</div>
          <div class="note warn"><b>口径提醒：</b>这里的 treat_strength 是 OLS 混合值（${fmtNum((r.cellEq.terms.find(t => t.name === 'treat_strength') || {}).coef, 6)}），与上方 SLX 拆出的本地效应（${fmtPct(r.spatial.direct)}）口径不同、符号可相反 —— 两者不可混用，也不可互相印证。</div>
        </div>` : ''}

        ${r.ringsSensitivity ? `<div class="card" style="margin-top:14px">
          <h3>距离环口径敏感性（已重跑，替代此前「只有标签、没有系数」）</h3>
          <p class="mini">同一套 DID 设定，只换距离环定义，检验结论是否依赖细环选择。细环 = 上游代码口径；两个合并环变体为本次审计新增。</p>
          <table><thead><tr><th>口径</th><th>距离环（km）</th><th>β_int</th><th>SE</th><th>p</th></tr></thead><tbody>
          ${[['fine', '细环（上游）'], ['coarse_rebin', '合并环 · 沿用权重值'], ['coarse_linear', '合并环 · 等差衰减']]
            .filter(([k]) => r.ringsSensitivity[k]).map(([k, label]) => {
              const v = r.ringsSensitivity[k];
              return `<tr><td>${esc(label)}</td><td>${(v.rings || []).map(z => z[0] + '–' + z[1]).join(' / ')}</td><td>${fmtNum(v.coef, 6)}</td><td>${fmtNum(v.se, 6)}</td><td>${fmtNum(v.p, 3)}</td></tr>`;
            }).join('')}
          </tbody></table>
          ${r.ringsCross ? `<div class="note"><b>跨口径可比性：</b>合并环改变了强度刻度（均值 ${nf((r.ringsSensitivity.fine || {}).strength_mean_treated, 3)} → ${nf((r.ringsSensitivity.coarse_rebin || {}).strength_mean_treated, 3)}），因此不能直接比 β_int。按「单位相对暴露的斜率」与「均值处效应」比较：斜率差异 ${fmtNum(r.ringsCross.slope_spread_pct, 1)}%、均值处效应差异 ${fmtNum(r.ringsCross.effect_at_mean_spread_pp, 2)}pp → ${esc(r.ringsCross.verdict || '')}</div>` : ''}
          <div class="mini">来源：${esc(r.ringsSource || 'portal/audit/p1_strength_rings.json')}；复现校准：与上游 did_panel.parquet 逐网点最大绝对差 ${fmtNum((((D.impact.strength_disclosure || {}).replication_check) || {}).strength_t0_max_abs_diff, 0)}。</div>
        </div>` : ''}

        <div class="card" style="margin-top:14px">
          <h3>精度折扣</h3>
          ${r.precision ? `<div class="note ${r.precision.tier === '低' ? 'warn' : ''}">
            <b>${esc(String(ip.eventYear))} 年事件 → 坐标精度等级：${esc(r.precision.tier)}</b>（${esc(r.precision.note)}）
          </div>` : '<div class="note">未指定事件年份，无法给出精度折扣。</div>'}
        </div>

        <div class="card" style="margin-top:14px">
          <h3>禁止用途</h3>
          <ul>${((T.impact || {}).guards || []).map(x => `<li>${esc(x)}</li>`).join('')}</ul>
        </div>
        ${caveatBlock(r.caveats, '使用边界（本模块强制披露）')}
        ${sourceBlock(r.source)}`;
      return;
    }

    if (cur === 'risk') {
      const box = document.getElementById('riskResult');
      if (!box) return;
      const ri = p.riskInput;
      if (!ri || !ri.year) {
        box.innerHTML = `<div class="card"><div class="note">调整上面的参数后，这里会实时给出归因结果。</div></div>`;
        return;
      }
      const r = E.risk({
        age: ri.age, log_depsumbr: Math.log1p(ri.deposit || 0), neighbor_count: ri.neighbor,
        lat: ri.lat, lng: ri.lng, bank_closed_rate: ri.bankClosedRate,
        year: ri.year, bkclass: ri.bkclass, fragility: ri.fragility,
      }, D);
      if (!r.ok) {
        box.innerHTML = `<div class="card"><h3>拒绝打分</h3>
          <div class="note danger"><b>${esc(r.reason)}</b>${r.detail ? `<br>${esc(r.detail)}` : ''}</div>
          <div class="note">这是护栏而不是缺陷：给出一个看似合理的错数，比拒绝服务危险得多。</div></div>`;
        return;
      }
      const items = r.contributions.filter(x => x.kind === 'numeric' || x.kind === 'categorical')
        .map(x => ({ label: x.name, value: x.value }))
        .sort((a, b) => Math.abs(b.value) - Math.abs(a.value));
      const wfSvg = CH.hbar({ items, w: 720, labelWidth: 190, fmt: v => nf(v, 3), zeroBased: true, axisNote: '贡献 = 系数 × 输入值（线性预测器尺度）', aria: '因子贡献' });
      const ratio = r.hazard > 0 ? (r.hazardConservative / r.hazard) : null;

      box.innerHTML = `
        <div class="card">
          <h3>结果</h3>
          <div class="grid g4">
            ${stat('线性预测器 η', fmtNum(r.eta, 4))}
            ${stat('全特征风险', (r.hazard * 100).toFixed(2) + '%', 'cloglog：1 − exp(−exp(η))')}
            ${stat('剔除泄漏特征后', (r.hazardConservative * 100).toFixed(2) + '%', ratio == null ? '' : '全特征的 ' + (ratio * 100).toFixed(0) + '%')}
            ${stat('截距（基线）', fmtNum(r.contributions[0] ? r.contributions[0].value : null, 4), '全特征取基准组时')}
          </div>
          <div class="note warn"><b>这两个数必须一起看。</b>全特征版本包含了存在目标泄漏的
            <code>${esc((r.leakageKeys || []).join('、'))}</code>，会系统性抬高风险；
            剔除后的保守值更接近"不含未来信息"的排序，但<b>它不是重新拟合的概率</b>，只能用于相对排序。</div>
          <div style="margin-top:8px">${gradeBadge(r.grade)}</div>
        </div>

        ${(D.risk.out_of_time && D.risk.out_of_time.conclusion) ? `<div class="card" style="margin-top:14px">
          <h3>时序外推验证（替代随机划分的乐观值）</h3>
          <div class="grid g4">
            ${stat('随机划分 AUC', fmtNum(D.risk.model_card.random_split_test_auc, 4), '原报告口径（测试集含训练期年份）')}
            ${stat('时序外推 AUC · 含泄漏', fmtNum(D.risk.model_card.out_of_time_auc_with_leak, 4), '滚动一步外推的窗口均值')}
            ${stat('时序外推 AUC · 剔泄漏', fmtNum(D.risk.model_card.out_of_time_auc_no_leak, 4), '≈随机 → 无时序判别力', 'neg')}
            ${stat('覆盖窗口', nf(((D.risk.out_of_time.conclusion.windows || {}).n), 0) + ' 个', (((D.risk.out_of_time.conclusion.windows || {}).years) || []).join('–'))}
          </div>
          <div class="note danger"><b>${esc((D.risk.out_of_time.conclusion || {}).headline || '')}</b></div>
          <div class="mini">协议：${esc(((D.risk.out_of_time.protocol || {}).type) || '')}；训练样本 ${esc(((D.risk.out_of_time.protocol || {}).train_sample) || '')}；测试 ${esc(((D.risk.out_of_time.protocol || {}).test_sample) || '')}</div>
          <div class="mini">${esc(((D.risk.out_of_time.protocol || {}).year_dummies) || '')}</div>
          <div class="mini">来源：<code>${esc(D.risk.audit_source || 'portal/audit/p2_out_of_time.json')}</code></div>
        </div>` : ''}

        <div class="card" style="margin-top:14px">
          <h3>因子贡献（谁在推动风险）</h3>
          ${wfSvg}
          <table style="margin-top:10px"><thead><tr><th>因子</th><th class="num">输入</th><th class="num">系数</th><th class="num">贡献</th></tr></thead><tbody>
          ${r.contributions.map(c => `<tr><td>${esc(c.name)}</td>
            <td class="num">${c.input == null ? '—' : (isFinite(c.input) ? Number(c.input).toFixed(4) : '—')}</td>
            <td class="num">${c.coef == null ? '—' : fmtNum(c.coef, 6)}</td>
            <td class="num">${fmtNum(c.value, 4)}</td></tr>`).join('')}
          </tbody></table>
          <div class="mini" style="margin-top:6px">基准组（未出现在系数表中的类别）系数按 0 处理；贡献之和等于 η。</div>
        </div>

        <div class="card" style="margin-top:14px">
          <h3>模型卡</h3>
          <table><tbody>
            <tr><td>模型</td><td>离散时间生存 · cloglog（GLM，样本 ${nf((((D.risk || {}).cloglog) || {}).n, 0)}，含全部事件）</td></tr>
            <tr><td>伪 R²</td><td>${fmtNum((((D.risk || {}).cloglog) || {}).pseudo_r2, 4)}</td></tr>
            <tr><td>测试集指标</td><td>AUC ${nf((((D.risk || {}).test) || {}).auc, 4)} ／ C-index ${nf((((D.risk || {}).test) || {}).c_index, 4)} ／ Brier ${nf((((D.risk || {}).test) || {}).brier, 4)}</td></tr>
            <tr><td>划分方式</td><td>${esc((((D.risk || {}).model_card) || {}).split || '—')}</td></tr>
            <tr><td>时序外推验证</td><td><span class="tag danger">无</span> ${esc((((D.risk || {}).model_card) || {}).out_of_time_note || '')}</td></tr>
            <tr><td>残差空间自相关</td><td>Moran's I = ${fmtNum((((D.risk || {}).moran) || {}).moran_i, 4)}（p = ${((((D.risk || {}).moran) || {}).p_value)}）→ 本地市场因素未进入模型</td></tr>
          </tbody></table>
          <div class="note danger"><b>为什么必须把这些指标和风险值一起看：</b>${esc((((D.risk || {}).model_card) || {}).event_rate_note || '')}</div>
        </div>
        ${caveatBlock(r.caveats, '使用边界（本模块强制披露）')}
        ${sourceBlock(r.source)}`;
      return;
    }

    if (cur === 'caliber') {
      const box = document.getElementById('caliberResult');
      if (!box) return;
      const sel = p.caliberInput || {};
      const r = E.caliber(sel, D);
      if (!r.ok) { box.innerHTML = `<div class="card"><div class="note danger">${esc(r.reason)}</div></div>`; return; }
      const moranSvg = CH.vbar({
        items: r.all.filter(x => x.moran != null).map(x => ({
          label: x.dataset, value: x.moran, sub: nf(x.cells, 0) + ' 格',
          color: x.dataset === r.dataset ? 'var(--brand)' : 'var(--fg-dim)',
        })), w: 720, h: 230, fmt: v => nf(v, 4), aria: "Moran's I 对比",
      });
      const ringSvg = r.rings.length ? CH.vbar({ items: r.rings, w: 720, h: 230, fmt: v => nf(v, 2), aria: '距离环溢出' }) : '';
      const ratio = r.all.length ? (Math.max(...r.all.map(x => x.moran || 0)) / Math.max(1e-9, Math.min(...r.all.filter(x => x.moran != null).map(x => x.moran)))) : null;

      box.innerHTML = `
        <div class="card">
          <h3>${esc(r.dataset)} 的实测阶梯</h3>
          <div class="grid g4">
            ${stat('L0 格数（H3 R' + esc(String(r.h3Res)) + '）', nf(r.cells, 0), '原始点 ' + nf(r.points, 0) + ' 个')}
            ${stat('L1 平均邻居数', fmtNum(r.meanNeighbors, 3), '孤岛 ' + nf(r.islands, 0) + ' 个')}
            ${stat("L2 Moran's I", fmtNum(r.moranI, 4), '空间滞后相关系数 ' + fmtNum(r.lagCorr, 4))}
            ${stat('口径敏感度', ratio == null ? null : (ratio).toFixed(0) + '×', '跨数据集 Moran\'s I 最大/最小比')}
          </div>
        </div>

        <div class="grid g2" style="margin-top:14px">
          ${figure("① 换数据集：Moran's I 相差数十倍", '稀疏数据的近邻格错配会显著压低空间自相关——这不是缺陷，而是"空间权重定义决定结论"的活教材', moranSvg)}
          ${r.rings.length ? figure('② 距离环溢出（' + (r.ringBasis === 'density' ? '密度口径' : '求和口径') + '）', esc(r.ringNote || ''), ringSvg) : ''}
        </div>

        <div class="card" style="margin-top:14px">
          <h3>四数据集对照</h3>
          <table><thead><tr><th>数据集</th><th class="num">点数</th><th class="num">格数</th><th class="num">平均邻居</th><th class="num">孤岛数</th><th class="num">Moran's I</th></tr></thead><tbody>
          ${r.all.map(x => `<tr><td><b>${esc(x.dataset)}</b></td><td class="num">${nf(x.points, 0)}</td>
            <td class="num">${nf(x.cells, 0)}</td><td class="num">${fmtNum(x.neighbors, 2)}</td>
            <td class="num">${nf(x.islands, 0)}</td><td class="num">${fmtNum(x.moran, 4)}</td></tr>`).join('')}
          </tbody></table>
        </div>
        ${caveatBlock(r.caveats, '使用边界（含商用许可）')}
        ${sourceBlock(r.source)}`;
      return;
    }
  }

  /* ================================================================== *
   * 4. 路由 / 搜索 / 主题
   * ================================================================== */
  const navEl = document.getElementById('nav');
  const tocEl = document.getElementById('toc');
  const viewEl = document.getElementById('view');
  let _cur = 'workbench';
  const current = () => _cur;

  function render(hash) {
    const id = String(hash || '').replace(/^#/, '') || 'workbench';
    const page = PAGES.find(p => p.id === id) || PAGES[0];
    _cur = page.id;
    viewEl.innerHTML = (FLOW_IDS.indexOf(page.id) >= 0 ? stepBar(page.id) : '') + page.render();
    [navEl, tocEl].forEach(box => $$('a', box).forEach(a => a.classList.toggle('on', a.dataset.id === _cur)));
    window.scrollTo({ top: 0, behavior: 'auto' });
    if (page.bind) page.bind();
    bindStatic();
    document.title = page.name + ' · 网点决策台';
  }

  function bindStatic() {
    $$('[data-goto]').forEach(b => b.addEventListener('click', () => { location.hash = '#' + b.dataset.goto; }));
    $$('[data-print]').forEach(b => b.addEventListener('click', () => {
      document.body.classList.add('print-report');
      const done = () => { document.body.classList.remove('print-report'); window.removeEventListener('afterprint', done); };
      window.addEventListener('afterprint', done);
      setTimeout(done, 30000);           // 兜底：不依赖 afterprint 的浏览器
      window.print();
    }));
    $$('[data-copy]').forEach(b => b.addEventListener('click', () => {
      const t = document.getElementById(b.dataset.copy);
      if (!t) return;
      const txt = t.dataset.raw || t.textContent;
      navigator.clipboard && navigator.clipboard.writeText(txt).then(
        () => { b.textContent = '已复制 ✓'; setTimeout(() => b.textContent = '复制', 1500); },
        () => alert('复制失败，请手动选择文本'));
    }));
    $$('[data-download]').forEach(b => b.addEventListener('click', () => {
      const t = document.getElementById(b.dataset.download);
      if (!t) return;
      download(b.dataset.filename || 'report.md', t.dataset.raw || t.textContent, b.dataset.mime || 'text/markdown');
    }));
  }

  function download(name, text, mime) {
    try {
      const blob = new Blob([text], { type: mime + ';charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = name; document.body.appendChild(a); a.click();
      setTimeout(() => { URL.revokeObjectURL(url); a.remove(); }, 500);
    } catch (e) {
      alert('下载失败（可能是浏览器限制）：' + e.message + '\n可改用「复制」按钮。');
    }
  }

  /* ---- 极简 Markdown → HTML（报告渲染用，先转义再处理） ---- */
  function md2html(md) {
    const lines = String(md).split('\n');
    let out = '', inTbl = false, inList = false, tRowIdx = 0;
    const closeAll = () => { if (inTbl) { out += '</tbody></table>'; inTbl = false; } if (inList) { out += '</ul>'; inList = false; } };
    for (let raw of lines) {
      const line = raw.replace(/\r$/, '');
      if (/^\s*\|/.test(line)) {
        const cells = line.trim().replace(/^\||\|$/g, '').split('|').map(c => c.trim());
        if (/^[\s|:\-]+$/.test(line) && cells.every(c => /^:?-{2,}:?$/.test(c) || c === '')) continue;
        if (!inTbl) { closeAll(); out += '<table><tbody>'; inTbl = true; tRowIdx = 0; }
        const head = tRowIdx === 0 ? 'th' : 'td';
        out += '<tr>' + cells.map(c => `<${head}>${inline(c)}</${head}>`).join('') + '</tr>';
        tRowIdx++;
        continue;
      }
      closeAll();
      const h = line.match(/^(#{1,4})\s+(.*)$/);
      if (h) { out += `<h${h[1].length}>${inline(h[2])}</h${h[1].length}>`; continue; }
      if (/^\s*[-*]\s+/.test(line)) { if (!inList) { out += '<ul>'; inList = true; } out += `<li>${inline(line.replace(/^\s*[-*]\s+/, ''))}</li>`; continue; }
      if (/^\s*>\s?/.test(line)) { out += `<div class="note">${inline(line.replace(/^\s*>\s?/, ''))}</div>`; continue; }
      if (line.trim() === '') continue;
      out += `<p>${inline(line)}</p>`;
    }
    closeAll();
    return out;
  }
  function inline(s) {
    return esc(s)
      .replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>')
      .replace(/`([^`]+)`/g, '<code>$1</code>')
      .replace(/\*([^*]+)\*/g, '<i>$1</i>');
  }

  /* ---- 上传体检 ---- */
  function bindUpload() {
    const st = document.getElementById('upState');
    const btn = document.getElementById('upBtn');
    const box = document.getElementById('upResult');
    if (!st) return;
    let online = false;
    fetch('/api/health').then(r => r.json()).then(h => {
      if (h && h.ok && h.datakit_available) {
        online = true;
        st.innerHTML = `<span class="tag ok">本地服务已连接</span> datakit v${esc(String(h.datakit_version))} · ${esc(String(h.python))}`;
      } else {
        st.innerHTML = `<span class="tag warn">本地服务已连接，但 datakit 不可用</span>`;
      }
    }).catch(() => {
      st.innerHTML = `<span class="tag warn">未检测到本地服务</span> 启动后可用：<code>python portal/serve.py</code>`;
    });

    if (!btn) return;
    btn.addEventListener('click', () => {
      const f = document.getElementById('upFile').files && document.getElementById('upFile').files[0];
      if (!f) { alert('请先选择一个 CSV / TSV 文件'); return; }
      if (!online) { alert('本地服务未启动。请在仓库根运行：\n\n  ./.venv/Scripts/python.exe portal/serve.py'); return; }
      box.innerHTML = '<div class="note">上传中并调用 datakit 体检…（大文件需要几秒）</div>';
      fetch('/api/intake?name=' + encodeURIComponent(f.name), { method: 'POST', body: f })
        .then(r => r.json())
        .then(res => {
          if (!res.ok) { box.innerHTML = `<div class="note danger"><b>体检失败：</b>${esc(res.error || '未知错误')}</div>`; return; }
          const c = res.columns || {};
          const pref = res.suggested_answers || {};
          // 自动预填问卷（不覆盖用户已填的非空项）
          const p = Store.load();
          const next = Object.assign({}, p.intakeAnswers);
          if (next.stableId == null) next.stableId = pref.stableId;
          if (next.coordNullRate == null) next.coordNullRate = pref.coordNullRate;
          if (next.years == null) next.years = pref.years;
          if (next.outcomeLevel == null) next.outcomeLevel = pref.outcomeLevel;
          if (next.idMatchRate == null && pref.idMatchRate != null) next.idMatchRate = pref.idMatchRate;
          p.intakeAnswers = next; Store.save();

          const v = (res.datakit || {}).validation || {};
          box.innerHTML = `
            <div class="note ok"><b>体检完成</b>（文件已删除，未持久化）　
              识别列：id=${esc(String(c.id))}，year=${esc(String(c.year))}，lat=${esc(String(c.lat))}，lon=${esc(String(c.lon))}，value=${esc(String(c.value))}</div>
            <table><thead><tr><th>检查项</th><th>结果</th><th>说明</th></tr></thead><tbody>
              ${(res.health.checks || []).map(x => `<tr>
                <td>${esc(x.title)}</td>
                <td><span class="tag ${x.level === 'ok' ? 'ok' : x.level === 'danger' ? 'danger' : 'warn'}">${esc(x.value)}</span></td>
                <td>${esc(x.note)}${x.action ? `<br><span class="mini">建议：${esc(x.action)}</span>` : ''}</td></tr>`).join('')}
            </tbody></table>
            <h4>datakit 断言校验（可复跑）</h4>
            <div class="mini">通过 ${v.pass_count}/${(v.summary || {}).total} —— 这些断言与 project1 固化的同款口径一致</div>
            <table style="margin-top:6px"><thead><tr><th>断言</th><th>结果</th><th>实测</th></tr></thead><tbody>
              ${(v.checks || []).map(x => `<tr><td>${esc(x.name)}</td>
                <td>${x.passed ? '<span class="tag ok">通过</span>' : '<span class="tag danger">失败</span>'}</td>
                <td class="mini">${esc(x.message || '')}</td></tr>`).join('')}
            </tbody></table>
            <div class="note warn"><b>注意：</b>「实体匹配准确率」无法由单键自动推出（实体不跨全期是正常的开关店行为），需人工二次校验后填写。</div>`;
        })
        .catch(e => { box.innerHTML = `<div class="note danger">请求失败：${esc(e.message)}</div>`; });
    });
  }

  /* ---- 搜索 ---- */
  let INDEX = [];
  function buildIndex() {
    INDEX = [];
    const tmp = document.createElement('div');
    PAGES.forEach(p => {
      try { tmp.innerHTML = p.render(); } catch (e) { return; }
      const txt = (tmp.textContent || '').replace(/\s+/g, ' ').trim();
      const parts = txt.split(/([。！？；])/);
      let buf = '';
      for (let i = 0; i < parts.length; i++) {
        buf += parts[i];
        if (/[。！？；]/.test(parts[i]) || i === parts.length - 1) {
          const s = buf.trim();
          if (s.length > 6) INDEX.push({ page: p.id, name: p.name, text: s });
          buf = '';
        }
      }
      INDEX.push({ page: p.id, name: p.name, text: p.name, isTitle: true });
      INDEX.push({ page: p.id, name: p.name, text: p.id, isTitle: true });
    });
  }

  /* ---- 启动 ---- */
  (function buildNav() {
    const byId = {};
    PAGES.forEach(p => { byId[p.id] = p; });
    const listed = {};
    const sections = NAV_SECTIONS.map(([, ids]) => {
      const items = ids.filter(id => byId[id]);
      if (!items.length) return '';
      return items.map(id => {
        listed[id] = 1;
        return { id, name: byId[id].name };
      });
    }).filter(s => s.length);
    // 兜底：未登记的页面追加到最后一组，避免"加了页面但导航里没有"
    const rest = PAGES.filter(p => !listed[p.id]).map(p => ({ id: p.id, name: p.name }));
    if (rest.length) sections.push(rest);

    navEl.innerHTML = sections.map(sec => sec.map(x =>
      `<a href="#${x.id}" data-id="${x.id}">${esc(x.name)}</a>`).join('')).join('<span class="sep"></span>');
    tocEl.innerHTML = sections.map((sec, i) => {
      const title = NAV_SECTIONS[i] ? NAV_SECTIONS[i][0] : '其他';
      return `<li class="grp">${esc(title)}</li>` + sec.map(x =>
        `<li><a href="#${x.id}" data-id="${x.id}">${esc(x.name)}</a></li>`).join('');
    }).join('');
  })();

  window.addEventListener('hashchange', () => render(location.hash));

  const themeBtn = document.getElementById('themeBtn');
  const savedTheme = localStorage.getItem('sdp-theme');
  if (savedTheme) document.documentElement.dataset.theme = savedTheme;
  themeBtn.addEventListener('click', () => {
    const next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
    document.documentElement.dataset.theme = next;
    localStorage.setItem('sdp-theme', next);
  });
  const tocBtn = document.getElementById('tocBtn');
  tocBtn.addEventListener('click', () => document.getElementById('sidebar').classList.toggle('show'));
  document.getElementById('brand').addEventListener('click', () => { location.hash = '#workbench'; });

  const bar = document.querySelector('#progress i');
  window.addEventListener('scroll', () => {
    const h = document.documentElement;
    bar.style.width = (h.scrollTop / Math.max(1, h.scrollHeight - h.clientHeight) * 100).toFixed(1) + '%';
  }, { passive: true });

  const sInput = document.getElementById('search');
  const sBox = document.getElementById('searchResults');
  function highlight(text, q) {
    const i = text.toLowerCase().indexOf(q.toLowerCase());
    if (i < 0) return esc(text.slice(0, 90));
    const a = Math.max(0, i - 30);
    return esc(text.slice(a, i)) + '<mark>' + esc(text.slice(i, i + q.length)) + '</mark>' + esc(text.slice(i + q.length, i + q.length + 60));
  }
  sInput.addEventListener('input', () => {
    const q = sInput.value.trim();
    if (!q) { sBox.hidden = true; return; }
    const hits = INDEX.filter(x => x.text.toLowerCase().includes(q.toLowerCase())).slice(0, 12);
    sBox.innerHTML = hits.length
      ? hits.map(h => `<div class="sr-item" data-page="${h.page}"><b>${esc(h.name)}${h.isTitle ? ' · 章节' : ''}</b><span>${highlight(h.text, q)}</span></div>`).join('')
      : '<div class="sr-empty">没有命中。试试「准入」「暴露强度」「泄漏」「结论强度」「再配置」。</div>';
    sBox.hidden = false;
  });
  sBox.addEventListener('click', ev => {
    const it = ev.target.closest('.sr-item'); if (!it) return;
    location.hash = '#' + it.dataset.page; sBox.hidden = true; sInput.value = '';
  });
  document.addEventListener('click', ev => { if (!ev.target.closest('.searchbox')) sBox.hidden = true; });

  (function dataState() {
    const miss = D.missing || [];
    const el = document.getElementById('dataState');
    if (!el) return;
    el.textContent = miss.length ? `${miss.length} 项缺失（已降级披露）` : '数据加载正常 · 0 缺失';
    if (miss.length) el.previousElementSibling.classList.add('warn');
    document.getElementById('genAt').textContent = (D.meta || {}).generated_at
      ? '数据层生成：' + String(D.meta.generated_at).replace('T', ' ').slice(0, 19) : '';
    document.getElementById('footMeta').textContent =
      `源数据（1.58 GB / 31.1 GB）不在版本库内：${(D.meta || {}).source_data_note || ''}`;
  })();

  render(location.hash);
  buildIndex();

  window.SDP_APP = { pages: PAGES, render, paint, store: Store, data: D, content: C, tools: T, engine: E };
})();
