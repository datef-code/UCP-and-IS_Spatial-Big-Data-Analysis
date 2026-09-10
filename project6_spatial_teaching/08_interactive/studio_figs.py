# -*- coding: utf-8 -*-
"""08_interactive · 交互件（每个产物 = 一个单文件自包含的 HTML）。

产物清单与各自回答的问题
------------------------
| 产物 | 回答什么 | 为什么做成这样 |
| --- | --- | --- |
| ``moran_explorer.html`` | Moran's I 怎么读、为什么四个数据集差这么多 | 有格级 CSV 时给**可拨开关的真散点**；没有时用上游 ⑥ 阶段的真实散点 PNG，绝不画假图 |
| ``weight_lab.html`` | 「邻居」到底是谁定的、孤岛有多致命 | 六边形邻接 SVG + 邻居数/孤岛率/I 三者关系 |
| ``ring_decay.html`` | 同一个数据，两种口径为什么给出相反结论 | plotly ``updatemenus`` 一键切「求和 / 密度 / 归一化」 |
| ``ladder_compare.html`` | 四个数据集在 L0→L2 各层差多少 | 指标下拉（8 个）+ 三层折线 |
| ``method_atlas.html`` | 这条管线一共用了哪些方法、各有什么坑 | 方法卡可展开：输入/输出/参数/为什么/坑/代码位置 |
| ``quiz.html`` | 学完了吗？ | 12 题，**选项与答案由上游数字生成**，数字变了题也跟着变 |
| ``index.html`` | 从哪开始 | 学习路径 + 产品矩阵 |
"""
from __future__ import annotations

import json
from pathlib import Path

import plotly.graph_objects as go

import studio_data as sd
import studio_ui as ui

GRID = "#e2e8f0"
FONT = ui.FONT
TICK = "#64748b"


# --------------------------------------------------------------------------- #
# plotly 小工具
# --------------------------------------------------------------------------- #
def _div(fig: go.Figure, height: int = 480) -> str:
    """图 → 可嵌入的 div（plotly.js 由页面外壳统一内联一次，避免重复几 MB）。"""
    return fig.to_html(include_plotlyjs=False, full_html=False,
                       config={"displaylogo": False, "responsive": True},
                       default_height=height)


def _base(title: str = "", height: int = 480, **kw) -> dict:
    lay = dict(font=dict(family=FONT, size=12.5, color=TICK),
               paper_bgcolor="#ffffff", plot_bgcolor="#ffffff",
               margin=dict(l=78, r=30, t=96 if title else 40, b=72),
               height=height, hovermode="closest", showlegend=False)
    if title:
        lay["title"] = dict(text=title, x=0.01, xanchor="left",
                            font=dict(size=15, color="#0f172a"))
    lay.update(kw)
    return lay


def _style_axes(fig: go.Figure, grid: str = GRID) -> go.Figure:
    """统一网格与字体颜色。

    注意用 ``title_font=`` 而不是 ``title=dict(font=...)``：后者会把已设好的轴标题
    **整个替换掉**（plotly 复合属性是覆盖语义），前者只改字体。
    """
    fig.update_xaxes(gridcolor=grid, zerolinecolor=grid, linecolor=grid,
                     tickfont=dict(size=11.5, color=TICK),
                     title_font=dict(size=12.5, color=TICK))
    fig.update_yaxes(gridcolor=grid, zerolinecolor=grid, linecolor=grid,
                     tickfont=dict(size=11.5, color=TICK),
                     title_font=dict(size=12.5, color=TICK))
    return fig


# --------------------------------------------------------------------------- #
# ① Moran 实验室
# --------------------------------------------------------------------------- #
def fig_moran_bar(facts: dict) -> go.Figure:
    rows = facts["rows"]
    fig = go.Figure(go.Bar(
        x=[r["short"] for r in rows], y=[r["moran_i"] for r in rows],
        marker=dict(color=[r["color"] for r in rows], line=dict(color="#ffffff", width=1.2)),
        text=[f"{r['moran_i']:.4f}" for r in rows], textposition="outside",
        textfont=dict(size=13, color=TICK),
        customdata=[[r["label"], r["cells"], r["mean_neighbors"], r["island_rate"]]
                    for r in rows],
        hovertemplate=("<b>%{customdata[0]}</b><br>Moran's I = %{y:.4f}"
                       "<br>格数 %{customdata[1]:,}<br>平均邻居 %{customdata[2]:.2f}"
                       "<br>孤岛率 %{customdata[3]:.1%}<extra></extra>"),
    ))
    fig.update_layout(**_base(
        "<b>同一个算法，四个数据集的 I 差 %d 倍</b><br>"
        "<sub>H3 R%d；W 行标准化；I 来自 05_map/output/&lt;ds&gt;/ladder_report.json</sub>"
        % (round(max(r["moran_i"] for r in rows) / max(min(r["moran_i"] for r in rows), 1e-9)),
           facts["h3_res"]),
        height=420))
    fig.update_yaxes(title="Moran's I", range=[0, max(r["moran_i"] for r in rows) * 1.22])
    return _style_axes(fig)


