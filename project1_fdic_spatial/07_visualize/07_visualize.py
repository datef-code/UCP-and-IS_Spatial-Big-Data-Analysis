# -*- coding: utf-8 -*-
"""07_visualize —— ⑦ 可视化（扩展阶段，规范 §8 / §8.8）。

入口文件与目录同名（``07_visualize.py``），必须暴露 ``run(project) -> dict``。
**只读**上游 ``05_map/output/data/`` 与 ``06_estimate/output/``，产物只进本阶段 ``output/``。

按指导图⑥：交互式可视化（关闭事件 + 各距离环存款变动 H3 分层渲染）
                报告图表（事件研究图、衰减曲线）

出图遵循 §8.8：先选对图型 → 中文可用（微软雅黑）→ 双格式（PNG + PDF）→
``figures/`` 统一落盘 → ``manifest.json`` 登记每张图的口径与来源。
"""
from __future__ import annotations

import datetime as _dt
import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

import datakit as dk

STAGE = "07_visualize"
TITLE = "⑦ 可视化（Kepler.gl + H3 分层 + 报告图表）"

ROOT = Path(__file__).resolve().parent.parent
OUT = Path(__file__).resolve().parent / "output"
IN_MAP = ROOT / "05_map" / "output" / "data"        # 只读 ⑤ 的交付数据
IN_EST = ROOT / "06_estimate" / "output"            # 只读 ⑥ 的估计结果
OUT_DATA = OUT / "data"
FIG = OUT / "figures"
KEPLER_DIR = OUT / "kepler"
LOGS = ROOT / "logs"
for _d in (OUT, OUT_DATA, FIG, KEPLER_DIR, LOGS):
    _d.mkdir(parents=True, exist_ok=True)

# 每张图的登记信息（§8.8.5 manifest）：文件名 → (标题, 回答的问题, alt_text, 口径)
_FIGURE_META = {
    "fig_event_study.png": (
        "同业关闭后存款增速逐年下行",
        "被辐射存活网点的存款增速在事件后如何演变？",
        "事件研究曲线显示 τ=0 起为负并随年份加深",
        "网点级 event-time dummies，基线 τ=-1，within entity+year"),
    "fig_twfe_coef.png": (
        "post 主效应为负，强度交互为正",
        "TWFE 的平均处理效应与强度交互是什么符号？",
        "两条系数条显示 post 为负、post×strength 为正",
        "双向固定效应 + UNINUMBR 聚类稳健 SE"),
    "fig_attenuation_curve.png": (
        "处理强度越高，cell 存款增长越低",
        "处理强度与 cell 存款增长的关系是否单调？",
        "分位均值曲线随处理强度上升而下降",
        "H3 R8 截面 2010→2014，按 treat_strength 20 分位"),
    "fig_residual_moran.png": (
        "OLS 残差仍有空间自相关",
        "是否需要引入空间计量模型？",
        "柱状图显示残差 Moran's I 显著为正",
        "KNN(k=6) 行标准化权重，999 次置换"),
    "fig_spatial_compare.png": (
        "各空间模型处理效应方向一致",
        "不同空间设定下的处理效应是否稳健？",
        "四条系数条（含 95% CI）方向一致",
        "OLS / SAR / SEM / SLX 的 treat_strength 系数"),
    "fig_event_attenuation.png": (
        "辐射强度随事件后年限递减",
        "处理强度在事件后如何衰减？",
        "两条曲线显示原始强度与 τ 衰减后强度",
        "事件-长表按 rel_year 聚合的均值"),
}


def log(msg: str) -> None:
    print(msg, flush=True)
    with (LOGS / "pipeline.log").open("a", encoding="utf-8") as f:
        f.write(msg + "\n")


warnings.filterwarnings("ignore")


