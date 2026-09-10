# -*- coding: utf-8 -*-
"""08_interactive —— ⑧ 交互教材（扩展阶段，规范 §8.2 / §8.5 / §8.8）。

``suggestions_for_projects_0908.md`` 给产品 6 定的主轴是**可复现交互教材**：
教学产品最忌堆静态图，学生看不懂逻辑链；必须给「可改参数、可重跑」的交互。

本阶段把「**空间权重矩阵的定义会改变结论**」做成能亲手拨的开关，并把内容
组织成一套**面向新人的产品矩阵**（不只是几张图）：

| 产物 | 角色 | 回答什么 |
| --- | --- | --- |
| ``index.html`` | 入口 | 从哪开始？学习路径 + 产品矩阵 |
| ``ebook/index.html`` | **教材主载体** | 15 页可翻页：目录/搜索/进度/主题/章内交互 |
| ``moran_explorer.html`` | 交互件 | Moran's I 怎么读、四个数据集差多少 |
| ``weight_lab.html`` | 交互件 | 「邻居」是谁定的、孤岛有多致命 |
| ``ring_decay.html`` | 交互件 | 两种口径为什么给出相反结论 |
| ``ladder_compare.html`` | 交互件 | 四数据集逐层对比（8 指标可切） |
| ``method_atlas.html`` | 交互件 | 14 个方法的输入/输出/坑/代码位置 |
| ``quiz.html`` | 交互件 | 12 题自测（题目由上游数字生成） |
| ``ladder_evolution.html`` | 交互件 | L0→L3 演化动图（需格级 CSV + ffmpeg） |

代码为什么拆成 4 个模块
----------------------
单个 2000+ 行的脚本没法维护。这里按「数据 / 设计系统 / 交互件 / 电子书」切开：

* ``studio_data.py``  —— 唯一权威源 = ``ladder_report.json``；格级 CSV 是可选增强；
* ``studio_ui.py``    —— 设计令牌 + 组件 + 页面外壳（改主色只动一处）；
* ``studio_figs.py``  —— 7 个交互件；
* ``studio_ebook.py`` —— 电子书框架。
"""
from __future__ import annotations

import datetime as _dt
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parent))      # 阶段由 importlib 按文件路径加载

import numpy as np
import pandas as pd

import datakit as dk
import studio_data as sd
import studio_ebook as seb
import studio_figs as sfg
import studio_ui as ui

STAGE = "08_interactive"
ROOT = Path(__file__).resolve().parent.parent
OUT = Path(__file__).resolve().parent / "output"

SCATTER_CAP = 15000     # 每个（数据集 × 权重 × 尺度）传给前端的散点上限
WEIGHTS = [
    {"key": "queen", "label": "Queen 邻接（H3 grid_disk k=1，行标准化）"},
    {"key": "knn4", "label": "KNN k=4（行标准化）"},
    {"key": "knn8", "label": "KNN k=8（行标准化）"},
]

# 深圳单车的可视化范围（深圳约 22.4–22.9°N / 113.7–114.6°E）
SZ_BBOX = (22.35, 23.05, 113.65, 114.75)      # lat_min, lat_max, lon_min, lon_max


# --------------------------------------------------------------------------- #
# 可选增强：格级 CSV 存在时才算（否则整段静默跳过）
# --------------------------------------------------------------------------- #
def _moran(x: np.ndarray, w) -> float:
    z = x - x.mean()
    den = float(z @ z)
    return float((z @ (w.sparse @ z)) / den) if den > 0 else float("nan")