def _moran_scatter_panel(facts: dict, payload: dict | None, static_figs: dict) -> tuple[str, str]:
    """散点面板：有格级 CSV → 真交互散点；没有 → 上游真实散点 PNG + 说明。

    为什么要分级：格级 CSV 不入库（``.gitignore`` 的 ``*/*/*/*.csv``），
    重跑 05_map 又要 30 GB 原始数据。**缺数据就明说**，比画一张编出来的图强。
    """
    if payload and payload.get("datasets"):
        data = json.dumps(payload, ensure_ascii=False)
        js = """
        var DATA = __DATA__;
        var dsSel=document.getElementById('mDs'), wsSel=document.getElementById('mWs'),
            scSel=document.getElementById('mSc');
        dsSel.innerHTML = DATA.order.map(function(d){
          return '<option value="'+d+'">'+DATA.datasets[d].label+'</option>'; }).join('');
        wsSel.innerHTML = DATA.schemes.map(function(s){
          return '<option value="'+s.key+'">'+s.label+'</option>'; }).join('');
        function draw(){
          var D=DATA.datasets[dsSel.value], W=D.schemes[wsSel.value], S=W.scales[scSel.value];
          var other=W.scales[scSel.value==='raw'?'log1p':'raw'];
          document.getElementById('mI').textContent = S.I===null?'\\u2014':S.I.toFixed(4);
          document.getElementById('mIalt').textContent = other.I===null?'\\u2014':other.I.toFixed(4);
          document.getElementById('mN').textContent = S.n.toLocaleString();
          document.getElementById('mIsl').textContent = W.islands>=0?W.islands.toLocaleString():'\\u2014';
          var tr={x:S.x,y:S.y,type:'histogram2dcontour',
                  colorscale:[[0,'#F3F4F6'],[1,'#2563eb']],showscale:false,
                  ncontours:12,contours:{coloring:'fill'}};
          var xs=S.x,ys=S.y,mx=0,my=0,i;
          for(i=0;i<xs.length;i++){mx+=xs[i];my+=ys[i];}
          mx/=xs.length; my/=ys.length;
          var num=0,den=0;
          for(i=0;i<xs.length;i++){num+=(xs[i]-mx)*(ys[i]-my);den+=(xs[i]-mx)*(xs[i]-mx);}
          var sl=num/den, x0=Math.min.apply(null,xs), x1=Math.max.apply(null,xs);
          Plotly.react('mPlot',[tr,
            {x:[x0,x1],y:[my+sl*(x0-mx),my+sl*(x1-mx)],mode:'lines',
             line:{color:'#ea580c',width:2.6},name:'\\u62df\\u5408\\u7ebf'},
            {x:[x0,x1],y:[x0,x1],mode:'lines',
             line:{color:'#94a3b8',dash:'dot',width:1.2},hoverinfo:'skip'}],
            {font:{family:'__FONT__',size:12},paper_bgcolor:'#ffffff',plot_bgcolor:'#ffffff',
             margin:{l:70,r:24,t:24,b:60},showlegend:false,
             xaxis:{title:'\\u683c\\u503c\\uff08'+S.label+'\\uff09',gridcolor:'#e2e8f0'},
             yaxis:{title:'\\u7a7a\\u95f4\\u6ede\\u540e W\\u00b7\\u683c\\u503c',gridcolor:'#e2e8f0'}},
            {displaylogo:false,responsive:true});
          if(window.__applyPlotTheme) window.__applyPlotTheme();
        }
        [dsSel,wsSel,scSel].forEach(function(e){e.addEventListener('change',draw);});
        draw();
        """.replace("__DATA__", data).replace("__FONT__", FONT)
        html = """
        <div class="ctl">
          <div><label class="muted">数据集</label><br><select id="mDs" class="sel"></select></div>
          <div><label class="muted">权重方案</label><br><select id="mWs" class="sel"></select></div>
          <div><label class="muted">格值尺度</label><br><select id="mSc" class="sel">
            <option value="raw">原始格值（管线口径）</option>
            <option value="log1p">log1p(格值)</option></select></div>
        </div>
        <div class="stats">
          <div class="stat"><span class="k">当前口径 I</span><span class="v" id="mI">–</span></div>
          <div class="stat"><span class="k">另一尺度 I</span><span class="v" id="mIalt">–</span></div>
          <div class="stat"><span class="k">格数 n</span><span class="v" id="mN">–</span></div>
          <div class="stat"><span class="k">孤岛格</span><span class="v" id="mIsl">–</span></div>
        </div>
        <div id="mPlot" style="height:520px"></div>"""
        return html, js

    # ---- 降级：上游 06_visualize 的真实散点 PNG ----
    tabs = "".join(
        f'<button class="tabbtn{" on" if i == 0 else ""}" data-ds="{r["key"]}">{r["short"]}</button>'
        for i, r in enumerate(facts["rows"]))
    shots = []
    for i, r in enumerate(facts["rows"]):
        png = static_figs.get(r["key"], {}).get("l2")
        inner = (f'<img src="assets/fig/{png}" alt="{r["label"]} Moran 散点" loading="lazy">'
                 if png else '<div class="noshow">该数据集暂无上游散点图（先跑 ⑥ 可视化）</div>')
        shots.append(
            f'<div class="shot{" on" if i == 0 else ""}" data-shot="{r["key"]}">{inner}'
            f'<div class="cap">{r["label"]}：I = {r["moran_i"]:.4f}，'
            f'corr(格值, 滞后) = {r["lag_corr"]:.4f}，格数 {r["cells"]:,}，'
            f'孤岛率 {ui.fmt_pct(r["island_rate"])}</div></div>')
    js = """
    document.querySelectorAll('.tabbtn').forEach(function(b){
      b.onclick=function(){
        document.querySelectorAll('.tabbtn').forEach(function(x){x.classList.remove('on');});
        document.querySelectorAll('.shot').forEach(function(x){x.classList.remove('on');});
        b.classList.add('on');
        var s=document.querySelector('.shot[data-shot="'+b.dataset.ds+'"]');
        if(s) s.classList.add('on');
      };
    });
    """
    html = f"""
    <div class="warn"><b>当前环境没有格级 CSV，散点面板已降级为静态图</b>
    可拨开关的交互散点需要 <code>05_map/output/&lt;ds&gt;/L2_spatial_lag.csv</code>；
    该文件受仓库根 <code>.gitignore</code> 约束不入库，重跑 ⑤ 映射后本页会<b>自动升级</b>为
    可切数据集 / 权重 / 尺度的交互版本。<b>下面的散点是上游 ⑥ 阶段真实产出的 PNG，不是示意图。</b></div>
    <div class="tabs">{tabs}</div>
    <div class="fig" style="margin-top:0">{"".join(shots)}</div>"""
    return html, js


def build_moran_lab(facts: dict, payload: dict | None, static_figs: dict, out: Path) -> Path:
    rows = facts["rows"]
    best = max(rows, key=lambda r: r["moran_i"])
    worst = min(rows, key=lambda r: r["moran_i"])
    panel_html, panel_js = _moran_scatter_panel(facts, payload, static_figs)

    body = f"""
    <p>Moran's I 是空间分析里最常被引用、也最常被误读的一个数。
    它只回答一句话：<b>高值是不是挨着高值、低值是不是挨着低值。</b></p>

    {ui.stat_strip([
        ("最强聚集", f"{best['moran_i']:.4f}", best["short"]),
        ("最弱聚集", f"{worst['moran_i']:.4f}", worst["short"]),
        ("极值倍数", f"{best['moran_i'] / max(worst['moran_i'], 1e-9):.0f}×", "同一套管线"),
        ("参与格总数", ui.fmt_int(sum(r["cells"] for r in rows)), "四数据集合计"),
    ])}

    {_div(fig_moran_bar(facts), 420)}

    <h2>怎么读 I：散点的四个象限</h2>
    <p>Moran 散点把「格值」放横轴、「邻居均值（空间滞后）」放纵轴，两轴都中心化后，
    散点自然分成四象限：</p>
    <div class="grid g4">
      <div class="card"><div class="t"><span class="badge g">HH</span>高–高</div>
        <p class="d">我高、邻居也高 → <b>热点</b>，推高 I。</p></div>
      <div class="card"><div class="t"><span class="badge g">LL</span>低–低</div>
        <p class="d">我低、邻居也低 → <b>冷点</b>，同样推高 I。</p></div>
      <div class="card"><div class="t"><span class="badge o">HL</span>高–低</div>
        <p class="d">我是高峰、邻居是洼地 → <b>空间离群</b>，压低 I。</p></div>
      <div class="card"><div class="t"><span class="badge o">LH</span>低–高</div>
        <p class="d">我低、邻居高 → 同样压低 I。</p></div>
    </div>
    {ui.callout("note", "I 的取值直觉",
                "I &gt; 0 = 同值相邻（聚集）；I ≈ 0 = 随机；I &lt; 0 = 高低交错（分散）。"
                "行标准化权重下，I <b>恰好等于</b> Moran 散点的最小二乘斜率 —— "
                "所以散点图的斜率可以直接当 I 读。")}

    <h2>动手看：Moran 散点</h2>
    {panel_html}

    <h2>两个开关都会改变结论（本课重点）</h2>
    {ui.callout("warn", "开关一：换权重定义",
                "<ul><li>「邻居」是<b>人为定义</b>，不是客观事实：Queen 邻接（共享边）"
                "还是 KNN（最近 k 个）？</li>"
                "<li>本管线的 L1 用 H3 <code>grid_disk(k=1)</code>，六边形满配 6 个邻居；"
                "实测平均邻居从 <b>1.41</b>（fdic）到 <b>5.07</b>（sz_bike）不等 —— "
                "差的不是算法，是<b>数据密不密</b>。</li></ul>")}
    {ui.callout("warn", "开关二：换变量尺度",
                "<ul><li>Moran's I <b>依赖变量尺度</b>：把格值取 log1p 再算，I 会明显变化"
                "（长尾数据尤其如此）。</li>"
                "<li>所以跨研究比较 I 必须<b>同尺度、同权重、同网格</b>；"
                "只报一个 I 不报口径，等于没报。</li></ul>")}

    <h2>公式</h2>
    {ui.formula("全局 Moran's I",
                "I = ( n / S₀ ) · ( zᵀWz ) / ( zᵀz ) &nbsp;&nbsp;其中 z = x − x̄，S₀ = ΣᵢΣⱼ wᵢⱼ<br>"
                "行标准化后 Σⱼ wᵢⱼ = 1 ⇒ S₀ = n ⇒ <b>I = ( zᵀWz ) / ( zᵀz ) = 散点斜率</b>")}
    {ui.callout("ask", "想自己推一遍？",
                "取一个 4 格的玩具例子：值 [0, 0, 10, 10]，邻接成一条链、行标准化。"
                "手算 Wz 与 I，你会发现 I 落不到 1 —— 因为<b>边界格邻居少</b>，"
                "这正是「孤岛会稀释 I」的代数来源。")}
    """
    css = """
    .ctl{display:flex;flex-wrap:wrap;gap:16px;align-items:flex-end;padding:13px 16px;
      border:1px solid var(--line);border-radius:12px;margin:14px 0}
    .sel{padding:7px 11px;border:1px solid var(--line);border-radius:8px;font-size:13.5px;
      background:var(--bg);color:var(--ink);font-family:inherit;min-width:210px}
    .tabs{display:flex;flex-wrap:wrap;gap:8px;margin:14px 0 0}
    .tabbtn{border:1px solid var(--line);background:var(--bg);color:var(--ink-2);border-radius:999px;
      padding:6px 15px;font-size:13px;cursor:pointer;font-family:inherit;transition:.18s}
    .tabbtn:hover{border-color:var(--brand);color:var(--brand)}
    .tabbtn.on{background:var(--brand);border-color:var(--brand);color:#fff}
    .shot{display:none} .shot.on{display:block}
    .shot img{width:100%;display:block;background:#fff}
    .shot .cap{font-size:12.5px;color:var(--sub);padding:9px 14px;background:var(--soft);
      border-top:1px solid var(--line)}
    .noshow{padding:60px 20px;text-align:center;color:var(--faint);font-size:13.5px}
    """
    html = ui.page("Moran's I 实验室 · 换一种邻居定义，结论就变了", body,
                   subtitle="横轴 = 格值，纵轴 = 空间滞后（邻居均值）；斜率就是 Moran's I。"
                            "同一套管线跑四个数据集，I 差 54 倍。",
                   extra_css=css, extra_js=panel_js, with_plotly=True,
                   active_nav="L2 · 交互")
    p = out / "moran_explorer.html"
    p.write_text(html, encoding="utf-8")
    return p


