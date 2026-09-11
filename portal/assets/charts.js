/* 纯 SVG 图表库（零外部依赖，离线可用）
 * 只用直线 / 折线 / 矩形 —— 不引入任何图表 CDN，保证 index.html 双击即开。
 * 所有函数返回 SVG 字符串，由 app.js 注入。
 */
(function (global) {
  'use strict';

  const esc = (s) => String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

  const nfmt = (v, d) => (v == null || Number.isNaN(v)) ? '—'
    : Number(v).toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });

  /** 事件研究折线图：带 ±1.96·SE 置信带、零线、基线竖线 */
  function lineCI(opt) {
    const w = opt.w || 760, h = opt.h || 300;
    const pad = Object.assign({ t: 16, r: 16, b: 34, l: 58 }, opt.pad || {});
    const pts = (opt.points || []).filter(p => p && p.y != null && !Number.isNaN(p.y));
    if (!pts.length) return '<div class="note">数据缺失，已降级：无法绘制该图。</div>';

    const xs = pts.map(p => p.x), ys = pts.map(p => p.y);
    const los = pts.map(p => p.lo == null ? p.y : p.lo), his = pts.map(p => p.hi == null ? p.y : p.hi);
    const x0 = Math.min(...xs), x1 = Math.max(...xs);
    let ymin = Math.min(...los, 0), ymax = Math.max(...his, 0);
    const span = (ymax - ymin) || 1;
    ymin -= span * 0.12; ymax += span * 0.12;

    const iw = w - pad.l - pad.r, ih = h - pad.t - pad.b;
    const X = v => pad.l + (x1 === x0 ? iw / 2 : (v - x0) / (x1 - x0) * iw);
    const Y = v => pad.t + ih - (v - ymin) / (ymax - ymin) * ih;

    const fmtY = opt.fmtY || (v => nfmt(v, 3));
    const ticksY = 5, out = [];

    // 横向网格 + Y 轴
    for (let i = 0; i <= ticksY; i++) {
      const v = ymin + (ymax - ymin) * i / ticksY, y = Y(v);
      out.push(`<line class="gridline" x1="${pad.l}" y1="${y.toFixed(1)}" x2="${w - pad.r}" y2="${y.toFixed(1)}"/>`);
      out.push(`<text x="${pad.l - 8}" y="${(y + 3.5).toFixed(1)}" text-anchor="end" fill="currentColor" style="opacity:.65;font-size:10.5px">${fmtY(v)}</text>`);
    }
    // 零线
    out.push(`<line x1="${pad.l}" y1="${Y(0).toFixed(1)}" x2="${w - pad.r}" y2="${Y(0).toFixed(1)}" stroke="currentColor" stroke-width="1.2" style="opacity:.55"/>`);
    // 基线竖线（τ = baseline）
    if (opt.baseline != null) {
      const bx = X(opt.baseline);
      out.push(`<line x1="${bx.toFixed(1)}" y1="${pad.t}" x2="${bx.toFixed(1)}" y2="${pad.t + ih}" stroke="var(--brand)" stroke-width="1.2" stroke-dasharray="4 4" style="opacity:.7"/>`);
    }
    // 置信带
    const up = pts.map(p => `${X(p.x).toFixed(1)},${Y(p.hi == null ? p.y : p.hi).toFixed(1)}`);
    const dn = pts.slice().reverse().map(p => `${X(p.x).toFixed(1)},${Y(p.lo == null ? p.y : p.lo).toFixed(1)}`);
    if (pts.length > 1) {
      out.push(`<polygon points="${up.concat(dn).join(' ')}" fill="var(--brand)" opacity=".13"/>`);
    }
    // 折线
    out.push(`<polyline points="${pts.map(p => `${X(p.x).toFixed(1)},${Y(p.y).toFixed(1)}`).join(' ')}" fill="none" stroke="var(--brand)" stroke-width="2.2" stroke-linejoin="round"/>`);
    // 点 + 数值
    pts.forEach(p => {
      const cx = X(p.x), cy = Y(p.y);
      const col = p.x < (opt.splitAt == null ? -0.5 : opt.splitAt) ? 'var(--fg-dim)' : 'var(--brand)';
      out.push(`<circle cx="${cx.toFixed(1)}" cy="${cy.toFixed(1)}" r="3.6" fill="${col}"/>`);
      if (opt.showValues !== false) {
        out.push(`<text x="${cx.toFixed(1)}" y="${(cy - 9).toFixed(1)}" text-anchor="middle" style="font-size:10px;fill:currentColor;opacity:.8">${fmtY(p.y)}</text>`);
      }
      if (p.label != null) {
        const up2 = p.y >= 0;
        out.push(`<text x="${cx.toFixed(1)}" y="${(up2 ? cy + 15 : cy + 15).toFixed(1)}" text-anchor="middle" style="font-size:10px;fill:currentColor;opacity:.6">${esc(p.label)}</text>`);
      }
    });
    // X 轴
    out.push(`<line x1="${pad.l}" y1="${pad.t + ih}" x2="${w - pad.r}" y2="${pad.t + ih}" stroke="currentColor" style="opacity:.35"/>`);
    pts.forEach(p => out.push(`<text x="${X(p.x).toFixed(1)}" y="${pad.t + ih + 16}" text-anchor="middle" style="font-size:10.5px;fill:currentColor;opacity:.65">${esc(p.tick == null ? p.x : p.tick)}</text>`));
    if (opt.xLabel) out.push(`<text x="${pad.l + iw / 2}" y="${h - 4}" text-anchor="middle" style="font-size:11px;fill:currentColor;opacity:.6">${esc(opt.xLabel)}</text>`);
    if (opt.yLabel) out.push(`<text x="12" y="${pad.t + ih / 2}" transform="rotate(-90 12 ${pad.t + ih / 2})" text-anchor="middle" style="font-size:11px;fill:currentColor;opacity:.6">${esc(opt.yLabel)}</text>`);

    return `<svg viewBox="0 0 ${w} ${h}" role="img" aria-label="${esc(opt.aria || '折线图')}">${out.join('')}</svg>`;
  }

  /** 水平条形图（可正可负，支持以 0 为中心的发散配色） */
  function hbar(opt) {
    const items = (opt.items || []).filter(i => i && i.value != null && !Number.isNaN(i.value));
    if (!items.length) return '<div class="note">数据缺失，已降级：无法绘制该图。</div>';
    const w = opt.w || 720, rowH = opt.rowH || 30, pad = Object.assign({ t: 8, r: 62, b: 22, l: opt.labelWidth || 110 }, opt.pad || {});
    const h = pad.t + pad.b + items.length * rowH;
    const iw = w - pad.l - pad.r;
    const vals = items.map(i => i.value), ciVals = items.flatMap(i => [i.lo, i.hi].filter(v => v != null));
    const all = vals.concat(ciVals);
    const zeroBased = opt.zeroBased !== false;
    let vmin = Math.min(...all, zeroBased ? 0 : -Infinity), vmax = Math.max(...all, zeroBased ? 0 : Infinity);
    if (!isFinite(vmin)) vmin = Math.min(...all);
    if (!isFinite(vmax)) vmax = Math.max(...all);
    const span = (vmax - vmin) || 1;
    const X = v => pad.l + (v - vmin) / span * iw;
    const fmt = opt.fmt || (v => nfmt(v, 4));
    const out = [];

    // 零线
    out.push(`<line x1="${X(0).toFixed(1)}" y1="${pad.t}" x2="${X(0).toFixed(1)}" y2="${h - pad.b}" stroke="currentColor" stroke-width="1.1" style="opacity:.5"/>`);

    items.forEach((it, k) => {
      const y = pad.t + k * rowH + 6, bh = rowH - 14;
      const x0 = X(Math.min(0, it.value)), x1 = X(Math.max(0, it.value));
      const bw = Math.max(1.5, x1 - x0);
      const col = it.color || (it.value >= 0 ? 'var(--brand)' : 'var(--danger)');
      out.push(`<text x="${pad.l - 8}" y="${(y + bh / 2 + 3.5).toFixed(1)}" text-anchor="end" style="font-size:11.5px;fill:currentColor;opacity:.85">${esc(it.label)}</text>`);
      out.push(`<rect x="${x0.toFixed(1)}" y="${y}" width="${bw.toFixed(1)}" height="${bh}" rx="3" fill="${col}" opacity="${it.muted ? .45 : .88}"/>`);
      // 误差线
      if (it.lo != null && it.hi != null) {
        const a = X(it.lo), b = X(it.hi), yc = y + bh / 2;
        out.push(`<line x1="${a.toFixed(1)}" y1="${yc}" x2="${b.toFixed(1)}" y2="${yc}" stroke="currentColor" stroke-width="1" style="opacity:.55"/>`);
        out.push(`<line x1="${a.toFixed(1)}" y1="${(yc - 3.5)}" x2="${a.toFixed(1)}" y2="${(yc + 3.5)}" stroke="currentColor" style="opacity:.55"/>`);
        out.push(`<line x1="${b.toFixed(1)}" y1="${(yc - 3.5)}" x2="${b.toFixed(1)}" y2="${(yc + 3.5)}" stroke="currentColor" style="opacity:.55"/>`);
      }
      const tx = it.value >= 0 ? x1 + 6 : x0 - 6;
      out.push(`<text x="${tx.toFixed(1)}" y="${(y + bh / 2 + 3.5).toFixed(1)}" text-anchor="${it.value >= 0 ? 'start' : 'end'}" style="font-size:10.5px;fill:currentColor;opacity:.8">${fmt(it.value)}${it.suffix || ''}</text>`);
    });
    out.push(`<text x="${pad.l}" y="${h - 5}" style="font-size:10.5px;fill:currentColor;opacity:.55">${esc(opt.axisNote || '')}</text>`);
    return `<svg viewBox="0 0 ${w} ${h}" role="img" aria-label="${esc(opt.aria || '条形图')}">${out.join('')}</svg>`;
  }

  /** 纵向柱状图（用于距离衰减、跨数据集对比） */
  function vbar(opt) {
    const items = (opt.items || []).filter(i => i && i.value != null && !Number.isNaN(i.value));
    if (!items.length) return '<div class="note">数据缺失，已降级：无法绘制该图。</div>';
    const w = opt.w || 720, h = opt.h || 240;
    const pad = Object.assign({ t: 18, r: 12, b: 40, l: 52 }, opt.pad || {});
    const iw = w - pad.l - pad.r, ih = h - pad.t - pad.b;
    const vmax = Math.max(...items.map(i => i.value), 0) || 1;
    const bw = iw / items.length * 0.62, step = iw / items.length;
    const fmt = opt.fmt || (v => nfmt(v, 2));
    const out = [];
    for (let i = 0; i <= 4; i++) {
      const v = vmax * i / 4, y = pad.t + ih - v / vmax * ih;
      out.push(`<line class="gridline" x1="${pad.l}" y1="${y.toFixed(1)}" x2="${w - pad.r}" y2="${y.toFixed(1)}"/>`);
      out.push(`<text x="${pad.l - 8}" y="${(y + 3.5).toFixed(1)}" text-anchor="end" style="font-size:10.5px;fill:currentColor;opacity:.6">${fmt(v)}</text>`);
    }
    items.forEach((it, k) => {
      const cx = pad.l + step * k + step / 2;
      const bh = Math.max(1, it.value / vmax * ih);
      const y = pad.t + ih - bh;
      out.push(`<rect x="${(cx - bw / 2).toFixed(1)}" y="${y.toFixed(1)}" width="${bw.toFixed(1)}" height="${bh.toFixed(1)}" rx="3" fill="${it.color || 'var(--brand)'}" opacity=".85"/>`);
      out.push(`<text x="${cx.toFixed(1)}" y="${(y - 5).toFixed(1)}" text-anchor="middle" style="font-size:10.5px;fill:currentColor;opacity:.85">${fmt(it.value)}</text>`);
      out.push(`<text x="${cx.toFixed(1)}" y="${(pad.t + ih + 15).toFixed(1)}" text-anchor="middle" style="font-size:10.5px;fill:currentColor;opacity:.7">${esc(it.label)}</text>`);
      if (it.sub) out.push(`<text x="${cx.toFixed(1)}" y="${(pad.t + ih + 28).toFixed(1)}" text-anchor="middle" style="font-size:9.5px;fill:currentColor;opacity:.5">${esc(it.sub)}</text>`);
    });
    out.push(`<line x1="${pad.l}" y1="${pad.t + ih}" x2="${w - pad.r}" y2="${pad.t + ih}" stroke="currentColor" style="opacity:.35"/>`);
    return `<svg viewBox="0 0 ${w} ${h}" role="img" aria-label="${esc(opt.aria || '柱状图')}">${out.join('')}</svg>`;
  }

  /** 迷你环形进度（用于断言通过率等指标） */
  function donut(opt) {
    const pct = Math.max(0, Math.min(1, opt.value == null ? 0 : opt.value));
    const r = opt.r || 34, s = opt.stroke || 8, c = 2 * Math.PI * r;
    const size = (r + s) * 2;
    return `<svg viewBox="0 0 ${size} ${size}" style="width:${size}px;height:${size}px" role="img" aria-label="${esc(opt.aria || '进度')}">
      <circle cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke="var(--line)" stroke-width="${s}"/>
      <circle cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke="${opt.color || 'var(--brand)'}" stroke-width="${s}"
        stroke-dasharray="${(c * pct).toFixed(1)} ${c.toFixed(1)}" stroke-linecap="round" transform="rotate(-90 ${size / 2} ${size / 2})"/>
      <text x="50%" y="50%" text-anchor="middle" dy="4" style="font-size:13px;font-weight:700;fill:currentColor">${esc(opt.label != null ? opt.label : Math.round(pct * 100) + '%')}</text>
    </svg>`;
  }

  /** 通用曲线图：折线 + 可选置信带 + 竖直标记线 + 背景区间着色
   *  opt = { points:[{x,y,lo?,hi?}], bands:[{from,to,label,color}], marks:[{x,y,label,color}],
   *          fmtX, fmtY, xLabel, yLabel, h, w }
   */
  function curve(opt) {
    const pts = (opt.points || []).filter(p => p && isFinite(p.x) && isFinite(p.y));
    if (pts.length < 2) return '<div class="note">数据不足，已降级：无法绘制该曲线。</div>';
    const w = opt.w || 760, h = opt.h || 300;
    const pad = Object.assign({ t: 18, r: 18, b: 38, l: 62 }, opt.pad || {});
    const iw = w - pad.l - pad.r, ih = h - pad.t - pad.b;

    let xmin = Math.min(...pts.map(p => p.x)), xmax = Math.max(...pts.map(p => p.x));
    if (xmin === xmax) { xmin -= 1; xmax += 1; }
    let ymin = Math.min(...pts.map(p => (p.lo == null ? p.y : p.lo)));
    let ymax = Math.max(...pts.map(p => (p.hi == null ? p.y : p.hi)));
    const sp = (ymax - ymin) || 1; ymin -= sp * 0.12; ymax += sp * 0.12;

    const X = v => pad.l + (v - xmin) / (xmax - xmin) * iw;
    const Y = v => pad.t + ih - (v - ymin) / (ymax - ymin) * ih;
    const fmtX = opt.fmtX || (v => nfmt(v, 2));
    const fmtY = opt.fmtY || (v => nfmt(v, 3));
    const out = [];

    // 背景区间（用于标注"观测支撑域"）
    (opt.bands || []).forEach(b => {
      const a = X(Math.max(b.from, xmin)), z = X(Math.min(b.to, xmax));
      if (z <= a) return;
      out.push(`<rect x="${a.toFixed(1)}" y="${pad.t}" width="${(z - a).toFixed(1)}" height="${ih}" fill="${b.color || 'var(--ok)'}" opacity=".09"/>`);
      if (b.label) out.push(`<text x="${((a + z) / 2).toFixed(1)}" y="${pad.t + 12}" text-anchor="middle" style="font-size:10px;fill:currentColor;opacity:.65">${esc(b.label)}</text>`);
    });

    for (let i = 0; i <= 4; i++) {
      const v = ymin + (ymax - ymin) * i / 4, y = Y(v);
      out.push(`<line class="gridline" x1="${pad.l}" y1="${y.toFixed(1)}" x2="${w - pad.r}" y2="${y.toFixed(1)}"/>`);
      out.push(`<text x="${pad.l - 8}" y="${(y + 3.5).toFixed(1)}" text-anchor="end" style="font-size:10.5px;fill:currentColor;opacity:.6">${fmtY(v)}</text>`);
    }
    if (ymin < 0 && ymax > 0) {
      out.push(`<line x1="${pad.l}" y1="${Y(0).toFixed(1)}" x2="${w - pad.r}" y2="${Y(0).toFixed(1)}" stroke="currentColor" stroke-width="1.1" style="opacity:.5"/>`);
    }
    if (pts[0].lo != null) {
      const up = pts.map(p => `${X(p.x).toFixed(1)},${Y(p.hi).toFixed(1)}`);
      const dn = pts.slice().reverse().map(p => `${X(p.x).toFixed(1)},${Y(p.lo).toFixed(1)}`);
      out.push(`<polygon points="${up.concat(dn).join(' ')}" fill="var(--brand)" opacity=".12"/>`);
    }
    out.push(`<polyline points="${pts.map(p => `${X(p.x).toFixed(1)},${Y(p.y).toFixed(1)}`).join(' ')}" fill="none" stroke="var(--brand)" stroke-width="2.2"/>`);
    (opt.marks || []).forEach(m => {
      const mx = X(m.x);
      out.push(`<line x1="${mx.toFixed(1)}" y1="${pad.t}" x2="${mx.toFixed(1)}" y2="${pad.t + ih}" stroke="${m.color || 'var(--accent)'}" stroke-width="1.4" stroke-dasharray="4 3"/>`);
      out.push(`<circle cx="${mx.toFixed(1)}" cy="${Y(m.y == null ? (ymin + ymax) / 2 : m.y).toFixed(1)}" r="4.2" fill="${m.color || 'var(--accent)'}"/>`);
      if (m.label) out.push(`<text x="${mx.toFixed(1)}" y="${pad.t - 6}" text-anchor="middle" style="font-size:10.5px;fill:${m.color || 'var(--accent)'}">${esc(m.label)}</text>`);
    });
    out.push(`<line x1="${pad.l}" y1="${pad.t + ih}" x2="${w - pad.r}" y2="${pad.t + ih}" stroke="currentColor" style="opacity:.35"/>`);
    for (let i = 0; i <= 4; i++) {
      const v = xmin + (xmax - xmin) * i / 4;
      out.push(`<text x="${X(v).toFixed(1)}" y="${pad.t + ih + 16}" text-anchor="middle" style="font-size:10.5px;fill:currentColor;opacity:.65">${fmtX(v)}</text>`);
    }
    if (opt.xLabel) out.push(`<text x="${pad.l + iw / 2}" y="${h - 4}" text-anchor="middle" style="font-size:11px;fill:currentColor;opacity:.6">${esc(opt.xLabel)}</text>`);
    if (opt.yLabel) out.push(`<text x="12" y="${pad.t + ih / 2}" transform="rotate(-90 12 ${pad.t + ih / 2})" text-anchor="middle" style="font-size:11px;fill:currentColor;opacity:.6">${esc(opt.yLabel)}</text>`);
    return `<svg viewBox="0 0 ${w} ${h}" role="img" aria-label="${esc(opt.aria || '曲线图')}">${out.join('')}</svg>`;
  }

  global.SDPCharts = { esc, nfmt, lineCI, curve, hbar, vbar, donut };
})(window);
