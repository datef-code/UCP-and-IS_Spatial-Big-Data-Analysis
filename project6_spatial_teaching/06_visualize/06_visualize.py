# -*- coding: utf-8 -*-
"""06_visualize —— ⑥ 可视化（扩展阶段，规范 §8）。

只读上游 ``05_map/output/<dataset>/`` 的 L0→L3 产物，产出教学用静态素材
（开源电子书 / 知乎专栏 / B站视频课）：

* 每数据集 3 张图：L0 格值集中度（ECDF）、L2 Moran 散点（六边形分箱）、L3 距离环溢出；
* 全局 1 张：四数据集 L0→L2 关键指标对比（导论章「权重矩阵定义对结论敏感」）。

出图规范（``PROJECT_STRUCTURE.md`` §8.8）：标题写结论、轴带单位、样本量 `n=`、
Okabe–Ito 色板、despine、脚注标来源产物与生成时间；PNG（看）+ PDF（进文档）双格式；
每张图登记进 ``manifest.json``（含 alt_text、口径、来源、n）。
"""
from __future__ import annotations

import datetime as _dt
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

import datakit as dk

STAGE = "06_visualize"
DATASETS = ("fdic", "sz_bike", "snap_brightkite", "snap_gowalla")
SCRIPT = "06_visualize/06_visualize.py"
OKABE_ITO = ["#0072B2", "#E69F00", "#009E73", "#CC79A7", "#56B4E9", "#D55E00"]

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


# --------------------------------------------------------------------------- #
# 画图基础设施（§8.8.2 / §8.8.3 / §8.8.4）
# --------------------------------------------------------------------------- #
def _plt():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib as mpl
    mpl.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["Microsoft YaHei", "SimHei", "Noto Sans CJK SC",
                            "Noto Sans SC", "KaiTi", "SimSun", "DejaVu Sans"],
        "axes.unicode_minus": False,
        "pdf.fonttype": 42, "ps.fonttype": 42, "svg.fonttype": "none",
        "figure.dpi": 110, "savefig.dpi": 200,
        "figure.facecolor": "white", "savefig.facecolor": "white",
        "axes.titlesize": 14, "axes.labelsize": 11, "xtick.labelsize": 9,
        "ytick.labelsize": 9, "legend.frameon": False,
    })
    return plt


def _save(fig, plt, png: Path) -> None:
    png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(png, dpi=200, bbox_inches="tight", pad_inches=0.1, facecolor="white")
    fig.savefig(png.with_suffix(".pdf"), bbox_inches="tight", pad_inches=0.1, facecolor="white")
    plt.close(fig)


def _despine(ax) -> None:
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.grid(axis="y", color="#9CA3AF", alpha=0.3, linewidth=0.7)
    ax.set_axisbelow(True)


def _footnote(fig, source: str, ts: str) -> None:
    fig.text(0.995, 0.005, f"数据来源：{source}　生成：{ts}（{SCRIPT}）",
             ha="right", va="bottom", fontsize=8, color="#6B7280")


def _subtitle(ax, text: str) -> None:
    ax.set_title(ax.get_title(), fontsize=14, pad=26)
    ax.text(0.0, 1.02, text, transform=ax.transAxes, fontsize=9, color="#4B5563")


def _human(n: float) -> str:
    v = float(n or 0)
    for unit in ("", "k", "M", "G"):
        if abs(v) < 1000:
            return f"{v:,.0f}{unit}"
        v /= 1000.0
    return f"{v:,.1f}T"