# --------------------------------------------------------------------------- #
# 1) 准备 Kepler.gl 数据：closed events + H3 cells
# --------------------------------------------------------------------------- #
def prepare_kepler_data(panel: pd.DataFrame,
                       exposure: pd.DataFrame,
                       branch_dim: pd.DataFrame) -> dict:
    """为 Kepler.gl 准备两份 GeoJSON-like 数据：
        - closed events: 关闭事件位置 + acq_year + 同业网点数（4环）
        - H3 hex: 每个 cell × t0/t1 的 DEPSUMBR + treat_strength

    Kepler.gl 期望 layers 配置由本函数返回的 dataset + config.json。
    """
    log("  [6.1] 准备 Kepler.gl 数据集（关闭事件 + H3 cell）")
    import h3

    geo = branch_dim.dropna(subset=["lat", "lng"]).copy()
    geo["UNINUMBR"] = geo["UNINUMBR"].astype(int)
    ev = geo.merge(exposure[["UNINUMBR", "acq_year", "same_ind_ring_0_1km",
                             "same_ind_ring_1_3km", "same_ind_ring_3_5km",
                             "same_ind_ring_5_10km", "same_ind_ring_0_2km",
                             "same_ind_ring_2_5km", "same_ind_ring_5_10km"]],
                   on="UNINUMBR", how="inner",
                   suffixes=("_dim", ""))
    if "acq_year" not in ev.columns:
        ev["acq_year"] = ev["acq_year_dim"] if "acq_year_dim" in ev.columns else 0
    ev["acq_year"] = ev["acq_year"].astype(int)

    # 为 Kepler.gl 输出 GeoJSON-like CSV (lat/lng + info)
    ev_out = ev[["UNINUMBR", "lat", "lng", "acq_year", "BKCLASS", "MSABR",
                 "same_ind_ring_0_1km", "same_ind_ring_1_3km",
                 "same_ind_ring_3_5km", "same_ind_ring_5_10km",
                 "same_ind_ring_0_2km", "same_ind_ring_2_5km",
                 "same_ind_ring_5_10km"]].copy()
    ev_out.to_csv(KEPLER_DIR / "closed_events.csv", index=False)
    log(f"    closed_events: {len(ev_out):,} 行")

    # H3 cell × year 面板
    p = panel.dropna(subset=["UNINUMBR", "YEAR", "DEPSUMBR"]).copy()
    p["YEAR"] = p["YEAR"].astype(int)
    p["UNINUMBR"] = p["UNINUMBR"].astype(int)
    p = p.merge(geo[["UNINUMBR", "h3"]] if "h3" in geo.columns else
                geo.assign(h3=lambda d: [h3.latlng_to_cell(la, ln, 8)
                                          for la, ln in zip(d["lat"], d["lng"])])[["UNINUMBR", "h3"]],
                on="UNINUMBR", how="left")
    p = p.dropna(subset=["h3"])
    cell_year = p.groupby(["h3", "YEAR"], as_index=False).agg(
        DEPSUMBR=("DEPSUMBR", "sum"), n=("UNINUMBR", "nunique"))
    cell_year.to_csv(OUT_DATA / "cell_year.csv", index=False)

    cs = pd.read_parquet(IN_EST / "data" / "spatial_cross_section.parquet")
    cs["lat"] = [h3.cell_to_latlng(c)[0] for c in cs["h3"]]
    cs["lng"] = [h3.cell_to_latlng(c)[1] for c in cs["h3"]]
    cs_out = cs[["h3", "lat", "lng", "DEPSUMBR_2010", "DEPSUMBR_2014",
                 "dep_growth", "treat_strength", "treated", "n_branches"]].copy()
    cs_out.to_csv(KEPLER_DIR / "h3_cells.csv", index=False)
    log(f"    h3_cells: {len(cs_out):,} 行")
    return {"n_events": len(ev_out), "n_cells": len(cs_out)}


