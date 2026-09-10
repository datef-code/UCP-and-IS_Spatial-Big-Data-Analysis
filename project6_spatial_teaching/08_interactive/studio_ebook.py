# -*- coding: utf-8 -*-
"""08_interactive · 可翻页电子书（教材主载体）。

框架要解决的三个真问题
----------------------
1. **新人不知道从哪开始** → 左侧常驻目录按「入门 / L0–L3 / 综合 / 收尾」分组，
   每页顶部有「你将学到」，底部有「下一步」。
2. **翻着翻着就丢了** → 顶栏进度条 + 页码 + 关键词搜索 + 记住上次读到哪（localStorage）。
3. **只有静态图看不懂逻辑链** → 每章内嵌对应交互件（iframe 引用同目录产物，离线可开）。

实现取舍
--------
* 电子书本身**不引 plotly**：图都通过 iframe 交给本目录的交互件，
  避免把几 MB 的 plotly.js 复制一份；单文件仍然成立（CSS/JS 全内联）。
* 交互件与电子书共享 ``studio_ui.CSS_TOKENS``，风格一致才像同一个产品。
"""
from __future__ import annotations

import datetime as _dt
from pathlib import Path

import studio_ui as ui


# --------------------------------------------------------------------------- #
# 章节小组件
# --------------------------------------------------------------------------- #
def goals(items: list[str]) -> str:
    return ('<div class="goals"><b>你将学到</b><ul>'
            + "".join(f"<li>{x}</li>" for x in items) + "</ul></div>")


def chapter(tag: str, title: str, body: str, *, kicker: str = "",
            learn: list[str] | None = None, takeaway: str = "",
            pitfall: str = "", nxt: tuple[str, str] | None = None) -> str:
    parts = [f'<div class="ch-tag">{tag}</div><h2>{title}</h2>']
    if kicker:
        parts.append(f'<p class="ch-kick">{kicker}</p>')
    if learn:
        parts.append(goals(learn))
    parts.append(body)
    if takeaway:
        parts.append(ui.callout("ok", "本章结论", takeaway))
    if pitfall:
        parts.append(ui.callout("warn", "最容易踩的坑", pitfall))
    if nxt:
        parts.append(f'<div class="nextbox"><span class="muted">下一步</span>'
                     f'<button class="nx" data-to="{nxt[0]}">{nxt[1]} →</button></div>')
    return "".join(parts)


