# -*- coding: utf-8 -*-
"""02_profile —— ② 画像。

入口文件与目录同名（``02_profile.py``），规范见 ``datakit/PROJECT_STRUCTURE.md`` §2-②。

回答「字段有哪些、哪些必需、数据质量有多差」：

* 字段清单（含 ``schema.yaml`` 声明的等级）、等级分布；
* 空值分析（按角色解释语义：主键缺失 = 缺陷，事件缺失 = 右删失）；
* 描述性统计、极端值 / 异常值（统计意义）；
* 规则违规（业务意义，由 ``datakit.schema`` 检验人的口径）。

源数据 ``data_raw/fdic`` **只读**；本阶段同时把导入后的长表落盘为过程数据
``output/raw_long.parquet``，供 ③ 清洗复用，避免 1.7 GB 源文件二次全量 IO。
"""
from __future__ import annotations

import datetime as _dt
from pathlib import Path

import numpy as np
import pandas as pd

import datakit as dk

STAGE = "02_profile"
TITLE = "② 画像（字段等级 + 空值 + 异常值 + 规则违规）"

ROOT = Path(__file__).resolve().parent.parent
OUT = Path(__file__).resolve().parent / "output"

# 面板需要的原始列（81 列只读这些；MSABR = 都会区统计区，早年无 CBSA_METRO）
RAW_COLS = [
    "UNINUMBR", "BRNUM", "CERT", "YEAR",
    "SIMS_ESTABLISHED_DATE", "SIMS_ACQUIRED_DATE",
    "DEPSUMBR", "SIMS_LATITUDE", "SIMS_LONGITUDE",
    "BKCLASS", "MSABR", "METROBR", "SIMS_PROJECTION",
]
_DATE_FMT = "%m/%d/%Y %I:%M:%S %p"
OUTLIER_TOP_N = 20            # 每个字段写入 outliers.csv 的明细条数（全量太大，只留 Top-N）


def read_source(project) -> pd.DataFrame:
    """逐年只读核心列（源数据只读），解析日期，纵向拼接为长表。"""
    files = sorted(project.source_root.glob("fdic_sod_*.csv"))
    if not files:
        raise FileNotFoundError(f"源数据目录未找到 fdic_sod_*.csv：{project.source_root}")
    frames = []
    for i, f in enumerate(files, 1):
        df = pd.read_csv(f, usecols=lambda c: c in RAW_COLS, low_memory=False)
        df = df.reindex(columns=RAW_COLS)
        est = pd.to_datetime(df["SIMS_ESTABLISHED_DATE"], format=_DATE_FMT, errors="coerce")
        acq = pd.to_datetime(df["SIMS_ACQUIRED_DATE"], format=_DATE_FMT, errors="coerce")
        frames.append(pd.DataFrame({
            "UNINUMBR": pd.to_numeric(df["UNINUMBR"], errors="coerce"),
            "BRNUM": pd.to_numeric(df["BRNUM"], errors="coerce"),
            "CERT": pd.to_numeric(df["CERT"], errors="coerce"),
            "YEAR": pd.to_numeric(df["YEAR"], errors="coerce").astype("Int64"),
            "SIMS_ESTABLISHED_DATE": est,
            "SIMS_ACQUIRED_DATE": acq,
            "DEPSUMBR": pd.to_numeric(df["DEPSUMBR"], errors="coerce"),
            "SIMS_LATITUDE": pd.to_numeric(df["SIMS_LATITUDE"], errors="coerce"),
            "SIMS_LONGITUDE": pd.to_numeric(df["SIMS_LONGITUDE"], errors="coerce"),
            "BKCLASS": df["BKCLASS"].astype("string"),
            "MSABR": df["MSABR"].astype("string"),
            "METROBR": pd.to_numeric(df["METROBR"], errors="coerce"),
            "SIMS_PROJECTION": df["SIMS_PROJECTION"].astype("string"),
        }))
        if i % 8 == 0 or i == len(files):
            project.log(f"    [②] 已读 {i}/{len(files)} 个年份文件")
    return pd.concat(frames, ignore_index=True)


