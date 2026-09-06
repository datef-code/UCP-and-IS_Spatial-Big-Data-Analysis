# -*- coding: utf-8 -*-
"""07_conclude —— ⑦ 结论（扩展阶段，规范 §8.5「结论」）。

结论必须带约束：写清**已知限制 / 止损条件**，以及每个数据集的许可状态。
所有数字来自本流水线实际产出（``05_map`` 的 ladder_report.json、``06_visualize`` 的
global_visual_report.json、``04_validate`` 的 version_lock.json），不写没跑过的内容。

产物：``output/conclusion.md`` + ``output/conclusion_report.json``。
"""
from __future__ import annotations

import datetime as _dt
import json
import sys
from pathlib import Path

import datakit as dk

STAGE = "07_conclude"
DATASETS = ("fdic", "sz_bike", "snap_brightkite", "snap_gowalla")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def run(project) -> dict:
    datasets = project.meta.get("datasets") or list(DATASETS)
    schema = project.config("schema") or {}
    per = schema.get("per_dataset") or {}

    rows, locks = [], {}
    for ds in datasets:
        ladder = _read(project.stage_path("05_map", ds, "ladder_report.json"))
        if not ladder:
            project.log(f"[{STAGE}] {ds}: 缺少 05_map 产物，跳过")
            continue
        t = ladder["tiers"]
        l3 = t["L3"]
        ring = l3.get("mean_spill_density_by_ring") or l3.get("mean_spill_by_ring") or {}
        rows.append({
            "dataset": ds,
            "license": (per.get(ds) or {}).get("license"),
            "role": (per.get(ds) or {}).get("role"),
            "value_semantics": (per.get(ds) or {}).get("value_semantics"),
            "points": int(t["L0"]["points"]),
            "cells": int(t["L0"]["cells"]),
            "mean_neighbors": round(float(t["L1"]["mean_neighbors"]), 2),
            "islands": int(t["L1"]["islands"]),
            "moran_i": round(float(t["L2"]["moran_i"]), 4),
            "lag_corr": round(float(t["L2"]["lag_corr"]), 4),
            "ring_metric": "溢出密度（环内格均摊）" if l3.get("mean_spill_density_by_ring") else "溢出求和",
            "ring_means": {k: round(float(v), 2) for k, v in ring.items()},
        })
        locks[ds] = _read(project.stage_path("04_validate", ds, "version_lock.json"))

    if not rows:
        raise RuntimeError("⑦ 结论：没有任何数据集产物可用（请先跑 01→05）")

    global_vis = _read(project.stage_path("06_visualize", "global_visual_report.json"))
    strongest = max(rows, key=lambda r: r["moran_i"])
    weakest = min(rows, key=lambda r: r["moran_i"])
    monotone = {r["dataset"]: list(r["ring_means"].values()) for r in rows}
    decay = {k: bool(all(b <= a + 1e-9 for a, b in zip(v, v[1:]))) for k, v in monotone.items()}

    conclusion = {
        "tier": "C",
        "chapter": "结论",
        "generated_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "positioning": {
            "role": "放大器",
            "not_role": "主菜",
            "purpose": "让 ③ 清洗、④ 校验（版本冻结）与 ⑤ 映射（L0→L3 空间结构化）的结果更易被理解、传播与教学",
            "metric": "不以阅读量/付费转化为核心指标，而以「读者能否按章节顺序复现 L0→L3」为质量判据",
        },
        "prerequisites": {
            "must_have": ["④ 校验：所有代码块随数据集版本冻结，git clone 后可复现",
                          "⑤ 映射：h3·libpysal 教学主线已实际跑通（L0→L3）"],
            "note": "⑤ 不适用：本方案不引入任何新算法、不做新建模，全部复用 ③④⑤ 已验证的产出",
            "kill_switch": "若 ③④⑤ 未做，本方向退化为官方文档翻译——那时应直接砍掉",
        },
        "datasets": rows,
        "findings": {
            "strongest": {"dataset": strongest["dataset"], "moran_i": strongest["moran_i"],
                          "why": "同城密集点位，邻接格彼此可观测"},
            "weakest": {"dataset": weakest["dataset"], "moran_i": weakest["moran_i"],
                        "why": "点位稀疏/全球分散，H3 R8 近邻格常为空，权重矩阵定义对结论敏感"},
            "distance_decay": decay,
            "lesson": "空间权重矩阵的定义（分辨率、邻接阶数、是否行标准化）直接改变结论："
                      "同一个数据集换一种 W，Moran's I 会变——这是本教程的核心观点，而非缺陷。",
        },
        "known_limits": [
            "成本参数为合成参数（h3_res=8、hot_top_n=100、距离环 0–1/1–3/3–5/5–10 km、抽样日=每月 15 日），非真实业务口径",
            "sz_bike 全量 30 GB 未全量载入，结论仅对抽样日成立；源标注数据源已停更（最后数据 2021-08）",
            "SNAP 两个数据集仅限研究用途、不允许商用、不再分发原始文件；数据年代 2010–2013",
            "L3 距离环溢出取 Top-N 热点为圆心，圆心选择影响环内溢出量级",
            "孤岛格（无邻居）不参与空间滞后，占比见各数据集 L1.islands",
        ],
        "reproducibility": {
            "version_locks": {k: {"frozen_at": v.get("frozen_at"),
                                  "library_versions": v.get("library_versions"),
                                  "cost_params": v.get("cost_params"),
                                  "rows": v.get("rows")} for k, v in locks.items()},
            "replay": "python main.py（阶段 01→07 顺序执行；单阶段 python main.py --stage 05）",
        },
        "deliverables": {
            "open_ebook": {"platform": "GitHub Pages / Jupyter Book / Quarto",
                           "content": "L0→L3 四阶认知阶梯，每章对应一个数据集的实际产出"},
            "zhihu_column": {"platform": "知乎专栏",
                             "content": "逐章图文，强调许可状态、合成参数标注与可复现性"},
            "bilibili": {"platform": "B站视频课",
                         "content": "配合代码仓库，演示从 H3 网格化到距离环溢出的完整流程"},
        },
        "global_figure": global_vis.get("file"),
    }
    out_dir = project.stage_output(STAGE)
    dk.write_json(out_dir, "conclusion_report", conclusion)

    table = ["| 数据集 | 角色 | 许可 | 点数 | L0 格数 | L1 平均邻居 | L2 Moran's I | L3 距离衰减 |",
             "| --- | --- | --- | ---: | ---: | ---: | ---: | --- |"]
    for r in rows:
        table.append(f"| `{r['dataset']}` | {r['role'] or '—'} | {r['license'] or '—'} | "
                     f"{r['points']:,} | {r['cells']:,} | {r['mean_neighbors']} | {r['moran_i']} | "
                     f"{'是' if decay.get(r['dataset']) else '否'} |")

    md = f"""# ⑦ 结论 · 项目6 空间结构化教学管线

> 自动生成于 {conclusion['generated_at']}；数字全部来自本流水线实际产出（05_map / 06_visualize / 04_validate）。

## 定位：放大器，不是主菜

本方向的定位是 **放大器**：让 ③ 清洗、④ 校验（版本冻结、可复现）与 ⑤ 映射
（H3·libpysal 空间结构化）的产出更容易被理解、传播与教学。它不回答新的研究问题，
也不承诺阅读量与付费转化。

- **必须先完成**：④ 校验 + ⑤ 映射（L0→L3 跑通）。
- **⑤ 不适用**：不引入任何新算法、不做新建模，全部复用上游已验证产出。
- **止损条件**：若 ④⑤ 未做，本方向退化为官方文档翻译——那时应直接砍掉。

## 实测结果（L0→L3）

{chr(10).join(table)}

## 核心结论

1. **{strongest['dataset']} 空间聚集最强**（Moran's I = {strongest['moran_i']}），
   **{weakest['dataset']} 最弱**（Moran's I = {weakest['moran_i']}）：点位越密集、同城尺度越小，
   邻接格越可观测，自相关越强。
2. **{weakest['dataset']} 偏低不是 bug，是教材**：全球稀疏签到在 R8（≈0.46 km）下近邻格常为空，
   换一种权重矩阵定义结论就会变——这正是「空间权重矩阵定义对结论敏感」的活教材。
3. **距离衰减（溢出密度口径：环内求和 ÷ 环内格数）**：
   {"、".join(f"{k} {'呈' if v else '未呈'}单调衰减" for k, v in decay.items())}。

## 已知限制（结论必须带约束）

{chr(10).join('- ' + x for x in conclusion['known_limits'])}

## 可复现性

- 每个数据集的 `04_validate/output/<dataset>/version_lock.json` 冻结了源数据指纹、行数、
  库版本与成本参数；版本漂移须重新出图。
- 重跑：`python main.py`（单阶段 `python main.py --stage 05`）。

## 传播形态

| 形态 | 平台 | 内容要点 |
| --- | --- | --- |
| 开源电子书 | GitHub Pages / Jupyter Book / Quarto | L0→L3 四阶阶梯，每章一个数据集 |
| 知乎专栏 | 知乎 | 逐章图文，标注许可状态与合成参数 |
| 视频课 | Bilibili | 配合代码仓库演示完整管线 |

## 核心判据

> 读者 `git clone` 后，能否按章节顺序完整复现 L0→L3 的教学主线？

能复现，教程才有价值；跑不通的教程比没有教程更伤。
"""
    dk.write_markdown(out_dir, "conclusion", md)
    project.log(f"[{STAGE}] 结论已写入 {out_dir}")

    return {
        "stage": STAGE,
        "blocking": False,
        "datasets": len(rows),
        "conclusion": (f"{strongest['dataset']} 空间聚集最强（Moran's I={strongest['moran_i']}），"
                       f"{weakest['dataset']} 最弱（{weakest['moran_i']}）——"
                       f"空间权重矩阵定义对结论敏感"),
    }


def main() -> None:
    import datakit as _dk
    root = Path(__file__).resolve().parent.parent
    print(run(_dk.Project.load(root)))


if __name__ == "__main__":
    main()
