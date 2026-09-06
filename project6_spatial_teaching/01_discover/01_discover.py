# -*- coding: utf-8 -*-
"""01_discover —— ① 采集（多数据集项目）。

逐数据集扫描只读源目录，回答「我手上到底有什么数据」：
总览 / 格式分布 / 目录分布 / 数据集分组 / 组内列结构漂移 / 文件级明细。

产物（规范 §1：多数据集阶段内按 ``<dataset>/`` 分目录，全局产物直接放 ``output/``）：

* ``output/<dataset>/{catalog.yaml, catalog.md, files.csv}``
* ``output/{catalog.yaml, catalog.md, files.csv}`` —— 四数据集总览

许可状态逐数据集标注（来自 ``config/schema.yaml`` 的 ``per_dataset``）：
不满足许可要求的数据不进入教学素材。
"""
from __future__ import annotations

import datetime as _dt
import sys
from pathlib import Path

import pandas as pd

import datakit as dk

STAGE = "01_discover"
OUT = Path(__file__).resolve().parent / "output"
DATASETS = ("fdic", "sz_bike", "snap_brightkite", "snap_gowalla")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def _human_size(n: float) -> str:
    v = float(n or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if v < 1024:
            return f"{v:.1f} {unit}"
        v /= 1024.0
    return f"{v:.1f} PB"


def _mtime(paths) -> list[str]:
    out = []
    for p in paths:
        try:
            out.append(_dt.datetime.fromtimestamp(Path(p).stat().st_mtime)
                       .isoformat(timespec="seconds"))
        except OSError:
            out.append("")
    return out


def _groups(cat: dk.Catalog) -> list[dict]:
    """分组视图：文件数 / 格式 / 体积 / 列数 / 组内列结构漂移。"""
    rows = []
    for name, srcs in sorted(cat.groups.items()):
        col_sets = [tuple(s.columns or []) for s in srcs]
        base = set(col_sets[0]) if col_sets else set()
        added: set[str] = set()
        missing: set[str] = set()
        drift = 0
        for cs in col_sets:
            a, m = set(cs) - base, base - set(cs)
            if a or m:
                drift += 1
                added |= a
                missing |= m
        size = int(sum(s.size or 0 for s in srcs))
        rows.append({
            "group": name,
            "file_count": len(srcs),
            "formats": sorted({s.format for s in srcs}),
            "total_size": size,
            "total_size_human": _human_size(size),
            "column_count": len(base),
            "column_sample": sorted(base)[:15],
            "drift_files": drift,
            "added_columns": sorted(added)[:20],
            "missing_columns": sorted(missing)[:20],
        })
    return rows


def _dist(frame: pd.DataFrame, by: str) -> list[dict]:
    if frame.empty:
        return []
    g = frame.groupby(by).agg(file_count=("name", "size"),
                              total_size=("size", "sum")).reset_index()
    g["total_size"] = g["total_size"].fillna(0).astype("int64")
    g["total_size_human"] = g["total_size"].map(_human_size)
    g["ratio"] = (g["total_size"] / max(int(g["total_size"].sum()), 1)).round(6)
    return g.to_dict("records")


def _report(project, ds: str, cat: dk.Catalog, frame: pd.DataFrame, groups: list[dict]) -> dict:
    per = ((project.config("schema") or {}).get("per_dataset") or {}).get(ds) or {}
    total = int(frame["size"].fillna(0).sum()) if len(frame) else 0
    return {
        "dataset": ds,
        "scan_root": str(cat.root),
        "scanned_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "license": {
            "role": per.get("role"),
            "license": per.get("license"),
            "restriction": per.get("note"),
        },
        "value_semantics": per.get("value_semantics"),
        "overview": {
            "file_count": int(len(frame)),
            "total_size": total,
            "total_size_human": _human_size(total),
            "group_count": len(cat.groups),
            "directory_count": int(frame["parent"].nunique()) if len(frame) else 0,
        },
        "format_distribution": _dist(frame, "format"),
        "directory_distribution": _dist(frame, "parent"),
        "groups": groups,
        "fingerprint_options": {
            "with_md5": bool(project.options.get("with_md5", False)),
            "count_rows": bool(project.options.get("count_rows", False)),
        },
    }