def run(project) -> dict:
    """读源数据 → 画像 → 违规检查，产出 profile 报告与过程数据。"""
    project.log(f"[{STAGE}] {TITLE}")
    schema = dk.load_schema(project.config("schema"))
    opts = project.options
    method = str(opts.get("outlier_method", "iqr"))

    long = read_source(project)
    year_min = int(long["YEAR"].min())
    year_max = int(long["YEAR"].max())
    project.log(f"    [②] 长表 {len(long):,} 行 × {long.shape[1]} 列（{year_min}–{year_max}）")

    # 过程数据：供 ③ 清洗复用（本机内存内传递更稳，落盘便于单阶段重跑）
    long.to_parquet(OUT / "raw_long.parquet", index=False)

    roles = dk.schema_roles(schema)
    prof = dk.profile(long, roles=roles, outlier_method=method)

    # --- 字段清单（补 schema 的等级 / 说明 / 规则数） ---
    spec_by_name = {s.name: s for s in schema}
    fields = pd.DataFrame([{
        "field": f.name,
        "dtype": f.dtype,
        "role": f.role,
        "level": spec_by_name.get(f.name).level if f.name in spec_by_name else "optional",
        "registered": f.name in spec_by_name,
        "non_null": f.non_null,
        "null_count": f.null_count,
        "null_rate": round(f.null_rate, 6),
        "unique": f.unique,
        **{k: v for k, v in f.stats.items() if k not in ("quantiles", "top")},
    } for f in prof.fields])
    level_dist = fields["level"].value_counts().to_dict()

    # --- 空值分析（按角色解释语义） ---
    nulls = prof.nulls.copy()
    nulls["null_rate"] = nulls["null_rate"].round(6)

    # --- 异常值：逐字段汇总 + Top-N 明细（全量明细太大，不落盘） ---
    if len(prof.outliers):
        out_sum = (prof.outliers.groupby("field")
                   .agg(outliers=("value", "size"),
                        lower_bound=("lower_bound", "first"),
                        upper_bound=("upper_bound", "first"))
                   .reset_index())
        out_sum["outlier_rate"] = (out_sum["outliers"] / len(long)).round(6)
        out_top = prof.outliers.groupby("field").head(OUTLIER_TOP_N)
    else:
        out_sum = pd.DataFrame(columns=["field", "outliers", "lower_bound", "upper_bound", "outlier_rate"])
        out_top = pd.DataFrame(columns=["field", "index", "value", "method", "lower_bound", "upper_bound"])

    # --- 规则违规（业务口径）---
    viol = dk.violations(long, schema)
    missing = dk.missing_fields(long, schema)
    unregistered = dk.unregistered_fields(long, schema)

    report = {
        "stage": STAGE,
        "profiled_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "source": {
            "root": str(project.source_root),
            "group": project.group,
            "rows": int(len(long)),
            "columns": list(long.columns),
            "year_range": [year_min, year_max],
        },
        "summary": prof.summary,
        "level_distribution": level_dist,
        "fields": fields.to_dict("records"),
        "nulls": nulls.to_dict("records"),
        "outliers": {
            "method": method,
            "total": int(len(prof.outliers)),
            "by_field": out_sum.to_dict("records"),
            "top_examples": out_top.to_dict("records"),
        },
        "violations": viol.to_dict("records"),
        "schema_check": {
            "declared_but_missing_in_data": missing,
            "in_data_but_unregistered": unregistered,
            "note": "规格声明但数据里没有 → 拼写错误/数据源变更；数据里有但未登记 → 默认按 optional 处理",
        },
    }
    project.write_stage(
        STAGE, "profile", report,
        tables={"fields": fields, "nulls": nulls, "outliers": out_sum, "violations": viol},
        markdown=_to_markdown(report, prof, fields, nulls, out_sum, viol),
    )
    project.log(f"    [②] 字段 {len(fields)}（等级分布 {level_dist}）；"
                f"异常值 {len(prof.outliers):,}；规则违规 {int(viol['violations'].sum()) if len(viol) else 0:,}")
    return {
        "stage": STAGE,
        "rows": int(len(long)),
        "columns": int(long.shape[1]),
        "year_range": f"{year_min}-{year_max}",
        "level_distribution": level_dist,
        "outliers": int(len(prof.outliers)),
        "violation_kinds": int(len(viol)),
    }