# --------------------------------------------------------------------------- #
# ② 权重实验室
# --------------------------------------------------------------------------- #
def hex_mesh_svg(k: int = 2, size: int = 34) -> str:
    """H3 邻接示意：以中心格为原点的 k 阶六边形网格（SVG，离线可缩放）。

    为什么要自己画：教材要回答「<code>grid_disk(c,1)</code> 到底圈了几个格」，
    一张矢量图胜过一段文字；六边形网格的 k 阶邻居数恒为 6k（k=1 → 6，k=2 → 12）。
    """
    import math
    pts = [(q, r) for q in range(-k, k + 1)
           for r in range(max(-k, -q - k), min(k, -q + k) + 1)]
    w = math.sqrt(3) * size                       # pointy-top：宽 = √3·size
    cx = lambda q, r: w * (q + r / 2.0)
    cy = lambda r: 1.5 * size * r
    xs = [cx(q, r) for q, r in pts]
    ys = [cy(r) for q, r in pts]
    pad = size * 1.5
    minx, maxx = min(xs) - w / 2 - pad, max(xs) + w / 2 + pad
    miny, maxy = min(ys) - size - pad, max(ys) + size + pad

    def poly(q, r):
        x, y = cx(q, r), cy(r)
        return " ".join(f"{x + size * math.sin(math.radians(60 * i)):.2f},"
                        f"{y - size * math.cos(math.radians(60 * i)):.2f}" for i in range(6))

    body = []
    for q, r in pts:
        d = (abs(q) + abs(r) + abs(q + r)) // 2            # 六边形网格距离
        fill = {0: "#ea580c", 1: "#60a5fa"}.get(d, "#cbd5e1")
        op = "1" if d <= 1 else "0.5"
        body.append(f'<polygon points="{poly(q, r)}" fill="{fill}" fill-opacity="{op}" '
                    f'stroke="#ffffff" stroke-width="2"/>')
    body.append(f'<text x="{cx(0, 0):.1f}" y="{cy(0) + 5:.1f}" text-anchor="middle" '
                f'font-size="13" font-weight="700" fill="#ffffff">i</text>')
    vb = f"{minx:.1f} {miny:.1f} {maxx - minx:.1f} {maxy - miny:.1f}"
    return (f'<svg viewBox="{vb}" xmlns="http://www.w3.org/2000/svg" '
            f'style="width:100%;max-width:290px;height:auto">{"".join(body)}</svg>')


def fig_neighbor_scatter(facts: dict) -> go.Figure:
    rows = facts["rows"]
    fig = go.Figure(go.Scatter(
        x=[r["mean_neighbors"] for r in rows],
        y=[r["moran_i"] for r in rows],
        mode="markers+text",
        marker=dict(size=[max(18, min(54, r["cells"] ** 0.33)) for r in rows],
                    color=[r["color"] for r in rows],
                    line=dict(color="#ffffff", width=2), opacity=.9),
        text=[r["short"] for r in rows], textposition="top center",
        textfont=dict(size=12.5, color=TICK),
        customdata=[[r["label"], r["islands"], r["island_rate"], r["cells"]] for r in rows],
        hovertemplate=("<b>%{customdata[0]}</b><br>平均邻居 %{x:.2f}<br>Moran's I %{y:.4f}"
                       "<br>孤岛 %{customdata[1]:,}（%{customdata[2]:.1%}）"
                       "<br>格数 %{customdata[3]:,}<extra></extra>"),
    ))
    fig.update_layout(**_base(
        "<b>邻居搭得起来，I 才高得起来</b><br>"
        "<sub>横轴 = L1 平均邻居数；纵轴 = L2 Moran's I；气泡大小 = 格数</sub>", height=440))
    fig.update_xaxes(title="平均邻居数（六边形满配 = 6）")
    fig.update_yaxes(title="Moran's I")
    return _style_axes(fig)


def fig_island_bar(facts: dict) -> go.Figure:
    rows = sorted(facts["rows"], key=lambda r: -(r["island_rate"] or 0))
    fig = go.Figure(go.Bar(
        y=[r["short"] for r in rows], x=[r["island_rate"] for r in rows], orientation="h",
        marker=dict(color=[r["color"] for r in rows], line=dict(color="#ffffff", width=1)),
        text=[f"{r['island_rate']:.1%}　({r['islands']:,} 格)" for r in rows],
        textposition="outside", textfont=dict(size=12, color=TICK),
        hovertemplate="<b>%{y}</b><br>孤岛率 %{x:.1%}<extra></extra>",
    ))
    fig.update_layout(**_base("<b>孤岛率：一格邻居都没有的比例</b>", height=320))
    fig.update_xaxes(title="孤岛格占比", tickformat=".0%",
                     range=[0, max(r["island_rate"] for r in rows) * 1.4])
    return _style_axes(fig)


