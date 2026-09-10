# -*- coding: utf-8 -*-
"""09_interactive · 展示层设计系统（产品 2 = 预测模型 / 可解释性产品型）。

为什么与 project6 的教材风格不同
--------------------------------
`suggestions_for_projects_0908.md` 给产品 2 的定位是
「**预测模型 / 可解释性产品型**，受众 = 分析师 + 风控 / 决策者，核心诉求是
**相信模型准、理解为什么、能上手试**」。

所以这套令牌刻意做得比教学产品更「看板化」：

* KPI 数字更大、指标条更密（决策者先看数，再读文）；
* 风险用**琥珀 → 朱红**语义色，安全用蓝；
* 「护栏 / 止损」用醒目红框 —— 本产品的要点就是**标注边界**，不能藏在文档里；
* 与 project6 共用同一套亮/深色令牌与 plotly 主题重着色（两个产品看起来是同一家公司做的）。
"""
from __future__ import annotations

import datetime as _dt
from pathlib import Path
from typing import Any

FONT = '"Microsoft YaHei","Noto Sans CJK SC","PingFang SC","Hiragino Sans GB",sans-serif'

CSS_TOKENS = """
:root{
  --ink:#0f172a; --ink-2:#334155; --sub:#64748b; --faint:#94a3b8;
  --line:#e2e8f0; --line-2:#cbd5e1; --bg:#ffffff; --soft:#f8fafc; --soft-2:#f1f5f9;
  --brand:#1d4ed8; --brand-soft:#eff4ff;
  --risk:#ea580c; --risk-soft:#fff5ed;
  --danger:#b91c1c; --danger-soft:#fef2f2;
  --ok:#0f766e; --ok-soft:#f0fdfa;
  --warn:#a16207; --warn-soft:#fefce8;
  --purple:#6d28d9; --purple-soft:#f5f3ff;
  --shadow:0 1px 2px rgba(15,23,42,.06), 0 8px 24px rgba(15,23,42,.06);
  --radius:14px;
}
:root[data-theme="dark"]{
  --ink:#e8eefc; --ink-2:#c3cee4; --sub:#94a3b8; --faint:#64748b;
  --line:#233047; --line-2:#33425e; --bg:#0b1220; --soft:#111a2c; --soft-2:#17223a;
  --brand:#7aa2ff; --brand-soft:#132240;
  --risk:#fb923c; --risk-soft:#2a1708;
  --danger:#f87171; --danger-soft:#2c1214;
  --ok:#2dd4bf; --ok-soft:#0c2622;
  --warn:#facc15; --warn-soft:#2a230d;
  --purple:#a78bfa; --purple-soft:#1c1733;
  --shadow:0 1px 2px rgba(0,0,0,.4), 0 8px 24px rgba(0,0,0,.35);
}
"""