# --------------------------------------------------------------------------- #
# 2) 生成 Kepler.gl 配置 + 自包含 HTML
# --------------------------------------------------------------------------- #
def build_kepler_config(n_events: int, n_cells: int) -> dict:
    """生成 Kepler.gl config（含事件点、H3 hex + multiple layers）。"""
    log("  [6.2] 构造 Kepler.gl 配置")

    config = {
        "version": "v1",
        "config": {
            "visState": {
                "filters": [],
                "layers": [
                    # H3 hex layer: deposit growth by cell
                    {
                        "id": "cell-hex-layer",
                        "type": "hexagon",
                        "config": {
                            "dataId": "h3_cells",
                            "label": "H3 R8 cells: deposit growth 2010→2014",
                            "color": [0, 0, 0],
                            "columns": {"lat": "lat", "lng": "lng"},
                            "isVisible": True,
                            "visConfig": {
                                "opacity": 0.5,
                                "worldUnitSize": 1.5,
                                "coverage": 1,
                                "elevationScale": 2,
                                "colorRange": {
                                    "name": "Global Warming",
                                    "type": "sequential",
                                    "colors": [
                                        "#2A2A3F", "#3D3399", "#5E2EFF", "#A23EFF",
                                        "#FF3DFF", "#FF608B", "#FF8C5A", "#FFB358",
                                        "#FFD96E", "#FFEF8B",
                                    ],
                                },
                                "coverageField": {"name": "n_branches"},
                                "elevationField": {"name": "dep_growth"},
                            },
                            "textLabel": [],
                        },
                        "visualChannels": {
                            "colorField": {"name": "dep_growth", "type": "real"},
                            "colorScale": "quantile",
                            "sizeField": {"name": "n_branches", "type": "real"},
                            "sizeScale": "sqrt",
                        },
                    },
                    # 关闭事件点
                    {
                        "id": "closed-events-layer",
                        "type": "point",
                        "config": {
                            "dataId": "closed_events",
                            "label": "Closed branch events",
                            "color": [255, 0, 0],
                            "columns": {"lat": "lat", "lng": "lng"},
                            "isVisible": True,
                            "visConfig": {
                                "radius": 3.5,
                                "fixedRadius": False,
                                "opacity": 0.85,
                                "outline": True,
                                "colorRange": {
                                    "name": "ColorBrewer Set1",
                                    "type": "qualitative",
                                    "colors": ["#FF0000", "#FFB300", "#FFF600",
                                               "#A6FD8E", "#13D6E8"],
                                },
                            },
                        },
                        "visualChannels": {
                            "colorField": {"name": "acq_year", "type": "integer"},
                            "colorScale": "quantile",
                        },
                    },
                ],
                "interactionConfig": {
                    "tooltip": {"enabled": True, "config": {"fieldsToShow": {
                        "h3_cells": ["dep_growth", "treat_strength", "treated"],
                        "closed_events": ["acq_year", "BKCLASS", "same_ind_ring_0_1km",
                                          "same_ind_ring_1_3km", "same_ind_ring_5_10km"],
                    }}},
                },
                "layerBlending": "additive",
                "splitMaps": [],
                "animationConfig": {"currentTime": None},
            },
            "mapStyle": {
                "styleType": "dark-matter",
                "topLayerGroups": {
                    "label": True, "road": True, "boundary": True, "water": True,
                    "land": True, "3d building": False,
                },
                "visibleLayerGroups": {
                    "label": True, "road": True, "border": False, "water": True,
                    "land": True, "building": False,
                },
            },
            "mapState": {
                "bearing": 0,
                "dragRotate": False,
                "latitude": 39.5,
                "longitude": -98.35,
                "pitch": 0,
                "zoom": 3,
                "isSplit": False,
            },
            "uiState": {
                "mapHeight": 720, "mapWidth": 1280,
            },
        },
    }
    return config


def write_kepler_html(config: dict) -> None:
    """写一份独立的 Kepler.gl HTML：嵌入 CSV + config + UMD Kepler.gl bundle。"""
    log("  [6.3] 写自包含的 Kepler.gl HTML (离线 + 数据嵌入)")

    import base64
    csv_events = (KEPLER_DIR / "closed_events.csv").read_text(encoding="utf-8")
    csv_cells = (KEPLER_DIR / "h3_cells.csv").read_text(encoding="utf-8")
    csv_events_b64 = base64.b64encode(csv_events.encode("utf-8")).decode("ascii")
    csv_cells_b64 = base64.b64encode(csv_cells.encode("utf-8")).decode("ascii")
    config_json = json.dumps(config, ensure_ascii=False)

    html = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>FDIC Spatial: Branch Closure &amp; Deposit Churn</title>
