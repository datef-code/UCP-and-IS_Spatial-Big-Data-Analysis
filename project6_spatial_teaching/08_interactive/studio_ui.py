# -*- coding: utf-8 -*-
"""08_interactive · 展示层设计系统（配色 / 组件 / 页面外壳）。

为什么要有设计系统
------------------
本阶段有 7 个独立 HTML 产物 + 一本电子书。如果每个文件各写一套 CSS，
改一次主色要动 7 处，而且新手打开不同页面会有「这是两个项目吗」的违和感。
这里把**设计令牌（token）+ 组件 + 页面外壳**收成一处，产物只写内容。

设计取向（面向带新人）：
* 高对比、大留白、卡片化 —— 第一次看就能分清「正文 / 结论 / 坑 / 图」；
* 深色模式随系统 + 可手动切（看投影不刺眼，自己看不累）；
* 所有交互件都是**单文件自包含**（内联 plotly、内联 CSS/JS），离线可开、挪动不丢图。
"""
from __future__ import annotations

import datetime as _dt
from typing import Any

FONT = '"Microsoft YaHei","Noto Sans CJK SC","PingFang SC","Hiragino Sans GB",sans-serif'

# 设计令牌：亮色 / 深色共享变量名，切换只改 :root 的值
CSS_TOKENS = """
:root{
  --ink:#0f172a; --ink-2:#334155; --sub:#64748b; --faint:#94a3b8;
  --line:#e2e8f0; --line-2:#cbd5e1; --bg:#ffffff; --soft:#f8fafc; --soft-2:#f1f5f9;
  --brand:#2563eb; --brand-soft:#eff6ff;
  --accent:#ea580c; --accent-soft:#fff7ed;
  --ok:#059669; --ok-soft:#ecfdf5;
  --warn:#b45309; --warn-soft:#fffbeb;
  --purple:#7c3aed; --purple-soft:#f5f3ff;
  --shadow:0 1px 2px rgba(15,23,42,.06), 0 8px 24px rgba(15,23,42,.06);
  --radius:14px;
}
:root[data-theme="dark"]{
  --ink:#e8eefc; --ink-2:#c3cee4; --sub:#94a3b8; --faint:#64748b;
  --line:#233047; --line-2:#33425e; --bg:#0d1424; --soft:#131c2f; --soft-2:#18233a;
  --brand:#60a5fa; --brand-soft:#13233d;
  --accent:#fb923c; --accent-soft:#2a1a0e;
  --ok:#34d399; --ok-soft:#0d2620;
  --warn:#fbbf24; --warn-soft:#2a2110;
  --purple:#a78bfa; --purple-soft:#1e1b34;
  --shadow:0 1px 2px rgba(0,0,0,.4), 0 8px 24px rgba(0,0,0,.35);
}
"""