CSS_BASE = CSS_TOKENS + """
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0;font-family:__FONT__;color:var(--ink);background:var(--bg);
     line-height:1.75;-webkit-font-smoothing:antialiased;transition:background .25s,color .25s}
a{color:var(--brand);text-decoration:none}
a:hover{text-decoration:underline}
.wrap{max-width:1180px;margin:0 auto;padding:26px 24px 80px}
h1,h2,h3{line-height:1.3;letter-spacing:-.01em}
h1{font-size:29px;margin:0 0 8px}
h2{font-size:21px;margin:38px 0 12px;padding-bottom:10px;border-bottom:1px solid var(--line)}
h3{font-size:16.5px;margin:22px 0 8px}
p{margin:10px 0;font-size:14.5px;color:var(--ink-2)}
.lede{font-size:15.5px;color:var(--sub);margin:8px 0 4px}
.kicker{font-size:11.5px;letter-spacing:.16em;color:var(--risk);font-weight:800;
        text-transform:uppercase;margin:0 0 6px}
.muted{color:var(--sub);font-size:13px}
code{background:var(--soft-2);padding:1.5px 6px;border-radius:5px;font-size:12.5px;
     font-family:ui-monospace,Consolas,"Courier New",monospace;color:var(--ink-2)}
hr{border:0;border-top:1px solid var(--line);margin:28px 0}

.topbar{position:sticky;top:0;z-index:20;display:flex;align-items:center;gap:12px;
  padding:11px 22px;background:var(--bg);border-bottom:1px solid var(--line);
  backdrop-filter:saturate(180%) blur(8px)}
.topbar .brand{font-weight:800;font-size:14px;letter-spacing:-.01em}
.topbar .brand span{color:var(--risk)}
.topbar .spacer{flex:1}
.chip{font-size:11px;padding:3px 9px;border-radius:999px;background:var(--soft-2);
  color:var(--sub);border:1px solid var(--line)}
.btn{border:1px solid var(--line);background:var(--bg);color:var(--ink-2);border-radius:9px;
  padding:6px 13px;font-size:13.5px;cursor:pointer;font-family:inherit;transition:.18s;
  white-space:nowrap;text-decoration:none;display:inline-block}
.btn:hover{border-color:var(--brand);color:var(--brand);transform:translateY(-1px);
  text-decoration:none}
.btn.primary{background:var(--brand);border-color:var(--brand);color:#fff}
.btn.primary:hover{filter:brightness(1.08);color:#fff}

.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:16px 0}
.stat{border:1px solid var(--line);border-radius:12px;padding:12px 14px;background:var(--soft)}
.stat .k{font-size:12px;color:var(--sub);display:block;margin-bottom:2px}
.stat .v{font-size:24px;font-weight:750;font-variant-numeric:tabular-nums;
  letter-spacing:-.02em;line-height:1.25;display:block}
.stat .h{font-size:11.5px;color:var(--faint);display:block;margin-top:2px}
.stat.good .v{color:var(--ok)} .stat.risk .v{color:var(--risk)}
.stat.brand .v{color:var(--brand)} .stat.warn .v{color:var(--warn)}

.grid{display:grid;gap:14px}
.g2{grid-template-columns:repeat(auto-fit,minmax(300px,1fr))}
.g3{grid-template-columns:repeat(auto-fit,minmax(230px,1fr))}
.g4{grid-template-columns:repeat(auto-fit,minmax(190px,1fr))}
.card{border:1px solid var(--line);border-radius:var(--radius);padding:16px 18px;
  background:var(--bg);box-shadow:var(--shadow);transition:.2s}
.card:hover{border-color:var(--line-2);transform:translateY(-2px)}
.card .t{font-weight:700;font-size:15px;margin:0 0 6px;display:flex;align-items:center;gap:8px}
.card .d{font-size:13.5px;color:var(--sub);margin:0;line-height:1.7}
.card .q{font-size:12.5px;color:var(--risk);margin:10px 0 0;font-weight:600}

.note,.warn,.ok,.ask,.danger{border-radius:0 12px 12px 0;padding:13px 17px;margin:16px 0;
  font-size:14px;border-left:4px solid}
.note{background:var(--brand-soft);border-color:var(--brand)}
.warn{background:var(--risk-soft);border-color:var(--risk)}
.ok{background:var(--ok-soft);border-color:var(--ok)}
.ask{background:var(--purple-soft);border-color:var(--purple)}
.danger{background:var(--danger-soft);border-color:var(--danger)}
.note b,.warn b,.ok b,.ask b,.danger b{display:block;margin-bottom:4px;font-size:14px}
.note ul,.warn ul,.ok ul,.ask ul,.danger ul{margin:6px 0 0;padding-left:20px}
.note li,.warn li,.ok li,.ask li,.danger li{margin:4px 0;font-size:13.5px;color:var(--ink-2)}
.note p,.warn p,.ok p,.danger p{margin:4px 0;font-size:13.5px;color:var(--ink-2)}

.guard{border:1px solid var(--line);border-left:4px solid var(--danger);
  border-radius:0 12px 12px 0;padding:13px 17px;margin:10px 0;background:var(--danger-soft)}
.guard b{font-size:13.5px;color:var(--danger);display:block;margin-bottom:3px}
.guard span{font-size:13.5px;color:var(--ink-2);line-height:1.7}

.fig{border:1px solid var(--line);border-radius:var(--radius);overflow:hidden;margin:16px 0;
  background:var(--bg);box-shadow:var(--shadow)}
.fig iframe{width:100%;height:540px;border:0;display:block;background:var(--bg)}
.fig img{width:100%;display:block;background:#fff}
.fig .cap{font-size:12.5px;color:var(--sub);padding:9px 14px;background:var(--soft);
  border-top:1px solid var(--line)}

table{width:100%;border-collapse:collapse;font-size:13.5px;margin:14px 0}
th,td{padding:9px 11px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
th{color:var(--sub);font-weight:650;font-size:12px;letter-spacing:.03em;text-transform:uppercase;
   background:var(--soft)}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
tbody tr:hover{background:var(--soft)}

.formula{background:var(--soft);border:1px solid var(--line);border-radius:12px;padding:14px 18px;
  margin:14px 0;font-family:ui-monospace,Consolas,monospace;font-size:13.5px;color:var(--ink);
  overflow-x:auto;line-height:1.9}
.formula .lbl{display:block;font-family:__FONT__;font-size:12px;color:var(--sub);margin-bottom:6px}

.steps{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px;margin:16px 0}
.step{border:1px solid var(--line);border-radius:12px;padding:13px 15px;background:var(--soft);
  position:relative;overflow:hidden;text-decoration:none;color:inherit;display:block}
.step:before{content:"";position:absolute;left:0;top:0;bottom:0;width:3px;background:var(--risk)}
.step b{display:block;font-size:13px;color:var(--risk);margin-bottom:4px;letter-spacing:.02em}
.step span{font-size:13px;color:var(--sub);line-height:1.65;display:block}

.badge{display:inline-block;font-size:11px;padding:2px 8px;border-radius:999px;
  border:1px solid var(--line);color:var(--sub);background:var(--soft);margin-right:6px}
.badge.b{color:var(--brand);border-color:var(--brand);background:var(--brand-soft)}
.badge.r{color:var(--risk);border-color:var(--risk);background:var(--risk-soft)}
.badge.g{color:var(--ok);border-color:var(--ok);background:var(--ok-soft)}
.badge.d{color:var(--danger);border-color:var(--danger);background:var(--danger-soft)}
.badge.p{color:var(--purple);border-color:var(--purple);background:var(--purple-soft)}

.foot{margin-top:56px;padding-top:16px;border-top:1px solid var(--line);font-size:12px;
  color:var(--faint)}
@media (max-width:720px){
  .wrap{padding:18px 14px 60px}
  .fig iframe{height:430px}
  h1{font-size:23px}
}
""".replace("__FONT__", FONT)