<script src="https://unpkg.com/kepler.gl@3.2.0/umd/keplergl.min.js"></script>
<style>
  body { margin: 0; font-family: -apple-system, BlinkMacSystemFont, sans-serif; }
  #content { display: flex; flex-direction: column; height: 100vh; }
  #titlebar { padding: 12px 24px; background: #1a1a2e; color: white; }
  #titlebar h1 { margin: 0 0 4px 0; font-size: 18px; }
  #titlebar p { margin: 0; font-size: 12px; opacity: 0.85; }
  #map { flex: 1; }
</style>
</head>
<body>
<div id="content">
  <div id="titlebar">
    <h1>方案⑥ · FDIC 网点关闭 + 周边同业存款变动 · H3 R8</h1>
    <p>事件点（颜色 = acq_year 队列）+ H3 R8 cells（高度 = deposit growth 2010→2014，颜色 = quantile）</p>
  </div>
  <div id="map"></div>
</div>
<script>
const CSV_EVENTS = "data:text/csv;base64,__CSV_EVENTS_B64__";
const CSV_CELLS = "data:text/csv;base64,__CSV_CELLS_B64__";
const CONFIG = __CONFIG_JSON__;

function b64ToBlob(b64) {
  const bin = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return new Blob([bytes], {type: "text/csv"});
}

const container = document.getElementById("map");
const app = new KeplerGL.default({
  container: container,
  mapboxAccessToken: null,
  width: window.innerWidth,
  height: window.innerHeight,
});