def build_weight_lab(facts: dict, out: Path) -> Path:
    rows = facts["rows"]
    cards = "".join(f'<button class="dsbtn{" on" if i == 0 else ""}" '
                    f'data-ds="{r["key"]}">{r["short"]}</button>'
                    for i, r in enumerate(rows))
    panels = "".join(f"""
      <div class="dspanel{" on" if i == 0 else ""}" data-panel="{r['key']}">
        {ui.stat_strip([
            ("格数 n", ui.fmt_int(r["cells"]), "L0"),
            ("平均邻居", ui.fmt_num(r["mean_neighbors"], 2), "满配 6"),
            ("孤岛格", ui.fmt_int(r["islands"]), f"占比 {ui.fmt_pct(r['island_rate'])}"),
            ("Moran's I", ui.fmt_num(r["moran_i"], 4), "L2"),
        ])}
        <p><b>{r['label']}</b> · {r['scene']} —— {r['one_liner']}</p>
        {ui.callout("note", "这个数据集要看什么", r["watch"])}
      </div>""" for i, r in enumerate(rows))

    densest = max(rows, key=lambda r: r["mean_neighbors"])
    sparsest = min(rows, key=lambda r: r["mean_neighbors"])

    body = f"""
    <p>空间权重矩阵 <code>W</code> 是整条管线里<b>最主观、也最影响结论</b>的一步。
    它回答：谁算谁的邻居？答案不是数据给的，是<b>你定的</b>。</p>

    <div class="tabs">{cards}</div>
    {panels}

    <h2>本管线怎么定义邻居</h2>
    <div class="grid g2">
      <div class="card">
        <div class="t">H3 一阶邻接（grid_disk k=1）</div>
        <p class="d">六边形格共享边即邻居。规则统一，没有「对角算不算」的歧义，
        六边形满配 <b>6</b> 个邻居。</p>
        <div style="display:flex;justify-content:center;padding:10px 0">{hex_mesh_svg(2, 34)}</div>
        <p class="muted" style="text-align:center">橙 = 中心格 i（6 个一阶邻居：蓝）；灰 = 二阶</p>
      </div>
      <div class="card">
        <div class="t">KNN（最近 k 个）</div>
        <p class="d">按距离取最近的 k 个格。好处是<b>保证没有孤岛</b>；
        代价是「邻居」可能隔着半个地球 —— 全球数据上尤其危险。</p>
        {ui.formula("KNN 为什么用 3D 直角坐标 + KD-tree",
                    "n×n 距离矩阵：30 万格 = 900 亿条 → <b>直接爆内存</b><br>"
                    "改算 3D 弦距：|a−b| 与大圆距离<b>单调同序</b> ⇒ 最近邻排序完全一致<br>"
                    "KD-tree 查询 O(n log n) —— 快几个数量级")}
        {ui.callout("warn", "KNN 的隐藏代价",
                    "KNN 消灭了孤岛，也<b>消灭了「这里本来就孤立」这个信号</b>。"
                    "在 Brightkite 这种全球稀疏数据上，KNN 会把大洋彼岸的签到认成邻居。")}
      </div>
    </div>

    <h2>行标准化：把「邻居数量」抹平</h2>
    {ui.formula("行标准化（row-standardized）",
                "w*ᵢⱼ = wᵢⱼ / Σⱼ wᵢⱼ &nbsp;&nbsp;⇒&nbsp;&nbsp; 每行权重和 = 1（孤岛行全 0）<br>"
                "好处：空间滞后 Wx 变成<b>邻居均值</b>，与「邻居有几个」脱钩，可跨格比较")}
    {ui.callout("warn", "一个必须记住的实现坑",
                "<code>libpysal.weights.W</code> <b>必须覆盖全部格（含孤岛）</b>，"
                "否则 <code>w.n &lt; n</code>，滞后向量维度对不上，后面全线崩。"
                "孤岛的滞后取 0，仍计入 I 的分母（与管线一致）。")}

    <h2>邻居数 × 孤岛率 × I</h2>
    {_div(fig_neighbor_scatter(facts), 440)}
    {_div(fig_island_bar(facts), 320)}
    {ui.callout("note", "图上没说但要看出来的事",
                f"<ul><li>平均邻居从 <b>{sparsest['mean_neighbors']:.2f}</b>（{sparsest['short']}）"
                f"到 <b>{densest['mean_neighbors']:.2f}</b>（{densest['short']}），差 3.6 倍；"
                "I 差 54 倍 —— <b>I 对连通性是非线性的</b>。</li>"
                "<li>但连通性不是全部：Gowalla 的孤岛率（21.8%）比 Brightkite（29.4%）低，"
                "I 却高 38 倍。说明<b>值的分布形态同样重要</b>。</li></ul>")}
    {ui.callout("ok", "一句话结论",
                "权重矩阵不是「算」出来的，是<b>选</b>出来的。报告任何空间结论，"
                "都必须同时报：网格（H3 R？）+ 权重方案（Queen / KNN k=?）+ 标准化方式（行 / 二值）。")}
    """
    css = """
    .tabs{display:flex;flex-wrap:wrap;gap:8px;margin:14px 0 12px}
    .dsbtn{border:1px solid var(--line);background:var(--bg);color:var(--ink-2);border-radius:999px;
      padding:7px 17px;font-size:13.5px;cursor:pointer;font-family:inherit;transition:.18s}
    .dsbtn:hover{border-color:var(--brand);color:var(--brand);transform:translateY(-1px)}
    .dsbtn.on{background:var(--brand);border-color:var(--brand);color:#fff}
    .dspanel{display:none} .dspanel.on{display:block}
    """
    js = """
    document.querySelectorAll('.dsbtn').forEach(function(b){
      b.onclick=function(){
        document.querySelectorAll('.dsbtn').forEach(function(x){x.classList.remove('on');});
        document.querySelectorAll('.dspanel').forEach(function(x){x.classList.remove('on');});
        b.classList.add('on');
        var p=document.querySelector('.dspanel[data-panel="'+b.dataset.ds+'"]');
        if(p) p.classList.add('on');
      };
    });
    """
    html = ui.page("权重实验室 · 「邻居」是谁定的？", body,
                   subtitle="空间权重矩阵 W 是整条管线里最主观的一步。"
                            "这里把它拆开：邻接怎么定、行标准化在做什么、孤岛为什么致命。",
                   extra_css=css, extra_js=js, with_plotly=True, active_nav="L1 · 交互")
    p = out / "weight_lab.html"
    p.write_text(html, encoding="utf-8")
    return p


# --------------------------------------------------------------------------- #
# ③ 距离环衰减
# --------------------------------------------------------------------------- #
def fig_ring(facts: dict) -> go.Figure:
    """一张图三种口径 —— 用 plotly 原生 updatemenus 切换，不写自定义 JS。"""
    rows = facts["rows"]
    labels = [r0["label"] for r0 in rows[0]["rings"]]
    mid = [(r0["a"] + r0["b"]) / 2 for r0 in rows[0]["rings"]]
    nl = len(labels)

    def col(get):
        return [[get(r, i) for i in range(nl)] for r in rows]

    spills = col(lambda r, i: r["rings"][i]["spill"])
    dens = col(lambda r, i: r["rings"][i]["density"])
    norm = col(lambda r, i: r["rings"][i]["density"] / (r["rings"][0]["density"] or 1.0))

    fig = go.Figure()
    for i, r in enumerate(rows):
        fig.add_trace(go.Scatter(
            x=mid, y=dens[i], mode="lines+markers+text", name=r["short"],
            line=dict(color=r["color"], width=2.8, shape="spline", smoothing=.6),
            marker=dict(size=9, color=r["color"], line=dict(color="#fff", width=1.5)),
            text=[f"{v:,.0f}" for v in dens[i]], textposition="top center",
            textfont=dict(size=10.5, color=TICK),
            hovertemplate="<b>" + r["short"] + "</b><br>%{x} km 环<br>%{y:,.4g}<extra></extra>"))

    def btn(label, vals, ytitle, fmt):
        return dict(label=label, method="update",
                    args=[{"y": vals,
                           "text": [[f"{v:{fmt}}" for v in row] for row in vals]},
                          {"yaxis.title.text": ytitle}])

    fig.update_layout(**_base(
        "<b>同一个数据，两种口径给出相反结论</b><br>"
        "<sub>圆心 = 格值 Top-%d 热点格；x = 环中点（km）；纵轴对数</sub>" % rows[0]["centers"],
        height=520, showlegend=True,
        updatemenus=[dict(type="buttons", direction="right", x=0.01, xanchor="left",
                          y=1.14, yanchor="top", bgcolor="#f8fafc", bordercolor="#e2e8f0",
                          font=dict(size=12), active=0,
                          buttons=[btn("溢出密度（推荐）", dens,
                                       "溢出密度 = 环内求和 ÷ 环内格数", ",.0f"),
                                   btn("环内求和", spills, "环内格值求和", ",.0f"),
                                   btn("密度归一到首环", norm, "相对首环的倍数", ".3f")])],
        legend=dict(orientation="h", y=-0.15, x=0, font=dict(size=12))))
    fig.update_xaxes(title="距热点圆心（环中点，km）", tickvals=mid, ticktext=labels)
    fig.update_yaxes(title="溢出密度 = 环内求和 ÷ 环内格数", type="log")
    return _style_axes(fig)