JS_THEME = """
(function(){
  var KEY='p2-theme';
  try{
    var saved=localStorage.getItem(KEY);
    if(!saved){ saved = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark':'light'; }
    document.documentElement.setAttribute('data-theme', saved);
  }catch(e){}
  window.__toggleTheme=function(){
    var cur=document.documentElement.getAttribute('data-theme')==='dark'?'light':'dark';
    document.documentElement.setAttribute('data-theme',cur);
    try{localStorage.setItem(KEY,cur);}catch(e){}
    var b=document.getElementById('themeBtn');
    if(b){ b.textContent = cur==='dark' ? '\\u2600 \\u65e5\\u95f4' : '\\u263e \\u591c\\u95f4'; }
    window.dispatchEvent(new Event('themechange'));
  };
  document.addEventListener('DOMContentLoaded',function(){
    var b=document.getElementById('themeBtn');
    if(b){ b.textContent = document.documentElement.getAttribute('data-theme')==='dark' ? '\\u2600 \\u65e5\\u95f4' : '\\u263e \\u591c\\u95f4'; }
  });
})();

/* Plotly 不认 CSS 变量，只能画完再按主题 relayout。 */
(function(){
  window.__applyPlotTheme=function(){
    var dark=document.documentElement.getAttribute('data-theme')==='dark';
    var bg=dark?'#0b1220':'#ffffff', grid=dark?'#233047':'#e2e8f0',
        fg=dark?'#e8eefc':'#0f172a', sub=dark?'#94a3b8':'#64748b';
    var plots=document.querySelectorAll('.js-plotly-plot');
    for(var i=0;i<plots.length;i++){
      var d=plots[i]; if(!d.layout) continue;
      var up={'paper_bgcolor':bg,'plot_bgcolor':bg,'font.color':sub};
      Object.keys(d.layout).forEach(function(k){
        if(/^[xy]axis\\d*$/.test(k)){
          up[k+'.gridcolor']=grid; up[k+'.linecolor']=grid;
          up[k+'.zerolinecolor']=grid; up[k+'.tickfont.color']=sub;
          up[k+'.title.font.color']=sub;
        }
      });
      if(d.layout.title) up['title.font.color']=fg;
      if(d.layout.legend) up['legend.font.color']=sub;
      if(d.layout.annotations) up['annotations']=(d.layout.annotations||[]).map(function(a){
        return Object.assign({},a,{font:Object.assign({},a.font||{},{color:sub})});
      });
      try{ Plotly.relayout(d, up); }catch(e){}
      if(window.Plotly && d.data){
        for(var j=0;j<d.data.length;j++){
          if(d.data[j] && d.data[j].text){ try{ Plotly.restyle(d,{'textfont.color':sub},[j]); }catch(e){} }
        }
      }
    }
  };
  document.addEventListener('DOMContentLoaded',function(){ setTimeout(window.__applyPlotTheme,60); });
  window.addEventListener('themechange',function(){ setTimeout(window.__applyPlotTheme,30); });
})();
"""

PLOTLY_VENDOR_REL = "assets/vendor/plotly.min.js"


def write_plotly_vendor(out: Path) -> bool:
    """plotly.js **只写一份**到 ``out/assets/vendor/``。

    单份就是 4.3 MB，逐页内联既撑爆仓库又让每次打开都重新解析；共享一份后可命中
    浏览器缓存（入口页里嵌的多个 iframe 第二次打开是瞬时的）。
    """
    try:
        from plotly.offline import get_plotlyjs
        js = get_plotlyjs()
    except Exception:
        return False
    p = out / "assets" / "vendor" / "plotly.min.js"
    p.parent.mkdir(parents=True, exist_ok=True)
    if (not p.exists()) or p.stat().st_size < 1_000_000:
        p.write_text(js, encoding="utf-8")
    return True