def _to_markdown(report, prof, fields, nulls, out_sum, viol) -> str:
    """人读画像报告（规范 §2-② 的报告块）。"""
    s = report["summary"]
    lines = [
        f"# ② 画像报告 · {Path(report['source']['root']).name}",
        "",
        f"- 源：`{report['source']['root']}`（只读）",
        f"- 行数列数：**{s['rows']:,} 行 × {s['columns']} 列**；年份 {report['source']['year_range'][0]}–{report['source']['year_range'][1]}",
        f"- 空单元格：{s['null_cells']:,}（整体缺失率 {s['null_rate']:.2%}）",
        f"- 异常值（{report['outliers']['method']}）：{report['outliers']['total']:,} 条",
        "",
        "## 等级分布",
        "",
        "| 等级 | 字段数 |",
        "| --- | --- |",
    ]
    for k, v in report["level_distribution"].items():
        lines.append(f"| {k} | {v} |")

    lines += ["", "## 字段清单（角色 / 等级 / 缺失 / 唯一值）", "",
              "| 字段 | 类型 | 角色 | 等级 | 非空 | 缺失率 | 唯一值 | 说明 |",
              "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    desc = {f["name"]: f.get("description", "") for f in []}
    for _, r in fields.iterrows():
        lines.append(f"| {r['field']} | {r['dtype']} | {r['role']} | {r['level']} | "
                     f"{r['non_null']:,} | {r['null_rate']:.2%} | {r['unique']:,} | "
                     f"{'未登记' if not r['registered'] else ''} |")

    lines += ["", "## 空值分析（按角色解释）", "",
              "| 字段 | 缺失数 | 缺失率 | 角色 | 语义 |", "| --- | --- | --- | --- | --- |"]
    for _, r in nulls.iterrows():
        lines.append(f"| {r['field']} | {r['null_count']:,} | {r['null_rate']:.2%} | {r['role']} | {r['semantic']} |")

    lines += ["", "## 极端值 / 异常值（统计意义）", "",
              f"- 检测方法：`{report['outliers']['method']}`",
              "", "| 字段 | 异常数 | 占比 | 下界 | 上界 |", "| --- | --- | --- | --- | --- |"]
    for _, r in out_sum.iterrows():
        lines.append(f"| {r['field']} | {int(r['outliers']):,} | {r['outlier_rate']:.2%} | "
                     f"{r['lower_bound']:.4g} | {r['upper_bound']:.4g} |")

    lines += ["", "## 规则违规（业务意义）", ""]
    if len(viol):
        lines += ["| 字段 | 等级 | 严重度 | 规则 | 违规数 | 占比 | 样本 |",
                  "| --- | --- | --- | --- | --- | --- | --- |"]
        for _, r in viol.iterrows():
            lines.append(f"| {r['field']} | {r['level']} | {r['severity']} | {r['rule']} | "
                         f"{int(r['violations']):,} | {r['rate']:.2%} | {', '.join(map(str, r['samples'][:3]))} |")
    else:
        lines.append("（无业务规则违规）")

    chk = report["schema_check"]
    if chk["declared_but_missing_in_data"] or chk["in_data_but_unregistered"]:
        lines += ["", "## 口径与数据的一致性", "",
                  f"- 规格声明但数据里缺失：{chk['declared_but_missing_in_data'] or '无'}",
                  f"- 数据里有但未登记：{chk['in_data_but_unregistered'] or '无'}"]
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    project = dk.Project.load(ROOT)
    print(run(project))


if __name__ == "__main__":
    main()
