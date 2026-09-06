# -*- coding: utf-8 -*-
"""项目6 空间结构化教学管线 —— 根编排（规范 §4.3）。

内置五阶段（01→05）+ 扩展阶段（06_visualize / 07_conclude）由 ``datakit.yaml`` 登记，
本文件只做编排：加载项目 → 按序 ``run(project)`` → 汇总 ``SUMMARY.md`` → 写 ``logs/pipeline.log``。

用法::

    python main.py                       # 全流程
    python main.py --stage 05            # 只跑 ⑤ 映射
    python main.py --stage 02 --datasets fdic,sz_bike   # 指定阶段 + 数据集子集

教学主线：L0 H3 网格化 → L1 空间权重矩阵 → L2 空间滞后 → L3 距离环溢出。
数据集：fdic / sz_bike / snap_brightkite / snap_gowalla（许可状态逐章标注）。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import datakit as dk

ROOT = Path(__file__).resolve().parent

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def main() -> None:
    ap = argparse.ArgumentParser(description="project6_spatial_teaching 五阶段 + 扩展阶段流水线")
    ap.add_argument("--stage", default=None,
                    help="01|02|03|04|05|06|07，缺省跑全流程（含 06/07 扩展阶段）")
    ap.add_argument("--datasets", default=None,
                    help="逗号分隔的数据集子集，缺省跑 datakit.yaml 里的全部数据集")
    args = ap.parse_args()

    project = dk.Project.load(ROOT)
    if args.datasets:
        project.meta["datasets"] = [d.strip() for d in args.datasets.split(",") if d.strip()]

    stages = None
    if args.stage:
        stages = [s for s in project.stage_names if s.startswith(args.stage)]
        if not stages:
            raise SystemExit(f"未匹配到阶段：{args.stage}（可选：{', '.join(project.stage_names)}）")

    project.log(f"数据集：{', '.join(project.meta.get('datasets') or [])}")
    summaries = project.run(stages)
    failed = [s for s in summaries if not s.get("ok", True)]
    if failed:
        project.log(f"存在失败/降级阶段：{[s['stage'] for s in failed]}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