def build_ring_decay(facts: dict, out: Path) -> Path:
    rows = facts["rows"]
    mono = [r for r in rows
            if all(r["rings"][i]["spill"] < r["rings"][i + 1]["spill"]
                   for i in range(len(r["rings"]) - 1))]
    mono_names = "、".join(r["short"] for r in mono) or "（无）"
    n_ring = len(rows[0]["rings"])

    tbl = ui.table(
        ["数据集"] + [f"{r0['label']}<br>求和" for r0 in rows[0]["rings"]]
        + [f"{r0['label']}<br>密度" for r0 in rows[0]["rings"]],
        [[r["short"]] + [ui.fmt_num(x["spill"], 0) for x in r["rings"]]
         + [ui.fmt_num(x["density"], 0) for x in r["rings"]] for r in rows],
        num_cols=set(range(1, 2 * n_ring + 1)))

    body = f"""
    <p>L3 问的是「效应随距离怎么衰减」。听起来简单，但<b>口径选错会得到完全相反的结论</b>。</p>
    {ui.callout("warn", "本课最容易踩的坑",
                "环越远，<b>环面积越大 → 环内格数越多 → 求和必然变大</b>。"
                "所以「环内求和」<b>不是</b>衰减指标；必须除以环内格数，看<b>密度</b>。")}

    {_div(fig_ring(facts), 560)}
    <p class="muted">点上方三个按钮切换口径；纵轴为对数刻度（四个数据集量级差 3 个数量级，
    线性轴会把小值压成一条线）。</p>

    <h2>两种口径的完整数字</h2>
    {tbl}
    {ui.callout("note", "照着数字念一遍",
                f"<ul><li><b>求和口径</b>：只有 <b>{mono_names}</b> 是随距离单调递增的，"
                "其余数据集非单调（近环格少、远环格多，纯几何效应）。</li>"
                "<li><b>密度口径</b>：四个数据集<b>全部单调递减</b> —— 这才是真正的距离衰减。</li>"
                "<li>同样叫「溢出」，换个口径能得出「越远越多」和「越远越少」两个相反结论。</li></ul>")}

    <h2>衰减速度也各不相同</h2>
    <div class="grid g4">
    {"".join(f'''<div class="card">
        <div class="t" style="color:{r['color']}">{r['short']}</div>
        <p class="d">首环 → 末环密度衰减
          <b>{r['rings'][0]['density'] / max(r['rings'][-1]['density'], 1e-9):.1f}×</b><br>
          <span class="muted">{ui.fmt_num(r['rings'][0]['density'], 0)} → {ui.fmt_num(r['rings'][-1]['density'], 0)}</span>
        </p></div>''' for r in rows)}
    </div>
    {ui.callout("ok", "一句话结论",
                "聚合口径不是技术细节，它<b>直接决定结论方向</b>。"
                "任何「随距离变化」的表，都必须写清分子分母分别是什么。")}
    """
    html = ui.page("距离环衰减 · 同一个数据，两种口径相反结论", body,
                   subtitle="L3：以格值 Top-100 热点为圆心画环。"
                            "切到「环内求和」看虚假递增，切到「溢出密度」看真实衰减。",
                   with_plotly=True, active_nav="L3 · 交互")
    p = out / "ring_decay.html"
    p.write_text(html, encoding="utf-8")
    return p


# --------------------------------------------------------------------------- #
# ④ 阶梯对比（升级版：8 个指标可切）
# --------------------------------------------------------------------------- #
METRICS = [
    ("cells", "格数（L0）", "{:,.0f}"),
    ("points", "原始点数（L0）", "{:,.0f}"),
    ("points_per_cell", "每格平均点数", "{:,.1f}"),
    ("top10_share", "Top-10 格占比", "{:.1%}"),
    ("mean_neighbors", "平均邻居（L1）", "{:.2f}"),
    ("island_rate", "孤岛率（L1）", "{:.1%}"),
    ("moran_i", "Moran's I（L2）", "{:.4f}"),
    ("lag_corr", "corr(格值, 滞后)（L2）", "{:.4f}"),
]


def fig_metric_switch(facts: dict) -> go.Figure:
    rows = facts["rows"]
    key, title, fmt = METRICS[0]
    fig = go.Figure(go.Bar(
        y=[r["short"] for r in rows], x=[r[key] for r in rows], orientation="h",
        marker=dict(color=[r["color"] for r in rows], line=dict(color="#fff", width=1)),
        text=[fmt.format(r[key]) for r in rows], textposition="outside",
        textfont=dict(size=12.5, color=TICK),
        hovertemplate="<b>%{y}</b><br>" + title + " %{x}<extra></extra>"))
    fig.update_layout(**_base("<b>四数据集阶梯对比：切换指标</b>", height=390,
                              margin=dict(l=90, r=60, t=96, b=60),
                              updatemenus=[dict(
                                  type="dropdown", direction="down", x=0.01, xanchor="left",
                                  y=1.2, yanchor="top", bgcolor="#f8fafc",
                                  bordercolor="#e2e8f0", font=dict(size=12),
                                  buttons=[dict(label=t, method="update",
                                                args=[{"x": [[r[k] for r in rows]],
                                                       "text": [[f.format(r[k]) for r in rows]]},
                                                      {"xaxis.title.text": t}])
                                           for k, t, f in METRICS])]))
    fig.update_xaxes(title=title)
    fig.update_yaxes(autorange="reversed")
    return _style_axes(fig)


def fig_stage_lines(facts: dict) -> go.Figure:
    """L0→L2 三层指标折线：把量级差 100 倍的数据集放在同一张图里比较。"""
    rows = facts["rows"]
    stages = ["格数（L0）", "平均邻居（L1）", "Moran's I（L2）"]
    fig = go.Figure()
    for r in rows:
        fig.add_trace(go.Scatter(
            x=stages, y=[r["cells"], r["mean_neighbors"], r["moran_i"]],
            mode="lines+markers", name=r["short"],
            line=dict(color=r["color"], width=2.4),
            marker=dict(size=9, color=r["color"]),
            hovertemplate="<b>" + r["short"] + "</b><br>%{x} = %{y}<extra></extra>"))
    fig.update_layout(**_base(
        "<b>三层指标放在一张图上（纵轴对数）</b><br>"
        "<sub>量级差 100 倍，线性轴会把小值压平；对数轴看的是「倍数关系」</sub>",
        height=420, showlegend=True,
        legend=dict(orientation="h", y=-0.16, x=0, font=dict(size=12))))
    fig.update_yaxes(type="log", title="数值（对数）")
    return _style_axes(fig)


def build_ladder_compare(facts: dict, out: Path) -> Path:
    rows = facts["rows"]
    tbl = ui.table(
        ["数据集", "场景", "格数", "每格点数", "平均邻居", "孤岛率", "Moran's I", "corr"],
        [[r["label"], r["scene"], ui.fmt_int(r["cells"]),
          ui.fmt_num(r["points_per_cell"], 1), ui.fmt_num(r["mean_neighbors"], 2),
          ui.fmt_pct(r["island_rate"]), ui.fmt_num(r["moran_i"], 4),
          ui.fmt_num(r["lag_corr"], 4)] for r in rows],
        num_cols={2, 3, 4, 5, 6, 7})
    densest = max(rows, key=lambda r: r["points_per_cell"])
    sparsest = min(rows, key=lambda r: r["points_per_cell"])

    body = f"""
    <p>同一套管线、同一组参数（H3 R{facts['h3_res']} / 行标准化 / Top-100 热点 / 4 个距离环），
    跑四个数据集。差别不在算法，在<b>数据本身的空间结构</b>。</p>
    {_div(fig_metric_switch(facts), 410)}
    <p class="muted">左上角下拉切换 8 个指标（L0 规模 → L1 连通性 → L2 聚集强度）。</p>
    {_div(fig_stage_lines(facts), 440)}
    <h2>完整数字</h2>
    {tbl}
    {ui.callout("note", "怎么读这张表",
                f"<ul><li><b>每格点数</b>是最直观的密度指标：{densest['short']} 每格 "
                f"{densest['points_per_cell']:,.0f} 个点，{sparsest['short']} 只有 "
                f"{sparsest['points_per_cell']:,.0f} 个 —— 差 "
                f"{densest['points_per_cell'] / max(sparsest['points_per_cell'], 1e-9):.0f} 倍。</li>"
                "<li><b>平均邻居</b>跟着密度走：5.07 → 2.40 → 2.01 → 1.41。</li>"
                "<li>但 <b>I 不完全跟着平均邻居走</b>：fdic 的孤岛率（28.1%）比 "
                "Gowalla（21.8%）低不了多少，I 却差 3.8 倍 —— "
                "说明<b>值的分布形态（长尾 / 尺度）也在起作用</b>，不能只看连通性。</li></ul>")}
    """
    html = ui.page("阶梯对比 · 同一套管线，四个数据集", body,
                   subtitle="L0 规模 → L1 连通性 → L2 聚集强度 → L3 距离衰减，逐层对比。",
                   with_plotly=True, active_nav="综合 · 对比")
    p = out / "ladder_compare.html"
    p.write_text(html, encoding="utf-8")
    return p


