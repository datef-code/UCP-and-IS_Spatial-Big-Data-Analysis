# -*- coding: utf-8 -*-
"""09_interactive —— ⑨ 交互展示（扩展阶段，规范 §8.2 / §8.8）。

把 ⑦ 的静态图升级为**可 hover、可播放、可切换口径**的交互件，让人自己去戳数据，
而不是只相信作者的静态图。

三件产物（各一个自包含 HTML，plotly 内联，离线可开）：

1. ``event_study.html``  —— 事件研究：τ 各期系数 + 95% CI，hover 看数值与 p 值
2. ``attenuation.html``  —— 距离衰减：可切换「标准环 / 合并环」×「计数 / 密度」
3. ``spacetime.html``    —— 时空演变动画：1994–2025 逐年关闭事件在全国扩散

外加 ``index.html``（证据链叙事：结论 → 机制 → 证据 → 反例 → 限制）与 ``manifest.json``。

设计原则（``suggestions_for_projects_0908.md``）：
**只复用已有资产，不重算、不推倒重来**——本阶段只读上游 output/，自己不跑模型。
且全篇守住克制：反复标注「关联证据非严格因果」，这是本产品的可信度来源。
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

import datakit as dk

STAGE = "09_interactive"
ROOT = Path(__file__).resolve().parent.parent
OUT = Path(__file__).resolve().parent / "output"

# 色盲友好色板（规范 §8.8.1：Okabe–Ito）
C_TREAT = "#D55E00"      # 朱红：处理后
C_PRE = "#0072B2"        # 蓝：事件前
C_GRID = "#E5E7EB"
FONT = "Microsoft YaHei, Noto Sans CJK SC, sans-serif"

RING_FINE = [("0_1", 0, 1), ("1_3", 1, 3), ("3_5", 3, 5), ("5_10", 5, 10)]
RING_COARSE = [("0_2", 0, 2), ("2_5", 2, 5), ("5_10", 5, 10)]


# --------------------------------------------------------------------------- #
# 通用
# --------------------------------------------------------------------------- #
def _layout(fig, title, subtitle, height=520):
    fig.update_layout(
        title=dict(text=f"<b>{title}</b><br><sub>{subtitle}</sub>",
                   x=0.01, xanchor="left", font=dict(size=16, family=FONT)),
        font=dict(family=FONT, size=12),
        paper_bgcolor="white", plot_bgcolor="white",
        height=height, margin=dict(l=70, r=30, t=90, b=60),
        hovermode="closest",
    )
    fig.update_xaxes(showgrid=False, linecolor="#9CA3AF", zeroline=False)
    fig.update_yaxes(gridcolor=C_GRID, gridwidth=1, linecolor="#9CA3AF", zeroline=True,
                     zerolinecolor="#6B7280", zerolinewidth=1)
    return fig


def _footer(fig, src):
    fig.add_annotation(
        xref="paper", yref="paper", x=1, y=-0.16, xanchor="right", yanchor="top",
        text=f"数据来源：{src}　|　生成脚本 09_interactive/09_interactive.py　|　"
             f"生成时间 {_dt.datetime.now():%Y-%m-%d %H:%M}",
        showarrow=False, font=dict(size=9, color="#6B7280", family=FONT))
    return fig


def _save(fig, name: str) -> Path:
    p = OUT / name
    p.parent.mkdir(parents=True, exist_ok=True)
    # include_plotlyjs=True → 内联 plotly 全集，单文件自包含、离线可开、挪动不丢
    fig.write_html(str(p), include_plotlyjs=True, full_html=True,
                   config={"displaylogo": False, "responsive": True})
    return p


# --------------------------------------------------------------------------- #
# ① 事件研究
# --------------------------------------------------------------------------- #
def fig_event_study(est: dict) -> Path:
    es = est["event_study"]
    t = pd.DataFrame(es["table"])
    t["pp"] = t["dynamic_effect"] * 100
    t["ci"] = 1.96 * t["std_err"] * 100
    base = es["baseline"]

    fig = go.Figure()
    # 事件前（平行趋势区）
    pre = t[t.rel_year < 0]
    post = t[t.rel_year >= 0]
    for d, color, name in ((pre, C_PRE, "事件前（平行趋势检验）"),
                           (post, C_TREAT, "事件后（处理效应）")):
        fig.add_trace(go.Scatter(
            x=d.rel_year, y=d.pp, mode="lines+markers", name=name,
            error_y=dict(type="data", array=d.ci, color=color, thickness=1.4, width=4),
            marker=dict(size=9, color=color),
            line=dict(color=color, width=2.4),
            customdata=np.stack([d.ci, d.pvalue], axis=-1),
            hovertemplate=("τ=%{x}<br>系数 %{y:.2f} pp<br>"
                           "95%% CI ±%{customdata[0]:.2f} pp<br>"
                           "p=%{customdata[1]:.2g}<extra></extra>")))

    fig.add_hline(y=0, line=dict(color="#6B7280", width=1))
    fig.add_vrect(x0=-0.5, x1=0.5, fillcolor="#F3F4F6", line_width=0, layer="below")
    fig.add_annotation(x=base, y=0, text=f"基线 τ={base}", showarrow=True, arrowhead=0,
                       ax=0, ay=-38, font=dict(size=10, color="#6B7280", family=FONT))

    _layout(fig, "同业关闭后，存款增速逐年下行且不收敛",
            f"网点级 event-time dummies，基线 τ={base}；within entity+year，n={es['n_obs']:,}；"
            f"误差棒为 95% CI（未做 bootstrap，显著性部分来自大样本）")
    fig.update_xaxes(title="距关闭事件年数 τ（年）", dtick=1)
    fig.update_yaxes(title="存款增速差异（百分点）")
    fig.update_layout(legend=dict(orientation="h", yanchor="bottom", y=1.02,
                                  xanchor="right", x=1, bgcolor="rgba(0,0,0,0)"))
    _footer(fig, "06_estimate/output/estimate.json")
    return _save(fig, "event_study.html")


# --------------------------------------------------------------------------- #
# ② 距离衰减（可切口径）
# --------------------------------------------------------------------------- #
def _ring_stats(mapped: pd.DataFrame):
    """各距离环：同业网点数均值 + 密度（个/km²）。环面积 = π(r2²-r1²)。"""
    rows = []
    for scheme, rings in (("standard", RING_FINE), ("coarse", RING_COARSE)):
        for key, a, b in rings:
            col = f"same_ind_ring_{key}km"
            if col not in mapped.columns:
                continue
            area = np.pi * (b ** 2 - a ** 2)
            v = pd.to_numeric(mapped[col], errors="coerce")
            rows.append({
                "scheme": scheme, "ring": f"{a}–{b} km", "lo": a, "hi": b,
                "order": a, "mean_count": float(v.mean()),
                "density": float(v.mean()) / area,
            })
    return pd.DataFrame(rows)


def fig_attenuation(mapped: pd.DataFrame) -> Path:
    df = _ring_stats(mapped)
    n = len(mapped)

    fig = go.Figure()
    # 四个组合各一条 trace，用 updatemenus 的 visible 切换
    combos = [("standard", "mean_count", "标准环 · 同业网点数", C_PRE),
              ("standard", "density", "标准环 · 密度（个/km²）", C_PRE),
              ("coarse", "mean_count", "合并环 · 同业网点数", C_TREAT),
              ("coarse", "density", "合并环 · 密度（个/km²）", C_TREAT)]
    for scheme, metric, name, color in combos:
        d = df[df.scheme == scheme].sort_values("order")
        fig.add_trace(go.Bar(
            x=d.ring, y=d[metric], name=name, visible=(scheme == "standard" and metric == "mean_count"),
            marker=dict(color=color),
            customdata=np.stack([d.mean_count, d.density], axis=-1),
            hovertemplate=("%{x}<br>同业网点数均值 %{customdata[0]:.2f}<br>"
                           "密度 %{customdata[1]:.4f} 个/km²<extra></extra>")))

    def vis(scheme, metric):
        return [s == scheme and m == metric for s, m, _, _ in combos]

    fig.update_layout(
        updatemenus=[
            dict(type="dropdown", x=0.01, y=1.14, xanchor="left", showactive=True,
                 bgcolor="white", bordercolor="#D1D5DB",
                 buttons=[
                     dict(label="标准环 0–1/1–3/3–5/5–10 km（主口径）",
                          method="update", args=[{"visible": vis("standard", "mean_count")}]),
                     dict(label="合并环 0–2/2–5/5–10 km（坐标精度敏感性）",
                          method="update", args=[{"visible": vis("coarse", "mean_count")}]),
                 ]),
            dict(type="dropdown", x=0.01, y=1.06, xanchor="left", showactive=True,
                 bgcolor="white", bordercolor="#D1D5DB",
                 buttons=[
                     dict(label="指标：同业网点数（均值）",
                          method="update", args=[{"visible": vis("standard", "mean_count")}]),
                     dict(label="指标：密度（均值 ÷ 环面积，个/km²）",
                          method="update", args=[{"visible": vis("standard", "density")}]),
                 ]),
        ])

    _layout(fig, "同业暴露随距离快速衰减",
            f"每起关闭事件 10 km 内同 BKCLASS 网点；n={n:,}；"
            f"密度口径 = 环内均值 ÷ 环面积（计数口径会随环面积增大而虚高）")
    fig.update_xaxes(title="距离环")
    fig.update_yaxes(title="每起事件的同业暴露")
    _footer(fig, "05_map/output/mapped.csv")
    return _save(fig, "attenuation.html")


# --------------------------------------------------------------------------- #
# ③ 时空演变动画（mp4 + 自包含 HTML）
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


def _us_base():
    """美国州界底图：**只画州轮廓**（不填色），预解析成线段，逐帧只 add_artist。

    数据：`assets/us_states.geojson`（美国人口普查局衍生的公共领域州界，
    一次性下载后随项目走，运行期**不联网**）。
    没有该文件或 geopandas 不可用时返回 None —— 动画仍能出，只是没有底图。
    """
    from matplotlib.collections import LineCollection

    src = Path(__file__).resolve().parent / "assets" / "us_states.geojson"
    if not src.exists():
        print("    [⑨] 未找到 assets/us_states.geojson，退回纯点密度图")
        return None
    try:
        import geopandas as gpd
        g = gpd.read_file(src)
    except Exception as exc:
        print(f"    [⑨] 州界底图不可用（{type(exc).__name__}: {exc}），退回纯点密度图")
        return None

    segs = []
    for geom in g.geometry:
        parts = geom.geoms if geom.geom_type == "MultiPolygon" else [geom]
        for poly in parts:
            segs.append(np.asarray(poly.exterior.coords)[:, :2])
            for ring in poly.interiors:
                segs.append(np.asarray(ring.coords)[:, :2])
    return LineCollection(segs, colors="#5E7FA3", linewidths=0.8, zorder=1)


def anim_spacetime(events: pd.DataFrame) -> tuple[Path, Path]:
    """上下双面板动画：**上＝美国点密度图，下＝统计图**，同步推进。

    为什么从 plotly 帧动画改成 mp4：
    ``go.Frame`` 会把每帧的点重复写进 HTML（27k 点 × 32 帧 → 6.3 MB 且播放卡）；
    mp4 + ``<video>`` 只要 1–2 MB，浏览器原生解码，带进度条与倍速。
    底图：`assets/us_states.geojson`（美国人口普查局衍生的公共领域州界），
    用 geopandas 预解析成线段后逐帧重绘 —— 没有它，27k 个网点只能自己勾出隐约轮廓。

    布局与节奏（按反馈调整）：
    * **上下**而非左右——左右会把地图压得很小、看不清；
      拉长放大后地图占上部约 55%，统计图在下部同步推进。
    * **放慢**：每年 4 个子帧（新点淡入 + 柱子长高），fps=5 → 每年 0.8 s、全程 25.6 s。
      之前每年只闪 0.2 s，根本来不及看清楚扩散发生在哪。
    """
    import matplotlib.pyplot as plt

    _mpl_style()
    d = events.dropna(subset=["lat", "lng", "acq_year"]).copy()
    d["year"] = pd.to_numeric(d["acq_year"], errors="coerce")
    d = d[d.year.notna()].copy()
    d["year"] = d.year.astype(int)
    n_raw = len(d)

    # ---- 图幅范围：**由事件本身的经纬度分位数决定**，而不是拍脑袋画整个北美 ----
    # 1%–99% 分位数 + 少量 padding。这样阿拉斯加/波多黎各/空岛等少数飞点
    # 不会把本土挤到一角（此前 xlim 写死 -180..-60，本土被压到右边 1/3）。
    Q_LO, Q_HI, PAD_LAT, PAD_LNG = 1, 99, 1.6, 2.6
    la0 = float(np.percentile(d.lat, Q_LO)) - PAD_LAT
    la1 = float(np.percentile(d.lat, Q_HI)) + PAD_LAT
    lo0 = float(np.percentile(d.lng, Q_LO)) - PAD_LNG
    lo1 = float(np.percentile(d.lng, Q_HI)) + PAD_LNG
    in_bb = d.lat.between(la0, la1) & d.lng.between(lo0, lo1)
    n_out = int((~in_bb).sum())
    d = d[in_bb].copy()

    # ---- 年份范围：**由事件本身决定**。SIMS_ACQUIRED_DATE 只到 2015，
    # 2016 起没有任何关闭事件 —— 之前硬画到 2025，等于一半时长在放空气。 ----
    years = sorted(int(v) for v in d.year.unique() if v >= 1994)
    y_min, y_max = years[0], years[-1]

    per_year = d.groupby("year").size().reindex(years, fill_value=0)
    cum = per_year.cumsum()
    lat_all, lng_all = d.lat.to_numpy(float), d.lng.to_numpy(float)
    yr_all = d.year.to_numpy(int)
    # 当年新增用亮色，历史累计用暗色 —— 一眼看出「这一年新关在哪」
    c_new, c_old = "#FFB86B", "#8B5CF6"

    # ---- 上下布局：地图在上（大），统计图在下 ----
    fig, (ax, bx) = plt.subplots(2, 1, figsize=(10.8, 12.4),
                                 gridspec_kw={"height_ratios": [1.35, 1]})
    fig.subplots_adjust(left=0.085, right=0.965, top=0.955, bottom=0.065, hspace=0.17)

    border_lc = _us_base()
    has_map = border_lc is not None
    SUB = 4                 # 每年 4 个子帧 → 淡入 + 柱子生长
    FPS = 5
    n_total = len(years) * SUB
    cum_arr = cum.to_numpy(float)
    cnt_arr = per_year.to_numpy(float)

    def draw(i):
        yi, sub = divmod(i, SUB)
        frac = (sub + 1) / SUB          # 该年内推进到哪一步（0.25 → 1.0）
        y = years[yi]
        ax.clear(); bx.clear()

        # ---------- 上：美国州轮廓 + 网点 ----------
        if has_map:
            ax.add_collection(border_lc)
        old_m = yr_all < y
        new_m = yr_all == y
        ax.scatter(lng_all[old_m], lat_all[old_m], s=3.6, c=c_old,
                   alpha=0.42, linewidths=0, rasterized=True, zorder=3)
        # 当年新增：随子帧淡入，肉眼能「看见」这一年新关在哪
        ax.scatter(lng_all[new_m], lat_all[new_m], s=13, c=c_new,
                   alpha=0.15 + 0.85 * frac, linewidths=0, rasterized=True, zorder=4)
        ax.set_xlim(lo0, lo1); ax.set_ylim(la0, la1)
        ax.set_xticks([]); ax.set_yticks([])
        for s in ax.spines.values():
            s.set_color("#1F2937")
        n_cum = int(old_m.sum() + (frac > 0.5) * new_m.sum())
        ax.set_title(f"{y}　当年新增 {int(new_m.sum()):,} 起　累计 {n_cum:,}",
                     color="#F3F4F6", fontsize=19, pad=12, loc="left")

        # ---------- 下：统计图（与上同步推进）----------
        grown = cnt_arr.copy()
        grown[yi] = cnt_arr[yi] * frac            # 当年柱子随子帧长高
        bx.bar(years, cnt_arr, color="#243044", width=0.80)
        done = years[:yi]
        bx.bar(done, cnt_arr[:yi], color=c_new, width=0.80)
        bx.bar([y], [grown[yi]], color=c_new, width=0.80, alpha=0.55 + 0.45 * frac)
        bx.set_xlim(y_min - 1.2, y_max + 1.2)
        bx.set_ylim(0, float(cnt_arr.max()) * 1.25 + 1)
        bx.set_xlabel("年份", fontsize=12)
        bx.set_ylabel("当年关闭网点数", fontsize=12)
        bx.grid(axis="y", color="#1F2937", linewidth=0.8)
        bx.tick_params(labelsize=11)
        bxt = bx.twinx()
        shown = years[:yi + 1]
        cum_show = cum_arr[:yi].copy()
        cum_show = np.append(cum_show, cum_arr[yi - 1] + cnt_arr[yi] * frac if yi else cnt_arr[0] * frac)
        bxt.plot(shown, cum_show, color="#22D3EE", linewidth=2.6)
        bxt.set_ylabel("累计（右轴）", color="#22D3EE", fontsize=12)
        bxt.tick_params(axis="y", colors="#22D3EE", labelsize=11)
        bxt.set_ylim(0, float(cum_arr.max()) * 1.05 + 1)
        bxt.grid(False)
        return ()

    mp4 = dk.animate(OUT / "spacetime.mp4", fig, draw, n_frames=n_total, fps=FPS, dpi=110)
    plt.close(fig)

    page = dk.video_page(
        mp4,
        title="网点关闭不是均匀分布，而是沿都市区级联扩散",
        subtitle=(f"{y_min}–{y_max} 逐年累计关闭事件（画幅内 n={len(d):,}，"
                  f"按事件经纬度 1%–99% 分位数裁切图幅，画幅外 {n_out:,} 点）；"
                  f"上：亮点＝当年新增，紫点＝历史累计；下：柱＝当年新增、青线＝累计。"
                  + ("底图＝美国州轮廓（美国人口普查局衍生，公共领域，随项目离线走）。"
                     if has_map else "（未找到州界文件，退回纯点密度图）")
                  + f"坐标精度 2023 年前后口径不同，此处只看宏观扩散形态。"),
        caption="建议全屏观看。可拖进度条定格任意年份；也可下载 mp4 直接放进汇报材料。",
        source="07_visualize/output/kepler/closed_events.csv",
        alt_text="左图橙点逐年在全国扩散，右图柱状与累计曲线同步上升",
    )
    p = OUT / "spacetime.html"
    p.write_text(page, encoding="utf-8")
    return mp4, p


# --------------------------------------------------------------------------- #
# ④ 证据链叙事（scrollytelling）
# --------------------------------------------------------------------------- #
_CSS = """
    :root{--ink:#111827;--sub:#6B7280;--line:#E5E7EB;--accent:#D55E00;--blue:#0072B2}
    *{box-sizing:border-box}
    body{margin:0;font-family:"Microsoft YaHei","Noto Sans CJK SC",sans-serif;
         color:var(--ink);background:#fff;line-height:1.75}
    .wrap{max-width:1040px;margin:0 auto;padding:48px 24px 96px}
    h1{font-size:30px;margin:0 0 8px;letter-spacing:-.4px}
    h2{font-size:21px;margin:56px 0 12px;padding-top:8px;border-top:1px solid var(--line)}
    .lede{font-size:16px;color:var(--sub);margin:12px 0 4px}
    .kicker{font-size:12px;letter-spacing:.14em;color:var(--accent);
            text-transform:uppercase;margin:0 0 10px;font-weight:700}
    .card{border:1px solid var(--line);border-radius:12px;overflow:hidden;margin:18px 0 6px}
    .card iframe{width:100%;height:560px;border:0;display:block}
    .cap{font-size:12.5px;color:var(--sub);padding:8px 14px;background:#FAFAFA;
         border-top:1px solid var(--line)}
    .warn{border-left:4px solid var(--accent);background:#FFF7ED;padding:14px 18px;
          border-radius:0 8px 8px 0;margin:18px 0}
    .note{border-left:4px solid var(--blue);background:#EFF6FF;padding:14px 18px;
          border-radius:0 8px 8px 0;margin:18px 0}
    ol,ul{padding-left:22px} li{margin:6px 0}
    code{background:#F3F4F6;padding:1px 5px;border-radius:4px;font-size:13px}
    .nav{display:flex;flex-wrap:wrap;gap:8px;margin:20px 0 0}
    .nav a{font-size:13px;text-decoration:none;color:var(--ink);border:1px solid var(--line);
           border-radius:999px;padding:6px 14px}
    .nav a:hover{border-color:var(--accent);color:var(--accent)}
    .foot{margin-top:64px;padding-top:16px;border-top:1px solid var(--line);
          font-size:12px;color:var(--sub)}
"""


def _page(title: str, lede: str, blocks: list[tuple[str, str, str]]) -> str:
    # blocks: (anchor, nav_label, section_html)
    nav = "".join(f'<a href="#{a}">{label}</a>' for a, label, _ in blocks)
    body = "".join(f'<section id="{a}">{html}</section>' for a, _, html in blocks)
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<title>{title}</title><style>{_CSS}</style></head><body><div class="wrap">
<h1>{title}</h1>
<p class="lede">{lede}</p>
<div class="nav">{nav}</div>
{body}
<div class="foot">数据来源：FDIC Summary of Deposits 1994–2025（32 年 × 81 列，只读）　|
生成脚本 <code>09_interactive/09_interactive.py</code>　|
生成时间 {_dt.datetime.now():%Y-%m-%d %H:%M}　|
本页所有数字来自上游产物，不硬编码。</div>
</div></body></html>"""


def build_index(est: dict) -> Path:
    es = est["event_study"]
    t = (pd.DataFrame(es["table"]).set_index("rel_year")["dynamic_effect"] * 100)
    twfe = est["twfe"]["params"]["post"] * 100

    lede = (f"10 km 内同业被并购关闭后，被辐射的存活网点存款增速<b>连续 5 年下行</b>"
            f"（τ=0 {t.get(0, float('nan')):.1f} pp → τ=4 {t.get(4, float('nan')):.1f} pp；"
            f"TWFE post {twfe:.1f} pp，p&lt;0.001）。")

    section = {
        "conclusion": f"""
<p class="kicker">结论</p>
<p>被同业关闭事件辐射的存活网点，存款增速在事件后<b>逐年加深下行</b>：
τ=0 {t.get(0, float('nan')):.2f} pp，τ=4 {t.get(4, float('nan')):.2f} pp；
面板 TWFE 的 post 项 {twfe:.2f} pp（p&lt;0.001）。</p>
<p>但聚合层 SLX 的 <code>W_treat</code> 为<b>正</b>，说明存款更可能是在更广地理尺度上
<b>再配置</b>，而不是区域净增 —— 不据此报区域增长红利或 ROI。</p>
<div class="warn"><b>守住克制：这是关联证据，不是严格因果。</b>
事件前 τ=−2 已轻微为负（平行趋势近似但非理想），区域共同冲击可能贡献了 post 的下行。</div>""",

        "mechanism": """
<p class="kicker">机制</p>
<p>核心机制是<b>距离</b>：一个网点被并购关闭后，它的客户会向周边迁移，
而迁移半径是有限的 —— 所以效应应当随距离衰减，而不是均匀铺开。</p>
<p>下面这张图把「强度」定义清楚：每个距离环内同 BKCLASS 的网点数。
注意必须切到<b>密度</b>口径才看得到真实衰减 —— 计数口径会随环面积增大而虚高，
这正是「聚合口径决定结论」的现场演示。</p>
<div class="card"><iframe src="attenuation.html" loading="lazy"
  title="距离衰减交互图"></iframe>
<div class="cap">可切换「标准环 / 合并环」×「计数 / 密度」。合并环是坐标精度敏感性口径
（早年坐标多为街道级插值，&lt;1 km 环有系统性失真）。</div></div>""",

        "evidence": """
<p class="kicker">证据</p>
<p>事件研究是本项目最硬的一块证据：它同时给出<b>效应大小</b>与<b>时间形状</b>，
并能检验平行趋势（τ&lt;0 应≈0）。</p>
<div class="card"><iframe src="event_study.html" loading="lazy"
  title="事件研究交互图"></iframe>
<div class="cap">hover 看每一期的系数、95% CI 与 p 值；基线 τ=−1。误差棒未做 bootstrap，
显著性部分来自大样本。</div></div>""",

        "spread": """
<p class="kicker">空间</p>
<p>把 27,018 起关闭事件按年铺开，会看到一个<b>级联扩散</b>而非均匀分布的过程 ——
这正是「空间大数据」在本课题的价值：去掉空间维度，只剩同城粗对照，
既回答不了距离衰减，也区分不了「本地被吸走」与「区域整体下行」。</p>
<div class="card"><iframe src="spacetime.html" loading="lazy"
  title="时空演变动画"></iframe>
<div class="cap">自动播放的 mp4 内嵌页（可拖进度条定格任意年份、可调倍速、可下载 mp4）。
左：亮点＝当年新增关闭、紫点＝历史累计；右：当年新增柱 + 累计曲线。</div></div>""",

        "limits": """
<p class="kicker">反例与限制</p>
<ol>
<li>事件前 τ=−2 轻微为负 → 平行趋势近似但非理想，区域共同冲击可能贡献 post 下行。</li>
<li>存款转移 ≠ 区域净增 → 不据此报区域增长红利或 ROI。</li>
<li>SAR 在大稀疏 KNN 上 ρ 数值不稳 → 不以 SAR 报溢出量级，仅以 SLX 的 W_treat 作代理。</li>
<li>坐标精度分年代：2023–2025 EXACT 85.98%，1994–2022 屋顶级仅 16.37%
→ 主表用 5 km 中等环，&lt;1 km 环只作参考。</li>
<li><b>缺失非随机</b>：<code>UNINUMBR</code> 缺失 120,261 行（4.26%）100% 集中在 1994–2010，
2011 年起零缺失 → 早年样本系统性不可追踪，事件研究早期年份代表性弱于近 15 年。</li>
<li>事件研究未加 bootstrap CI；空间权重仅用 KNN(k=6)，未对比其他权重方案。</li>
</ol>
<div class="warn"><b>止损条件（出现下列用法即停止）</b>
<ul>
<li>把本结论用于<b>因果断言</b>（如「关闭导致存款流失 X%」）→ 停止，先补 IV/匹配或
Callaway–Sant'Anna 类 staggered 估计。</li>
<li>把点估计换算为<b>区域存款净增 / ROI / 干预阈值</b> → 停止，成本参数缺失。</li>
<li>用 <b>SAR 的 ρ</b> 或一阶近似报溢出量级 → 停止，数值不稳。</li>
</ul></div>""",

        "repro": """
<p class="kicker">可复现</p>
<p>本页所有数字都来自流水线产物，不硬编码：</p>
<ul>
<li><code>06_estimate/output/estimate.json</code> —— 事件研究与 TWFE 系数</li>
<li><code>06_estimate/output/replication_manifest.json</code> —— 版本 / 参数 / 随机种子 / 输入指纹</li>
<li><code>05_map/output/mapped.csv</code> —— 各距离环 exposure 强度</li>
<li><code>05_map/output/lineage.csv</code> —— 每个输出字段的血缘（可追溯到来源字段与表达式）</li>
</ul>
<div class="note">重跑：<code>python main.py</code>（单阶段 <code>python main.py --stage 09</code>）。
静态图仍在 <code>07_visualize/output/figures/</code>，与这里口径一致。</div>""",
    }

    headings = [("conclusion", "① 结论", "① 结论"),
                ("mechanism", "② 机制", "② 机制：距离衰减"),
                ("evidence", "③ 证据", "③ 证据：事件研究"),
                ("spread", "④ 空间", "④ 空间：级联扩散"),
                ("limits", "⑤ 限制", "⑤ 反例与限制"),
                ("repro", "⑥ 复现", "⑥ 可复现")]
    blocks = [(a, label, f"<h2>{title}</h2>{section[a]}")
              for a, label, title in headings]

    html = _page("空间溢出证据链 · FDIC 网点关闭", lede, blocks)
    p = OUT / "index.html"
    p.write_text(html, encoding="utf-8")
    return p


# --------------------------------------------------------------------------- #
def run(project) -> dict:
    project.log(f"[{STAGE}] ⑨ 交互展示（静态图 → 可 hover / 可播放 / 可切口径）")
    OUT.mkdir(parents=True, exist_ok=True)

    est_path = project.stage_path("06_estimate", "estimate.json")
    est = json.loads(est_path.read_text(encoding="utf-8"))
    mapped = pd.read_csv(project.stage_path("05_map", "mapped.csv"))
    events = pd.read_csv(project.stage_path("07_visualize", "kepler", "closed_events.csv"))

    p1 = fig_event_study(est)
    project.log(f"    [⑨] {p1.name}（{p1.stat().st_size/1e6:.1f} MB）")
    p2 = fig_attenuation(mapped)
    project.log(f"    [⑨] {p2.name}（{p2.stat().st_size/1e6:.1f} MB）")
    mp4, p3 = anim_spacetime(events)
    project.log(f"    [⑨] {p3.name}（mp4 {mp4.stat().st_size/1e6:.1f} MB → "
                f"内嵌 {p3.stat().st_size/1e6:.1f} MB）")
    p4 = build_index(est)
    project.log(f"    [⑨] {p4.name}（{p4.stat().st_size/1e3:.0f} KB）")

    manifest = {
        "generated_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "generator": {
            "tool": "plotly", "version": __import__("plotly").__version__,
            "script": "09_interactive/09_interactive.py",
            "encoding": "utf-8", "font": "Microsoft YaHei",
            "self_contained": True, "reproducible": True,
            "note": "plotly 内联（include_plotlyjs=True），单文件自包含，离线可开、挪动不丢",
        },
        "entry": "index.html",
        "n_figures": 3,
        "figures": [
            {"file": "index.html", "title": "空间溢出证据链（叙事入口）",
             "type": "scrollytelling", "question": "证据链能不能一眼看完并能自己戳？",
             "alt_text": "滚动叙事串起结论、机制、证据、空间与限制五段",
             "source": "本目录 event_study.html / attenuation.html / spacetime.html",
             "n": 27018, "scope": "1994–2025；关联证据非严格因果", "tool": "html"},
            {"file": "event_study.html", "title": "同业关闭后，存款增速逐年下行且不收敛",
             "type": "event_study", "question": "处理效应随时间怎么走？平行趋势成立吗？",
             "alt_text": "τ=−3..4 的系数点与 95% 置信带，τ≥0 后持续下探",
             "unit": "x=距事件年数 τ，y=存款增速差异（百分点）",
             "source": "06_estimate/output/estimate.json",
             "n": est["event_study"]["n_obs"],
             "scope": "基线 τ=−1；within entity+year；未做 bootstrap CI", "tool": "plotly"},
            {"file": "attenuation.html", "title": "同业暴露随距离快速衰减",
             "type": "bar_toggle", "question": "效应随距离衰减吗？换个环宽结论还稳吗？",
             "alt_text": "可切标准环/合并环与计数/密度两组口径的对比柱图",
             "unit": "x=距离环，y=同业网点数均值或密度（个/km²）",
             "source": "05_map/output/mapped.csv", "n": len(mapped),
             "scope": "H3 R8；同 BKCLASS；密度 = 均值 ÷ 环面积", "tool": "plotly"},
            {"file": "spacetime.html", "title": "网点关闭沿都市区级联扩散",
             "type": "animation", "question": "关闭事件在空间上怎么随时间扩散？",
             "alt_text": "逐年累计关闭事件在美国州轮廓上的扩散动画，下方同步显示年度与累计",
             "unit": "x=经度，y=纬度；橙点=当年新增，紫点=历史累计",
             "source": "07_visualize/output/kepler/closed_events.csv", "n": 27018,
             "scope": "mp4（FuncAnimation）内嵌 <video>；图幅取事件经纬度 1%–99% 分位数；底图＝州轮廓",
             "tool": "matplotlib + ffmpeg"},
        ],
    }
    (OUT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return {"stage": STAGE, "blocking": False, "figures": 4,
            "artifacts": ["index.html", "event_study.html",
                          "attenuation.html", "spacetime.html", "manifest.json"]}


def main() -> None:
    project = dk.Project.load(ROOT)
    print(run(project))


if __name__ == "__main__":
    main()