(async () => {
  const e1 = await fetch(CSV_EVENTS);
  const e2 = await fetch(CSV_CELLS);
  const eventsCsv = await e1.text();
  const cellsCsv = await e2.text();
  const evDataset = await app.csvDataset(eventsCsv);
  const ceDataset = await app.csvDataset(cellsCsv);
  app.addDataToMap({
    datasets: [
      {info: {label: "closed_events", id: "closed_events"}, data: evDataset},
      {info: {label: "h3_cells",      id: "h3_cells"},      data: ceDataset},
    ],
    config: CONFIG.config,
  });
})();
</script>
</body>
</html>"""
    # 安全替换占位符（避免 f-string 中花括号问题）
    html = (html.replace("__CSV_EVENTS_B64__", csv_events_b64)
                .replace("__CSV_CELLS_B64__", csv_cells_b64)
                .replace("__CONFIG_JSON__", config_json))
    (KEPLER_DIR / "kepler_map.html").write_text(html, encoding="utf-8")
    (KEPLER_DIR / "kepler_config.json").write_text(
        json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")


# --------------------------------------------------------------------------- #
# 3) matplotlib 静态图：事件研究、衰减曲线、residual Moran's I
# --------------------------------------------------------------------------- #
def _setup_cjk_font() -> None:
    """注册并启用中文字体（规范 §8.8.3）：乱码 90% 是字形缺失，解法是换字体。"""
    import matplotlib
    from matplotlib import font_manager

    candidates = [
        r"C:\Windows\Fonts\msyh.ttc",      # 微软雅黑
        r"C:\Windows\Fonts\msyhbd.ttc",    # 微软雅黑 Bold
        r"C:\Windows\Fonts\simhei.ttf",    # 黑体
        r"C:\Windows\Fonts\simsun.ttc",    # 宋体
    ]
    for path in candidates:
        if Path(path).exists():
            try:
                font_manager.fontManager.addfont(path)
            except Exception as e:  # 字体损坏/占用等：忽略继续
                log(f"    [warn] 注册字体失败 {path}: {e}")

    matplotlib.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["Microsoft YaHei", "SimHei", "Noto Sans CJK SC",
                            "Noto Sans SC", "SimSun", "DejaVu Sans"],
        "axes.unicode_minus": False,     # 负号变方块的元凶
        "pdf.fonttype": 42,              # PDF 嵌入 TrueType，别人打开不缺字
        "figure.dpi": 110, "savefig.dpi": 200,
        "figure.facecolor": "white", "savefig.facecolor": "white",
    })


def _save(fig, name: str) -> Path:
    """统一落盘：PNG（看）+ PDF（矢量，进文档），位置 ``output/figures/``。"""
    p = FIG / name
    fig.tight_layout()
    fig.savefig(p, dpi=200, bbox_inches="tight", pad_inches=0.1, facecolor="white")
    fig.savefig(p.with_suffix(".pdf"), bbox_inches="tight", pad_inches=0.1, facecolor="white")
    return p


def plot_event_study(event: dict) -> None:
    """事件研究图（cohort × rel_year dummies）。"""
    log("  [6.4] 事件研究图（cohort × event-time）")
    import matplotlib.pyplot as plt
    _setup_cjk_font()

    if not event or "table" not in event or not event["table"]:
        log("    [跳过] event_study 无表")
        return

    table = event["table"]
    rel_years = [t["rel_year"] for t in table]
    effects = [t["dynamic_effect"] for t in table]
    ses = [t.get("std_err", 0.0) for t in table]

    fig, ax = plt.subplots(figsize=(7, 4.2))
    ax.axhline(0, color="gray", lw=0.8)
    ax.axvline(-1, color="gray", lw=0.8, linestyle="--", alpha=0.5)
    ax.plot(rel_years, effects, marker="o", color="#3366ff",
            lw=2, label="dynamic effect (vs τ=-1)")
    ax.fill_between(rel_years,
                    [e - 1.96 * s for e, s in zip(effects, ses)],
                    [e + 1.96 * s for e, s in zip(effects, ses)],
                    color="#3366ff", alpha=0.15, label="95% CI")
    ax.set_xlabel("event time τ (years since first nearby closure)")
    ax.set_ylabel("Δ dep_chg_rate vs baseline τ=-1 (within entity+year)")
    ax.set_title("Event-study: deposit churn of surviving branches after nearby peer closure")
    ax.legend()
    p = _save(fig, "fig_event_study.png")
    plt.close(fig)
    log(f"    saved → {p}")


def plot_attenuation_curve(cs: pd.DataFrame) -> None:
    """衰减曲线：H3 截面中 treat_strength 取分位数后对 dep_growth 的局部均值"""
    log("  [6.5] 衰减曲线（按 treat_strength 分位 → cell 均值）")
    import matplotlib.pyplot as plt
    _setup_cjk_font()

    df = cs.dropna(subset=["treat_strength", "dep_growth_clip"]).copy()
    df["q"] = pd.qcut(df["treat_strength"], q=20, labels=False, duplicates="drop")
    grouped = df.groupby("q").agg(
        treat_mean=("treat_strength", "mean"),
        dep_mean=("dep_growth_clip", "mean"),
        dep_sem=("dep_growth_clip", lambda s: s.std() / np.sqrt(len(s))),
        n=("dep_growth_clip", "size"),
    )

    fig, ax = plt.subplots(figsize=(7, 4.2))
    ax.errorbar(grouped["treat_mean"], grouped["dep_mean"],
                yerr=grouped["dep_sem"], fmt="o-", color="#0a8f4e",
                lw=2, capsize=3)
    ax.axhline(df["dep_growth_clip"].mean(), color="red", linestyle="--",
               lw=0.8, label="global mean")
    ax.set_xlabel("treat_strength quantile → mean")
    ax.set_ylabel("mean dep_growth_clip (cell)")
    ax.set_title("Attenuation: dep_growth vs treatment intensity (H3 R8 cells, 2010→2014)")
    ax.legend()
    p = _save(fig, "fig_attenuation_curve.png")
    plt.close(fig)
    log(f"    saved → {p}")


def plot_residual_moran(mi_info: dict) -> None:
    """残差 Moran's I summary 柱状图 + 显著性注解"""
    log("  [6.6] 残差 Moran's I 注解图")
    import matplotlib.pyplot as plt
    _setup_cjk_font()

    if not mi_info:
        return
    fig, ax = plt.subplots(figsize=(6.4, 3.2))
    I = mi_info.get("I", 0.0)
    z = mi_info.get("z_sim", 0.0)
    p = mi_info.get("p_sim", 1.0)
    ax.bar(["OLS residuals"], [I], color="#0077b6" if p < 0.05 else "#888888",
           alpha=0.85)
    ax.axhline(mi_info.get("E_I", -1 / (30_000 - 1)), color="red",
               linestyle="--", lw=0.8, label="E[I]")
    ax.set_ylabel("Moran's I")
    ax.set_title(f"OLS residual spatial autocorrelation  "
                 f"(z={z:.3g}, p_sim={p:.3g}, "
                 f"{'significant → 加空间项' if p < 0.05 else 'not significant'})")
    ax.legend()
    out = _save(fig, "fig_residual_moran.png")
    plt.close(fig)
    log(f"    saved → {out}")