CSS_BASE = CSS_TOKENS + """
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0;font-family:__FONT__;color:var(--ink);background:var(--bg);
     line-height:1.78;-webkit-font-smoothing:antialiased;
     transition:background .25s,color .25s}
a{color:var(--brand);text-decoration:none}
a:hover{text-decoration:underline}
.wrap{max-width:1180px;margin:0 auto;padding:28px 24px 80px}
h1,h2,h3{line-height:1.3;letter-spacing:-.01em}
h1{font-size:30px;margin:0 0 8px}
h2{font-size:22px;margin:38px 0 12px;padding-bottom:10px;border-bottom:1px solid var(--line)}
h3{font-size:16.5px;margin:22px 0 8px}
p{margin:10px 0;font-size:15px;color:var(--ink-2)}
.lede{font-size:16px;color:var(--sub);margin:8px 0 4px}
.kicker{font-size:11.5px;letter-spacing:.16em;color:var(--accent);font-weight:800;
        text-transform:uppercase;margin:0 0 6px}
.muted{color:var(--sub);font-size:13px}
code{background:var(--soft-2);padding:1.5px 6px;border-radius:5px;font-size:13px;
     font-family:ui-monospace,Consolas,"Courier New",monospace;color:var(--ink-2)}
hr{border:0;border-top:1px solid var(--line);margin:28px 0}

/* ---- 顶栏 ---- */
.topbar{position:sticky;top:0;z-index:20;display:flex;align-items:center;gap:14px;
  padding:11px 22px;background:var(--bg);border-bottom:1px solid var(--line);
  backdrop-filter:saturate(180%) blur(8px)}
.topbar .brand{font-weight:800;font-size:14px;letter-spacing:-.01em}
.topbar .brand span{color:var(--accent)}
.topbar .spacer{flex:1}
.chip{font-size:11px;padding:3px 9px;border-radius:999px;background:var(--soft-2);
  color:var(--sub);border:1px solid var(--line)}
.btn{border:1px solid var(--line);background:var(--bg);color:var(--ink-2);
  border-radius:9px;padding:6px 13px;font-size:13.5px;cursor:pointer;font-family:inherit;
  transition:.18s;white-space:nowrap}
.btn:hover{border-color:var(--brand);color:var(--brand);transform:translateY(-1px)}
.btn.primary{background:var(--brand);border-color:var(--brand);color:#fff}
.btn.primary:hover{filter:brightness(1.08);color:#fff}
.btn:disabled{opacity:.4;cursor:not-allowed;transform:none}

/* ---- 卡片 / 网格 ---- */
.grid{display:grid;gap:14px}
.g2{grid-template-columns:repeat(auto-fit,minmax(300px,1fr))}
.g3{grid-template-columns:repeat(auto-fit,minmax(230px,1fr))}
.g4{grid-template-columns:repeat(auto-fit,minmax(190px,1fr))}
.card{border:1px solid var(--line);border-radius:var(--radius);padding:16px 18px;
  background:var(--bg);box-shadow:var(--shadow);transition:.2s}
.card:hover{border-color:var(--line-2);transform:translateY(-2px)}
.card .t{font-weight:700;font-size:15px;margin:0 0 6px;display:flex;align-items:center;gap:8px}
.card .d{font-size:13.5px;color:var(--sub);margin:0;line-height:1.7}
.card .q{font-size:12.5px;color:var(--accent);margin:10px 0 0;font-weight:600}

/* ---- 指标条 ---- */
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:16px 0}
.stat{border:1px solid var(--line);border-radius:12px;padding:12px 14px;background:var(--soft)}
.stat .k{font-size:12px;color:var(--sub);display:block;margin-bottom:2px}
.stat .v{font-size:23px;font-weight:750;font-variant-numeric:tabular-nums;
  letter-spacing:-.02em;line-height:1.25}
.stat .h{font-size:11.5px;color:var(--faint)}

/* ---- 提示块 ---- */
.note,.warn,.ok,.ask{border-radius:0 12px 12px 0;padding:13px 17px;margin:16px 0;
  font-size:14px;border-left:4px solid}
.note{background:var(--brand-soft);border-color:var(--brand)}
.warn{background:var(--accent-soft);border-color:var(--accent)}
.ok{background:var(--ok-soft);border-color:var(--ok)}
.ask{background:var(--purple-soft);border-color:var(--purple)}
.note b,.warn b,.ok b,.ask b{display:block;margin-bottom:4px;font-size:14px}
.note ul,.warn ul,.ok ul,.ask ul{margin:6px 0 0;padding-left:20px}
.note li,.warn li,.ok li,.ask li{margin:4px 0;font-size:13.5px;color:var(--ink-2)}

/* ---- 图 ---- */
.fig{border:1px solid var(--line);border-radius:var(--radius);overflow:hidden;margin:16px 0;
  background:var(--bg);box-shadow:var(--shadow)}
.fig iframe{width:100%;height:520px;border:0;display:block;background:var(--bg)}
.fig img{width:100%;display:block;background:#fff}
.fig .cap{font-size:12.5px;color:var(--sub);padding:9px 14px;background:var(--soft);
  border-top:1px solid var(--line)}

/* ---- 表 ---- */
table{width:100%;border-collapse:collapse;font-size:13.5px;margin:14px 0}
th,td{padding:9px 11px;border-bottom:1px solid var(--line);text-align:left}
th{color:var(--sub);font-weight:650;font-size:12px;letter-spacing:.03em;
   text-transform:uppercase;background:var(--soft)}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
tbody tr:hover{background:var(--soft)}

/* ---- 公式 ---- */
.formula{background:var(--soft);border:1px solid var(--line);border-radius:12px;
  padding:14px 18px;margin:14px 0;font-family:ui-monospace,Consolas,monospace;
  font-size:14px;color:var(--ink);overflow-x:auto;line-height:1.9}
.formula .lbl{display:block;font-family:__FONT__;font-size:12px;color:var(--sub);margin-bottom:6px}

/* ---- 步骤条 ---- */
.steps{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin:16px 0}
.step{border:1px solid var(--line);border-radius:12px;padding:13px 15px;background:var(--soft);
  position:relative;overflow:hidden}
.step:before{content:"";position:absolute;left:0;top:0;bottom:0;width:3px;background:var(--accent)}
.step b{display:block;font-size:13px;color:var(--accent);margin-bottom:4px;letter-spacing:.02em}
.step span{font-size:13px;color:var(--sub);line-height:1.65}

/* ---- 徽章 ---- */
.badge{display:inline-block;font-size:11px;padding:2px 8px;border-radius:999px;
  border:1px solid var(--line);color:var(--sub);background:var(--soft);margin-right:6px}
.badge.b{color:var(--brand);border-color:var(--brand);background:var(--brand-soft)}
.badge.o{color:var(--accent);border-color:var(--accent);background:var(--accent-soft)}
.badge.g{color:var(--ok);border-color:var(--ok);background:var(--ok-soft)}
.badge.p{color:var(--purple);border-color:var(--purple);background:var(--purple-soft)}

.foot{margin-top:56px;padding-top:16px;border-top:1px solid var(--line);
  font-size:12px;color:var(--faint)}
@media (max-width:720px){
  .wrap{padding:18px 14px 60px}
  .fig iframe{height:420px}
  h1{font-size:23px}
}
""".replace("__FONT__", FONT)