def _markdown(rep: dict) -> str:
    ov = rep["overview"]
    lic = rep["license"]
    lines = [
        f"# ① 采集清单 · {rep['dataset']}",
        "",
        f"> 扫描根：`{rep['scan_root']}`　扫描时间：{rep['scanned_at']}",
        "",
        f"**许可状态**：{lic.get('license') or '—'}（{lic.get('role') or '—'}）"
        + (f"　限制：{lic['restriction']}" if lic.get("restriction") else ""),
        "",
        "## 总览",
        "",
        f"- 文件总数：{ov['file_count']:,}",
        f"- 总体积：{ov['total_size']:,} 字节（{ov['total_size_human']}）",
        f"- 分组数：{ov['group_count']}　目录数：{ov['directory_count']}",
        f"- 度量语义：{rep.get('value_semantics') or '—'}",
        "",
        "## 格式分布",
        "",
        "| 格式 | 文件数 | 体积 | 占比 |",
        "| --- | ---: | ---: | ---: |",
    ]
    for r in rep["format_distribution"]:
        lines.append(f"| {r[list(r)[0]]} | {r['file_count']:,} | {r['total_size_human']} | {r['ratio']:.2%} |")
    lines += ["", "## 目录分布", "", "| 目录 | 文件数 | 体积 | 占比 |", "| --- | ---: | ---: | ---: |"]
    for r in rep["directory_distribution"]:
        lines.append(f"| {r[list(r)[0]]} | {r['file_count']:,} | {r['total_size_human']} | {r['ratio']:.2%} |")
    lines += ["", "## 数据集分组与列结构漂移", "",
              "| 分组 | 文件数 | 格式 | 体积 | 列数 | 漂移文件 |",
              "| --- | ---: | --- | ---: | ---: | ---: |"]
    for g in rep["groups"]:
        lines.append(f"| `{g['group']}` | {g['file_count']:,} | {', '.join(g['formats'])} | "
                     f"{g['total_size_human']} | {g['column_count']} | {g['drift_files']} |")
        if g["added_columns"] or g["missing_columns"]:
            lines.append(f"  - 漂移：新增 {g['added_columns'] or '—'}；缺失 {g['missing_columns'] or '—'}")
    lines += ["", "> 文件级明细见同目录 `files.csv`。", ""]
    return "\n".join(lines)


def run(project) -> dict:
    datasets = project.meta.get("datasets") or list(DATASETS)
    out = project.stage_output(STAGE)
    frames, rows = [], []

    for ds in datasets:
        src = project.source_root / ds
        if not src.exists():
            project.log(f"[{STAGE}] {ds}: 源目录缺失，跳过（{src}）")
            continue
        project.log(f"[{STAGE}] 扫描 {ds} …")
        # SNAP 数据是 .txt.gz：datakit 的 SUPPORTED_FORMATS 不含 txt，此处显式纳入
        formats = set(dk.SUPPORTED_FORMATS) | {"txt"}
        cat = dk.scan(src, formats=formats,
                      with_md5=bool(project.options.get("with_md5", False)),
                      count_rows=bool(project.options.get("count_rows", False)))
        frame = cat.to_frame()
        if frame.empty:
            frame = pd.DataFrame(columns=["path", "name", "format", "parent", "size",
                                          "rows", "cols", "columns", "group", "md5"])
        frame.insert(0, "dataset", ds)
        frame["modified"] = _mtime(frame["path"]) if len(frame) else []
        frame = frame[["dataset", "path", "name", "format", "parent", "size",
                       "rows", "cols", "columns", "group", "md5", "modified"]]
        groups = _groups(cat)
        rep = _report(project, ds, cat, frame, groups)

        d_out = out / ds
        dk.write_yaml(d_out, "catalog", rep)
        dk.write_markdown(d_out, "catalog", _markdown(rep))
        if len(frame):
            frame.assign(columns=frame["columns"].map(lambda c: "|".join(c) if c else "")) \
                 .to_csv(d_out / "files.csv", index=False, encoding="utf-8-sig")

        frames.append(frame)
        rows.append({
            "dataset": ds,
            "file_count": rep["overview"]["file_count"],
            "total_size_human": rep["overview"]["total_size_human"],
            "group_count": rep["overview"]["group_count"],
            "license": rep["license"]["license"],
        })
        project.log(f"[{STAGE}] {ds}: {rep['overview']['file_count']:,} 个文件 / "
                    f"{rep['overview']['total_size_human']}")

    if not frames:
        raise RuntimeError("① 采集：没有任何数据集被扫描到")

    all_files = pd.concat(frames, ignore_index=True)
    all_files.to_csv(out / "files.csv", index=False, encoding="utf-8-sig")
    total_bytes = int(all_files["size"].fillna(0).sum())
    global_rep = {
        "project": project.name,
        "scanned_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "source_root": str(project.source_root),
        "dataset_count": len(rows),
        "file_count": int(len(all_files)),
        "total_size": total_bytes,
        "total_size_human": _human_size(total_bytes),
        "datasets": rows,
    }
    dk.write_yaml(out, "catalog", global_rep)
    md = ["# ① 采集总览（跨数据集）", "",
          f"- 源数据根：`{global_rep['source_root']}`",
          f"- 数据集：{global_rep['dataset_count']}　文件：{global_rep['file_count']:,}"
          f"　体积：{global_rep['total_size_human']}", "",
          "| 数据集 | 文件数 | 体积 | 分组数 | 许可状态 |", "| --- | ---: | ---: | ---: | --- |"]
    for r in rows:
        md.append(f"| {r['dataset']} | {r['file_count']:,} | {r['total_size_human']} | "
                  f"{r['group_count']} | {r['license']} |")
    md += ["", "> 每章开头必须标注许可状态；SNAP 数据不得商用、不再分发原始文件。", ""]
    dk.write_markdown(out, "catalog", "\n".join(md))

    return {
        "stage": STAGE,
        "dataset_count": len(rows),
        "file_count": int(len(all_files)),
        "total_size_human": _human_size(total_bytes),
    }


def main() -> None:
    import datakit as _dk
    root = Path(__file__).resolve().parent.parent
    print(run(_dk.Project.load(root)))


if __name__ == "__main__":
    main()
