# -*- coding: utf-8 -*-
"""project2_fdic_survival —— 根编排入口（规范 ``datakit/PROJECT_STRUCTURE.md`` §4）。

按顺序执行：内置五阶段 ``01_discover`` … ``05_map``，再执行 ``datakit.yaml``
里登记的扩展阶段 ``06_train`` / ``07_visualize`` / ``08_conclude``。

阶段目录名带数字前缀（不是合法模块名），因此一律用 ``importlib`` 按文件路径加载
（``dk.Project.load_stage`` 已封装）。扩展阶段默认 ``blocking: false``，失败降级为
告警并写入 ``SUMMARY.md``。

用法::

    python main.py                 # 全流水线
    python main.py --stage 03      # 只跑 03_clean
    python main.py --stage 06      # 只跑扩展阶段 06_train
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import datakit as dk

ROOT = Path(__file__).resolve().parent


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="project2_fdic_survival 流水线")
    ap.add_argument("--stage", default=None,
                    help="只跑指定阶段：01|02|03|04|05|06|07|08，缺省跑全流程")
    ap.add_argument("--list", action="store_true", help="列出所有阶段后退出")
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    project = dk.Project.load(ROOT)

    if args.list:
        for s in project.stage_names:
            print(s)
        return 0

    stages = None
    if args.stage:
        prefix = args.stage if args.stage.startswith("0") else f"0{args.stage}"
        stages = [s for s in project.stage_names if s.startswith(prefix)]
        if not stages:
            print(f"未匹配到阶段：{args.stage}（可用：{', '.join(project.stage_names)}）")
            return 2

    summaries = project.run(stages)
    failed = [s for s in summaries if not s.get("ok", True)]
    if failed:
        print(f"⚠️  {len(failed)} 个阶段失败/降级："
              f"{', '.join(str(s.get('stage')) for s in failed)}")
    print(f"SUMMARY → {ROOT / 'SUMMARY.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