# 主题切换 + 进度记忆的公共脚本（所有页面共用，保证行为一致）
JS_THEME = """
(function(){
  var KEY='p6-theme';
  try{
    var saved=localStorage.getItem(KEY);
    if(!saved){ saved = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark':'light'; }
    document.documentElement.setAttribute('data-theme', saved);
  }catch(e){}
  window.__toggleTheme=function(){
    var cur=document.documentElement.getAttribute('data-theme')==='dark'?'light':'dark';
    document.documentElement.setAttribute('data-theme',cur);
    try{localStorage.setItem(KEY,cur);}catch(e){}
    var b=document.getElementById('themeBtn'); if(b){b.textContent = cur==='dark'?'☀ 日间':'☾ 夜间';}
    window.dispatchEvent(new Event('themechange'));
  };
  document.addEventListener('DOMContentLoaded',function(){
    var b=document.getElementById('themeBtn');
    if(b){ b.textContent = document.documentElement.getAttribute('data-theme')==='dark'?'☀ 日间':'☾ 夜间'; }
  });
})();

/* Plotly 图随主题重着色：plotly 不认 CSS 变量，只能画完再 relayout。 */
(function(){
  function hex(v){return v;}
  window.__applyPlotTheme=function(){
    var dark=document.documentElement.getAttribute('data-theme')==='dark';
    var bg=dark?'#0d1424':'#ffffff', grid=dark?'#233047':'#e2e8f0',
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


# --------------------------------------------------------------------------- #
def fmt_int(v: Any) -> str:
    return "—" if v is None else f"{int(round(float(v))):,}"


def fmt_num(v: Any, nd: int = 3) -> str:
    return "—" if v is None else f"{float(v):.{nd}f}"


def fmt_pct(v: Any, nd: int = 1) -> str:
    return "—" if v is None else f"{float(v) * 100:.{nd}f}%"


PLOTLY_VENDOR_REL = "assets/vendor/plotly.min.js"


def write_plotly_vendor(out: Path) -> bool:
    """把 plotly.js **只写一份**到 ``out/assets/vendor/``，各页面用相对路径引用。

    为什么不每个页面内联一份：单个 plotly.min.js 就是 4.3 MB，7 个页面内联 = 30 MB，
    而且浏览器每次都要重新解析。共享一份后：
    * 产物目录体积从 ~22 MB 降到 ~11 MB；
    * 电子书里嵌的 iframe 会命中同一份缓存，翻页明显更快（这就是「流畅」）。
    代价是「单独拷走一个 HTML 会丢图」—— 因此规范改为：<b>整个 ``output/`` 目录</b>
    是一个自包含单元，可整体拷走/离线打开。
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
    """引用共享的 plotly.js；未生成 vendor 文件时退回 CDN，页面仍可用。"""
    return f'<script src="{rel}"></script>'