def plotly_tag(rel: str = PLOTLY_VENDOR_REL) -> str:
    return f'<script src="{rel}"></script>'


# --------------------------------------------------------------------------- #
def fmt_int(v: Any) -> str:
    return "—" if v is None else f"{int(round(float(v))):,}"


def fmt_num(v: Any, nd: int = 3) -> str:
    return "—" if v is None else f"{float(v):.{nd}f}"


def fmt_pct(v: Any, nd: int = 2) -> str:
    return "—" if v is None else f"{float(v) * 100:.{nd}f}%"


def page(title: str, body: str, *, subtitle: str = "", home: str = "index.html",
         extra_css: str = "", extra_js: str = "", with_plotly: bool = False,
         active_nav: str = "") -> str:
    nav = f'<a class="btn" href="{home}">← 返回入口</a>' if home else ""
    plotly = plotly_tag() if with_plotly else ""
    sub = f'<p class="lede">{subtitle}</p>' if subtitle else ""
    return f"""<!doctype html><html lang="zh-CN" data-theme="light"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<script>{JS_THEME}</script>
<style>{CSS_BASE}{extra_css}</style>
{plotly}
</head><body>
<div class="topbar">
  <span class="brand">FDIC 网点寿命模型 <span>· 风险预测</span></span>
  <span class="chip">{active_nav}</span>
  <span class="spacer"></span>
  <button class="btn" id="themeBtn" onclick="__toggleTheme()">☾ 夜间</button>
  {nav}
</div>
<div class="wrap">
  <h1>{title}</h1>{sub}
  {body}
  <div class="foot">生成脚本 <code>09_interactive/09_interactive.py</code>　|
  生成时间 {_dt.datetime.now():%Y-%m-%d %H:%M}　|
  数字来自上游产物 <code>06_train/output/</code> 与 <code>08_conclude/output/</code>，不硬编码。</div>
</div>
<script>{extra_js}</script>
</body></html>"""


def kpi_strip(items: list[tuple[str, str, str | None, str | None]]) -> str:
    """KPI 条：``[(标签, 值, 说明, 语义class)]``，class ∈ good / risk / brand / warn。"""
    cells = "".join(
        f'<div class="stat {cls or ""}"><span class="k">{k}</span>'
        f'<span class="v">{v}</span>' + (f'<span class="h">{h}</span>' if h else "") + "</div>"
        for k, v, h, cls in items)
    return f'<div class="stats">{cells}</div>'


def callout(kind: str, title: str, body: str) -> str:
    return f'<div class="{kind}"><b>{title}</b>{body}</div>'


def guard(title: str, body: str) -> str:
    """护栏 / 止损条件卡（产品 2 的差异化组件：边界必须写在页面上）。"""
    return f'<div class="guard"><b>{title}</b><span>{body}</span></div>'


def fig_iframe(src: str, caption: str = "", height: int = 540) -> str:
    return (f'<div class="fig"><iframe src="{src}" loading="lazy" '
            f'style="height:{height}px"></iframe><div class="cap">{caption}</div></div>')


def fig_img(src: str, caption: str = "", alt: str = "") -> str:
    return (f'<div class="fig"><img src="{src}" alt="{alt}" loading="lazy">'
            f'<div class="cap">{caption}</div></div>')


def table(headers: list[str], rows: list[list[str]], num_cols: set[int] | None = None) -> str:
    num_cols = num_cols or set()
    th = "".join(f'<th class="{"num" if i in num_cols else ""}">{h}</th>'
                 for i, h in enumerate(headers))
    tb = "".join("<tr>" + "".join(
        f'<td class="{"num" if i in num_cols else ""}">{c}</td>'
        for i, c in enumerate(r)) + "</tr>" for r in rows)
    return f"<table><thead><tr>{th}</tr></thead><tbody>{tb}</tbody></table>"


def formula(label: str, expr: str) -> str:
    return f'<div class="formula"><span class="lbl">{label}</span>{expr}</div>'


def steps(items: list[tuple[str, str]], hrefs: list[str] | None = None) -> str:
    hrefs = hrefs or [None] * len(items)
    out = []
    for (a, b), h in zip(items, hrefs):
        out.append(f'<a class="step" href="{h}"><b>{a}</b><span>{b}</span></a>' if h
                   else f'<div class="step"><b>{a}</b><span>{b}</span></div>')
    return '<div class="steps">' + "".join(out) + "</div>"
