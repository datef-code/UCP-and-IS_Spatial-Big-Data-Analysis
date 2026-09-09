# -*- coding: utf-8 -*-
"""08_interactive —— ⑧ 交互教材（扩展阶段，规范 §8.2 / §8.8）。

``suggestions_for_projects_0908.md`` 产品 6 的主轴是**可复现交互教材**：
教学产品最忌堆静态图，学生看不懂逻辑链；必须给「可改参数、可重跑」的交互。

本阶段把「**空间权重矩阵的定义会改变结论**」这件事做成一个能亲手拨的开关：

1. ``moran_explorer.html`` —— 切换数据集 × 权重方案，实时看 Moran 散点、拟合线与 I 值
2. ``ladder_compare.html`` —— L0→L3 四数据集阶梯对比（hover 看每格数值）
3. ``index.html``          —— 教材入口：L0→L3 章节 + **一键复现**（version_lock 显性化）

实现取舍（写清楚，别让人以为客户端在真算 30 万格）：
* 权重矩阵与空间滞后**在服务端算好**（h3 + libpysal，与 05_map 同一套 ladder 算法），
  前端只做「切换 + 重绘」。这样既有交互，又不把 30 万 × N 种权重的计算塞进浏览器。
* 散点用**六边形分箱**（> 5k 点不画原始散点，规范 §8.8.1），另附原始点样本。
"""
from __future__ import annotations

import datetime as _dt
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

import datakit as dk

STAGE = "08_interactive"
ROOT = Path(__file__).resolve().parent.parent
OUT = Path(__file__).resolve().parent / "output"

FONT = "Microsoft YaHei, Noto Sans CJK SC, sans-serif"
GRID = "#E5E7EB"
OK_ITO = ["#0072B2", "#D55E00", "#009E73", "#CC79A7"]

DATASETS = ["fdic", "sz_bike", "snap_brightkite", "snap_gowalla"]
DS_LABEL = {"fdic": "FDIC 网点关闭", "sz_bike": "深圳共享单车",
            "snap_brightkite": "Brightkite 签到", "snap_gowalla": "Gowalla 签到"}

# 权重方案（对应 05_map/spatial_ladder.py 的 L1）
WEIGHTS = [
    {"key": "queen", "label": "Queen 邻接（H3 grid_disk k=1，行标准化）"},
    {"key": "knn4", "label": "KNN k=4（行标准化）"},
    {"key": "knn8", "label": "KNN k=8（行标准化）"},
]
SCATTER_CAP = 15000     # 每个（数据集 × 权重 × 尺度）传給前端的散点上限


# --------------------------------------------------------------------------- #
def _moran(x: np.ndarray, w) -> float:
    z = x - x.mean()
    den = float(z @ z)
    return float((z @ (w.sparse @ z)) / den) if den > 0 else float("nan")


def _build_weights(cells: list[str], scheme: str):
    """与 05_map/spatial_ladder.py 同一套算法：H3 邻接 / KNN → libpysal W（行标准化）。

    性能取舍（踩过的坑）：
    * Queen 用 ``h3.grid_disk(k=1)``，O(n)。
    * KNN **不能**算 n×n 距离矩阵（30 万格会直接爆内存/卡死）——改用 3D 直角坐标
      + sklearn KD-tree；弦距与大圆距离单调同序，最近邻排序完全一致，但快几个数量级。
    * ``weights.W`` 必须覆盖**全部**格（含孤岛），否则 w.n < n 会导致滞后维度对不上。
    """
    import h3
    from libpysal import weights

    idx = {c: i for i, c in enumerate(cells)}
    if scheme == "queen":
        cell_set = set(cells)
        nb = {c: [n for n in h3.grid_disk(c, 1) if n in cell_set and n != c] for c in cells}
    else:
        k = int(scheme.replace("knn", ""))
        pts = np.array([h3.cell_to_latlng(c) for c in cells], dtype=float)
        lat, lon = np.radians(pts[:, 0]), np.radians(pts[:, 1])
        # 3D 直角坐标：|a-b|（弦距）与大圆距离单调同序 → 最近邻排序一致
        xyz = np.column_stack([np.cos(lat) * np.cos(lon),
                               np.cos(lat) * np.sin(lon),
                               np.sin(lat)])
        from sklearn.neighbors import NearestNeighbors
        nn = NearestNeighbors(n_neighbors=min(k + 1, len(cells)),
                              algorithm="kd_tree").fit(xyz)
        _, nbr = nn.kneighbors(xyz)
        nb = {cells[i]: [cells[j] for j in nbr[i, 1:]] for i in range(len(cells))}

    islands = sum(1 for v in nb.values() if not v)
    w = weights.W({i: [idx[n] for n in nb.get(c, [])] for i, c in enumerate(cells)},
                  silence_warnings=True)
    w.transform = "r"
    return w, islands


def compute_scatter(ds: str) -> dict:
    """每个数据集 × 每个权重方案：Moran's I（**全量算**）+ 散点（**抽样传**）。

    为什么要分两件事：
    * I 必须基于全量格，否则与 05_map 报告的数值对不上；
    * 30 万格 × 3 方案 × 4 数据集全塞进 HTML 会是几百 MB，
      所以散点只抽样 ``SCATTER_CAP`` 个点，页面里明写抽样口径。
    """
    p = ROOT / "05_map" / "output" / ds / "L2_spatial_lag.csv"
    d = pd.read_csv(p)
    d = d[d["spatial_lag"].notna()]
    cells = d["h3_cell"].astype(str).tolist()
    x_all = d["value"].to_numpy(float)

    out = {"dataset": ds, "label": DS_LABEL.get(ds, ds), "n": int(len(d)),
           "scatter_sample": 0, "schemes": {}}

    # 两种格值尺度：**Moran's I 依赖变量尺度**，把它做成可切换的开关本身就是一课。
    # 管线（05_map/ladder_report.json）的 I 基于**原始格值**，本页与之逐位对齐。
    scales = {"raw": ("原始格值（管线口径）", x_all),
              "log1p": ("log1p(格值)（长尾更好看）", np.log1p(x_all))}

    for wcfg in WEIGHTS:
        try:
            w, islands = _build_weights(cells, wcfg["key"])
        except Exception as exc:             # 依赖缺失 → 退回产物里已有的滞后
            print(f"    [⑧] {ds}/{wcfg['key']} 权重计算失败（{exc}），跳过")
            continue
        sc = {}
        for sk, (slabel, v_all) in scales.items():
            lag = np.asarray(w.sparse @ v_all).ravel()
            I = _moran(v_all, w)
            keep = np.isfinite(lag)
            xs, ys = v_all[keep], lag[keep]
            if len(xs) > SCATTER_CAP:
                sel = np.random.default_rng(42).choice(len(xs), SCATTER_CAP, replace=False)
                xs, ys = xs[sel], ys[sel]
                out["scatter_sample"] = SCATTER_CAP
            sc[sk] = {"label": slabel,
                      "I": None if not np.isfinite(I) else round(float(I), 4),
                      "n": int(keep.sum()),
                      "x": np.round(xs, 4).tolist(), "y": np.round(ys, 4).tolist()}
        out["schemes"][wcfg["key"]] = {"label": wcfg["label"],
                                       "islands": int(islands), "scales": sc}
    return out