def plotly_cfg() -> str:
    return "{displaylogo:false,responsive:true,modeBarButtonsToRemove:['lasso2d','select2d']}"


def page(title: str, body: str, *, subtitle: str = "", home: str = "index.html",
         extra_css: str = "", extra_js: str = "", with_plotly: bool = False,
         active_nav: str = "") -> str:
    """统一的页面外壳：顶栏（含主题切换 + 返回入口）+ 内容 + 页脚。"""
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
  <span class="brand">空间大数据方法 <span>L0→L3</span></span>
  <span class="chip">{active_nav}</span>
  <span class="spacer"></span>
  <button class="btn" id="themeBtn" onclick="__toggleTheme()">☾ 夜间</button>
  {nav}
</div>
<div class="wrap">
  <h1>{title}</h1>{sub}
  {body}
  <div class="foot">生成脚本 <code>08_interactive/08_interactive.py</code>　|
  生成时间 {_dt.datetime.now():%Y-%m-%d %H:%M}　|
  所有数字来自上游产物 <code>05_map/output/&lt;ds&gt;/ladder_report.json</code>，不硬编码。</div>
</div>
<script>{extra_js}</script>
</body></html>"""


# --------------------------------------------------------------------------- #
def stat_strip(items: list[tuple[str, str, str | None]]) -> str:
    """指标条：[(标签, 值, 说明)]。"""
    cells = "".join(
        f'<div class="stat"><span class="k">{k}</span><span class="v">{v}</span>'
        + (f'<span class="h">{h}</span>' if h else "") + "</div>"
        for k, v, h in items)
    return f'<div class="stats">{cells}</div>'


def callout(kind: str, title: str, body: str) -> str:
    return f'<div class="{kind}"><b>{title}</b>{body}</div>'


def fig_iframe(src: str, caption: str = "", height: int = 520) -> str:
    return (f'<div class="fig"><iframe src="{src}" loading="lazy"></iframe>'
            f'<div class="cap">{caption}</div></div>')


def fig_img(src: str, caption: str = "", alt: str = "") -> str:
    return (f'<div class="fig"><img src="{src}" alt="{alt}" loading="lazy">'
            f'<div class="cap">{caption}</div></div>')


def table(headers: list[str], rows: list[list[str]], num_cols: set[int] | None = None) -> str:
    num_cols = num_cols or set()
    th = "".join(f'<th class="{"num" if i in num_cols else ""}">{h}</th>'
                 for i, h in enumerate(headers))
    tb = "".join("<tr>" + "".join(
        f'<td class="{"num" if i in num_cols else ""}">{c}</td>' for i, c in enumerate(r))
        + "</tr>" for r in rows)
    return f"<table><thead><tr>{th}</tr></thead><tbody>{tb}</tbody></table>"


def formula(label: str, expr: str) -> str:
    return f'<div class="formula"><span class="lbl">{label}</span>{expr}</div>'


def steps(items: list[tuple[str, str]]) -> str:
    return '<div class="steps">' + "".join(
        f'<div class="step"><b>{a}</b><span>{b}</span></div>' for a, b in items) + "</div>"
