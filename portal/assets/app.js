/* ============================================================================
 * 网点决策台 v2 · 应用层
 * 结构：工作台（评估项目）→ ① 准入体检 → ② 冲击评估 → ③ 风险归因
 *       → ④ 口径实验室 → ⑤ 评估报告   ／   说明页：产品 · 证据与边界 · 关于
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

  /** 由真实产物推导的结论强度（不是手填的） */
  function computeGrade(p) {
    const prj = p || Store.load();
    const ia = prj.intakeAnswers || {};
    const exo = ia.exogenous === 'yes' ? true : (ia.exogenous === 'no' ? false : null);
    const esT = ((((D.impact || {}).event_study) || {}).pre_trend_max_abs_t);
    const tbl = (((D.impact || {}).event_study) || {}).table || [];
    const t0 = (tbl.find(r => r.tau === 0) || {}).effect;
    const tm2 = (tbl.find(r => r.tau === -2) || {}).effect;
    const ratio = (t0 && tm2 != null) ? Math.abs(tm2 / t0) : null;
    const audit = (D.impact || {}).sensitivity_audit || {};
    return E.gradeEvidence({
      exogenous: exo,
      preTrendMaxAbsT: esT,
      preTrendRatio: ratio,
      ringsVerified: !!audit.rings_alternative_has_coefficients,
      bootstrapCI: !!audit.bootstrap_ci,
      outOfTime: false,
    });
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
      <div class="card" id="rpOut"><div class="note">点击「生成 / 刷新报告」。</div></div>
      <pre id="rpMd" data-raw="" style="display:none"></pre>`;
    },
    bind() {
      const build = () => {
        const p = Store.load();
        const ia = p.intakeAnswers || {};
        const ans = {
          stableId: ia.stableId, idMatchRate: ia.idMatchRate, coordNullRate: ia.coordNullRate,
          outcomeLevel: ia.outcomeLevel, years: ia.years, eventDefined: ia.eventDefined,
          exogenous: ia.exogenous === 'yes' ? true : (ia.exogenous === 'no' ? false : null),
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

      const patches = (T.patches || []).map(p => {
        const cls = p.status === '待修' ? 'danger' : p.status === '部分修' ? 'warn' : 'ok';
        return `<div class="risk-item" style="border-left-color:var(--${cls === 'danger' ? 'danger' : cls === 'warn' ? 'accent' : 'ok'})">
          <div class="t"><code>${esc(p.id)}</code> <span class="tag ${cls}">${esc(p.status)}</span> ${esc(p.title)}</div>
          <div class="b"><b>影响：</b>${esc(p.impact)}<br>${esc(p.detail)}</div>
          <div class="m"><b>修复方案：</b>${esc(p.fix)}</div></div>`;
      }).join('');

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
        ${figure('事件研究：效应何时出现、逐年多深', 'τ=−2 显著为负（p=3.76e-05）→ 平行趋势不完美，故结论降格为关联级', tauSvg)}
        ${figure("跨数据集 Moran's I", '同一方法在稀疏与密集数据上相差数十倍 → 空间结论强依赖数据分布与口径', moranSvg)}
      </div>
      <div style="margin-top:14px">${figure('SHAP 特征重要性（风险模型）', 'year 与 bank_closed_rate 远超其余；age（网点年龄）排名最后 → 「老网点更容易死」在本数据上几乎不成立', shapSvg)}</div>

      <div class="page-head" style="margin-top:22px"><div class="kicker">PATCH BOARD</div>
        <h1 style="font-size:19px">已知缺陷与修补看板</h1>
        <p>这些不是"以后再说"的待办，而是会影响结论解读的实质问题。产品选择公开它们，并在受影响的模块中强制披露。</p></div>
      <div class="card">${patches}</div>

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
node --test portal/tests/engines.test.js            # 26 项引擎单测
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
        <p>计算引擎共 26 项单元测试，覆盖数值正确性（正态近似、cloglog 链接、零交叉点）、
          护栏行为（一票否决、适用域拒绝、退化类别拒绝）与报告生成（含降级路径）。</p>
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
        exogenous: a.exogenous === 'yes' ? true : (a.exogenous === 'no' ? false : null),
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
      const r = E.impact({ strength: ip.strength, eventYear: ip.eventYear }, D);
      if (!r.ok) { box.innerHTML = `<div class="card"><div class="note danger">${esc(r.reason)}</div></div>`; return; }

      // τ 曲线
      const tauPts = r.byTau.map(x => ({ x: x.tau, y: x.effect, lo: x.lo, hi: x.hi }));
      const tauSvg = CH.curve({
        points: tauPts, w: 760, h: 290, marks: [{ x: 0, y: (r.byTau.find(z => z.tau === 0) || {}).effect, label: 'τ=0', color: 'var(--brand)' }],
        fmtY: v => (v * 100).toFixed(1) + 'pp', fmtX: v => 'τ=' + v,
        xLabel: '事件相对年份 τ（基线 τ=−1）', yLabel: '对结果变量的影响', aria: '事件研究动态效应',
      });
      // 强度曲线
      const sPts = [];
      for (let s = 0; s <= 5.0001; s += 0.125) {
        const c = r.marginal.beta0 + r.marginal.beta1 * s;
        const se = Math.sqrt(Math.pow(r.marginal.b0se, 2) + s * s * Math.pow(r.marginal.beta1se, 2));
        sPts.push({ x: s, y: c, lo: c - 1.96 * se, hi: c + 1.96 * se });
      }
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
          </div>
          <div style="margin-top:10px">${gradeBadge(r.grade)}</div>
          ${ip.strength != null && ip.strength < r.supportLowerBound
            ? `<div class="note danger"><b>你输入的强度落在外推区：</b>强度 ${nf(ip.strength, 2)} 小于训练样本处理组的下界 ${r.supportLowerBound.toFixed(2)}（= log1p(1)，即 1 起同业关闭事件）。该点未被观测，结果不可直接引用。</div>`
            : `<div class="note"><b>你输入的强度位于观测支撑域内</b>（下界 ${r.supportLowerBound.toFixed(2)}）。</div>`}
        </div>

        <div class="grid g2" style="margin-top:14px">
          ${figure('① 事件后逐年动态效应', '平均处理效应，阴影为 ±1.96·SE；τ=−2 显著为负 → 平行趋势不完美', tauSvg)}
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
    viewEl.innerHTML = page.render();
    [navEl, tocEl].forEach(box => $$('a', box).forEach(a => a.classList.toggle('on', a.dataset.id === _cur)));
    window.scrollTo({ top: 0, behavior: 'auto' });
    if (page.bind) page.bind();
    bindStatic();
    document.title = page.name + ' · 网点决策台';
  }

  function bindStatic() {
    $$('[data-goto]').forEach(b => b.addEventListener('click', () => { location.hash = '#' + b.dataset.goto; }));
    $$('[data-print]').forEach(b => b.addEventListener('click', () => window.print()));
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
    let out = '', inTbl = false, inList = false;
    const closeAll = () => { if (inTbl) { out += '</tbody></table>'; inTbl = false; } if (inList) { out += '</ul>'; inList = false; } };
    for (let raw of lines) {
      const line = raw.replace(/\r$/, '');
      if (/^\s*\|/.test(line)) {
        const cells = line.trim().replace(/^\||\|$/g, '').split('|').map(c => c.trim());
        if (/^[\s|:\-]+$/.test(line) && cells.every(c => /^:?-{2,}:?$/.test(c) || c === '')) continue;
        if (!inTbl) { closeAll(); out += '<table><tbody>'; inTbl = true; }
        out += '<tr>' + cells.map(c => `<td>${inline(c)}</td>`).join('') + '</tr>';
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
  navEl.innerHTML = PAGES.map(p => `<a href="#${p.id}" data-id="${p.id}">${esc(p.name)}</a>`).join('');
  tocEl.innerHTML = PAGES.map(p => `<li><a href="#${p.id}" data-id="${p.id}">${esc(p.name)}</a></li>`).join('');

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
