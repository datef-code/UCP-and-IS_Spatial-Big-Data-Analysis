# -*- coding: utf-8 -*-
"""01_discover —— ① 采集。

入口文件与目录同名（``01_discover.py``），规范见 ``datakit/PROJECT_STRUCTURE.md`` §2-①：
必须暴露 ``run(project) -> dict``，返回本阶段摘要供 ``SUMMARY.md`` 汇总。

回答「我手上到底有什么数据」：扫描 ``data_raw/fdic``（只读），产出
文件级明细、格式/目录分布、数据集分组，以及跨年文件的**列结构漂移**。

算法一律由 datakit 提供（``dk.scan``），本文件只写口径与报告拼装。
"""
from __future__ import annotations

import datetime as _dt
from pathlib import Path

import pandas as pd

import datakit as dk

STAGE = "01_discover"
TITLE = "① 采集（只读扫描 FDIC SOD 年度文件）"

ROOT = Path(__file__).resolve().parent.parent
OUT = Path(__file__).resolve().parent / "output"


def _human(n: float) -> str:
    """字节数 → 人类可读字符串。"""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024 or unit == "TB":
            return f"{n:.2f} {unit}" if unit != "B" else f"{int(n)} B"
        n /= 1024
    return f"{n:.2f} TB"


def _drift(sources: list) -> list[dict]:
    """同组文件的列结构漂移：以第一个文件（最早年份）为基准。"""
    if not sources:
        return []
    base = list(sources[0].columns or [])
    base_set = set(base)
    rows = []
    for s in sources:
        cols = list(s.columns or [])
        added = [c for c in cols if c not in base_set]
        missing = [c for c in base if c not in set(cols)]
        rows.append({
            "file": s.name,
            "cols": len(cols),
            "added_vs_base": added,
            "missing_vs_base": missing,
            "same_as_base": not added and not missing,
        })
    return rows


def run(project) -> dict:
    """扫描源数据目录，产出采集清单与列结构漂移检查。"""
    project.log(f"[{STAGE}] {TITLE}")
    root = project.source_root
    with_md5 = bool(project.options.get("with_md5", False))
    count_rows = bool(project.options.get("count_rows", False))

    catalog = dk.scan(root, with_md5=with_md5, count_rows=count_rows)
    if not catalog.sources:
        raise RuntimeError(f"源数据目录为空：{root}")

    files = catalog.to_frame()
    total_size = int(files["size"].fillna(0).sum()) if len(files) else 0

    # 格式分布 / 目录分布
    fmt = (files.groupby("format")
           .agg(files=("name", "count"), size=("size", "sum"))
           .reset_index())
    fmt["size_human"] = fmt["size"].map(_human)
    fmt["size_pct"] = (fmt["size"] / total_size).round(6) if total_size else 0.0

    dirs = (files.groupby("parent")
            .agg(files=("name", "count"), size=("size", "sum"),
                 formats=("format", lambda s: sorted(set(s))))
            .reset_index())

    groups = {}
    drift_rows = []
    for name, srcs in sorted(catalog.groups.items()):
        gsize = sum(s.size or 0 for s in srcs)
        gcols = sorted({c for s in srcs for c in (s.columns or [])})
        groups[name] = {
            "file_count": len(srcs),
            "formats": sorted({s.format for s in srcs}),
            "total_size": gsize,
            "total_size_human": _human(gsize),
            "total_rows": int(sum(s.rows or 0 for s in srcs)) if count_rows else None,
            "column_count": len(gcols),
            "columns": gcols,
        }
        drift_rows.extend([{"group": name, **r} for r in _drift(srcs)])

    report = {
        "stage": STAGE,
        "scanned_root": str(root),
        "scanned_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "file_count": len(catalog),
        "total_size": total_size,
        "total_size_human": _human(total_size),
        "group_count": len(catalog.groups),
        "format_distribution": fmt.to_dict("records"),
        "directory_distribution": dirs.to_dict("records"),
        "groups": groups,
        "column_drift": {
            "note": "同组文件以第一个（年份最早）文件为基准比较列集合；跨年 SOD 字段会增减",
            "consistent": all(r["same_as_base"] for r in drift_rows) if drift_rows else True,
            "files": drift_rows,
        },
        "options": {"with_md5": with_md5, "count_rows": count_rows},
    }
    project.write_stage(STAGE, "catalog", report,
                        tables={"files": files},
                        markdown=_to_markdown(report, files))
    project.log(f"[{STAGE}] {len(catalog)} 个文件 / {len(catalog.groups)} 个分组 / {_human(total_size)}")
    return {
        "stage": STAGE,
        "file_count": len(catalog),
        "group_count": len(catalog.groups),
        "total_size_human": _human(total_size),
        "columns_consistent": report["column_drift"]["consistent"],
    }


def _to_markdown(report: dict, files: pd.DataFrame) -> str:
    """人读清单（规范 §2-① 的报告块）。"""
    lines = [
        f"# ① 采集报告 · {Path(report['scanned_root']).name}",
        "",
        f"- 扫描根：`{report['scanned_root']}`",
        f"- 扫描时间：{report['scanned_at']}",
        f"- 文件总数：**{report['file_count']}**，总体积：**{report['total_size_human']}**（{report['total_size']:,} 字节）",
        f"- 数据集分组数：{report['group_count']}",
        "",
        "## 格式分布",
        "",
        "| 格式 | 文件数 | 体积 | 占比 |",
        "| --- | --- | --- | --- |",
    ]
    for r in report["format_distribution"]:
        lines.append(f"| {r['format']} | {r['files']} | {r['size_human']} | {r['size_pct']:.2%} |")

    lines += ["", "## 数据集分组", "", "| 分组 | 文件数 | 格式 | 总体积 | 总行数 | 列数 |",
              "| --- | --- | --- | --- | --- | --- |"]
    for name, g in report["groups"].items():
        rows = g["total_rows"]
        lines.append(f"| {name} | {g['file_count']} | {', '.join(g['formats'])} | "
                     f"{g['total_size_human']} | {rows if rows is not None else '—'} | {g['column_count']} |")

    drift = report["column_drift"]
    lines += ["", "## 组内列结构一致性", "",
              f"- 结论：**{'全部一致' if drift['consistent'] else '存在漂移'}**（{drift['note']}）", ""]
    bad = [d for d in drift["files"] if not d["same_as_base"]]
    if bad:
        lines += ["| 文件 | 列数 | 新增列 | 缺失列 |", "| --- | --- | --- | --- |"]
        for d in bad[:20]:
            lines.append(f"| {d['file']} | {d['cols']} | {', '.join(d['added_vs_base']) or '—'} | "
                         f"{', '.join(d['missing_vs_base']) or '—'} |")

    lines += ["", "## 文件级明细（前 40 行）", "",
              "| 文件 | 格式 | 大小 | 列数 | 行数 | 修改时间 |", "| --- | --- | --- | --- | --- | --- |"]
    for _, r in files.head(40).iterrows():
        try:
            mtime = _dt.datetime.fromtimestamp(Path(r["path"]).stat().st_mtime).isoformat(timespec="seconds")
        except OSError:
            mtime = "—"
        lines.append(f"| {r['name']} | {r['format']} | {_human(r['size'] or 0)} | {r['cols']} | "
                     f"{r['rows'] if pd.notna(r['rows']) else '—'} | {mtime} |")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    project = dk.Project.load(ROOT)
    print(run(project))


if __name__ == "__main__":
    main()