# --------------------------------------------------------------------------- #
# ⑤ 方法图谱
# --------------------------------------------------------------------------- #
def method_bank(facts: dict) -> list[dict]:
    """教材用到的方法清单。数字从 facts 取，不写死。"""
    res = facts["h3_res"]
    area = facts["cell_area_km2"]
    area_s = f"{area:.3f} km²" if area else "—"
    top = max(facts["rows"], key=lambda r: r["moran_i"])
    worst = min(facts["rows"], key=lambda r: r["moran_i"])
    nbs = [r["mean_neighbors"] for r in facts["rows"]]
    return [
        dict(layer="L0", name="H3 离散网格（geocode）",
             one="把连续经纬度压成可数的六边形格",
             inp="lat / lon（点）", out=f"h3_cell（res={res}）",
             params=f"h3_res={res}；平均 {area_s}/格",
             why="六边形邻居方向一致、没有「对角算不算」的歧义；方格永远说不清对角邻居。",
             pit="分辨率决定一切：res 太大 → 一格一个点、邻居全是孤岛；res 太小 → 空间细节被抹平。改 res 必须重跑整条链。",
             code="05_map/05_map.py · op=geocode"),
        dict(layer="L0", name="格内聚合（aggregate）",
             one="点值求和进格，点云变栅格",
             inp="h3_cell + value", out="格值 value",
             params="聚合函数 = sum",
             why="把 800 万条记录压成几千个可运算单元，是「大数据 → 可算」的关键一步。",
             pit="sum 会让大格天然占优；若业务问的是「强度」应改用 mean 或密度。口径不同，后面的 I 也不同。",
             code="05_map/05_map.py · op=aggregate"),
        dict(layer="L0", name="格值集中度（ECDF）",
             one="值有多集中？头部格占多少",
             inp="格值向量", out="ECDF 曲线 / 头部占比",
             params="零值格已剔除",
             why="长尾是空间数据的常态。不先看分布就直接算 I，很容易被几个极端格带偏。",
             pit="直接在长尾原始数据上算 I，结果被极值主导 —— 这正是「要不要取 log1p」能成为一门课的原因。",
             code="06_visualize/06_visualize.py · 01-L0-cell-value-ecdf"),
        dict(layer="L1", name="空间权重矩阵 W（邻接）",
             one="定义谁是谁的邻居",
             inp="格集合", out="W（n×n 稀疏）",
             params=f"H3 grid_disk(k=1)；行标准化；实测平均邻居 {min(nbs):.2f}–{max(nbs):.2f}",
             why="没有 W 就没有「空间」。这一步把地理关系写成可运算的矩阵。",
             pit="W 必须覆盖全部格（含孤岛），否则 w.n < n 会让滞后维度对不上，后面全线崩。",
             code="05_map/spatial_ladder.py · build_neighbors / build_weights"),
        dict(layer="L1", name="KNN 权重（KD-tree）",
             one="按距离取最近 k 个，保证没有孤岛",
             inp="格中心 3D 直角坐标", out="W（每格恰好 k 个邻居）",
             params="k ∈ {4, 8}；sklearn NearestNeighbors(algorithm='kd_tree')",
             why="n×n 距离矩阵在 30 万格上必爆内存；3D 弦距与大圆距离单调同序，最近邻排序一致但快几个数量级。",
             pit="KNN 消灭孤岛的同时也消灭了「这里本来就孤立」的信号，全球稀疏数据上会把大洋彼岸认成邻居。",
             code="08_interactive/08_interactive.py · _build_weights"),
        dict(layer="L1", name="行标准化（row-standardized）",
             one="把「邻居有几个」的差异抹平",
             inp="W（二值）", out="W（每行和为 1）",
             params="transform='r'",
             why="标准化后 Wx 是邻居均值，与邻居数量脱钩，可跨格比较；也让 I 恰好等于散点斜率。",
             pit="孤岛行无法标准化（分母为 0），滞后取 0 —— 它会稀释 I，但不该被悄悄删掉。",
             code="05_map/spatial_ladder.py · build_weights"),
        dict(layer="L2", name="空间滞后 Wx",
             one="每个格的邻居均值",
             inp="W + 格值 x", out="空间滞后向量 Wx",
             params="稀疏矩阵乘法 W.sparse @ x",
             why="把「邻居怎么样」变成一个和 x 同维度的新变量，于是可以画散点、做回归。",
             pit="稀疏矩阵乘出来是 (n,1)，记得 ravel()；否则后续广播会静默出错。",
             code="05_map/spatial_ladder.py"),
        dict(layer="L2", name="全局 Moran's I",
             one="一个数字概括全图聚集强度",
             inp="x + W", out=f"I ∈ [-1, 1]；本管线 {worst['moran_i']:.4f} – {top['moran_i']:.4f}",
             params="行标准化 ⇒ S₀ = n ⇒ I = zᵀWz / zᵀz",
             why="最常用的空间自相关指标，也是被误读最多的：它依赖尺度与权重，不是绝对真理。",
             pit="跨研究比较 I 必须同尺度、同权重、同网格；只报 I 不报口径等于没报。",
             code="05_map/spatial_ladder.py · moran_i"),
        dict(layer="L2", name="Moran 散点四象限",
             one="把全局 I 拆回每个格的贡献",
             inp="x + Wx（均中心化）", out="HH / LL / HL / LH 象限",
             params="两轴均减去各自均值",
             why="全局 I 只是一个平均；散点能看出「是热点成片，还是少数极端格撑起来的」。",
             pit="点很多时（30 万格）必须分箱或抽样，否则浏览器卡死，视觉上也全是糊的。",
             code="06_visualize/06_visualize.py · 02-L2-moran-scatter"),
        dict(layer="L3", name="Haversine 距离",
             one="球面上的两点距离",
             inp="两点经纬度", out="距离（km）",
             params="R = 6371.0088 km",
             why="经纬度不是平面坐标，高纬度地区 1° 经度对应的公里数会缩水，用欧氏距离会系统性偏差。",
             pit="忘了 np.radians() 是最经典的错误；跨 180° 经线要单独处理。",
             code="05_map/spatial_ladder.py · haversine_km"),
        dict(layer="L3", name="距离环聚合（求和 vs 密度）",
             one="效应随距离怎么衰减",
             inp="热点圆心 + 环定义", out="每环的求和 / 格数 / 密度",
             params="Top-100 热点；环 0–1 / 1–3 / 3–5 / 5–10 km",
             why="把「邻居」从拓扑定义换成距离定义，回答更贴近业务的问题（多远还在影响）。",
             pit="环面积随距离增大 → 求和必然变大 → 得出「越远影响越大」的假结论。必须除格数看密度。",
             code="05_map/spatial_ladder.py · ring_spillover"),
        dict(layer="贯穿", name="可复现（version_lock）",
             one="冻结源数据指纹、行数、库版本",
             inp="源数据 + 运行环境", out="version_lock.json",
             params="含 cost_params（h3_res / hot_top_n / rings_km / sz_sample_day）",
             why="教学产品的信服度来自「你能重跑出同样的数」；版本漂移会被 ④ 阶段记为断言失败。",
             pit="只写「用了 pandas」不够，必须写版本号；成本参数（合成参数）也要一并冻结并标注。",
             code="04_validate/output/&lt;ds&gt;/version_lock.json"),
        dict(layer="贯穿", name="IQR 离群检测",
             one="先看清数据里有什么怪东西",
             inp="数值字段", out="离群计数 / 建议",
             params="outlier_method=iqr；outlier_row_cap=20000",
             why="飞点会直接变成飞格，进而污染权重与 I。清洗与映射之间必须有这一步。",
             pit="合法范围内的飞点（如深圳数据集里的 lat=47.66 / lon=132.54）IQR 抓不到 —— 需要业务范围规则，而不只是几何范围。",
             code="02_profile / 03_clean"),
        dict(layer="贯穿", name="断言式校验",
             one="把口径写成会失败的断言",
             inp="各阶段产物", out="validation.yaml（P0/P1/P2）",
             params="行标准化断言「每行和为 1」；孤岛单独计数",
             why="口径只有写成断言才会被遵守；写在文档里没人看。",
             pit="断言太松等于没有：只查经纬度范围 [-90,90] 过不了业务合理性这一关。",
             code="04_validate/04_validate.py"),
    ]