def plot_twfe_coef(twfe: dict) -> None:
    """TWFE 系数条形图 + 95% CI"""
    log("  [6.7] TWFE 系数条形图")
    import matplotlib.pyplot as plt
    _setup_cjk_font()

    if not twfe or "params" not in twfe:
        return
    params = twfe["params"]
    se = twfe.get("std_err", {k: 0.0 for k in params})
    labels = list(params.keys())
    vals = list(params.values())
    errs = [1.96 * se.get(k, 0.0) for k in labels]

    fig, ax = plt.subplots(figsize=(7, 3.6))
    y = np.arange(len(labels))
    ax.barh(y, vals, xerr=errs, color="#845ec2", alpha=0.85, capsize=4)
    ax.axvline(0, color="gray", lw=0.8)
    ax.set_yticks(y, labels=labels)
    ax.set_xlabel("coefficient (95% CI)")
    ax.set_title(f"TWFE 双向固定效应（n={twfe.get('n_obs','?'):,}）  "
                 f"β(post×strength)={params.get('post_x_strength', 0.0):.4g}")
    out = _save(fig, "fig_twfe_coef.png")
    plt.close(fig)
    log(f"    saved → {out}")


def plot_spatial_diagnostics(fits: dict, cs: pd.DataFrame) -> None:
    """SAR/SEM/SLX 直接系数对比图"""
    log("  [6.8] 空间模型对比（直接效应）")
    import matplotlib.pyplot as plt
    _setup_cjk_font()

    rows = []
    for label in ["ols", "sar", "sem", "slx"]:
        m = fits.get(label)
        if not m:
            continue
        p = m.get("params", {})
        beta = p.get("treat_strength", float("nan"))
        se = m.get("std_err", {}).get("treat_strength", float("nan"))
        rows.append({"model": label.upper(), "beta": beta, "se": se})
    if not rows:
        return
    df = pd.DataFrame(rows)

    fig, ax = plt.subplots(figsize=(7, 3.4))
    y = np.arange(len(df))
    ax.barh(y, df["beta"], xerr=1.96 * df["se"], color="#2d6a4f",
            alpha=0.8, capsize=4)
    ax.axvline(0, color="gray", lw=0.8)
    ax.set_yticks(y, labels=df["model"])
    ax.set_xlabel("treat_strength coefficient (95% CI)")
    ax.set_title("直接效应：不同空间模型下的 treat_strength 系数对比")
    out = _save(fig, "fig_spatial_compare.png")
    plt.close(fig)
    log(f"    saved → {out}")


# --------------------------------------------------------------------------- #
# 4) 衰减曲线（基于事件-长表的 τ 维度）
# --------------------------------------------------------------------------- #
def plot_event_attenuation() -> None:
    """事件长表：在 τ（事件后第几年）维度上的平均 strength_decay。"""
    log("  [6.9] 事件衰减曲线（τ 维）")
    import matplotlib.pyplot as plt
    _setup_cjk_font()
    long = pd.read_parquet(IN_EST / "data" / "did_event_long.parquet")
    agg = long.groupby("rel_year").agg(
        strength_mean=("strength_t0", "mean"),
        strength_decay_mean=("strength_decay", "mean"),
        n=("event_UNINUMBR", "count"),
    )

    fig, ax = plt.subplots(figsize=(6.5, 3.6))
    ax.plot(agg.index, agg["strength_mean"], marker="o", lw=2,
            color="#ff6f61", label="平均 ring-stacking 强度")
    ax.plot(agg.index, agg["strength_decay_mean"], marker="s", lw=1.5,
            color="#1e88e5", label="τ 衰减后 (× 1/(1+τ))")
    ax.set_xlabel("event time τ = YEAR - acq_year")
    ax.set_ylabel("强度")
    ax.set_title("事件长表的强度衰减（τ × distance stack）")
    ax.legend()
    ax.grid(True, alpha=0.3)
    out = _save(fig, "fig_event_attenuation.png")
    plt.close(fig)
    log(f"    saved → {out}")