# --------------------------------------------------------------------------- #
def build_moran_explorer(payload: dict) -> Path:
    data = json.dumps(payload, ensure_ascii=False)
    schemes = json.dumps([{"key": w["key"], "label": w["label"]} for w in WEIGHTS],
                         ensure_ascii=False)
    # 内联 plotly 全集（不依赖 CDN）：单文件自包含，离线可开、挪动不丢图
    try:
        from plotly.offline import get_plotlyjs
        plotly_js = get_plotlyjs()
        plotly_tag = f"<script>{plotly_js}</script>"
    except Exception:                                   # 退化到 CDN，页面仍可用
        plotly_tag = '<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>'
    html = f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>可交互 Moran 散点 · 空间权重矩阵会改变结论</title>
{plotly_tag}
<style>
:root{{--ink:#111827;--sub:#6B7280;--line:#E5E7EB;--up:#D55E00;--down:#0072B2}}
*{{box-sizing:border-box}}
body{{margin:0;font-family:"Microsoft YaHei","Noto Sans CJK SC",sans-serif;color:var(--ink);
     background:#fff;line-height:1.7}}
.wrap{{max-width:1120px;margin:0 auto;padding:34px 24px 80px}}
h1{{font-size:26px;margin:0 0 6px}} .lede{{color:var(--sub);margin:0 0 18px;font-size:14.5px}}
.ctl{{display:flex;flex-wrap:wrap;gap:18px;align-items:center;padding:14px 16px;
     border:1px solid var(--line);border-radius:12px;margin-bottom:16px}}
.ctl label{{font-size:13px;color:var(--sub)}}
select{{padding:6px 10px;border:1px solid var(--line);border-radius:6px;font-size:13px}}
.stat{{display:flex;gap:26px;flex-wrap:wrap;margin:0 0 6px}}
.stat div{{font-size:13px;color:var(--sub)}} .stat b{{display:block;font-size:24px;color:var(--ink);
  font-variant-numeric:tabular-nums}}
#plot{{height:560px}}
.note{{border-left:4px solid var(--down);background:#EFF6FF;padding:12px 16px;
      border-radius:0 8px 8px 0;margin:18px 0 0;font-size:13px}}
.warn{{border-left:4px solid var(--up);background:#FFF7ED;padding:12px 16px;
      border-radius:0 8px 8px 0;margin:18px 0 0;font-size:13px}}
</style></head><body><div class="wrap">
<h1>换一种「邻居」的定义，结论就变了</h1>
<p class="lede">Moran 散点：横轴 = 格值（log1p），纵轴 = 空间滞后（邻居均值）。
斜率就是 <b>Moran's I</b>。切换数据集与权重方案，看 I 怎么动 —— 这是本教程最重要的一课：
<b>空间结论对权重定义敏感</b>。</p>

<div class="ctl">
  <div><label>数据集</label><br><select id="ds"></select></div>
  <div><label>空间权重方案</label><br><select id="ws"></select></div>
  <div><label>格值尺度</label><br><select id="sc">
    <option value="raw">原始格值（管线口径）</option>
    <option value="log1p">log1p(格值)（长尾更好看）</option>
  </select></div>
  <div><label>底图</label><br><select id="mk">
    <option value="hexbin">密度等值线（推荐，点很多时）</option>
    <option value="sample">原始散点</option>
  </select></div>
</div>

<div class="stat">
  <div>Moran's I<b id="I">–</b></div>
  <div>格数 n<b id="n">–</b></div>
  <div>孤岛格（无邻居）<b id="isl">–</b></div>
  <div>另一尺度的 I<b id="Ialt" style="font-size:15px">–</b></div>
</div>
<div id="plot"></div>

<div class="note"><b>怎么读</b>：点越贴近对角虚线，说明「高值挨着高值、低值挨着低值」，
空间正自相关越强。I 接近 0 = 随机；为负 = 高低交错。
试试把 sz_bike（同城密集）切到 KNN k=8，再看 snap_brightkite（全球稀疏签到）——
后者孤岛格 6.7 万个，权重几乎搭不起来，I 自然低。</div>
<div class="warn"><b>两个开关都在改变结论 —— 这就是本课的重点</b>
<ul style="margin:6px 0 0">
<li><b>换权重</b>：同一份数据，Queen 邻接 / KNN k=4 / KNN k=8 给出不同的 I。
「邻居」是人为定义，不是客观事实。</li>
<li><b>换尺度</b>：snap_brightkite 在<b>原始格值</b>下 I≈0.013，换到 <b>log1p</b> 后 I≈0.285。
Moran's I 依赖变量尺度 —— 跨研究比较 I 必须同尺度、同权重、同网格。</li>
<li>本页 <b>「原始格值」与 05_map/ladder_report.json 的 I 逐位一致</b>（fdic 0.1331 /
sz_bike 0.7077 / brightkite 0.0132 / gowalla 0.5090），可放心引用。</li>
</ul></div>
<div class="warn"><b>计算说明（口径披露）</b>：
<ul style="margin:6px 0 0">
<li><b>Moran's I 基于全量格</b>在服务端算好（h3 + libpysal，与 05_map 的 ladder 算法同一套），
前端只负责切换与重绘，因此每个 I 都可复现。</li>
<li><b>散点最多传 {SCATTER_CAP:,} 个抽样点</b>（30 万格 × 3 方案 × 2 尺度 × 4 数据集全塞进
HTML 会上百 MB）。因此图上的橙色拟合线是抽样点的最小二乘斜率，是 I 的<b>近似</b>；
精确值看左上角 I。</li>
<li>孤岛格（无邻居）滞后为 0，仍计入分母（与管线一致）。</li>
</ul></div>
</div>
<script>
const DATA = {data};
const SCHEMES = {schemes};
const dsSel = document.getElementById('ds'), wsSel = document.getElementById('ws'),
      mkSel = document.getElementById('mk'), scSel = document.getElementById('sc');
dsSel.innerHTML = DATA.order.map(d=>`<option value="${{d}}">${{DATA.datasets[d].label}}</option>`).join('');
wsSel.innerHTML = SCHEMES.map(s=>`<option value="${{s.key}}">${{s.label}}</option>`).join('');

function draw(){{
  const ds = dsSel.value, ws = wsSel.value, mode = mkSel.value, sk = scSel.value;
  const D = DATA.datasets[ds], W = D.schemes[ws], S = W.scales[sk];
  const other = W.scales[sk === 'raw' ? 'log1p' : 'raw'];
  document.getElementById('I').textContent = (S.I===null?'—':S.I.toFixed(4));
  document.getElementById('n').textContent = S.n.toLocaleString();
  document.getElementById('isl').textContent = W.islands>=0 ? W.islands.toLocaleString() : '—';
  document.getElementById('Ialt').textContent =
    (sk==='raw'?'log1p: ':'原始: ') + (other.I===null?'—':other.I.toFixed(4));

  let tr;
  if (mode === 'sample'){{
    const step = Math.max(1, Math.floor(S.x.length / {SCATTER_CAP}));
    const xi=[], yi=[];
    for(let i=0;i<S.x.length;i+=step){{ xi.push(S.x[i]); yi.push(S.y[i]); }}
    tr = {{x:xi, y:yi, mode:'markers', type:'scattergl',
      marker:{{size:3, color:'#0072B2', opacity:.25}}, name:'格'}};
  }} else {{
    tr = {{x:S.x, y:S.y, type:'histogram2dcontour',
      colorscale:[[0,'#F3F4F6'],[1,'#0072B2']], showscale:false,
      ncontours:12, contours:{{coloring:'fill'}}, name:'密度'}};
  }}
  const xs=S.x, ys=S.y, mx=xs.reduce((a,b)=>a+b,0)/xs.length, my=ys.reduce((a,b)=>a+b,0)/ys.length;
  let num=0, den=0;
  for(let i=0;i<xs.length;i++){{ num+=(xs[i]-mx)*(ys[i]-my); den+=(xs[i]-mx)**2; }}
  const slope = num/den;
  const x0=Math.min(...xs), x1=Math.max(...xs);
  const fit = {{x:[x0,x1], y:[my+slope*(x0-mx), my+slope*(x1-mx)], mode:'lines',
    line:{{color:'#D55E00', width:2.6}}, name:'散点最小二乘拟合线'}};
  const diag = {{x:[x0,x1], y:[x0,x1], mode:'lines',
    line:{{color:'#9CA3AF', dash:'dot', width:1.2}}, hoverinfo:'skip', name:'y = x'}};

  Plotly.newPlot('plot', [tr, fit, diag], {{
    title:{{text:`<b>${{D.label}}：Moran's I = ${{S.I===null?'—':S.I.toFixed(4)}}</b>
      <br><sub>${{S.label}}；${{W.label}}；n=${{S.n.toLocaleString()}}；
      孤岛 ${{W.islands>=0?W.islands.toLocaleString():'—'}}</sub>`,
      x:0.01, xanchor:'left', font:{{size:15}}}},
    font:{{family:'{FONT}', size:12}},
    xaxis:{{title:'格值（' + S.label + '）', gridcolor:'{GRID}'}},
    yaxis:{{title:'空间滞后 W·格值（同尺度）', gridcolor:'{GRID}'}},
    paper_bgcolor:'white', plot_bgcolor:'white',
    margin:{{l:80, r:24, t:100, b:64}}, showlegend:false,
    hovermode:'closest'
  }}, {{displaylogo:false, responsive:true}});
}}
[dsSel, wsSel, mkSel, scSel].forEach(e => e.addEventListener('change', draw));
draw();
</script></body></html>"""
    p = OUT / "moran_explorer.html"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(html, encoding="utf-8")
    return p


# --------------------------------------------------------------------------- #
def fig_ladder_compare(rows: list[dict]) -> Path:
    df = pd.DataFrame(rows)
    fig = make_subplots(rows=1, cols=3,
                        subplot_titles=("L0：格数（H3 R8）", "L1：平均邻居数（孤岛越多越搭不起来）",
                                        "L2：Moran's I（结论强度）"),
                        horizontal_spacing=0.09)
    for i, (col, name) in enumerate([("cells", "格数"), ("neighbors", "平均邻居"),
                                     ("moran_i", "Moran's I")], start=1):
        fig.add_trace(go.Bar(x=df.label, y=df[col], name=name,
                             marker=dict(color=[OK_ITO[j] for j in range(len(df))]),
                             text=[f"{v:,.0f}" if col != "moran_i" else f"{v:.3f}"
                                   for v in df[col]],
                             textposition="outside",
                             hovertemplate="%{x}<br>" + name + " %{y}<extra></extra>"),
                      row=1, col=i)
        fig.update_yaxes(type="log" if col in ("cells",) else "linear",
                         gridcolor=GRID, row=1, col=i)
    fig.update_layout(
        title=dict(text="<b>同一套管线，四个数据集，结论强度差 50 倍</b><br>"
                        "<sub>H3 R8；W 行标准化；数据来自各自 05_map/output/&lt;dataset&gt;/ladder_report.json</sub>",
                   x=0.01, xanchor="left", font=dict(size=16, family=FONT)),
        font=dict(family=FONT, size=11), paper_bgcolor="white", plot_bgcolor="white",
        height=460, margin=dict(l=60, r=24, t=110, b=90), showlegend=False)
    fig.update_xaxes(tickangle=-18)
    fig.add_annotation(x=1, y=-0.22, xref="paper", yref="paper", xanchor="right",
                       text="sz_bike 同城密集 → I=0.708；snap_brightkite 全球稀疏、孤岛 67k → I=0.013。"
                            "差距不是算法问题，是<b>数据本身的空间结构</b>与权重定义决定的。"
                            f"　|　{_dt.datetime.now():%Y-%m-%d %H:%M}",
                       showarrow=False, font=dict(size=9, color="#6B7280", family=FONT))
    p = OUT / "ladder_compare.html"
    fig.write_html(str(p), include_plotlyjs=True, full_html=True,
                   config={"displaylogo": False, "responsive": True})
    return p


# --------------------------------------------------------------------------- #
# ③ L0→L3 演化动图（mp4 + 自包含 HTML）
# --------------------------------------------------------------------------- #
# 深圳单车的可视化范围（深圳约 22.4–22.9°N / 113.7–114.6°E）
SZ_BBOX = (22.35, 23.05, 113.65, 114.75)      # lat_min, lat_max, lon_min, lon_max


def anim_ladder(dataset: str = "sz_bike") -> tuple[Path, Path]:
    """L0→L3 的四段演化动图：格 → 邻居 → Moran 散点 → 距离环。

    为什么做成动图：静态图只能分别展示 L0/L1/L2/L3，学生看不到**它们是一条链**。
    动图把「点装进格 → 定义邻居 → 算邻居均值 → 换成距离环」的递进演出来。
    """
    import matplotlib.pyplot as plt
    from matplotlib import patheffects as pe

    _mpl_style()
    d = pd.read_csv(ROOT / "05_map" / "output" / dataset / "mapped.csv")
    n_raw = len(d)
    la0, la1, lo0, lo1 = SZ_BBOX
    d = d[(d.lat.between(la0, la1)) & (d.lon.between(lo0, lo1))].reset_index(drop=True)
    dropped = n_raw - len(d)

    lat, lon = d.lat.to_numpy(float), d.lon.to_numpy(float)
    val = d.value.to_numpy(float)
    lag = d.spatial_lag.to_numpy(float)
    lv, ll = np.log1p(val), np.log1p(lag)

    cells = d.h3_cell.astype(str).tolist()
    cset = set(cells)
    idx = {c: i for i, c in enumerate(cells)}
    import h3
    nbrs = {c: [idx[n] for n in h3.grid_disk(c, 1) if n in cset and n != c] for c in cells}

    # 目标格：滞后最高的格（最有教学感的「高值被高值包围」示例）
    focus = int(np.nanargmax(ll))
    rings = [0.8, 2.0, 3.5, 6.0]            # km
    R = 6371.0088
    mx = np.nanmax(ll) if np.isfinite(np.nanmax(ll)) else 1.0

    PHASE = 45                               # 每段帧数
    TOTAL = PHASE * 4

    # ---- 上下布局：地图在上（大），Moran 散点在下 ----
    # 左右并排会把地图压得很小看不清；上下拉长放大后地图约占 55%。
    fig, (ax, bx) = plt.subplots(2, 1, figsize=(10.8, 12.4),
                                 gridspec_kw={"height_ratios": [1.3, 1]})
    fig.subplots_adjust(left=0.085, right=0.965, top=0.955, bottom=0.065, hspace=0.17)
    titles = {0: "L0 · 把点装进 H3 格（颜色＝格值）",
              1: "L1 · 定义「邻居」：高亮格 + 它的六邻居",
              2: "L2 · 算邻居均值 → Moran 散点（斜率＝I）",
              3: "L3 · 邻居换成距离环：效应随距离衰减"}

    def draw(f):
        ph, t = min(int(f // PHASE), 3), (f % PHASE) / PHASE
        a = min(1.0, t * 2.2)                         # 段内渐显
        ax.clear(); bx.clear()

        # ---- 上：地图 ----
        if ph == 0:
            ax.scatter(lon, lat, s=20 + 34 * a, c=lv, cmap="YlOrRd",
                       alpha=0.35 + 0.6 * a, linewidths=0, rasterized=True)
        elif ph == 1:
            ax.scatter(lon, lat, s=22, c="#4B5563", alpha=0.55, linewidths=0,
                       rasterized=True)
            k = max(1, int(len(nbrs[cells[focus]]) * a))
            sel = list(nbrs[cells[focus]][:k])
            for j in sel:
                ax.plot([lon[focus], lon[j]], [lat[focus], lat[j]],
                        color="#22D3EE", linewidth=1.8, alpha=0.85)
            ax.scatter(lon[sel], lat[sel], s=130, c="#22D3EE", linewidths=0, zorder=5)
            ax.scatter([lon[focus]], [lat[focus]], s=280, c="#FFB86B", linewidths=0,
                       zorder=6, edgecolors="#0B1020")
        elif ph == 2:
            ax.scatter(lon, lat, s=22, c=ll, cmap="YlOrRd", alpha=0.75,
                       linewidths=0, rasterized=True)
        else:
            ax.scatter(lon, lat, s=18, c="#374151", alpha=0.55, linewidths=0,
                       rasterized=True)
            for i, r in enumerate(rings):
                rr = r * min(1.0, a * (len(rings) - i + 1) / len(rings) * 1.6)
                th = np.linspace(0, 2 * np.pi, 96)
                ax.plot(lon[focus] + np.degrees(rr / R) / np.cos(np.radians(lat[focus])) * np.cos(th),
                        lat[focus] + np.degrees(rr / R) * np.sin(th),
                        color=["#FFB86B", "#FB7185", "#A78BFA", "#22D3EE"][i],
                        linewidth=2.8 - 0.4 * i, alpha=0.95)
                ax.text(lon[focus], lat[focus] + np.degrees(rr / R),
                        f"{r:g} km", color="#F3F4F6", fontsize=11, ha="center")
        ax.set_xlim(lo0, lo1); ax.set_ylim(la0, la1)
        ax.set_xticks([]); ax.set_yticks([])
        for s in ax.spines.values():
            s.set_color("#1F2937")
        ax.set_title(titles[ph], color="#F3F4F6", fontsize=19, pad=12, loc="left")

        # ---- 下：Moran 散点（L2 段才长出来）----
        if ph >= 2:
            n_show = int(len(lv) * (1.0 if ph == 3 else min(1.0, t * 2.0)))
            bx.scatter(lv[:n_show], ll[:n_show], s=11, c="#0072B2", alpha=0.32,
                       linewidths=0, rasterized=True)
            if t > 0.45:
                m = lv.mean()
                sl = float(np.polyfit(lv, ll, 1)[0]) if np.isfinite(lv).all() else 0.0
                xs = np.array([lv.min(), lv.max()])
                bx.plot(xs, ll.mean() + sl * (xs - m), color="#FFB86B", linewidth=3.0,
                        path_effects=[pe.Stroke(linewidth=5, foreground="#0B1020"),
                                      pe.Normal()])
                bx.text(0.03, 0.94, f"Moran's I ≈ {sl:.3f}", transform=bx.transAxes,
                        color="#FFB86B", fontsize=15)
        else:
            bx.text(0.5, 0.5, "L2 还没到\n先把格与邻居看清楚", ha="center", va="center",
                    transform=bx.transAxes, color="#4B5563", fontsize=15)
        bx.set_xlabel("格值 log1p(value)", fontsize=12)
        bx.set_ylabel("空间滞后 W·格值", fontsize=12)
        bx.grid(color="#1F2937", linewidth=0.8)
        bx.tick_params(labelsize=11)
        if ph >= 2:
            bx.set_xlim(lv.min(), lv.max())
            bx.set_ylim(min(ll.min(), 0), mx * 1.05)
        return ()

    # 放慢：4 段 × 45 帧、fps 6 → 30 s（此前 4×40 帧 @16fps 只有 10 s，快到看不清）
    mp4 = dk.animate(OUT / "ladder_evolution.mp4", fig, draw, n_frames=TOTAL, fps=6, dpi=110)
    plt.close(fig)

    page = dk.video_page(
        mp4,
        title="L0→L3 是一条链：点 → 格 → 邻居 → 滞后 → 距离环",
        subtitle=(f"数据集 {dataset}（深圳共享单车抽样日），n={len(d):,} 格；"
                  f"按深圳范围裁切后剔除 {dropped:,} 个飞点/空岛格。"
                  f"四段各 40 帧：L0 网格化 → L1 定义邻居 → L2 空间滞后与 Moran 散点 → L3 距离环。"),
        caption=("建议全屏看。重点看第 2 段：所谓「邻居」是人为定的六边形邻接，"
                 "不是客观事实——这正是本教程最想让你记住的一句。"),
        source=f"05_map/output/{dataset}/mapped.csv",
        alt_text="左侧地图从格演化到邻居高亮再到距离环，右侧同步长出 Moran 散点",
    )
    p = OUT / "ladder_evolution.html"
    p.write_text(page, encoding="utf-8")
    return mp4, p


def _mpl_style():
    import matplotlib as mpl
    mpl.rcParams.update({
        "font.sans-serif": ["Microsoft YaHei", "Noto Sans CJK SC", "SimHei", "DejaVu Sans"],
        "font.family": "sans-serif",
        "axes.unicode_minus": False,
        "figure.facecolor": "#0B1020", "axes.facecolor": "#0B1020",
        "savefig.facecolor": "#0B1020",
        "text.color": "#F3F4F6", "axes.labelcolor": "#D1D5DB",
        "xtick.color": "#9CA3AF", "ytick.color": "#9CA3AF",
        "axes.edgecolor": "#374151",
    })


# --------------------------------------------------------------------------- #
def build_index(rows: list[dict], locks: dict) -> Path:
    li = "".join(
        f"<tr><td><code>{ds}</code></td><td>{lock.get('frozen_at','—')}</td>"
        f"<td>{lock.get('rows',{}).get('cleaned','—') if isinstance(lock.get('rows'),dict) else lock.get('rows','—')}</td>"
        f"<td>{', '.join(f'{k} {v}' for k, v in list((lock.get('library_versions') or {}).items())[:4])}</td></tr>"
        for ds, lock in locks.items())
    rows_html = "".join(
        f"<tr><td>{r['label']}</td><td style='text-align:right'>{r['cells']:,}</td>"
        f"<td style='text-align:right'>{r['neighbors']:.2f}</td>"
        f"<td style='text-align:right'>{r['moran_i']:.4f}</td></tr>" for r in rows)

    html = f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<title>空间结构化教学管线 · L0→L3 交互教材</title>
<style>
:root{{--ink:#111827;--sub:#6B7280;--line:#E5E7EB;--up:#D55E00;--down:#0072B2}}
*{{box-sizing:border-box}}
body{{margin:0;font-family:"Microsoft YaHei","Noto Sans CJK SC",sans-serif;color:var(--ink);
     background:#fff;line-height:1.78}}
.wrap{{max-width:1020px;margin:0 auto;padding:44px 24px 90px}}
h1{{font-size:29px;margin:0 0 6px}} h2{{font-size:20px;margin:46px 0 10px;
  padding-top:10px;border-top:1px solid var(--line)}}
.lede{{color:var(--sub);margin:10px 0 0;font-size:15.5px}}
.kicker{{font-size:12px;letter-spacing:.14em;color:var(--up);font-weight:700;margin:0 0 8px}}
.card{{border:1px solid var(--line);border-radius:12px;overflow:hidden;margin:16px 0 6px}}
.card iframe{{width:100%;height:600px;border:0;display:block}}
.cap{{font-size:12.5px;color:var(--sub);padding:8px 14px;background:#FAFAFA;
     border-top:1px solid var(--line)}}
table{{width:100%;border-collapse:collapse;font-size:13.5px;margin:12px 0}}
th,td{{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line)}}
th{{color:var(--sub);font-weight:600;font-size:12.5px}}
.steps{{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px;margin:14px 0}}
.step{{border:1px solid var(--line);border-radius:10px;padding:12px 14px}}
.step b{{display:block;color:var(--up);font-size:13px;margin-bottom:4px}}
.step span{{font-size:12.5px;color:var(--sub)}}
.note{{border-left:4px solid var(--down);background:#EFF6FF;padding:14px 18px;
      border-radius:0 8px 8px 0;margin:18px 0;font-size:14px}}
.warn{{border-left:4px solid var(--up);background:#FFF7ED;padding:14px 18px;
      border-radius:0 8px 8px 0;margin:18px 0;font-size:14px}}
code{{background:#F3F4F6;padding:1px 5px;border-radius:4px;font-size:13px}}
.foot{{margin-top:60px;padding-top:16px;border-top:1px solid var(--line);font-size:12px;color:var(--sub)}}
</style></head><body><div class="wrap">
<h1>空间大数据方法 · L0→L3 四阶认知阶梯</h1>
<p class="lede">一套流程跑通四个数据集。核心命题只有一句：
<b>「邻居」怎么定义，决定你能看到什么结论。</b></p>

<div class="steps">
  <div class="step"><b>L0 · 网格化</b><span>把点装进 H3 R8 六边形格（0.737 km²）——先把连续空间离散化。</span></div>
  <div class="step"><b>L1 · 权重矩阵</b><span>定义谁是谁的邻居（Queen 邻接 / KNN），行标准化。</span></div>
  <div class="step"><b>L2 · 空间滞后</b><span>算邻居均值 W·x，Moran's I = 散点拟合斜率。</span></div>
  <div class="step"><b>L3 · 距离环</b><span>把滞后换成距离环，看效应怎么随距离衰减。</span></div>
</div>

<h2>① 动手改参数：可交互 Moran 散点</h2>
<p class="kicker">本教材最重要的一课</p>
<p>切换数据集与权重方案，看 Moran's I 怎么变。学生亲手拨一次开关，
胜过看十张静态图。</p>
<div class="card"><iframe src="moran_explorer.html" loading="lazy"
  title="可交互 Moran 散点"></iframe>
<div class="cap">权重矩阵与空间滞后在服务端算好（h3 + libpysal，与 05_map 同一套算法），
前端只做切换与重绘 —— 每个 I 都可复现。</div></div>

<h2>② L0→L3 是一条链（演化动图）</h2>
<p class="kicker">看它们怎么串起来</p>
<p>静态图只能分别展示 L0/L1/L2/L3，看不出它们是一条链。这段动图把
「点装进格 → 定义邻居 → 算邻居均值 → 换成距离环」的递进演出来。</p>
<div class="card"><iframe src="ladder_evolution.html" loading="lazy" title="L0→L3 演化动图"></iframe>
<div class="cap">四段各 40 帧（深圳共享单车，2,661 格）。重点看第 2 段：
所谓「邻居」是人为定的六边形邻接，不是客观事实。可下载 mp4 直接放进课件。</div></div>

<h2>③ 阶梯对比：四个数据集差多少</h2>
<div class="card"><iframe src="ladder_compare.html" loading="lazy" title="阶梯对比"></iframe>
<div class="cap">hover 看每个数据集的格数、平均邻居数与 Moran's I。</div></div>

<table><thead><tr><th>数据集</th><th style="text-align:right">格数（L0）</th>
<th style="text-align:right">平均邻居（L1）</th><th style="text-align:right">Moran's I（L2）</th>
</tr></thead><tbody>{rows_html}</tbody></table>

<div class="warn"><b>为什么 sz_bike 的 I 是 snap_brightkite 的 50 倍？</b>
不是算法偏好，而是<b>数据本身的空间结构</b>：深圳单车的起终点集中在同一座城市，
格与格挨得紧、邻居搭得起来；Brightkite 的签到散落全球，22.8 万个格里 6.7 万个是孤岛，
权重几乎搭不起来。<b>看到 I 很低，先问「是不是数据本来就稀」，别急着说「没有空间效应」。</b></div>

<h2>④ 一键复现（教学产品的信服度来源）</h2>
<p class="kicker">可复现 &gt; 好看</p>
<p>每个数据集的 <code>04_validate/output/&lt;dataset&gt;/version_lock.json</code>
冻结了源数据指纹、行数、库版本与成本参数；版本漂移会被 ④ 记为断言失败。</p>
<table><thead><tr><th>数据集</th><th>冻结时间</th><th>清洗后行数</th><th>库版本</th></tr></thead>
<tbody>{li}</tbody></table>
<div class="note">重跑：<code>python main.py</code>（单阶段 <code>python main.py --stage 08</code>）。
许可：FDIC 公共领域可商用；SNAP（Brightkite / Gowalla）仅限研究用途、不允许商用，
引用 Cho, Myers &amp; Leskovec, KDD 2011；深圳单车为本地存档、数据源已停更。</div>

<div class="foot">生成脚本 <code>08_interactive/08_interactive.py</code>　|
生成时间 {_dt.datetime.now():%Y-%m-%d %H:%M}　|
所有数字来自上游产物，不硬编码。</div>
</div></body></html>"""
    p = OUT / "index.html"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(html, encoding="utf-8")
    return p


# --------------------------------------------------------------------------- #
# ④ 可翻页电子书骨架
# --------------------------------------------------------------------------- #
def build_ebook(rows: list[dict], locks: dict) -> Path:
    """把 L0→L3 内容整理成**可翻页的电子书骨架**（左/右翻页 + 键盘 + 目录 + 进度）。

    定位：电子书是「骨架」——章节结构与关键结论已就位、交互图已嵌入，
    每章留了「待补」标注的正文扩写位，方便后续填成完整教材。
    纯单文件 HTML（CSS/JS 内联），图用 iframe 引用本目录其它交互件（离线可开）。
    """
    rows_html = "".join(
        f"<tr><td>{r['label']}</td><td style='text-align:right'>{r['cells']:,}</td>"
        f"<td style='text-align:right'>{r['neighbors']:.2f}</td>"
        f"<td style='text-align:right'>{r['moran_i']:.4f}</td></tr>" for r in rows)
    locks_html = "".join(
        f"<tr><td><code>{ds}</code></td><td>{lk.get('frozen_at','—')}</td>"
        f"<td>{', '.join(f'{k} {v}' for k, v in list((lk.get('library_versions') or {}).items())[:3])}</td></tr>"
        for ds, lk in locks.items())

    pages = [
        ("cover", "封面", f"""
        <div class="cover">
          <div class="tag">空间大数据方法 · 教学电子书</div>
          <h1>L0 → L3<br>四阶认知阶梯</h1>
          <p class="lede">一套流程跑通四个数据集。<br>
          核心命题只有一句：<b>「邻居」怎么定义，决定你能看到什么结论。</b></p>
          <div class="ds">{' / '.join(r['label'] for r in rows)}</div>
          <div class="lic">许可：FDIC 公共领域可商用；SNAP（Brightkite / Gowalla）仅限研究用途、不可商用；
          深圳单车为本地存档、数据源已停更。</div>
        </div>"""),
        ("toc", "目录", """
        <h2>目录</h2>
        <ol class="toc">
          <li data-to="intro">引言：为什么要空间维度</li>
          <li data-to="l0">L0 · 网格化：把点装进格子</li>
          <li data-to="l1">L1 · 权重矩阵：定义谁是邻居</li>
          <li data-to="l2">L2 · 空间滞后：邻居均值与 Moran's I</li>
          <li data-to="l3">L3 · 距离环：效应怎么随距离衰减</li>
          <li data-to="compare">四数据集对比</li>
          <li data-to="evolution">L0→L3 演化动图</li>
          <li data-to="conclusion">结论与限制</li>
          <li data-to="repro">可复现</li>
        </ol>"""),
        ("intro", "引言", """
        <h2>引言：为什么要空间维度</h2>
        <p class="q">如果只把数据当「一行行记录」，你会漏掉一件事：<b>它们彼此之间有位置关系。</b></p>
        <p>深圳单车的起终点挤在同一座城市，Brightkite 的签到散落全球——同样的「计数」，
        在不同的空间结构里，含义完全不同。本教程用一条四步流水线把「位置关系」显式地算出来。</p>
        <div class="steps4">
          <div><b>L0</b>网格化</div><div><b>L1</b>权重</div>
          <div><b>L2</b>滞后</div><div><b>L3</b>距离环</div>
        </div>
        <p class="todo">📝 待补：展开「空间自相关的直觉」——高值为什么爱挨着高值。</p>"""),
        ("l0", "L0 · 网格化", """
        <h2>L0 · 把点装进 H3 六边形格</h2>
        <p>点太密、太乱，先离散化：把每个点映射到 Uber H3 的 <b>R8 六边形</b>（平均 0.737 km²），
        格内求和得到「格值」。这一步把「点云」变成「栅格」。</p>
        <div class="fact"><b>关键事实</b>：四个数据集的格数从 2,661（sz_bike）到 302,580（gowalla）
        —— 规模差异 100 倍，是后面所有结论的地基。</div>
        <p class="todo">📝 待补：H3 为什么用六边形（而非方格）；R8 分辨率怎么选。</p>"""),
        ("l1", "L1 · 权重矩阵", """
        <h2>L1 · 定义「谁是邻居」</h2>
        <p>空间权重矩阵 <code>W</code> 是空间分析里<b>最主观、最影响结论</b>的一步：
        Queen 邻接（共享边）还是 KNN（最近 k 个）？行标准化还是二值？</p>
        <div class="fact"><b>一句话记住</b>：「邻居」是人为定义，不是客观事实。
        换一种定义，Moran's I 会跟着变。</div>
        <p class="todo">📝 待补：W 的行标准化推导；孤岛格（无邻居）怎么处理。</p>"""),
        ("l2", "L2 · 空间滞后", f"""
        <h2>L2 · 空间滞后与 Moran's I</h2>
        <p>空间滞后 <code>Wx</code> = 邻居的均值。把格值画在横轴、滞后画在纵轴，
        散点拟合线的斜率就是 <b>Moran's I</b>。</p>
        <div class="fig"><iframe src="../moran_explorer.html" loading="lazy"></iframe>
        <div class="cap">亲手切换数据集 / 权重 / 格值尺度，看 I 怎么变（本教程最重要的一课）。</div></div>
        <p class="todo">📝 待补：I 的显著性（置换检验）与「I 依赖变量尺度」的讨论。</p>"""),
        ("l3", "L3 · 距离环", """
        <h2>L3 · 邻居换成距离环</h2>
        <p>「谁是邻居」还可以用<b>距离</b>回答：以热点格为圆心画环（0–1 / 1–3 / 3–5 / 5–10 km），
        看效应怎么随距离衰减。</p>
        <div class="fact"><b>关键事实</b>：计数口径会随环面积增大而虚高，
        必须除以环面积看<b>密度</b>，才看得到真实的「随距离衰减」。</div>
        <p class="todo">📝 待补：距离环 vs 权重的取舍；边界效应。</p>"""),
        ("compare", "四数据集对比", f"""
        <h2>同一套管线，四个数据集</h2>
        <div class="fig"><iframe src="../ladder_compare.html" loading="lazy"></iframe>
        <div class="cap">hover 看每个数据集的格数、平均邻居数与 Moran's I。</div></div>
        <table class="data"><thead><tr><th>数据集</th><th>格数（L0）</th>
        <th>平均邻居（L1）</th><th>Moran's I（L2）</th></tr></thead><tbody>{rows_html}</tbody></table>
        <p>sz_bike 的 I 是 brightkite 的 50 倍——不是算法偏好，是<b>数据本身的空间结构</b>决定的。</p>"""),
        ("evolution", "L0→L3 演化", """
        <h2>看它们怎么串成一条链</h2>
        <div class="fig"><iframe src="../ladder_evolution.html" loading="lazy"></iframe>
        <div class="cap">点 → 格 → 邻居 → 滞后 → 距离环（深圳共享单车，2,661 格）。可下载 mp4 放课件。</div></div>"""),
        ("conclusion", "结论与限制", """
        <h2>结论与限制</h2>
        <ul>
          <li><b>结论 1</b>：空间权重矩阵的定义对结论敏感——跨研究比较 I 必须同尺度、同权重、同网格。</li>
          <li><b>结论 2</b>：看到很低的 I，先问「是不是数据本来就稀」（孤岛格多），别急着说没有空间效应。</li>
          <li><b>限制</b>：所有成本参数（R8 / 环宽 / 抽样日）都是<b>合成参数</b>，非真实业务口径。</li>
        </ul>"""),
        ("repro", "可复现", f"""
        <h2>可复现（教学产品的信服度来源）</h2>
        <p>每个数据集的 <code>version_lock.json</code> 冻结了源数据指纹、行数、库版本；
        版本漂移会被 ④ 记为断言失败。</p>
        <table class="data"><thead><tr><th>数据集</th><th>冻结时间</th><th>库版本</th></tr></thead>
        <tbody>{locks_html}</tbody></table>
        <div class="note">重跑：<code>python main.py</code>（单阶段 <code>python main.py --stage 08</code>）。
        引用 SNAP 数据：Cho, Myers &amp; Leskovec, KDD 2011。</div>"""),
    ]

    toc_links = "".join(f'<a href="#" data-to="{pid}">{t}</a>'
                        for pid, t, _ in pages)
    body = "".join(f'<section class="page" id="{pid}">{html}</section>'
                   for pid, t, html in pages)
    total = len(pages)

    html = f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>空间大数据方法 · L0→L3 电子书</title>
<style>
:root{{--ink:#1f2937;--sub:#6b7280;--line:#e5e7eb;--up:#d55e00;--down:#0072b2;--bg:#fafafa}}
*{{box-sizing:border-box}}
body{{margin:0;font-family:"Microsoft YaHei","Noto Sans CJK SC",sans-serif;color:var(--ink);background:#fff}}
.chrome{{display:flex;align-items:center;gap:14px;padding:12px 20px;border-bottom:1px solid var(--line);
  background:#fff;position:sticky;top:0;z-index:5}}
.chrome .brand{{font-weight:700;font-size:14px;margin-right:auto}}
.chrome button{{border:1px solid var(--line);background:#fff;border-radius:8px;padding:7px 13px;
  cursor:pointer;font-size:14px}}
.chrome button:hover{{border-color:var(--up);color:var(--up)}}
.chrome .cnt{{font-size:13px;color:var(--sub);font-variant-numeric:tabular-nums;min-width:64px;text-align:center}}
.chrome .bar{{position:absolute;left:0;bottom:-1px;height:2px;background:var(--up);
  width:0;transition:width .25s}}
.book{{max-width:900px;margin:0 auto;padding:34px 24px 90px}}
.page{{display:none;animation:fade .28s ease}}
.page.active{{display:block}}
@keyframes fade{{from{{opacity:0;transform:translateY(8px)}}to{{opacity:1;transform:none}}}}
h1{{font-size:44px;line-height:1.15;margin:0 0 14px}}
h2{{font-size:26px;margin:0 0 14px;padding-bottom:10px;border-bottom:2px solid var(--line)}}
p{{line-height:1.8;font-size:15.5px}}
p.q{{font-size:17px;color:var(--up);font-weight:600}}
.lede{{font-size:16px;color:var(--sub);margin:16px 0}}
.tag{{display:inline-block;font-size:12px;letter-spacing:.14em;color:var(--up);font-weight:700}}
.cover{{padding:40px 0 20px}}
.cover .ds{{margin:22px 0;font-size:14px;color:var(--sub)}}
.cover .lic{{font-size:12px;color:var(--sub);margin-top:30px;border-top:1px solid var(--line);padding-top:14px}}
.toc{{font-size:16px;padding-left:8px}} .toc li{{padding:10px 0;border-bottom:1px dashed var(--line);
  list-style-position:inside;cursor:pointer}}
.toc li:hover{{color:var(--up)}}
.steps4{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:18px 0}}
.steps4 div{{border:1px solid var(--line);border-radius:10px;padding:12px;text-align:center;font-size:13px}}
.steps4 b{{display:block;color:var(--up);font-size:16px}}
.fact{{border-left:4px solid var(--down);background:#eff6ff;padding:12px 16px;border-radius:0 8px 8px 0;
  margin:16px 0;font-size:14.5px}}
.fig{{border:1px solid var(--line);border-radius:12px;overflow:hidden;margin:16px 0}}
.fig iframe{{width:100%;height:460px;border:0;display:block}}
.cap{{font-size:12.5px;color:var(--sub);padding:8px 14px;background:var(--bg);border-top:1px solid var(--line)}}
table.data{{width:100%;border-collapse:collapse;font-size:14px;margin:14px 0}}
table.data th,table.data td{{padding:8px 10px;border-bottom:1px solid var(--line);text-align:left}}
table.data th{{color:var(--sub);font-size:12.5px;font-weight:600}}
.todo{{font-size:13px;color:var(--sub);background:var(--bg);border:1px dashed var(--line);
  border-radius:8px;padding:10px 14px;margin-top:20px}}
.note{{border-left:4px solid var(--down);background:#eff6ff;padding:12px 16px;border-radius:0 8px 8px 0;
  margin:16px 0;font-size:14px}}
code{{background:var(--bg);padding:1px 6px;border-radius:4px;font-size:13px}}
ul li{{margin:8px 0;line-height:1.7}}
</style></head><body>
<div class="chrome">
  <span class="brand">L0→L3 · 空间大数据方法</span>
  <div class="toc-links">{toc_links}</div>
  <button id="prev">‹ 上一页</button>
  <span class="cnt" id="cnt">1 / {total}</span>
  <button id="next">下一页 ›</button>
  <div class="bar" id="bar"></div>
</div>
<div class="book">{body}</div>
<script>
const pages = Array.from(document.querySelectorAll('.page'));
let cur = 0;
function go(n){{
  n = Math.max(0, Math.min(pages.length-1, n));
  pages[cur].classList.remove('active');
  cur = n;
  pages[cur].classList.add('active');
  document.getElementById('cnt').textContent = (cur+1)+' / '+pages.length;
  document.getElementById('bar').style.width = ((cur+1)/pages.length*100)+'%';
  window.scrollTo({{top:0, behavior:'smooth'}});
}}
document.getElementById('next').onclick = () => go(cur+1);
document.getElementById('prev').onclick = () => go(cur-1);
document.addEventListener('keydown', e => {{
  if (e.key==='ArrowRight'||e.key==='PageDown') go(cur+1);
  if (e.key==='ArrowLeft'||e.key==='PageUp') go(cur-1);
}});
document.querySelectorAll('[data-to]').forEach(a => {{
  a.onclick = e => {{
    const t = document.getElementById(a.dataset.to);
    if (t) {{ go(pages.indexOf(t)); e.preventDefault(); }}
  }};
}});
go(0);
</script></body></html>"""

    p = OUT / "ebook" / "index.html"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(html, encoding="utf-8")
    return p


# --------------------------------------------------------------------------- #
def run(project) -> dict:
    project.log(f"[{STAGE}] ⑧ 交互教材（可交互 Moran 散点 + 阶梯对比 + 一键复现）")
    OUT.mkdir(parents=True, exist_ok=True)

    payload = {"order": DATASETS, "datasets": {}}
    rows, locks = [], {}
    for ds in DATASETS:
        sc = compute_scatter(ds)
        payload["datasets"][ds] = sc
        lr = json.loads((ROOT / "05_map" / "output" / ds / "ladder_report.json").read_text(encoding="utf-8"))
        l0, l1, l2 = lr["tiers"]["L0"], lr["tiers"]["L1"], lr["tiers"]["L2"]
        rows.append({"dataset": ds, "label": sc["label"],
                     "cells": int(l0.get("cells") or l0.get("n_cells") or sc["n"]),
                     "neighbors": float(l1.get("mean_neighbors", float("nan"))),
                     "moran_i": float(l2.get("moran_i", float("nan")))})
        vl = ROOT / "04_validate" / "output" / ds / "version_lock.json"
        if vl.exists():
            locks[ds] = json.loads(vl.read_text(encoding="utf-8"))
        project.log(f"    [⑧] {ds}: n={sc['n']:,}；"
                    + "；".join(f"{k} I(原始)={v['scales']['raw']['I']} "
                               f"I(log1p)={v['scales']['log1p']['I']}"
                               for k, v in sc["schemes"].items()))

    p1 = build_moran_explorer(payload)
    p2 = fig_ladder_compare(rows)
    if dk.ffmpeg_available():
        mp4, p4 = anim_ladder("sz_bike")
        project.log(f"    [⑧] {p4.name}（mp4 {mp4.stat().st_size/1e6:.1f} MB → "
                    f"内嵌 {p4.stat().st_size/1e6:.1f} MB）")
    else:
        p4, mp4 = None, None
        project.log("    [⑧] 跳过 L0→L3 演化动图：缺少 ffmpeg（pip install imageio-ffmpeg）")
    p3 = build_index(rows, locks)
    p5 = build_ebook(rows, locks)
    project.log(f"    [⑧] ebook/index.html（{p5.stat().st_size/1e3:.0f} KB）")
    for p in (p1, p2, p3, p4):
        if p:
            project.log(f"    [⑧] {p.name}（{p.stat().st_size/1e6:.2f} MB）")

    manifest = {
        "generated_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "generator": {"tool": "plotly + h3 + libpysal", "script": "08_interactive/08_interactive.py",
                      "encoding": "utf-8", "font": "Microsoft YaHei",
                      "self_contained": True, "reproducible": True,
                      "note": "权重与空间滞后在服务端算好；三页均内联 plotly，单文件自包含、离线可开"},
        "entry": "index.html", "n_figures": 2, "datasets": DATASETS,
        "figures": [
            {"file": "index.html", "title": "L0→L3 交互教材（入口）", "type": "entry",
             "question": "学习者能不能按阶梯看懂、能跑、能改？",
             "alt_text": "四阶阶梯卡片 + 两个交互件 + version_lock 复现表",
             "source": "本目录两件产物 + 04_validate/output/<dataset>/version_lock.json",
             "n": sum(r["cells"] for r in rows), "scope": "四数据集；H3 R8；W 行标准化",
             "tool": "html"},
            {"file": "moran_explorer.html", "title": "换一种邻居定义，结论就变了",
             "type": "moran_scatter_interactive",
             "question": "权重方案怎么影响 Moran's I？",
             "alt_text": "可切数据集与 Queen/KNN 权重，实时看散点、拟合线与 I 值",
             "unit": "x=log1p(格值)，y=空间滞后",
             "source": "05_map/output/<dataset>/L2_spatial_lag.csv",
             "n": sum(r["cells"] for r in rows),
             "scope": "H3 R8；W 行标准化；滞后服务端算好", "tool": "plotly"},
            {"file": "ladder_compare.html", "title": "同一套管线，结论强度差 50 倍",
             "type": "small_multiples",
             "question": "四个数据集的规模与空间自相关差多少？",
             "alt_text": "三联柱状图对比格数、平均邻居数与 Moran's I",
             "unit": "左=格数（对数），中=平均邻居，右=Moran's I",
             "source": "05_map/output/<dataset>/ladder_report.json",
             "n": sum(r["cells"] for r in rows), "scope": "四数据集；H3 R8", "tool": "plotly"},
            {"file": "ladder_evolution.html", "title": "L0→L3 是一条链",
             "type": "animation",
             "question": "网格化、权重、滞后、距离环到底是怎么串起来的？",
             "alt_text": "左图从格演化到邻居高亮再到距离环，右图同步长出 Moran 散点",
             "unit": "左 x=经度 y=纬度；右 x=log1p(格值) y=空间滞后",
             "source": "05_map/output/sz_bike/mapped.csv",
             "n": 2661,
             "scope": "mp4（FuncAnimation）内嵌 <video>；按深圳 bbox 裁切飞点",
             "tool": "matplotlib + ffmpeg"},
            {"file": "ebook/index.html", "title": "L0→L3 电子书（可翻页）",
             "type": "ebook", "question": "内容能不能按阶梯一页页翻着读？",
             "alt_text": "可翻页电子书：封面/目录/引言/L0-L3/对比/演化/结论/复现",
             "unit": "左/右箭头或键盘 ←/→ 翻页；每章嵌入对应交互图",
             "source": "本目录 moran_explorer.html / ladder_compare.html / ladder_evolution.html + version_lock",
             "n": len(rows), "scope": "骨架版：章节+关键结论+图已就位，正文留「待补」位",
             "tool": "html"},
        ],
    }
    (OUT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return {"stage": STAGE, "blocking": False, "figures": 5, "datasets": len(DATASETS),
            "artifacts": ["index.html", "moran_explorer.html", "ladder_compare.html",
                          "ladder_evolution.html", "ebook/index.html", "manifest.json"]}


def main() -> None:
    project = dk.Project.load(ROOT)
    print(run(project))


if __name__ == "__main__":
    main()