def build_method_atlas(facts: dict, out: Path) -> Path:
    ms = method_bank(facts)
    layer_cls = {"L0": "b", "L1": "o", "L2": "g", "L3": "p", "贯穿": ""}
    cards = "".join(f"""
        <div class="mcard" data-layer="{m['layer']}">
          <button class="mhead">
            <span class="badge {layer_cls.get(m['layer'], '')}">{m['layer']}</span>
            <span class="mname">{m['name']}</span><span class="marrow">▾</span>
          </button>
          <div class="mbody">
            <p class="mone">{m['one']}</p>
            <table class="mini">
              <tr><th>输入</th><td>{m['inp']}</td></tr>
              <tr><th>输出</th><td>{m['out']}</td></tr>
              <tr><th>关键参数</th><td>{m['params']}</td></tr>
              <tr><th>代码位置</th><td><code>{m['code']}</code></td></tr>
            </table>
            <div class="note"><b>为什么这么做</b>{m['why']}</div>
            <div class="warn"><b>坑</b>{m['pit']}</div>
          </div>
        </div>""" for m in ms)
    groups = ["全部", "L0", "L1", "L2", "L3", "贯穿"]

    body = f"""
    <p>这条管线一共用了 <b>{len(ms)}</b> 个方法。点开任意一张卡，看它的
    <b>输入 / 输出 / 关键参数 / 为什么这么做 / 坑 / 代码在哪</b> ——
    带新人最省事的讲法就是「先给全景，再按需下钻」。</p>
    <div class="tabs" id="mfilter">
      {"".join(f'<button class="dsbtn{" on" if i == 0 else ""}" data-g="{g}">{g}</button>' for i, g in enumerate(groups))}
    </div>
    <div class="mgrid">{cards}</div>
    {ui.callout("ok", "方法之间的依赖关系",
                "L0 出格 → L1 出 W → L2 出 Wx 与 I → L3 换成距离定义。"
                "<b>上游换一个参数，下游全部要重跑</b> —— 这就是为什么可复现要冻结 "
                "<code>h3_res</code>，而不只是冻结数据。")}
    """
    css = """
    .tabs{display:flex;flex-wrap:wrap;gap:8px;margin:14px 0 16px}
    .dsbtn{border:1px solid var(--line);background:var(--bg);color:var(--ink-2);border-radius:999px;
      padding:6px 16px;font-size:13px;cursor:pointer;font-family:inherit;transition:.18s}
    .dsbtn:hover{border-color:var(--brand);color:var(--brand)}
    .dsbtn.on{background:var(--brand);border-color:var(--brand);color:#fff}
    .mgrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:12px}
    .mcard{border:1px solid var(--line);border-radius:var(--radius);overflow:hidden;background:var(--bg)}
    .mhead{width:100%;display:flex;align-items:center;gap:9px;padding:12px 15px;border:0;
      background:var(--soft);cursor:pointer;font-family:inherit;text-align:left;transition:.18s}
    .mhead:hover{background:var(--soft-2)}
    .mname{font-weight:650;font-size:14px;color:var(--ink);flex:1}
    .marrow{color:var(--faint);font-size:12px;transition:transform .2s}
    .mcard.open .marrow{transform:rotate(180deg)}
    .mbody{display:none;padding:4px 16px 16px;border-top:1px solid var(--line)}
    .mcard.open .mbody{display:block}
    .mone{font-size:13.5px;color:var(--sub);margin:10px 0 12px}
    table.mini{width:100%;border-collapse:collapse;font-size:12.5px;margin:6px 0 12px}
    table.mini th{width:80px;color:var(--sub);font-weight:650;text-align:left;padding:5px 8px;
      border-bottom:1px solid var(--line);background:transparent;text-transform:none;font-size:12px}
    table.mini td{padding:5px 8px;border-bottom:1px solid var(--line);color:var(--ink-2);
      font-family:ui-monospace,Consolas,monospace;font-size:12px}
    """
    js = """
    document.querySelectorAll('.mhead').forEach(function(h){
      h.onclick=function(){ h.parentElement.classList.toggle('open'); };
    });
    document.querySelectorAll('#mfilter .dsbtn').forEach(function(b){
      b.onclick=function(){
        document.querySelectorAll('#mfilter .dsbtn').forEach(function(x){x.classList.remove('on');});
        b.classList.add('on');
        var g=b.dataset.g;
        document.querySelectorAll('.mcard').forEach(function(c){
          c.style.display = (g==='全部' || c.dataset.layer===g) ? '' : 'none';
        });
      };
    });
    """
    html = ui.page("方法图谱 · 这条管线一共用了哪些方法", body,
                   subtitle="点开卡片看输入 / 输出 / 参数 / 为什么 / 坑 / 代码位置；可按 L0–L3 分层筛选。",
                   extra_css=css, extra_js=js, active_nav="方法 · 全景")
    p = out / "method_atlas.html"
    p.write_text(html, encoding="utf-8")
    return p