# --------------------------------------------------------------------------- #
# 主流程
# --------------------------------------------------------------------------- #
def build_manifest(n_cells: int) -> dict:
    """按规范 §8.8.5 生成 manifest.json（图清单：文件名 → 标题 → 口径 → 来源 → alt_text）。"""
    import matplotlib

    figures = []
    for p in sorted(FIG.glob("*.png")):
        meta = _FIGURE_META.get(p.name)
        figures.append({
            "file": f"figures/{p.name}",
            "pdf": f"figures/{p.stem}.pdf",
            "title": meta[0] if meta else p.stem,
            "question": meta[1] if meta else "",
            "alt_text": meta[2] if meta else "",
            "scope": meta[3] if meta else "",
            "source": "05_map/output/data/ + 06_estimate/output/estimate.json",
            "unit": "见各图轴标签",
        })
    return {
        "generated_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "generator": {
            "tool": "matplotlib", "version": matplotlib.__version__,
            "script": "07_visualize/07_visualize.py",
            "encoding": "utf-8", "font": "Microsoft YaHei", "reproducible": True,
        },
        "kepler_html": "kepler/kepler_map.html",
        "kepler_config": "kepler/kepler_config.json",
        "n_figures": len(figures),
        "n_cells": n_cells,
        "figures": figures,
    }


def run(project) -> dict:
    """只读上游产物，产出 Kepler 地图 + 报告图表 + manifest.json。"""
    log("=" * 60)
    log(f"[{STAGE}] {TITLE}")

    panel = pd.read_parquet(IN_MAP / "branch_year_panel.parquet")
    exposure = pd.read_csv(IN_MAP / "closure_exposure.csv")
    branch_dim = pd.read_csv(IN_MAP / "branch_dim.csv")
    log(f"  读入：panel={len(panel):,}，exposure={len(exposure):,}，branch_dim={len(branch_dim):,}")

    sizes = prepare_kepler_data(panel, exposure, branch_dim)
    config = build_kepler_config(sizes["n_events"], sizes["n_cells"])
    write_kepler_html(config)

    # matplotlib 静态图（数据源 = ⑥ 的估计结果）
    estimate = json.loads((IN_EST / "estimate.json").read_text(encoding="utf-8"))
    plot_event_study(estimate.get("event_study", {}))
    plot_twfe_coef(estimate.get("twfe", {}))

    cs = pd.read_parquet(IN_EST / "data" / "spatial_cross_section.parquet")
    plot_attenuation_curve(cs)
    plot_residual_moran(estimate.get("spatial_fits", {}).get("residuals_morans_i"))
    plot_spatial_diagnostics(estimate.get("spatial_fits", {}), cs)
    plot_event_attenuation()

    manifest = build_manifest(sizes["n_cells"])
    dk.write_json(OUT, "manifest", manifest)
    log(f"完成 ⑦ 可视化 → 07_visualize/output/（{manifest['n_figures']} 图 + kepler/kepler_map.html）")
    return {
        "stage": STAGE, "blocking": False,
        "figures": manifest["n_figures"],
        "h3_cells": sizes["n_cells"],
        "closure_events": sizes["n_events"],
        "artifacts": ["manifest.json", "figures/", "kepler/kepler_map.html"],
    }


def main() -> None:
    project = dk.Project.load(ROOT)
    print(run(project))


if __name__ == "__main__":
    main()