# --------------------------------------------------------------------------- #
# 三张教学图
# --------------------------------------------------------------------------- #
def fig_cell_value_ecdf(plt, df: pd.DataFrame, out: Path, ctx: dict) -> dict:
    vals = df["value"].to_numpy(dtype=float)
    pos = vals[vals > 0]
    share = float(pos[np.argsort(-pos)][:max(1, len(pos) // 10)].sum() / pos.sum()) if len(pos) else 0.0
    x = np.sort(pos)
    y = np.arange(1, len(x) + 1) / len(x) if len(x) else np.array([])

    fig, ax = plt.subplots(figsize=(6, 4))
    ax.plot(x, y, color=OKABE_ITO[0], linewidth=1.8)
    ax.set_xscale("log")
    ax.set_xlabel("格值（对数刻度，单位同度量语义）")
    ax.set_ylabel("累计占比")
    ax.set_title(f"前 10% 的格贡献 {share:.0%} 的总量")
    _subtitle(ax, f"n={len(vals):,} 格；口径：H3 R{ctx['h3_res']} 求和聚合，零值格已剔除")
    ax.set_ylim(0, 1.02)
    _despine(ax)
    _save(fig, plt, out / "01-L0-cell-value-ecdf.png")
    return {
        "file": "figures/01-L0-cell-value-ecdf.png",
        "pdf": "figures/01-L0-cell-value-ecdf.pdf",
        "title": f"前 10% 的格贡献 {share:.0%} 的总量",
        "type": "ecdf",
        "question": "格值是均匀分布还是高度集中？",
        "alt_text": f"ECDF 曲线显示格值长尾，前 10% 的格贡献 {share:.0%} 的总量",
        "unit": "x=格值（对数），y=累计占比",
        "notes": "零值格已剔除；口径为 R8 求和聚合",
    }


def fig_moran_scatter(plt, df: pd.DataFrame, out: Path, ctx: dict) -> dict:
    d = df[(df["value"] > 0) & (df["spatial_lag"] > 0)]
    moran = float(ctx["moran_i"])
    if moran >= 0.3:
        title = f"强空间聚集：Moran's I={moran:.2f}"
    elif moran >= 0.05:
        title = f"弱空间聚集：Moran's I={moran:.2f}"
    else:
        title = f"几乎无空间聚集：Moran's I={moran:.2f}"

    fig, ax = plt.subplots(figsize=(6, 5))
    if len(d) > 50:
        hb = ax.hexbin(d["value"], d["spatial_lag"], gridsize=45, mincnt=1,
                       xscale="log", yscale="log", cmap="viridis", bins="log", linewidths=0)
        cb = fig.colorbar(hb, ax=ax, label="格数（对数）")
        cb.outline.set_visible(False)
    else:
        ax.scatter(d["value"], d["spatial_lag"], s=14, alpha=0.5, color=OKABE_ITO[0], edgecolors="none")
    lims = [max(d["value"].min(), 1e-9), d["value"].max()]
    ax.plot(lims, lims, color="#9CA3AF", linestyle="--", linewidth=1, label="y = x（等比参考）")
    ax.legend(loc="upper left", fontsize=9)
    ax.set_xlabel("格值（对数刻度）")
    ax.set_ylabel("空间滞后 Wx（对数刻度）")
    ax.set_title(title)
    _subtitle(ax, f"n={len(d):,} 非零格；H3 R{ctx['h3_res']} 邻接，W 行标准化")
    _despine(ax)
    _save(fig, plt, out / "02-L2-moran-scatter.png")
    return {
        "file": "figures/02-L2-moran-scatter.png",
        "pdf": "figures/02-L2-moran-scatter.pdf",
        "title": title,
        "type": "moran_scatter",
        "question": "格值与其邻居均值是否同向变化？",
        "alt_text": f"六边形分箱散点显示格值与空间滞后{'正相关' if moran > 0 else '不相关'}，I={moran:.2f}",
        "unit": "x=格值，y=空间滞后（均为对数刻度）",
        "notes": "零值格已剔除；虚线为 y=x 参考线",
    }


def fig_ring_spillover(plt, spill: pd.DataFrame, out: Path, ctx: dict) -> dict:
    # 优先用「溢出密度」（环内格均摊）：环面积随距离增大，求和口径不会衰减
    den_cols = [c for c in spill.columns if c.startswith("spillden_")]
    sum_cols = [c for c in spill.columns if c.startswith("spill_") and not c.startswith("spillden_")]
    use_den = bool(den_cols)
    cols = den_cols if use_den else sum_cols
    means = spill[cols].mean(skipna=True)
    labels = [c.replace("spillden_", "").replace("spill_", "")
               .replace("p", ".").replace("km", "").replace("_", "–") + " km"
              for c in cols]
    vals = means.to_numpy(dtype=float)
    decreasing = bool(all(np.diff(vals) <= 0))
    title = "溢出密度随距离衰减" if decreasing else "溢出密度未随距离衰减"

    fig, ax = plt.subplots(figsize=(6.5, 4))
    bars = ax.bar(labels, vals, color=OKABE_ITO[0], width=0.62)
    for bar, v in zip(bars, vals):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(),
                _human(v), ha="center", va="bottom", fontsize=9)
    ax.set_xlabel("距热点圆心距离环")
    ax.set_ylabel("溢出密度（环内格均摊）" if use_den else "平均溢出值（求和）")
    ax.set_title(title)
    scope = ("口径：环内格值求和 ÷ 环内格数（密度）" if use_den
             else "口径：环内格值求和后取均值（环面积随距离增大，求和不衰减）")
    _subtitle(ax, f"n={len(spill)} 个热点圆心（Top-{ctx['hot_top_n']}）；{scope}")
    ax.set_ylim(0, max(vals.max() * 1.18, 1e-9))
    _despine(ax)
    _save(fig, plt, out / "03-L3-ring-spillover.png")
    return {
        "file": "figures/03-L3-ring-spillover.png",
        "pdf": "figures/03-L3-ring-spillover.pdf",
        "title": title,
        "type": "bar",
        "question": "热点周边溢出是否随距离衰减？",
        "alt_text": ("柱状图显示四个距离环的溢出密度" +
                     ("由近及远递减" if decreasing else "未呈现递减")),
        "unit": "x=距离环（km），y=溢出密度" if use_den else "x=距离环（km），y=平均溢出值",
        "notes": f"圆心为格值 Top-{ctx['hot_top_n']} 的热点格；"
                 + ("密度 = 环内求和 ÷ 环内格数" if use_den else "求和口径"),
    }


def fig_global_compare(plt, rows: list[dict], out: Path) -> dict:
    names = [r["dataset"] for r in rows]
    points = [r["points"] for r in rows]
    cells = [r["cells"] for r in rows]
    moran = [r["moran_i"] for r in rows]
    hi = names[int(np.argmax(moran))]
    lo = names[int(np.argmin(moran))]

    fig, axes = plt.subplots(1, 3, figsize=(13.5, 4.2))
    for ax, vals, label, color in ((axes[0], points, "L0 原始点数", OKABE_ITO[0]),
                                   (axes[1], cells, f"L0 H3 格数", OKABE_ITO[1]),
                                   (axes[2], moran, "L2 Moran's I", OKABE_ITO[2])):
        ax.bar(names, vals, color=color, width=0.62)
        ax.set_ylabel(label)
        if ax is axes[0] or ax is axes[1]:
            ax.set_yscale("log")
        ax.tick_params(axis="x", labelrotation=15)
        for t in ax.get_xticklabels():
            t.set_horizontalalignment("right")
        _despine(ax)
    for ax in axes[:2]:
        for bar, v in zip(ax.patches, (points if ax is axes[0] else cells)):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(), _human(v),
                    ha="center", va="bottom", fontsize=8)
    for bar, v in zip(axes[2].patches, moran):
        axes[2].text(bar.get_x() + bar.get_width() / 2, bar.get_height(), f"{v:.2f}",
                     ha="center", va="bottom", fontsize=8)
    axes[2].set_ylim(min(0, min(moran)) - 0.05, max(moran) * 1.2 + 0.05)
    fig.suptitle(f"{hi} 空间聚集最强，{lo} 最弱", fontsize=14, y=1.02)
    fig.text(0.01, -0.02, "口径：H3 R8 邻接 + 行标准化 W；点数/格数为对数刻度", fontsize=9, color="#4B5563")
    fig.tight_layout()
    _save(fig, plt, out / "01-global-ladder-comparison.png")
    return {
        "file": "figures/01-global-ladder-comparison.png",
        "pdf": "figures/01-global-ladder-comparison.pdf",
        "title": f"{hi} 空间聚集最强，{lo} 最弱",
        "type": "small_multiples",
        "question": "四个数据集的规模与空间自相关差多少？",
        "alt_text": f"三联柱状图：{hi} 的 Moran's I 最高、{lo} 最低",
        "unit": "左/中=数量（对数），右=Moran's I",
        "notes": "导论章用图：说明空间权重矩阵定义对结论敏感",
    }


# --------------------------------------------------------------------------- #
def run(project) -> dict:
    try:
        plt = _plt()
    except ImportError as exc:
        project.log(f"[{STAGE}] matplotlib 不可用，跳过出图：{exc}")
        return {"stage": STAGE, "ok": False, "blocking": False, "error": str(exc)}

    import matplotlib
    import h3

    datasets = project.meta.get("datasets") or list(DATASETS)
    ts = _dt.datetime.now().isoformat(timespec="seconds")
    out_root = project.stage_output(STAGE)
    rows: list[dict] = []

    for ds in datasets:
        base = project.stage_output("05_map") / ds
        ladder = json.loads((base / "ladder_report.json").read_text(encoding="utf-8"))
        lag = pd.read_csv(base / "L2_spatial_lag.csv")
        spill = pd.read_csv(base / "L3_ring_spillover.csv")
        l0, l1, l2, l3 = ladder["tiers"]["L0"], ladder["tiers"]["L1"], ladder["tiers"]["L2"], ladder["tiers"]["L3"]
        ctx = {"h3_res": l0["h3_res"], "moran_i": float(l2["moran_i"]), "hot_top_n": l3["centers"]}

        fig_dir = out_root / ds / "figures"
        figs = [
            fig_cell_value_ecdf(plt, lag, fig_dir, ctx),
            fig_moran_scatter(plt, lag, fig_dir, ctx),
            fig_ring_spillover(plt, spill, fig_dir, ctx),
        ]
        source = f"05_map/output/{ds}/{{L2_spatial_lag.csv, L3_ring_spillover.csv, ladder_report.json}}"
        for f in figs:
            f.update({"source": source, "n": int(len(lag)),
                      "scope": f"H3 R{l0['h3_res']}；W 行标准化；孤岛 {l1['islands']} 个",
                      "tool": "matplotlib", "reproducible": True})
        manifest = {
            "generated_at": ts,
            "generator": {"tool": "matplotlib", "version": matplotlib.__version__,
                          "script": SCRIPT, "encoding": "utf-8", "font": "Microsoft YaHei",
                          "h3": h3.__version__, "reproducible": True},
            "dataset": ds,
            "license": (((project.config("schema") or {}).get("per_dataset") or {}).get(ds) or {}).get("license"),
            "figures": figs,
        }
        (out_root / ds).mkdir(parents=True, exist_ok=True)
        (out_root / ds / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        project.log(f"[{STAGE}] {ds}: {len(figs)} 张图 → {fig_dir}")
        rows.append({"dataset": ds, "points": int(l0["points"]), "cells": int(l0["cells"]),
                     "moran_i": float(l2["moran_i"]), "mean_neighbors": float(l1["mean_neighbors"]),
                     "islands": int(l1["islands"]), "figures": len(figs)})

    # ---- 全局跨数据集对比 ----
    gdir = out_root / "figures"
    gfig = fig_global_compare(plt, rows, gdir)
    gfig.update({"source": "05_map/output/<dataset>/ladder_report.json",
                 "n": int(sum(r["cells"] for r in rows)),
                 "scope": "四数据集；H3 R8；Moran's I 为行标准化 W 下的全局值",
                 "tool": "matplotlib", "reproducible": True})
    (out_root / "manifest.json").write_text(json.dumps({
        "generated_at": ts,
        "generator": {"tool": "matplotlib", "version": matplotlib.__version__, "script": SCRIPT,
                      "encoding": "utf-8", "font": "Microsoft YaHei", "reproducible": True},
        "scope": "跨数据集对比（导论章）",
        "figures": [gfig],
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    dk.write_json(out_root, "global_visual_report", {
        "tier": "V", "chapter": "全局可视化（跨数据集对比）",
        "file": gfig["file"], "title": gfig["title"],
        "datasets": [r["dataset"] for r in rows],
        "metrics": {"points": {r["dataset"]: r["points"] for r in rows},
                    "cells": {r["dataset"]: r["cells"] for r in rows},
                    "moran_i": {r["dataset"]: r["moran_i"] for r in rows},
                    "mean_neighbors": {r["dataset"]: r["mean_neighbors"] for r in rows}},
        "generated_at": ts,
    })
    project.log(f"[{STAGE}] 全局对比图 → {gdir / Path(gfig['file']).name}")

    return {
        "stage": STAGE,
        "blocking": False,
        "figures": int(sum(r["figures"] for r in rows) + 1),
        "datasets": len(rows),
    }


def main() -> None:
    import datakit as _dk
    root = Path(__file__).resolve().parent.parent
    print(run(_dk.Project.load(root)))


if __name__ == "__main__":
    main()