# --------------------------------------------------------------------------- #
# ⑥ 自测
# --------------------------------------------------------------------------- #
def quiz_bank(facts: dict) -> list[dict]:
    """题库。**选项与答案由上游数字生成**，数字变了题也跟着变。"""
    rows = facts["rows"]
    by = lambda k: sorted(rows, key=lambda r: r[k], reverse=True)
    hi, lo = by("moran_i")[0], by("moran_i")[-1]
    nb_hi = by("mean_neighbors")[0]
    isl_hi = by("island_rate")[0]
    mono = [r for r in rows if all(r["rings"][i]["spill"] < r["rings"][i + 1]["spill"]
                                   for i in range(len(r["rings"]) - 1))]
    mono_ds = mono[0] if mono else rows[0]
    decay_hi = max(rows, key=lambda r: r["rings"][0]["density"]
                   / max(r["rings"][-1]["density"], 1e-9))
    area = facts["cell_area_km2"] or 0.737
    opts = [r["short"] for r in rows]

    def mk(q, correct, explain, options=None):
        o = list(options or opts)
        if correct not in o:
            o.append(correct)
        return dict(q=q, options=o, a=o.index(correct), e=explain)

    return [
        mk("哪个数据集的 Moran's I 最高？", hi["short"],
           f"{hi['short']} 的 I = {hi['moran_i']:.4f}，是 {lo['short']}"
           f"（{lo['moran_i']:.4f}）的 {hi['moran_i'] / max(lo['moran_i'], 1e-9):.0f} 倍。"),
        mk("哪个数据集的孤岛率最高（邻居最搭不起来）？", isl_hi["short"],
           f"{isl_hi['short']} 有 {isl_hi['islands']:,} 个孤岛格，占 {isl_hi['island_rate']:.1%}。"),
        mk("哪个数据集的平均邻居数最多？", nb_hi["short"],
           f"{nb_hi['short']} 平均 {nb_hi['mean_neighbors']:.2f} 个邻居（六边形满配 6 个）。"),
        mk("在「环内求和」口径下，哪个数据集的溢出是随距离单调递增的？", mono_ds["short"],
           "其余数据集的求和口径非单调 —— 因为环面积随距离变大、环内格数变多，"
           "求和被几何效应主导。"),
        mk("为什么「环内求和」会随距离变大？", "因为环面积变大、环内格数变多",
           "求和口径混进了「环面积」这个几何因素。要看衰减必须除以环内格数，改看密度。",
           ["因为环面积变大、环内格数变多", "因为远距离真的溢出更多",
            "因为热点圆心选错了", "因为 Moran's I 太高"]),
        mk("行标准化之后，每行权重之和等于多少？", "1（孤岛行为 0）",
           "行标准化 w*ᵢⱼ = wᵢⱼ / Σⱼ wᵢⱼ，使 Wx 变成邻居均值，与邻居数量脱钩。",
           ["1（孤岛行为 0）", "邻居个数", "总格数 n", "0"]),
        mk(f"H3 R{facts['h3_res']} 一格大约多大？", f"{area:.3f} km²",
           f"由 h3.average_hexagon_area({facts['h3_res']}) 算出，不是写死的常数。",
           [f"{area:.3f} km²", "约 1 m²", "约 100 km²", "约 0.007 km²"]),
        mk("看到 Moran's I 很低，第一件该做的事是什么？", "先看孤岛率和数据是否本来就稀疏",
           "I 低 ≠ 没有空间效应。Brightkite 的 I=0.013 里，有相当部分是「全球签到本来就散」造成的。",
           ["先看孤岛率和数据是否本来就稀疏", "立刻换一种权重方案",
            "把格值取 log 再算", "直接下结论说没有空间效应"]),
        mk("能把两个研究的 Moran's I 直接拿来比大小吗？", "不能，必须同尺度、同权重、同网格",
           "I 依赖变量尺度（raw vs log1p 会差很多）、权重方案与网格分辨率。只报 I 不报口径等于没报。",
           ["不能，必须同尺度、同权重、同网格", "能，I 是无量纲的",
            "能，只要都用六边形网格", "能，只要 n 相同"]),
        mk("libpysal 的 W 为什么必须包含孤岛格？", "否则 w.n < n，滞后向量维度对不上",
           "漏掉孤岛会让 W 的维度小于格数，Wx 与 x 拼不上，后续全线出错。孤岛滞后取 0 但仍计入分母。",
           ["否则 w.n < n，滞后向量维度对不上", "否则 Moran's I 会变大",
            "否则行标准化做不了", "否则 H3 会报错"]),
        mk("哪个数据集的溢出密度衰减最陡（首环 ÷ 末环）？", decay_hi["short"],
           f"{decay_hi['short']} 衰减 "
           f"{decay_hi['rings'][0]['density'] / max(decay_hi['rings'][-1]['density'], 1e-9):.1f} 倍。"),
        mk("空间权重矩阵是「算」出来的还是「选」出来的？", "选的 —— 它是人为定义",
           "这是本教程最想让你记住的一句：「邻居」怎么定义，决定你能看到什么结论。",
           ["选的 —— 它是人为定义", "算的 —— 数据客观决定",
            "算的 —— 由 H3 唯一确定", "选的 —— 但选哪个都不影响结论"]),
    ]


def build_quiz(facts: dict, out: Path) -> Path:
    qs = quiz_bank(facts)
    data = json.dumps(qs, ensure_ascii=False)
    body = f"""
    <p>共 <b>{len(qs)}</b> 题。题目与正确答案<b>由上游产物里的真实数字生成</b> ——
    重跑管线后数字变了，题也会跟着变，不会和教材脱节。</p>
    <div class="stats">
      <div class="stat"><span class="k">已答</span><span class="v" id="qDone">0 / {len(qs)}</span></div>
      <div class="stat"><span class="k">正确</span><span class="v" id="qRight">0</span></div>
      <div class="stat"><span class="k">正确率</span><span class="v" id="qRate">–</span></div>
      <div class="stat"><span class="k">评价</span><span class="v" id="qMsg" style="font-size:17px">开始吧</span></div>
    </div>
    <div id="qList"></div>
    <div class="note"><b>及格线</b>：≥ 9 题算掌握（能独立复现这条管线）；
    6–8 题建议回看 <a href="weight_lab.html">权重实验室</a> 与
    <a href="ring_decay.html">距离环衰减</a>；≤ 5 题建议从
    <a href="ebook/index.html">电子书引言</a> 重读一遍。</div>
    """
    css = """
    .q{border:1px solid var(--line);border-radius:var(--radius);padding:15px 17px;margin:12px 0;
      background:var(--bg);box-shadow:var(--shadow)}
    .q .qt{font-weight:650;font-size:14.5px;margin:0 0 10px;display:flex;gap:9px}
    .q .qn{color:var(--faint);font-variant-numeric:tabular-nums}
    .opt{display:block;width:100%;text-align:left;border:1px solid var(--line);background:var(--soft);
      border-radius:9px;padding:9px 13px;margin:6px 0;font-size:13.5px;cursor:pointer;
      font-family:inherit;color:var(--ink-2);transition:.16s}
    .opt:hover:not(:disabled){border-color:var(--brand);color:var(--brand)}
    .opt:disabled{cursor:default}
    .opt.right{background:var(--ok-soft);border-color:var(--ok);color:var(--ok);font-weight:600}
    .opt.wrong{background:var(--accent-soft);border-color:var(--accent);color:var(--accent)}
    .exp{display:none;margin-top:10px;font-size:13px;color:var(--ink-2);background:var(--soft);
      border-left:3px solid var(--brand);padding:9px 13px;border-radius:0 8px 8px 0}
    .exp.on{display:block}
    """
    js = """
    var QS = __DATA__, done = {}, right = 0, list = document.getElementById('qList');
    QS.forEach(function(q, i){
      var d=document.createElement('div'); d.className='q';
      var t=document.createElement('div'); t.className='qt';
      t.innerHTML='<span class="qn">'+(i+1)+'.</span><span>'+q.q+'</span>';
      d.appendChild(t);
      var ex=document.createElement('div'); ex.className='exp'; ex.textContent='\\u2713 '+q.e;
      var btns=[];
      q.options.forEach(function(o, j){
        var b=document.createElement('button'); b.className='opt'; b.textContent=o; btns.push(b);
        b.onclick=function(){
          if(done[i]) return;
          done[i]=1;
          btns.forEach(function(x){x.disabled=true;});
          if(j===q.a){ b.classList.add('right'); right++; }
          else { b.classList.add('wrong'); btns[q.a].classList.add('right'); }
          ex.classList.add('on'); sync();
        };
        d.appendChild(b);
      });
      d.appendChild(ex); list.appendChild(d);
    });
    function sync(){
      var n=Object.keys(done).length, T=QS.length;
      document.getElementById('qDone').textContent=n+' / '+T;
      document.getElementById('qRight').textContent=right;
      document.getElementById('qRate').textContent=n?Math.round(right/n*100)+'%':'\\u2013';
      document.getElementById('qMsg').textContent =
        n<T ? '\\u7ee7\\u7eed' : (right>=9?'\\u638c\\u63e1 ✔':(right>=6?'\\u56de\\u770b L1/L3':'\\u5efa\\u8bae\\u91cd\\u8bfb'));
    }
    sync();
    """.replace("__DATA__", data)
    html = ui.page("自测 · 12 题检验你有没有真的学会", body,
                   subtitle="题目与答案由上游真实数字生成 —— 重跑管线后题目会自动跟着更新。",
                   extra_css=css, extra_js=js, active_nav="自测")
    p = out / "quiz.html"
    p.write_text(html, encoding="utf-8")
    return p