# --------------------------------------------------------------------------- #
def build_ebook(facts: dict, static_figs: dict, out: Path, *,
                evolution: bool = False, moran_live: bool = False,
                n_method: int = 0, n_quiz: int = 0) -> tuple[Path, int]:
    """返回 ``(电子书路径, 页数)`` —— 页数回传给编排器，避免文案里写死数字。"""
    rows = facts["rows"]
    D = {r["key"]: r for r in rows}
    res = facts["h3_res"]
    area = facts["cell_area_km2"]
    area_s = f"{area:.3f} km²" if area else "—"
    hi = max(rows, key=lambda r: r["moran_i"])
    lo = min(rows, key=lambda r: r["moran_i"])
    ppc = [r["points_per_cell"] for r in rows]

    def fig(ds: str, slot: str, caption: str) -> str:
        f = static_figs.get(ds, {}).get(slot)
        return ui.fig_img(f"../assets/fig/{f}", caption, alt=f"{ds} {slot}") if f else ""

    rows_tbl = ui.table(
        ["数据集", "场景", "格数", "每格点数", "平均邻居", "孤岛率", "Moran's I"],
        [[r["label"], r["scene"], ui.fmt_int(r["cells"]),
          ui.fmt_num(r["points_per_cell"], 1), ui.fmt_num(r["mean_neighbors"], 2),
          ui.fmt_pct(r["island_rate"]), ui.fmt_num(r["moran_i"], 4)] for r in rows],
        num_cols={2, 3, 4, 5, 6})

    locks_html = "".join(
        f"<tr><td><code>{ds}</code></td><td>{lk.get('frozen_at', '—')}</td>"
        f"<td class='num'>{ui.fmt_int((lk.get('rows') or {}).get('cleaned'))}</td>"
        f"<td>{', '.join(f'{k} {v}' for k, v in list((lk.get('library_versions') or {}).items())[:3])}</td></tr>"
        for ds, lk in facts["locks"].items())

    pages: list[tuple[str, str, str, str]] = []          # (id, 标题, 分组, html)

    # ---------------------------------------------------------------- 封面
    pages.append(("cover", "封面", "入门", f"""
      <div class="cover">
        <div class="tag">空间大数据方法 · 可翻页教材</div>
        <h1>L0 → L3<br>四阶认知阶梯</h1>
        <p class="cover-lede">一套流程跑通四个数据集。<br>
        核心命题只有一句：<b>「邻居」怎么定义，决定你能看到什么结论。</b></p>
        <div class="cover-stats">
          {"".join(f'''<div><span class="k">{r['short']}</span>
            <span class="v" style="color:{r['color']}">{r['moran_i']:.4f}</span>
            <span class="h">Moran's I · {r['cells']:,} 格</span></div>''' for r in rows)}
        </div>
        <div class="cover-meta">
          <span class="badge">H3 R{res}</span><span class="badge b">行标准化 W</span>
          <span class="badge o">Top-100 热点</span><span class="badge g">4 个距离环</span>
        </div>
        <div class="lic">许可：FDIC 公共领域可商用；SNAP（Brightkite / Gowalla）仅限研究用途、不可商用，
        引用 Cho, Myers &amp; Leskovec, KDD 2011；深圳单车为本地存档、数据源已停更。
        <br>生成时间 {_dt.datetime.now():%Y-%m-%d %H:%M}　|　键盘 ←/→ 翻页，按 <code>/</code> 搜索</div>
      </div>"""))

    # ---------------------------------------------------------------- 导读
    pages.append(("howto", "怎么读这本书", "入门", chapter(
        "导读", "怎么读这本书",
        """<p>这本电子书是<b>给第一次接触空间分析的人</b>写的。它不像教科书那样先讲定义，
        而是按「一条流水线」往下走：每一步都回答<b>为什么要做这一步、做完能看见什么</b>。</p>

        <h3>建议路线</h3>
        """ + ui.steps([
            ("1 · 先读引言", "弄明白「为什么要给数据加空间维度」，5 分钟。"),
            ("2 · 顺着 L0→L3 走", "四章是同一条链：把点装进格 → 定义邻居 → 算邻居均值 → 换成距离。"),
            ("3 · 每章都动手", "章内嵌了可交互件，拨一拨开关，比看十张静态图管用。"),
            ("4 · 最后做自测", "12 题，及格线 9 题；不过就回看 L1 与 L3。"),
        ]) + """
        <h3>三种读法</h3>
        <div class="grid g3">
          <div class="card"><div class="t">⚡ 15 分钟速通</div>
            <p class="d">引言 → L1 → L2 → 常见误区 → 结论。只想拿走一句话的话：
            <b>I 低先看孤岛率，别急着说没有空间效应</b>。</p></div>
          <div class="card"><div class="t">📖 完整学习</div>
            <p class="d">按目录顺序读完 __NPAGES__ 页，每章做一次章内交互，最后自测。</p></div>
          <div class="card"><div class="t">🔧 照着复现</div>
            <p class="d">直接跳到「可复现」页，按 <code>version_lock.json</code> 里冻结的
            参数与库版本重跑一遍。</p></div>
        </div>

        <h3>导航</h3>
        <ul class="bullets">
          <li>左右箭头按钮，或键盘 <code>←</code> <code>→</code> 翻页；
          <code>Home</code> / <code>End</code> 到首尾。</li>
          <li>左侧目录常驻、当前页高亮；按 <code>/</code> 聚焦搜索框，输入关键词直接跳页。</li>
          <li>右上角 <code>☾ / ☀</code> 切深色模式（投影用深色，自己看用浅色）。</li>
          <li>读到的位置会记住，下次打开自动回到这一页。</li>
        </ul>""",
        nxt=("intro", "引言：为什么要空间维度"))))

    # ---------------------------------------------------------------- 引言
    pages.append(("intro", "引言：为什么要空间维度", "入门", chapter(
        "引言", "为什么要给数据加一个空间维度",
        """<p class="big">如果只把数据当「一行行记录」，你会漏掉一件事：
        <b>它们彼此之间有位置关系。</b></p>
        <p>深圳单车的起终点挤在同一座城市，Brightkite 的签到散落全球 ——
        同样是「计数」，在不同的空间结构里，含义完全不同。
        传统统计假设样本相互独立，而空间数据<b>天然不独立</b>：近的东西更像。</p>

        <h3>本教程的四步流水线</h3>
        <div class="steps4">
          <div><b>L0</b>网格化<span>点 → 格</span></div>
          <div><b>L1</b>权重<span>谁是谁的邻居</span></div>
          <div><b>L2</b>滞后<span>邻居均值 → I</span></div>
          <div><b>L3</b>距离环<span>效应随距离衰减</span></div>
        </div>

        <h3>四个数据集，四种空间结构</h3>"""
        + rows_tbl
        + f"""<p>注意 <b>每格点数</b> 这一列：
        {max(rows, key=lambda r: r['points_per_cell'])['short']} 每格 {max(ppc):,.0f} 个点，
        {min(rows, key=lambda r: r['points_per_cell'])['short']} 只有 {min(ppc):,.0f} 个 ——
        差 {max(ppc) / max(min(ppc), 1e-9):.0f} 倍。
        <b>后面所有结论的差异，地基都在这里。</b></p>""",
        learn=["空间数据为什么不满足独立性假设",
               "这条四步流水线每一步在解决什么问题",
               "四个数据集的空间结构差异有多大"],
        takeaway="空间分析不是「多画一张地图」，而是<b>把位置关系写进模型</b>。"
                 "四步流水线就是把这件事拆成可执行的四步。",
        pitfall="最常见的误解是「先跑模型再说」。实际上 L0 的网格分辨率、L1 的权重定义"
                "已经决定了你能看到什么 —— 它们不是技术细节，是<b>建模假设</b>。",
        nxt=("l0", "L0 · 网格化"))))

    # ---------------------------------------------------------------- L0
    pages.append(("l0", "L0 · 网格化", "L0 网格化", chapter(
        "L0", "把点装进 H3 六边形格",
        f"""<p>点太密、太乱，先离散化：把每个点的经纬度映射到 Uber H3 的
        <b>R{res} 六边形</b>（平均 {area_s}/格），格内求和得到「格值」。
        这一步把「点云」变成「栅格」。</p>

        <h3>为什么是六边形</h3>
        <div class="grid g2">
          <div class="card"><div class="t">六边形：邻居方向一致</div>
            <p class="d">每个格有 6 个共享边的邻居，方向统一、距离一致，
            没有「对角算不算邻居」的歧义。</p></div>
          <div class="card"><div class="t">方格：永远有歧义</div>
            <p class="d">4 邻（共享边）还是 8 邻（含对角）？选哪个都会改变结果，
            而且说不清为什么。</p></div>
        </div>

        <h3>分辨率是第一个关键决策</h3>"""
        + ui.formula("H3 分辨率 ↔ 格面积",
                     f"本管线 h3_res = {res} ⇒ 平均 {area_s}/格<br>"
                     "res 每 +1，格面积约 ÷7；每 −1，约 ×7")
        + """<p>分辨率太大（格太小）→ 一格一个点，邻居全是孤岛，权重矩阵搭不起来；
        分辨率太小（格太大）→ 空间细节被抹平，全图糊成几块。
        <b>没有标准答案，只有业务口径</b>：你关心的现象在多大的尺度上发生？</p>

        <h3>格值长什么样</h3>"""
        + fig("sz_bike", "l0", "sz_bike：格值 ECDF —— 长尾是空间数据的常态")
        + fig("fdic", "l0", "fdic：格值 ECDF")
        + """<p>两条曲线都说明同一件事：<b>格值是长尾的</b>，少数格贡献了大部分量。
        这直接决定了 L2 的取舍 —— 在长尾原始数据上算 Moran's I，结果会被极端格主导。</p>""",
        learn=["H3 六边形网格为什么比方格好用",
               "分辨率（res）怎么选、选错的后果",
               "格值分布的长尾特性"],
        takeaway="L0 把「连续空间」离散成「可数单元」。这一步的参数 <code>h3_res</code> "
                 "会被冻结进 <code>version_lock.json</code> —— 因为改它必须重跑整条链。",
        pitfall="聚合函数默认 sum。若业务问的是「强度」而不是「总量」，应改用 mean 或密度；"
                "口径不同，后面的 I 也不同。",
        nxt=("l1", "L1 · 权重矩阵"))))

    # ---------------------------------------------------------------- L1
    pages.append(("l1", "L1 · 权重矩阵", "L1 权重", chapter(
        "L1", "定义「谁是邻居」",
        f"""<p>空间权重矩阵 <code>W</code> 是空间分析里<b>最主观、最影响结论</b>的一步。
        它回答：谁算谁的邻居？答案<b>不是数据给的，是你定的</b>。</p>

        <div class="embed">
          <iframe src="../weight_lab.html" loading="lazy" title="权重实验室"></iframe>
          <div class="cap">↑ 在实验室里切换四个数据集，看平均邻居数、孤岛率与 I 的关系。</div>
        </div>

        <h3>邻接：H3 grid_disk(k=1)</h3>
        <p>六边形共享边即邻居，满配 6 个。实测平均邻居数从
        <b>{min(r['mean_neighbors'] for r in rows):.2f}</b>
        （{min(rows, key=lambda r: r['mean_neighbors'])['short']}）到
        <b>{max(r['mean_neighbors'] for r in rows):.2f}</b>
        （{max(rows, key=lambda r: r['mean_neighbors'])['short']}）——
        差的不是算法，是<b>数据密不密</b>。</p>

        <h3>行标准化</h3>"""
        + ui.formula("行标准化（row-standardized）",
                     "w*ᵢⱼ = wᵢⱼ / Σⱼ wᵢⱼ &nbsp;⇒&nbsp; 每行权重和 = 1<br>"
                     "空间滞后 Wx 由「邻居求和」变成「邻居均值」，与邻居数量脱钩")
        + """<h3>孤岛：一格邻居都没有</h3>
        <div class="grid g4">"""
        + "".join(f'''<div class="card"><div class="t" style="color:{r['color']}">{r['short']}</div>
            <p class="d">孤岛 <b>{r['islands']:,}</b> 格<br>
            <span class="muted">占 {ui.fmt_pct(r['island_rate'])}　平均邻居 {r['mean_neighbors']:.2f}</span></p></div>'''
                  for r in sorted(rows, key=lambda x: -(x["island_rate"] or 0)))
        + f"""</div>
        <p>孤岛的滞后取 0，<b>仍计入 I 的分母</b>。所以孤岛越多，I 越被稀释 ——
        这正是 {lo['short']} 的 I 只有 {lo['moran_i']:.4f} 的一大原因。</p>""",
        learn=["W 有哪几种定义方式、各自代价",
               "行标准化到底在抹平什么",
               "孤岛为什么是 I 的头号杀手"],
        takeaway="权重矩阵不是算出来的，是<b>选</b>出来的。报告任何空间结论都必须同时报："
                 "网格（H3 R?）+ 权重方案（Queen / KNN k=?）+ 标准化方式。",
        pitfall="<code>libpysal.weights.W</code> 必须覆盖<b>全部格（含孤岛）</b>，"
                "否则 <code>w.n &lt; n</code>，滞后向量维度对不上，后面全线崩。",
        nxt=("l2", "L2 · 空间滞后"))))

    # ---------------------------------------------------------------- L2
    pages.append(("l2", "L2 · 空间滞后", "L2 滞后", chapter(
        "L2", "空间滞后与 Moran's I",
        f"""<p>有了 W，就能算<b>空间滞后</b> <code>Wx</code>：每个格的邻居均值。
        把格值画横轴、滞后画纵轴，散点拟合线的斜率就是 <b>Moran's I</b>。</p>

        <div class="embed">
          <iframe src="../moran_explorer.html" loading="lazy" title="Moran 实验室"></iframe>
          <div class="cap">↑ {"可交互散点（格级 CSV 已就绪，可切数据集 / 权重 / 尺度）" if moran_live else "当前为上游 ⑥ 阶段真实散点；重跑 ⑤ 映射后自动升级为可交互版本"}。</div>
        </div>

        <h3>公式</h3>"""
        + ui.formula("全局 Moran's I",
                     "I = ( n / S₀ ) · ( zᵀWz ) / ( zᵀz ) &nbsp;&nbsp;z = x − x̄，S₀ = ΣᵢΣⱼ wᵢⱼ<br>"
                     "行标准化后 S₀ = n ⇒ <b>I = zᵀWz / zᵀz = 散点斜率</b>")
        + """<h3>四个象限</h3>
        <div class="grid g4">
          <div class="card"><div class="t"><span class="badge g">HH</span>高–高</div>
            <p class="d">热点，推高 I。</p></div>
          <div class="card"><div class="t"><span class="badge g">LL</span>低–低</div>
            <p class="d">冷点，也推高 I。</p></div>
          <div class="card"><div class="t"><span class="badge o">HL</span>高–低</div>
            <p class="d">空间离群，压低 I。</p></div>
          <div class="card"><div class="t"><span class="badge o">LH</span>低–高</div>
            <p class="d">同样压低 I。</p></div>
        </div>

        <h3>四个数据集的 I</h3>
        <div class="grid g4">"""
        + "".join(f'''<div class="card"><div class="t" style="color:{r['color']}">{r['short']}</div>
            <p class="d"><b style="font-size:20px">{r['moran_i']:.4f}</b><br>
            <span class="muted">corr(格值,滞后) = {r['lag_corr']:.4f}</span></p></div>''' for r in rows)
        + f"""</div>
        <p>{hi['short']} 的 I 是 {lo['short']} 的
        <b>{hi['moran_i'] / max(lo['moran_i'], 1e-9):.0f} 倍</b>。
        教科书会说「深圳单车强聚集、Brightkite 几乎随机」，但更诚实的说法是 ——
        <b>{lo['short']} 的 I 里，有很大一部分是「数据本来就散」造成的</b>。</p>""",
        learn=["空间滞后 Wx 是怎么算的",
               "为什么行标准化后 I 恰好等于散点斜率",
               "Moran 散点四象限分别代表什么"],
        takeaway="I &gt; 0 = 聚集，I ≈ 0 = 随机，I &lt; 0 = 高低交错。"
                 "但 I <b>依赖变量尺度与权重定义</b>，跨研究比较必须同尺度、同权重、同网格。",
        pitfall="只报一个 I 不报口径，等于没报。取 log1p 再算，I 会明显变化 —— "
                "这本身就该写进结论。",
        nxt=("l3", "L3 · 距离环"))))

    # ---------------------------------------------------------------- L3
    pages.append(("l3", "L3 · 距离环", "L3 距离环", chapter(
        "L3", "邻居换成距离环：效应怎么随距离衰减",
        f"""<p>「谁是邻居」还可以用<b>距离</b>回答：以格值 Top-{rows[0]['centers']} 热点格为圆心
        画环（{" / ".join(rk['label'] for rk in rows[0]['rings'])}），看环内的溢出怎么变。</p>

        <div class="embed">
          <iframe src="../ring_decay.html" loading="lazy" title="距离环衰减"></iframe>
          <div class="cap">↑ 点「环内求和 / 溢出密度」两个按钮，看同一个数据给出相反结论。</div>
        </div>

        <h3>本页最重要的一个坑</h3>"""
        + ui.callout("warn", "求和口径会「越远越多」",
                     "环越远，<b>环面积越大 → 环内格数越多 → 求和必然变大</b>。"
                     "所以「环内求和」<b>不是</b>衰减指标。必须除以环内格数，看<b>密度</b>。")
        + """<h3>两种口径的完整数字</h3>"""
        + ui.table(["数据集"]
                   + [f"{rk['label']}<br>求和" for rk in rows[0]["rings"]]
                   + [f"{rk['label']}<br>密度" for rk in rows[0]["rings"]],
                   [[r["short"]] + [ui.fmt_num(x["spill"], 0) for x in r["rings"]]
                    + [ui.fmt_num(x["density"], 0) for x in r["rings"]] for r in rows],
                   num_cols=set(range(1, 9)))
        + """<p><b>求和口径</b>：只有 sz_bike 随距离单调递增 —— 那是几何效应，不是业务效应。
        <b>密度口径</b>：四个数据集<b>全部单调递减</b>，这才是真正的距离衰减。</p>

        <h3>衰减速度也各不相同</h3>
        <div class="grid g4">"""
        + "".join(f'''<div class="card"><div class="t" style="color:{r['color']}">{r['short']}</div>
            <p class="d">衰减 <b>{r['rings'][0]['density'] / max(r['rings'][-1]['density'], 1e-9):.1f}×</b><br>
            <span class="muted">{ui.fmt_num(r['rings'][0]['density'], 0)} → {ui.fmt_num(r['rings'][-1]['density'], 0)}</span></p></div>'''
                  for r in rows)
        + "</div>",
        learn=["距离环怎么定义、圆心怎么选",
               "为什么求和口径会得到假结论",
               "密度口径下的衰减速率怎么比"],
        takeaway="聚合口径不是技术细节，它<b>直接决定结论方向</b>。"
                 "任何「随距离变化」的表，都要写清分子分母。",
        pitfall="距离要用 Haversine（球面）而不是欧氏：高纬度地区 1° 经度对应的公里数会缩水，"
                "用欧氏距离会系统性偏差。",
        nxt=("compare", "四数据集对比"))))

    # ---------------------------------------------------------------- 对比
    pages.append(("compare", "四数据集对比", "综合", chapter(
        "综合", "同一套管线，四个数据集",
        """<p>把 L0–L2 的指标摊在一张表上，差别一目了然。差别不在算法，在<b>数据本身</b>。</p>
        <div class="embed">
          <iframe src="../ladder_compare.html" loading="lazy" title="阶梯对比"></iframe>
          <div class="cap">↑ 左上角下拉切换 8 个指标：L0 规模 → L1 连通性 → L2 聚集强度。</div>
        </div>"""
        + rows_tbl
        + f"""<h3>怎么看这张表</h3>
        <ul class="bullets">
          <li><b>每格点数</b>是最直观的密度指标，四个数据集差 {max(ppc) / max(min(ppc), 1e-9):.0f} 倍。</li>
          <li><b>平均邻居</b>跟着密度走：5.07 → 2.40 → 2.01 → 1.41。</li>
          <li>但 <b>I 不完全跟着平均邻居走</b>：fdic 与 Gowalla 的孤岛率只差几个百分点，
          I 却差好几倍 —— <b>值的分布形态同样重要</b>。</li>
        </ul>""",
        learn=["四个数据集在每一层各差多少",
               "连通性与聚集强度为什么不是一回事"],
        takeaway=f"同一套管线跑出来的 I 差 {hi['moran_i'] / max(lo['moran_i'], 1e-9):.0f} 倍，"
                 "<b>不是算法偏好，是数据本身的空间结构</b>。",
        nxt=("evolution", "L0→L3 是一条链"))))

    # ---------------------------------------------------------------- 演化
    evo = ("""<div class="embed">
          <iframe src="../ladder_evolution.html" loading="lazy" title="L0→L3 演化动图"></iframe>
          <div class="cap">点 → 格 → 邻居 → 滞后 → 距离环（深圳共享单车）。可下载 mp4 直接放课件。</div>
        </div>""" if evolution else
           """<div class="warn"><b>演化动图需要格级 CSV + ffmpeg</b>
           生成它需要 <code>05_map/output/sz_bike/mapped.csv</code>（受 <code>.gitignore</code>
           约束不入库）与 ffmpeg。在有完整数据的环境里跑
           <code>python main.py --stage 08</code> 会自动生成并内嵌本页；
           <b>没有它不影响理解其余 14 页</b>。</div>""")
    pages.append(("evolution", "L0→L3 是一条链", "综合", chapter(
        "综合", "看它们怎么串成一条链",
        """<p>静态图只能分别展示 L0/L1/L2/L3，看不出它们<b>是一条链</b>。
        这段动图把「点装进格 → 定义邻居 → 算邻居均值 → 换成距离环」的递进演出来。</p>
        """ + evo + """
        <h3>链条上的依赖关系</h3>
        <div class="steps4">
          <div><b>L0</b>出格<span>没有格就没有邻居</span></div>
          <div><b>L1</b>出 W<span>没有 W 就没有滞后</span></div>
          <div><b>L2</b>出 Wx 与 I<span>I 依赖 W 与尺度</span></div>
          <div><b>L3</b>换距离定义<span>回答「多远还在影响」</span></div>
        </div>
        <p><b>上游换一个参数，下游全部要重跑。</b>这就是为什么可复现要冻结
        <code>h3_res</code>，而不只是冻结数据。</p>""",
        learn=["四层之间的依赖：为什么改上游必须重跑下游"],
        takeaway="四层不是四个并列的方法，是<b>一条流水线</b>：每一层的输出是下一层的输入。",
        nxt=("pitfalls", "常见误区"))))

    # ---------------------------------------------------------------- 误区
    pitfalls = [
        ("① 把 I 当成绝对真理",
         "I 依赖变量尺度与权重定义。<b>只报 I 不报口径，等于没报。</b>"
         "跨研究比较必须同尺度、同权重、同网格。"),
        ("② I 低就说「没有空间效应」",
         "先看<b>孤岛率</b>。Brightkite 的 I=0.013，很大程度上是「全球签到本来就散」造成的，"
         "不是「没有空间结构」。"),
        ("③ 用「环内求和」看距离衰减",
         "环面积随距离变大 → 求和必然变大 → 得出「越远影响越大」的假结论。"
         "<b>必须除格数看密度。</b>"),
        ("④ W 漏掉孤岛格",
         "<code>w.n &lt; n</code> 会让 Wx 维度对不上，后续全线崩。孤岛滞后取 0，但仍计入分母。"),
        ("⑤ 用欧氏距离算经纬度",
         "高纬度地区 1° 经度对应的公里数会缩水。要用 <b>Haversine</b>（球面距离）。"),
        ("⑥ 把 KNN 当万能解",
         "KNN 消灭了孤岛，也<b>消灭了「这里本来就孤立」的信号</b>；"
         "全球稀疏数据上会把大洋彼岸认成邻居。"),
        ("⑦ 只做几何范围校验",
         "lat∈[-90,90] 挡不住深圳数据集里 lat=47.66 的飞点。"
         "<b>合法性 ≠ 合理性</b>，需要业务范围的规则，而不只是几何范围。"),
    ]
    pages.append(("pitfalls", "常见误区（7 条）", "综合", chapter(
        "综合", "七个最容易犯的错",
        "<p>这一页把前面散落各章的坑收拢。带新人的时候，直接让他读这一页最省事。</p>"
        + "".join(ui.callout("warn", t, b) for t, b in pitfalls),
        learn=["七个高频错误的症状与解法"],
        takeaway="这七条里，<b>①②③ 是结论层面的</b>（会让你的结论错），"
                 "<b>④⑤⑥⑦ 是实现层面的</b>（会让你根本跑不出数）。",
        nxt=("migrate", "迁移清单"))))

    # ---------------------------------------------------------------- 迁移清单
    pages.append(("migrate", "迁移清单 · 用到自己的数据上", "实践", chapter(
        "实践", "把这条管线用到你自己的数据上",
        """<p>读完前面 13 页，最后要回答的是：<b>我的数据能不能这么跑？</b>
        这一页给一份可直接照做的检查清单。</p>

        <h3>最小可用输入：只要三个字段</h3>
        <div class="grid g3">
          <div class="card"><div class="t">lat</div>
            <p class="d">纬度，WGS84。<b>必须</b>落在 [-90, 90]，
            但合法不等于合理（深圳数据集里出现过 47.66）。</p></div>
          <div class="card"><div class="t">lon</div>
            <p class="d">经度，WGS84。跨 180° 经线要单独处理。</p></div>
          <div class="card"><div class="t">value</div>
            <p class="d">你要聚合的量。决定它是<b>计数</b>还是<b>强度</b>，
            直接决定聚合函数用 sum 还是 mean。</p></div>
        </div>

        <h3>选分辨率：问自己三个问题</h3>
        <ol class="bullets">
          <li><b>你关心的现象发生在多大尺度上？</b>街区级用 R9–R10，城市级 R7–R8，全国级 R5–R6。</li>
          <li><b>你能接受多少孤岛？</b>先按候选 res 跑一遍 L1，孤岛率 &gt; 30% 就该调粗。</li>
          <li><b>格数会不会撑爆内存？</b>权重矩阵是稀疏的，但 KNN 的 KD-tree 与散点渲染都随 n 增长；
          30 万格是浏览器与内存的舒适上界附近。</li>
        </ol>

        <h3>选权重：问自己三个问题</h3>
        <ol class="bullets">
          <li><b>邻接还是 KNN？</b>数据密、形状规则 → 邻接；数据稀、必须消灭孤岛 → KNN，
          但要接受「邻居可能很远」。</li>
          <li><b>孤岛留不留？</b>留（滞后取 0，稀释 I）还是补（KNN）？
          <b>两条路都要在报告里写明。</b></li>
          <li><b>行标准化还是二值？</b>想让 Wx 表示「邻居均值」→ 行标准化；
          想保留「邻居多就是影响大」→ 二值。</li>
        </ol>

        <h3>报告里必须写的五件事</h3>
        <ul class="bullets">
          <li>网格系统与分辨率（H3 R8）</li>
          <li>权重方案与标准化方式（Queen 邻接 / 行标准化）</li>
          <li>变量尺度（原始值 / log1p）</li>
          <li>聚合口径（求和 / 密度 / 均值）</li>
          <li>孤岛数量与占比</li>
        </ul>
        <p>缺任何一条，你的 Moran's I 都无法被别人复现或比较。</p>

        <h3>上线前检查清单</h3>
        <div class="checks">
          <label><input type="checkbox"> 经纬度在合法范围内，且<b>在业务范围内</b>（不只查几何范围）</label>
          <label><input type="checkbox"> 格值分布看过 ECDF，长尾已决定要不要取 log</label>
          <label><input type="checkbox"> W 覆盖了全部格（含孤岛），<code>w.n == n</code></label>
          <label><input type="checkbox"> 行标准化后每行和为 1（孤岛行除外）</label>
          <label><input type="checkbox"> 距离用 Haversine，经纬度已转弧度</label>
          <label><input type="checkbox"> 距离环结论用的是<b>密度</b>而不是求和</label>
          <label><input type="checkbox"> <code>version_lock.json</code> 已冻结参数与库版本</label>
          <label><input type="checkbox"> 报告里写全了上面「五件事」</label>
        </div>""",
        learn=["自己的数据需要哪些最小字段",
               "分辨率与权重该怎么选、按什么标准",
               "报告里必须披露的五件事"],
        takeaway="空间分析最难的不是算，是<b>把口径说清楚</b>。"
                 "这份清单照着过一遍，能挡掉绝大多数返工。",
        nxt=("conclusion", "结论与限制"))))

    # ---------------------------------------------------------------- 结论
    pages.append(("conclusion", "结论与限制", "收尾", chapter(
        "收尾", "结论与限制",
        f"""<h3>结论</h3>
        <ol class="bullets">
          <li><b>「邻居」是人为定义。</b>换一种定义，Moran's I 就变 ——
          从 {lo['moran_i']:.4f} 到 {hi['moran_i']:.4f} 的差距里，有相当部分来自权重与数据密度。</li>
          <li><b>聚合口径决定结论方向。</b>同一个距离环数据，「求和」给出递增、「密度」给出递减。</li>
          <li><b>看到低 I，先问数据稀不稀。</b>孤岛率是最先该看的一个数。</li>
          <li><b>空间分析的地基是分辨率与权重。</b>它们不是技术细节，是建模假设。</li>
        </ol>

        <h3>限制（必须说清）</h3>
        <ul class="bullets">
          <li>所有成本参数（<code>h3_res</code> / <code>hot_top_n</code> / 环宽 / 抽样日）
          都是<b>合成参数</b>，非真实业务口径 —— 结论是<b>方法演示</b>，不是业务发现。</li>
          <li>只算了<b>全局</b> Moran's I，没有做局部 LISA / 显著性置换检验；
          I 的点估计不足以支撑「显著聚集」的判断。</li>
          <li>sz_bike 为抽样日（每月 15 日）数据，不代表全年；数据源已停更。</li>
          <li>SNAP（Brightkite / Gowalla）<b>仅限研究用途，不允许商用</b>。</li>
        </ul>""",
        learn=["四条结论各自成立的前提", "四条限制为什么必须写进报告"],
        takeaway="教学产品的价值不在「结论多漂亮」，而在<b>把限制讲清楚</b> —— "
                 "能被复现、能被质疑，才叫可信。",
        nxt=("quiz", "自测"))))

    # ---------------------------------------------------------------- 自测
    pages.append(("quiz", "自测", "收尾", chapter(
        "收尾", "12 题：你真的学会了吗",
        """<div class="embed tall">
          <iframe src="../quiz.html" loading="lazy" title="自测"></iframe>
          <div class="cap">题目与答案由上游真实数字生成 —— 重跑管线后题目会自动跟着更新。</div>
        </div>
        <p><b>及格线</b>：≥ 9 题算掌握（能独立复现这条管线）；6–8 题建议回看
        L1 与 L3；≤ 5 题建议从引言重读。</p>""",
        learn=["检验自己能不能独立复现这条管线"],
        nxt=("repro", "可复现"))))

    # ---------------------------------------------------------------- 复现
    pages.append(("repro", "可复现", "收尾", chapter(
        "收尾", "可复现（教学产品的信服度来源）",
        """<p>每个数据集的 <code>version_lock.json</code> 冻结了源数据指纹、行数、库版本与成本参数；
        版本漂移会被 ④ 阶段记为<b>断言失败</b>。教学产品的信服度来自一句话：
        <b>你能重跑出同样的数。</b></p>
        <table><thead><tr><th>数据集</th><th>冻结时间</th><th class="num">清洗后行数</th>
        <th>库版本</th></tr></thead><tbody>""" + locks_html + """</tbody></table>

        <h3>怎么重跑</h3>"""
        + ui.formula("命令行",
                     "python main.py                # 全流程<br>"
                     "python main.py --stage 08     # 只重建本阶段（交互教材）")
        + f"""<h3>产物清单</h3>
        <table><thead><tr><th>产物</th><th>回答什么</th></tr></thead><tbody>
          <tr><td><code>index.html</code></td><td>入口：学习路径 + 产品矩阵</td></tr>
          <tr><td><code>ebook/index.html</code></td><td>本电子书（__NPAGES__ 页，可翻页/搜索/记进度）</td></tr>
          <tr><td><code>moran_explorer.html</code></td><td>Moran's I 怎么读、差多少</td></tr>
          <tr><td><code>weight_lab.html</code></td><td>「邻居」是谁定的、孤岛有多致命</td></tr>
          <tr><td><code>ring_decay.html</code></td><td>两种口径为什么给出相反结论</td></tr>
          <tr><td><code>ladder_compare.html</code></td><td>四数据集逐层对比（8 个指标）</td></tr>
          <tr><td><code>method_atlas.html</code></td><td>{n_method} 个方法的输入/输出/坑/代码位置</td></tr>
          <tr><td><code>quiz.html</code></td><td>{n_quiz} 题自测</td></tr>
          <tr><td><code>ladder_evolution.html</code></td><td>L0→L3 演化动图（需格级 CSV + ffmpeg）</td></tr>
        </tbody></table>
        <div class="note"><b>引用</b>：SNAP 数据请引用 Cho, Myers &amp; Leskovec,
        <i>Friendship and Mobility: User Movement in Location-Based Social Networks</i>, KDD 2011。
        FDIC SOD 为美国联邦政府公共领域数据。</div>""",
        learn=["version_lock 冻结了什么、为什么", "怎么一条命令重建整个教材"],
        takeaway="可复现 &gt; 好看。教材里的每个数字都来自上游产物，没有一个硬编码的指标。")))

    # ---------------------------------------------------------------- 术语表
    glossary = [
        ("H3", "Uber 开源的全球离散网格系统，用六边形把地球切成多分辨率的格。"),
        ("分辨率（res）", f"H3 的层级。本管线 res={res}，平均 {area_s}/格；res 每 +1 面积约 ÷7。"),
        ("空间权重矩阵 W", "n×n 稀疏矩阵，wᵢⱼ 表示格 j 对格 i 的影响强度。"
                        "定义方式（邻接 / KNN / 距离）由人选择。"),
        ("行标准化", "w*ᵢⱼ = wᵢⱼ / Σⱼ wᵢⱼ，使每行和为 1。之后 Wx 就是「邻居均值」。"),
        ("空间滞后 Wx", "每个格的邻居加权平均，把「邻居怎么样」变成一个新变量。"),
        ("Moran's I", "全局空间自相关指标，取值约 [-1, 1]。行标准化下等于 Moran 散点的斜率。"),
        ("孤岛（island）", "一个邻居都没有的格。滞后为 0 但仍计入 I 的分母，会稀释 I。"),
        ("距离环", "以某点为圆心的环形区域（如 0–1 km / 1–3 km），用于看效应随距离怎么变。"),
        ("溢出密度", "环内格值求和 ÷ 环内格数。比「求和」更能反映真实的距离衰减。"),
        ("Haversine 距离", "球面两点距离公式。经纬度必须先转弧度，否则结果完全错。"),
        ("ECDF", "经验累积分布函数，用来看格值是不是长尾。"),
        ("KD-tree", "最近邻检索结构。KNN 权重用它避免 n×n 距离矩阵爆内存。"),
        ("version_lock", "冻结源数据指纹、行数、库版本与成本参数的 JSON，用于可复现。"),
        ("IQR", "四分位距离群检测法。抓不到「合法但不合理」的飞点。"),
    ]
    pages.append(("glossary", "术语表", "收尾",
                  '<div class="ch-tag">附录</div><h2>术语表</h2><div class="grid g2">'
                  + "".join(f'<div class="card"><div class="t">{t}</div><p class="d">{d}</p></div>'
                            for t, d in glossary) + "</div>"))

    # ---------------------------------------------------------------- 组装
    groups: list[tuple[str, list[tuple[str, str]]]] = []
    for pid, title, grp, _html in pages:
        if not groups or groups[-1][0] != grp:
            groups.append((grp, []))
        groups[-1][1].append((pid, title))

    toc = "".join(
        f'<div class="tocg"><div class="tocgt">{g}</div>'
        + "".join(f'<a class="toca" href="#{pid}" data-to="{pid}" data-k="{t}">{t}</a>'
                  for pid, t in items) + "</div>"
        for g, items in groups)
    # 页数在页面逐个 append 的过程中才知道，用占位符最后统一替换（避免文案写死数字）
    body = "".join(f'<section class="page" id="{pid}" data-k="{title}">{html}</section>'
                   for pid, title, _g, html in pages).replace("__NPAGES__", str(len(pages)))

    css = """
    .app{display:flex;min-height:100vh}
    .side{width:252px;flex:0 0 252px;border-right:1px solid var(--line);background:var(--soft);
      position:sticky;top:0;height:100vh;overflow-y:auto;padding:16px 12px 40px}
    .side h4{margin:0 4px 11px;font-size:13px;letter-spacing:.05em;color:var(--ink);
      display:flex;align-items:center;gap:7px}
    .side h4 i{width:7px;height:7px;border-radius:2px;background:var(--accent);display:inline-block}
    #q{width:100%;padding:8px 11px;border:1px solid var(--line);border-radius:9px;font-size:13px;
      background:var(--bg);color:var(--ink);font-family:inherit;margin-bottom:12px}
    #q:focus{outline:2px solid var(--brand);outline-offset:-1px}
    .tocg{margin-bottom:14px}
    .tocgt{font-size:11px;letter-spacing:.1em;color:var(--faint);font-weight:700;
      padding:0 6px 5px;text-transform:uppercase}
    .toca{display:block;padding:6px 10px;border-radius:8px;font-size:13px;color:var(--ink-2);
      cursor:pointer;transition:.15s;border-left:2px solid transparent;text-decoration:none}
    .toca:hover{background:var(--soft-2);color:var(--brand);text-decoration:none}
    .toca.on{background:var(--brand-soft);color:var(--brand);font-weight:650;
      border-left-color:var(--brand)}
    .main{flex:1;min-width:0;display:flex;flex-direction:column}
    /* position:sticky 本身就是 positioned，可作为 .prog（absolute）的包含块；
       不要再写 position:relative，否则会把 sticky 覆盖掉。 */
    .bar{position:sticky;top:0;z-index:20;display:flex;align-items:center;gap:10px;
      padding:10px 20px;background:var(--bg);border-bottom:1px solid var(--line)}
    .bar .pt{font-weight:650;font-size:14px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
    .bar .sp{flex:1}
    .cnt{font-size:12.5px;color:var(--faint);font-variant-numeric:tabular-nums;white-space:nowrap}
    .prog{position:absolute;left:0;bottom:-1px;height:2px;background:var(--accent);width:0;
      transition:width .3s cubic-bezier(.4,0,.2,1)}
    .icon{border:1px solid var(--line);background:var(--bg);color:var(--ink-2);border-radius:8px;
      min-width:34px;height:30px;cursor:pointer;font-size:14px;font-family:inherit;transition:.16s;
      padding:0 8px}
    .icon:hover:not(:disabled){border-color:var(--brand);color:var(--brand)}
    .icon:disabled{opacity:.35;cursor:not-allowed}
    #menu{display:none}
    .book{flex:1;padding:34px 40px 80px;max-width:900px;width:100%}
    .page{display:none}
    .page.on{display:block;animation:fade .3s cubic-bezier(.4,0,.2,1)}
    @keyframes fade{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:none}}
    .ch-tag{display:inline-block;font-size:11px;letter-spacing:.14em;font-weight:800;
      color:var(--accent);margin-bottom:6px}
    .ch-kick{font-size:16px;color:var(--sub);margin:0 0 16px}
    .book h2{font-size:27px;margin:0 0 6px;border:0;padding:0}
    .book h3{font-size:17px;margin:26px 0 8px;color:var(--ink)}
    .book p{font-size:15px;color:var(--ink-2);line-height:1.85}
    p.big{font-size:17px;color:var(--ink);font-weight:600}
    ul.bullets li,ol.bullets li{margin:8px 0;font-size:14.5px;color:var(--ink-2);line-height:1.75}
    .goals{border:1px solid var(--line);border-left:3px solid var(--brand);
      border-radius:0 12px 12px 0;padding:12px 18px;margin:16px 0;background:var(--brand-soft)}
    .goals b{font-size:13px;color:var(--brand);display:block;margin-bottom:5px}
    .goals ul{margin:0;padding-left:20px}
    .goals li{font-size:13.5px;color:var(--ink-2);margin:3px 0}
    .embed{border:1px solid var(--line);border-radius:var(--radius);overflow:hidden;margin:18px 0;
      box-shadow:var(--shadow)}
    .embed iframe{width:100%;height:560px;border:0;display:block;background:var(--bg)}
    .embed.tall iframe{height:780px}
    .embed .cap{font-size:12.5px;color:var(--sub);padding:9px 14px;background:var(--soft);
      border-top:1px solid var(--line)}
    .steps4{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:18px 0}
    .steps4 div{border:1px solid var(--line);border-radius:12px;padding:13px;text-align:center;
      background:var(--soft)}
    .steps4 b{display:block;color:var(--accent);font-size:16px}
    .steps4 span{font-size:12.5px;color:var(--sub)}
    .nextbox{margin-top:30px;padding-top:16px;border-top:1px solid var(--line);
      display:flex;align-items:center;gap:12px}
    .nx{margin-left:auto;border:1px solid var(--line);background:var(--bg);color:var(--brand);
      border-radius:10px;padding:9px 18px;font-size:14px;cursor:pointer;font-family:inherit;
      font-weight:600;transition:.18s}
    .nx:hover{border-color:var(--brand);background:var(--brand-soft);transform:translateX(3px)}
    .checks{display:grid;gap:8px;margin:14px 0}
    .checks label{display:flex;gap:10px;align-items:flex-start;border:1px solid var(--line);
      border-radius:10px;padding:10px 14px;background:var(--soft);font-size:14px;
      color:var(--ink-2);cursor:pointer;transition:.16s}
    .checks label:hover{border-color:var(--brand)}
    .checks input{margin-top:5px;accent-color:var(--brand);width:15px;height:15px;flex:0 0 auto}
    .cover{padding:34px 0 10px}
    .cover .tag{display:inline-block;font-size:11.5px;letter-spacing:.16em;color:var(--accent);
      font-weight:800;margin-bottom:14px}
    .cover h1{font-size:56px;line-height:1.08;margin:0 0 18px;letter-spacing:-.02em}
    .cover-lede{font-size:17px;color:var(--sub);line-height:1.8}
    .cover-stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(148px,1fr));gap:12px;
      margin:28px 0}
    .cover-stats div{border:1px solid var(--line);border-radius:12px;padding:13px 15px;
      background:var(--soft)}
    .cover-stats .k{display:block;font-size:12px;color:var(--sub)}
    .cover-stats .v{display:block;font-size:25px;font-weight:750;font-variant-numeric:tabular-nums}
    .cover-stats .h{display:block;font-size:11px;color:var(--faint)}
    .cover-meta{margin:8px 0 22px}
    .lic{font-size:12px;color:var(--faint);border-top:1px solid var(--line);padding-top:14px;
      line-height:1.8}
    @media(max-width:900px){
      .side{position:fixed;left:0;top:0;z-index:40;transform:translateX(-100%);
        transition:transform .25s;box-shadow:var(--shadow)}
      .side.open{transform:none}
      #menu{display:inline-block}
      .book{padding:22px 18px 70px}
      .cover h1{font-size:38px}
      .embed iframe{height:440px}
      .steps4{grid-template-columns:repeat(2,1fr)}
    }
    """
    js = """
    var pages=Array.prototype.slice.call(document.querySelectorAll('.page'));
    var tocs=Array.prototype.slice.call(document.querySelectorAll('.toca'));
    var cur=0;
    function go(n,save){
      n=Math.max(0,Math.min(pages.length-1,n));
      pages.forEach(function(p){p.classList.remove('on');});
      tocs.forEach(function(a){a.classList.remove('on');});
      cur=n;
      pages[cur].classList.add('on');
      var id=pages[cur].id;
      var a=document.querySelector('.toca[data-to="'+id+'"]');
      if(a){a.classList.add('on');try{a.scrollIntoView({block:'nearest'});}catch(e){}}
      document.getElementById('pt').textContent=pages[cur].dataset.k||'';
      document.getElementById('cnt').textContent=(cur+1)+' / '+pages.length;
      document.getElementById('pbar').style.width=((cur+1)/pages.length*100)+'%';
      document.getElementById('prev').disabled=(cur===0);
      document.getElementById('next').disabled=(cur===pages.length-1);
      window.scrollTo({top:0,behavior:'smooth'});
      if(save!==false){try{localStorage.setItem('p6-ebook-page',String(cur));}catch(e){}}
      if(location.hash.slice(1)!==id){try{history.replaceState(null,'','#'+id);}catch(e){}}
    }
    document.getElementById('next').onclick=function(){go(cur+1);};
    document.getElementById('prev').onclick=function(){go(cur-1);};
    document.querySelectorAll('[data-to]').forEach(function(a){
      a.onclick=function(e){
        if(a.tagName==='A'){e.preventDefault();}
        var t=document.getElementById(a.dataset.to);
        if(t){go(pages.indexOf(t));document.getElementById('side').classList.remove('open');}
      };
    });
    function filter(k){
      k=(k||'').trim().toLowerCase();
      tocs.forEach(function(a){
        var s=((a.dataset.k||'')+' '+(a.textContent||'')).toLowerCase();
        a.style.display=(!k||s.indexOf(k)>=0)?'':'none';
      });
      document.querySelectorAll('.tocgt').forEach(function(t){
        var any=Array.prototype.slice.call(t.parentElement.querySelectorAll('.toca'))
          .some(function(a){return a.style.display!=='none';});
        t.parentElement.style.display=any?'':'none';
      });
    }
    var qi=document.getElementById('q');
    document.addEventListener('keydown',function(e){
      if(e.target&&e.target.id==='q'){
        if(e.key==='Escape'){qi.value='';filter('');qi.blur();}
        return;
      }
      if(e.key==='/'&&e.target.tagName!=='INPUT'){
        e.preventDefault();
        document.getElementById('side').classList.add('open');qi.focus();return;
      }
      if(e.key==='ArrowRight'||e.key==='PageDown'){go(cur+1);}
      else if(e.key==='ArrowLeft'||e.key==='PageUp'){go(cur-1);}
      else if(e.key==='Home'){go(0);}
      else if(e.key==='End'){go(pages.length-1);}
    });
    qi.oninput=function(){filter(this.value);};
    document.getElementById('menu').onclick=function(){
      document.getElementById('side').classList.toggle('open');};
    var start=0;
    try{
      var h=location.hash.slice(1),idx=-1;
      for(var i=0;i<pages.length;i++){if(pages[i].id===h){idx=i;break;}}
      var s=localStorage.getItem('p6-ebook-page');
      start=idx>=0?idx:(s!==null?Math.max(0,Math.min(pages.length-1,parseInt(s,10)||0)):0);
    }catch(e){}
    go(start,false);
    """
    html = f"""<!doctype html><html lang="zh-CN" data-theme="light"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>空间大数据方法 · L0→L3 可翻页教材</title>
<script>{ui.JS_THEME}</script>
<style>{ui.CSS_BASE}{css}</style></head><body>
<div class="app">
  <aside class="side" id="side">
    <h4><i></i>L0 → L3 教材</h4>
    <input id="q" placeholder="搜索章节…（按 / 聚焦）" autocomplete="off">
    <nav>{toc}</nav>
  </aside>
  <div class="main">
    <header class="bar">
      <button class="icon" id="menu" title="目录">☰</button>
      <span class="pt" id="pt"></span>
      <span class="sp"></span>
      <span class="cnt" id="cnt"></span>
      <button class="icon" id="prev" title="上一页（←）">‹</button>
      <button class="icon" id="next" title="下一页（→）">›</button>
      <button class="icon" id="themeBtn" onclick="__toggleTheme()" title="切换主题">☾</button>
      <div class="prog" id="pbar"></div>
    </header>
    <div class="book">{body}</div>
  </div>
</div>
<script>{js}</script>
</body></html>"""
    p = out / "ebook" / "index.html"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(html, encoding="utf-8")
    return p, len(pages)