def _build_weights(cells: list[str], scheme: str):
    """与 05_map/spatial_ladder.py 同一套算法：H3 邻接 / KNN → libpysal W（行标准化）。

    性能取舍（踩过的坑）：
    * Queen 用 ``h3.grid_disk(k=1)``，O(n)。
    * KNN **不能**算 n×n 距离矩阵（30 万格直接爆内存）——改用 3D 直角坐标
      + sklearn KD-tree；弦距与大圆距离单调同序，最近邻排序完全一致，但快几个数量级。
    * ``weights.W`` 必须覆盖**全部**格（含孤岛），否则 w.n < n 会让滞后维度对不上。
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


def compute_scatter(ds: str) -> dict | None:
    """Moran's I（**全量算**）+ 散点（**抽样传**）。缺 CSV 返回 None。

    为什么分两件事：I 必须基于全量格，否则与 05_map 报告对不上；
    而 30 万格 × 3 方案 × 4 数据集全塞进 HTML 会是几百 MB。
    """
    p = ROOT / "05_map" / "output" / ds / "L2_spatial_lag.csv"
    if not p.exists():
        return None
    d = pd.read_csv(p)
    d = d[d["spatial_lag"].notna()]
    cells = d["h3_cell"].astype(str).tolist()
    x_all = d["value"].to_numpy(float)

    out = {"dataset": ds, "label": sd.DS_LABEL.get(ds, ds), "n": int(len(d)),
           "scatter_sample": 0, "schemes": {}}
    scales = {"raw": ("原始格值（管线口径）", x_all),
              "log1p": ("log1p(格值)", np.log1p(x_all))}

    for wcfg in WEIGHTS:
        try:
            w, islands = _build_weights(cells, wcfg["key"])
        except Exception as exc:                      # 依赖缺失 → 跳过，不阻断
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
# ③ L0→L3 演化动图（mp4 + 自包含 HTML）
# --------------------------------------------------------------------------- #
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


def anim_ladder(dataset: str = "sz_bike") -> tuple[Path, Path]:
    """L0→L3 的四段演化动图：格 → 邻居 → Moran 散点 → 距离环。

    为什么做成动图：静态图只能分别展示 L0/L1/L2/L3，学生看不到**它们是一条链**。
    """
    import matplotlib.pyplot as plt
    from matplotlib import patheffects as pe

    import h3

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
    nbrs = {c: [idx[n] for n in h3.grid_disk(c, 1) if n in cset and n != c] for c in cells}

    focus = int(np.nanargmax(ll))
    rings = [0.8, 2.0, 3.5, 6.0]            # km
    R = 6371.0088
    mx = np.nanmax(ll) if np.isfinite(np.nanmax(ll)) else 1.0

    PHASE = 45                               # 每段帧数
    TOTAL = PHASE * 4

    fig, (ax, bx) = plt.subplots(2, 1, figsize=(10.8, 12.4),
                                 gridspec_kw={"height_ratios": [1.3, 1]})
    fig.subplots_adjust(left=0.085, right=0.965, top=0.955, bottom=0.065, hspace=0.17)
    titles = {0: "L0 · 把点装进 H3 格（颜色＝格值）",
              1: "L1 · 定义「邻居」：高亮格 + 它的六邻居",
              2: "L2 · 算邻居均值 → Moran 散点（斜率＝I）",
              3: "L3 · 邻居换成距离环：效应随距离衰减"}

    def draw(f):
        ph, t = min(int(f // PHASE), 3), (f % PHASE) / PHASE
        a = min(1.0, t * 2.2)
        ax.clear(); bx.clear()

        if ph == 0:
            ax.scatter(lon, lat, s=20 + 34 * a, c=lv, cmap="YlOrRd",
                       alpha=0.35 + 0.6 * a, linewidths=0, rasterized=True)
        elif ph == 1:
            ax.scatter(lon, lat, s=22, c="#4B5563", alpha=0.55, linewidths=0, rasterized=True)
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
            ax.scatter(lon, lat, s=18, c="#374151", alpha=0.55, linewidths=0, rasterized=True)
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

        if ph >= 2:
            n_show = int(len(lv) * (1.0 if ph == 3 else min(1.0, t * 2.0)))
            bx.scatter(lv[:n_show], ll[:n_show], s=11, c="#0072B2", alpha=0.32,
                       linewidths=0, rasterized=True)
            if t > 0.45:
                m = lv.mean()
                sl = float(np.polyfit(lv, ll, 1)[0]) if np.isfinite(lv).all() else 0.0
                xs = np.array([lv.min(), lv.max()])
                bx.plot(xs, ll.mean() + sl * (xs - m), color="#FFB86B", linewidth=3.0,
                        path_effects=[pe.Stroke(linewidth=5, foreground="#0B1020"), pe.Normal()])
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

    # 放慢：4 段 × 45 帧、fps 6 → 30 s（此前 4×40 @16fps 只有 10 s，快到看不清）
    mp4 = dk.animate(OUT / "ladder_evolution.mp4", fig, draw, n_frames=TOTAL, fps=6, dpi=110)
    plt.close(fig)

    page = dk.video_page(
        mp4,
        title="L0→L3 是一条链：点 → 格 → 邻居 → 滞后 → 距离环",
        subtitle=(f"数据集 {dataset}（深圳共享单车抽样日），n={len(d):,} 格；"
                  f"按深圳范围裁切后剔除 {dropped:,} 个飞点/空岛格。"
                  f"四段各 {PHASE} 帧：L0 网格化 → L1 定义邻居 → "
                  f"L2 空间滞后与 Moran 散点 → L3 距离环。"),
        caption=("建议全屏看。重点看第 2 段：所谓「邻居」是人为定的六边形邻接，"
                 "不是客观事实——这正是本教程最想让你记住的一句。"),
        source=f"05_map/output/{dataset}/mapped.csv",
        alt_text="上方地图从格演化到邻居高亮再到距离环，下方同步长出 Moran 散点",
    )
    p = OUT / "ladder_evolution.html"
    p.write_text(page, encoding="utf-8")
    return mp4, p


# --------------------------------------------------------------------------- #
# 入口页 index.html
# --------------------------------------------------------------------------- #
def build_index(facts: dict, out: Path, *, evolution: bool, moran_live: bool,
                csv_missing: list[str], n_pages: int = 0) -> Path:
    rows = facts["rows"]
    hi = max(rows, key=lambda r: r["moran_i"])
    lo = min(rows, key=lambda r: r["moran_i"])
    res = facts["h3_res"]
    area = facts["cell_area_km2"] or 0.0

    products = [
        ("ebook/index.html", "📖", "可翻页电子书", "教材主载体",
         f"{n_pages} 页：入门 / L0–L3 / 综合 / 实践 / 收尾。常驻目录 + 搜索 + 进度记忆 + 深色模式，"
         "每章内嵌交互件、章首「你将学到」、章尾「下一步」。", "新人从这里开始", "b"),
        ("moran_explorer.html", "📈", "Moran's I 实验室", "L2",
         "四象限怎么读、I 的公式、为什么尺度与权重会改变结论。"
         + ("可切数据集 / 权重 / 尺度的真交互散点。" if moran_live else "当前为上游真实散点。"),
         "最重要的一课", "o"),
        ("weight_lab.html", "🕸", "权重实验室", "L1",
         "六边形邻接示意 + 邻居数/孤岛率/I 关系散点，切数据集看各自的连通性。",
         "「邻居」是谁定的", "g"),
        ("ring_decay.html", "🎯", "距离环衰减", "L3",
         "一键切「环内求和 / 溢出密度 / 归一化」，看同一数据给出相反结论。",
         "聚合口径的坑", "p"),
        ("ladder_compare.html", "📊", "阶梯对比", "综合",
         "8 个指标下拉切换（L0 规模 → L1 连通性 → L2 强度）+ 三层折线 + 完整数字表。",
         "四数据集差多少", ""),
        ("method_atlas.html", "🧭", "方法图谱", "全景",
         "方法卡：输入 / 输出 / 关键参数 / 为什么 / 坑 / 代码在哪，可按层筛选。",
         "先给全景再下钻", ""),
        ("quiz.html", "✅", "自测", "检验",
         "题目与答案由上游真实数字生成 —— 重跑管线后题目自动跟着更新。",
         "及格线 9 题", ""),
    ]
    if evolution:
        products.append(("ladder_evolution.html", "🎬", "L0→L3 演化动图", "综合",
                         "点 → 格 → 邻居 → 滞后 → 距离环，30 秒看懂它们是一条链（可下载 mp4）。",
                         "适合放课件", ""))

    cards = "".join(
        f'''<a class="pcard c-{cls}" href="{href}">
          <span class="ico">{ico}</span>
          <span class="pt">{title}</span>
          <span class="pb">{badge}</span>
          <span class="pd">{desc}</span>
          <span class="pq">→ {cta}</span>
        </a>''' for href, ico, title, badge, desc, cta, cls in products)

    locks_html = "".join(
        f"<tr><td><code>{ds}</code></td><td>{lk.get('frozen_at', '—')}</td>"
        f"<td class='num'>{ui.fmt_int((lk.get('rows') or {}).get('cleaned'))}</td>"
        f"<td>{', '.join(f'{k} {v}' for k, v in list((lk.get('library_versions') or {}).items())[:4])}</td></tr>"
        for ds, lk in facts["locks"].items())

    warn = ""
    if csv_missing:
        warn = ui.callout("warn", "当前环境缺格级 CSV，部分交互件已降级",
                          f"<code>05_map/output/&lt;ds&gt;/L2_spatial_lag.csv</code> 未找到"
                          f"（{len(csv_missing)}/4 个数据集）。该文件受仓库根 "
                          "<code>.gitignore</code> 约束不入库，在有完整数据的环境里重跑 "
                          "<code>python main.py --stage 08</code> 会自动升级为完整交互版。"
                          "<b>其余产物不受影响，数字全部来自入库的 "
                          "<code>ladder_report.json</code>。</b>")

    ratio = hi["moran_i"] / max(lo["moran_i"], 1e-9)
    body = f"""
    <div class="hero">
      <div class="hero-l">
        <div class="tag">空间大数据方法 · 可复现交互教材</div>
        <h1 class="hero-h">「邻居」怎么定义，<br>决定你能看到什么结论</h1>
        <p class="hero-p">一套 L0→L3 四阶流水线跑通四个数据集。
        Moran's I 从 <b style="color:{lo['color']}">{lo['moran_i']:.4f}</b>（{lo['short']}）到
        <b style="color:{hi['color']}">{hi['moran_i']:.4f}</b>（{hi['short']}），
        差 <b>{ratio:.0f} 倍</b> —— 不是算法偏好，
        是<b>数据本身的空间结构</b>与<b>权重的定义方式</b>共同决定的。</p>
        <div class="hero-btns">
          <a class="btn primary big" href="ebook/index.html">开始阅读 →</a>
          <a class="btn big" href="moran_explorer.html">直接动手拨开关</a>
          <a class="btn big" href="quiz.html">先测一下</a>
        </div>
      </div>
      <div class="hero-r">
        {"".join(f'''<div class="mini" style="border-left:3px solid {r['color']}">
          <span class="k">{r['short']} · {r['scene']}</span>
          <span class="v" style="color:{r['color']}">{r['moran_i']:.4f}</span>
          <span class="h">{r['cells']:,} 格 · 平均邻居 {r['mean_neighbors']:.2f} · 孤岛 {ui.fmt_pct(r['island_rate'])}</span>
        </div>''' for r in rows)}
      </div>
    </div>

    {warn}

    <h2>① 学习路径：L0 → L3</h2>
    <p class="muted">四层不是四个并列的方法，是<b>一条流水线</b>：每一层的输出是下一层的输入。</p>
    <div class="grid g4">
      <a class="step link" href="ebook/index.html#l0"><b>L0 · 网格化</b>
        <span>把点装进 H3 R{res} 六边形格（平均 {area:.3f} km²） —— 先把连续空间离散化。</span></a>
      <a class="step link" href="ebook/index.html#l1"><b>L1 · 权重矩阵</b>
        <span>定义谁是谁的邻居（Queen 邻接 / KNN），行标准化。最主观的一步。</span></a>
      <a class="step link" href="ebook/index.html#l2"><b>L2 · 空间滞后</b>
        <span>算邻居均值 W·x，Moran's I = 散点拟合斜率。</span></a>
      <a class="step link" href="ebook/index.html#l3"><b>L3 · 距离环</b>
        <span>把滞后换成距离环，看效应怎么随距离衰减。</span></a>
    </div>

    <h2>② 产品矩阵：{len(products)} 个交互件</h2>
    <p class="muted">按你想回答的问题挑一个点进去。每个都单文件自包含、离线可开。</p>
    <div class="pgrid">{cards}</div>

    <h2>③ 四个数据集：规模与结构</h2>""" + ui.table(
        ["数据集", "场景", "格数（L0）", "每格点数", "平均邻居（L1）", "孤岛率（L1）", "Moran's I（L2）"],
        [[f'<a href="ebook/index.html#compare">{r["label"]}</a>', r["scene"],
          ui.fmt_int(r["cells"]), ui.fmt_num(r["points_per_cell"], 1),
          ui.fmt_num(r["mean_neighbors"], 2), ui.fmt_pct(r["island_rate"]),
          ui.fmt_num(r["moran_i"], 4)] for r in rows],
        num_cols={2, 3, 4, 5, 6}) + f"""
    {ui.callout("warn", f"为什么 {hi['short']} 的 I 是 {lo['short']} 的 {ratio:.0f} 倍？",
                "不是算法偏好，而是<b>数据本身的空间结构</b>：深圳单车的起终点集中在同一座城市，"
                "格与格挨得紧、邻居搭得起来；Brightkite 的签到散落全球，22.8 万个格里 6.7 万个是孤岛，"
                "权重几乎搭不起来。<b>看到 I 很低，先问「是不是数据本来就稀」，"
                "别急着说「没有空间效应」。</b>")}

    <h2>④ 一键复现（教学产品的信服度来源）</h2>
    <p class="kicker">可复现 &gt; 好看</p>
    <p>每个数据集的 <code>04_validate/output/&lt;dataset&gt;/version_lock.json</code>
    冻结了源数据指纹、行数、库版本与成本参数；版本漂移会被 ④ 记为断言失败。</p>
    <table><thead><tr><th>数据集</th><th>冻结时间</th><th class="num">清洗后行数</th>
    <th>库版本</th></tr></thead><tbody>{locks_html}</tbody></table>
    {ui.callout("note", "重跑与许可",
                "重跑：<code>python main.py</code>（单阶段 <code>python main.py --stage 08</code>）。"
                "许可：FDIC 公共领域可商用；SNAP（Brightkite / Gowalla）仅限研究用途、不允许商用，"
                "引用 Cho, Myers &amp; Leskovec, KDD 2011；深圳单车为本地存档、数据源已停更。")}
    """
    css = """
    .hero{display:grid;grid-template-columns:1.15fr .85fr;gap:28px;align-items:center;
      padding:8px 0 12px}
    .hero .tag{display:inline-block;font-size:11.5px;letter-spacing:.16em;color:var(--accent);
      font-weight:800;margin-bottom:12px}
    .hero-h{font-size:38px;line-height:1.18;margin:0 0 14px;letter-spacing:-.02em}
    .hero-p{font-size:15.5px;color:var(--sub);line-height:1.85;margin:0 0 20px}
    .hero-btns{display:flex;flex-wrap:wrap;gap:10px}
    .btn.big{padding:10px 20px;font-size:14.5px;text-decoration:none;display:inline-block}
    .btn.big:hover{text-decoration:none}
    .hero-r{display:grid;gap:10px}
    .mini{border:1px solid var(--line);border-radius:12px;padding:11px 14px;background:var(--soft)}
    .mini .k{display:block;font-size:12px;color:var(--sub)}
    .mini .v{display:block;font-size:26px;font-weight:750;font-variant-numeric:tabular-nums;
      line-height:1.3}
    .mini .h{display:block;font-size:11px;color:var(--faint)}
    a.step.link{text-decoration:none;color:inherit}
    a.step.link:hover{border-color:var(--brand);text-decoration:none}
    a.step.link b{color:var(--accent)}
    .pgrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(268px,1fr));gap:14px}
    .pcard{display:flex;flex-direction:column;border:1px solid var(--line);
      border-radius:var(--radius);padding:16px 18px;background:var(--bg);box-shadow:var(--shadow);
      text-decoration:none;color:inherit;transition:.2s;overflow:hidden}
    .pcard:hover{transform:translateY(-3px);border-color:var(--brand);text-decoration:none}
    .pcard .ico{font-size:22px;margin-bottom:8px}
    .pcard .pt{font-weight:700;font-size:15.5px;color:var(--ink)}
    .pcard .pb{display:inline-block;font-size:11px;padding:2px 8px;border-radius:999px;
      background:var(--soft-2);color:var(--sub);margin:6px 0 8px;align-self:flex-start}
    .pcard .pd{font-size:13.5px;color:var(--sub);line-height:1.7;flex:1}
    .pcard .pq{font-size:13px;color:var(--brand);font-weight:650;margin-top:10px}
    .pcard.c-b{border-top:3px solid var(--brand)}
    .pcard.c-o{border-top:3px solid var(--accent)}
    .pcard.c-g{border-top:3px solid var(--ok)}
    .pcard.c-p{border-top:3px solid var(--purple)}
    @media(max-width:900px){ .hero{grid-template-columns:1fr} .hero-h{font-size:28px} }
    """
    html = ui.page("空间大数据方法 · L0→L3 交互教材", body,
                   subtitle=f"一套流程跑通四个数据集 · H3 R{res} · 行标准化 W · "
                            f"{len(products)} 个交互件 · {n_pages} 页可翻页教材",
                   extra_css=css, active_nav="入口", home="")
    p = out / "index.html"
    p.write_text(html, encoding="utf-8")
    return p


# --------------------------------------------------------------------------- #
def run(project) -> dict:
    project.log(f"[{STAGE}] ⑧ 交互教材（教材主载体 + 交互件 + 一键复现）")
    OUT.mkdir(parents=True, exist_ok=True)

    facts = sd.load_facts(ROOT)
    status = sd.csv_status(ROOT, facts["order"])
    static_figs = sd.collect_static_figs(ROOT, facts["order"], OUT / "assets" / "fig")
    ui.write_plotly_vendor(OUT)          # plotly.js 全站共享一份
    project.log(f"    [⑧] 静态配图 {sum(len(v) for v in static_figs.values())} 张 "
                f"（从 06_visualize 复制到 output/assets/fig/）")

    # ---- 可选增强：格级 CSV → 可交互散点 ----
    payload = None
    if status["available"]:
        payload = {"order": [], "datasets": {},
                   "schemes": [{"key": w["key"], "label": w["label"]} for w in WEIGHTS]}
        for ds in status["present"]:
            sc = compute_scatter(ds)
            if sc and sc["schemes"]:
                payload["order"].append(ds)
                payload["datasets"][ds] = sc
                project.log(f"    [⑧] {ds}: n={sc['n']:,}；"
                            + "；".join(f"{k} I(原始)={v['scales']['raw']['I']} "
                                        f"I(log1p)={v['scales']['log1p']['I']}"
                                        for k, v in sc["schemes"].items()))
        if not payload["datasets"]:
            payload = None
    if status["missing"]:
        project.log(f"    [⑧] 缺格级 CSV（{len(status['missing'])}/4）→ 散点面板降级为上游静态图")
    moran_live = payload is not None

    p1 = sfg.build_moran_lab(facts, payload, static_figs, OUT)
    p2 = sfg.build_weight_lab(facts, OUT)
    p3 = sfg.build_ring_decay(facts, OUT)
    p4 = sfg.build_ladder_compare(facts, OUT)
    p5 = sfg.build_method_atlas(facts, OUT)
    p6 = sfg.build_quiz(facts, OUT)

    # ---- 演化动图：需要格级 CSV + ffmpeg，缺任一就保留既有产物 ----
    evo_html = OUT / "ladder_evolution.html"
    if (ROOT / "05_map" / "output" / "sz_bike" / "mapped.csv").exists() and dk.ffmpeg_available():
        mp4, evo_html = anim_ladder("sz_bike")
        project.log(f"    [⑧] {evo_html.name}（mp4 {mp4.stat().st_size / 1e6:.1f} MB → "
                    f"内嵌 {evo_html.stat().st_size / 1e6:.1f} MB）")
    else:
        project.log("    [⑧] 跳过演化动图（需 05_map/output/sz_bike/mapped.csv + ffmpeg）；"
                    + ("保留既有产物" if evo_html.exists() else "当前无产物"))
    evolution = evo_html.exists()

    n_cells = sum(r["cells"] for r in facts["rows"])
    n_method = len(sfg.method_bank(facts))
    n_quiz = len(sfg.quiz_bank(facts))
    res = facts["h3_res"]

    p8, n_pages = seb.build_ebook(facts, static_figs, OUT, evolution=evolution,
                                  moran_live=moran_live, n_method=n_method, n_quiz=n_quiz)
    p7 = build_index(facts, OUT, evolution=evolution, moran_live=moran_live,
                     csv_missing=status["missing"], n_pages=n_pages)
    project.log(f"    [⑧] ebook/index.html（{p8.stat().st_size / 1e3:.0f} KB，{n_pages} 页）")

    for p in (p1, p2, p3, p4, p5, p6, p7):
        project.log(f"    [⑧] {p.name}（{p.stat().st_size / 1e3:.0f} KB）")


    figures = [
        {"file": "index.html", "title": "L0→L3 交互教材（入口）", "type": "entry",
         "question": "学习者能不能按阶梯看懂、能跑、能改？",
         "alt_text": "Hero + 学习路径 + 产品矩阵 + 四数据集结构表 + version_lock 复现表",
         "source": "本目录各产物 + 04_validate/output/<dataset>/version_lock.json",
         "n": n_cells, "scope": f"四数据集；H3 R{res}；W 行标准化", "tool": "html"},
        {"file": "ebook/index.html", "title": "L0→L3 可翻页教材", "type": "ebook",
         "question": "新人能不能按阶梯一页页读懂并动手？",
         "alt_text": "15 页：封面/导读/引言/L0-L3/对比/演化/误区/结论/自测/复现/术语表；"
                     "常驻目录 + 搜索 + 进度记忆 + 深色模式",
         "unit": "←/→ 翻页，/ 搜索，Home/End 首尾；每章内嵌对应交互件",
         "source": "05_map/output/<ds>/ladder_report.json + 本目录交互件 + 06_visualize 静态图",
         "n": n_cells, "scope": "15 页；章首「你将学到」+ 章尾「下一步」", "tool": "html"},
        {"file": "moran_explorer.html", "title": "Moran's I 实验室",
         "type": "moran_scatter_interactive",
         "question": "Moran's I 怎么读、四个数据集为什么差这么多？",
         "alt_text": "四象限解读 + I 对比条 + 公式；"
                     + ("可切数据集/权重/尺度的交互散点" if moran_live else "上游真实散点 PNG（降级）"),
         "unit": "x=格值，y=空间滞后 W·格值",
         "source": "05_map/output/<ds>/ladder_report.json"
                   + (" + L2_spatial_lag.csv" if moran_live else ""),
         "n": n_cells, "scope": f"H3 R{res}；W 行标准化", "tool": "plotly",
         "degraded": not moran_live},
        {"file": "weight_lab.html", "title": "权重实验室：邻居是谁定的", "type": "weight_lab",
         "question": "邻接怎么定、行标准化在做什么、孤岛有多致命？",
         "alt_text": "数据集切换卡 + 六边形邻接 SVG + 邻居数×I 散点 + 孤岛率条",
         "unit": "x=平均邻居数，y=Moran's I，气泡=格数",
         "source": "05_map/output/<ds>/ladder_report.json（L1）",
         "n": n_cells, "scope": "四数据集；六边形满配 6 邻居", "tool": "plotly + svg"},
        {"file": "ring_decay.html", "title": "距离环衰减：两种口径相反结论", "type": "ring_decay",
         "question": "同一个距离环数据，为什么求和递增、密度递减？",
         "alt_text": "四数据集四条线，updatemenus 切换求和/密度/归一化三种口径",
         "unit": "x=环中点(km)，y=溢出值（对数轴）",
         "source": "05_map/output/<ds>/ladder_report.json（L3）",
         "n": n_cells, "scope": "Top-100 热点；环 0–1/1–3/3–5/5–10 km", "tool": "plotly"},
        {"file": "ladder_compare.html", "title": "阶梯对比：四数据集", "type": "small_multiples",
         "question": "四个数据集在 L0→L2 各层差多少？",
         "alt_text": "8 指标下拉切换的横向条形 + 三层对数折线 + 完整数字表",
         "source": "05_map/output/<ds>/ladder_report.json",
         "n": n_cells, "scope": f"四数据集；H3 R{res}", "tool": "plotly"},
        {"file": "method_atlas.html", "title": "方法图谱", "type": "method_atlas",
         "question": "这条管线一共用了哪些方法、各有什么坑？",
         "alt_text": f"{n_method} 张可展开方法卡：输入/输出/参数/为什么/坑/代码位置",
         "source": "05_map/spatial_ladder.py 等（人工梳理，参数来自上游产物）",
         "n": n_method, "scope": "L0/L1/L2/L3 + 贯穿方法", "tool": "html"},
        {"file": "quiz.html", "title": "自测", "type": "quiz",
         "question": "学完了吗？",
         "alt_text": f"{n_quiz} 道选择题，即时判分，题目与答案由上游数字生成",
         "source": "05_map/output/<ds>/ladder_report.json",
         "n": n_quiz, "scope": "及格线 9 题", "tool": "html"},
    ]
    if evolution:
        figures.append({
            "file": "ladder_evolution.html", "title": "L0→L3 是一条链", "type": "animation",
            "question": "网格化、权重、滞后、距离环到底怎么串起来的？",
            "alt_text": "上地图从格演化到邻居高亮再到距离环，下 Moran 散点同步长出",
            "unit": "上 x=经度 y=纬度；下 x=log1p(格值) y=空间滞后",
            "source": "05_map/output/sz_bike/mapped.csv", "n": 2661,
            "scope": "mp4（FuncAnimation）内嵌 <video>；按深圳 bbox 裁切飞点",
            "tool": "matplotlib + ffmpeg"})

    manifest = {
        "generated_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "generator": {"tool": "plotly + h3 + libpysal", "script": "08_interactive/08_interactive.py",
                      "modules": ["studio_data.py", "studio_ui.py", "studio_figs.py",
                                  "studio_ebook.py"],
                      "encoding": "utf-8", "font": "Microsoft YaHei",
                      "self_contained": True, "reproducible": True,
                      "note": "数字全部来自 05_map/output/<ds>/ladder_report.json；"
                              "格级 CSV 为可选增强，缺失时相关面板降级并显式披露"},
        "entry": "index.html", "n_figures": len(figures), "datasets": facts["order"],
        "degraded": {"moran_scatter": not moran_live,
                     "missing_csv": status["missing"],
                     "reason": "05_map/output/<ds>/L2_spatial_lag.csv 受 .gitignore 约束不入库"},
        "figures": figures,
    }
    (OUT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return {"stage": STAGE, "blocking": False, "figures": len(figures),
            "datasets": len(facts["order"]),
            "artifacts": ["index.html", "moran_explorer.html", "weight_lab.html",
                          "ring_decay.html", "ladder_compare.html", "method_atlas.html",
                          "quiz.html", "ebook/index.html", "manifest.json"]}


def main() -> None:
    project = dk.Project.load(ROOT)
    print(run(project))


if __name__ == "__main__":
    main()
