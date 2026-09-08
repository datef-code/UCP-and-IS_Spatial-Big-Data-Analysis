# -*- coding: utf-8 -*-
"""02_profile —— ② 画像（多数据集项目）。

回答「字段有哪些、哪些必需、数据质量有多差」：字段等级（来自 ``config/schema.yaml``）、
空值语义、描述性统计、极端值（IQR/z-score/MAD）、**规则违规**（业务意义上不合法的值）。

产物（``output/<dataset>/``）：

* ``profile.yaml`` / ``profile.md`` —— 机读 + 人读报告
* ``fields.csv`` —— 字段清单（含等级）
* ``nulls.csv`` —— 空值表（按角色解释语义）
* ``outliers.csv`` —— 极端值明细（统计意义；大表抽样截断，总数见 yaml）
* ``violations.csv`` —— 规则违规表（业务意义）

源数据只用 ``02_profile/loaders.py`` 读一次，**不落盘过程数据**：
阶段 3 按规范数据流向自己从 ``data_raw/`` 重读（同一份加载口径）。
"""
from __future__ import annotations

import datetime as _dt
import sys
from pathlib import Path

import pandas as pd

import datakit as dk

sys.path.insert(0, str(Path(__file__).resolve().parent))       # 同目录辅助模块
from loaders import DATASETS, VALUE_SEMANTICS, load_points     # noqa: E402

STAGE = "02_profile"
OUTLIER_ROW_CAP = 20_000          # 明细表截断条数（总数仍记入 profile.yaml）


def _level_map(project) -> dict:
    specs = dk.load_schema(project.config("schema"))
    return {s.name: s.level for s in specs}


def _desc_map(project) -> dict:
    specs = dk.load_schema(project.config("schema"))
    return {s.name: s.description for s in specs}


def _reason_map(project) -> dict:
    """角色 / 等级的判定依据（规范 §3.5）——写进 fields.csv 的 level_reason 列。"""
    specs = dk.load_schema(project.config("schema"))
    return {s.name: (s.note or s.description) for s in specs}


def _run_one(project, ds: str, specs) -> dict:
    roles = dk.schema_roles(specs)
    method = str(project.options.get("outlier_method", "iqr"))
    pts, fp = load_points(project, ds, log=project.log)

    prof = dk.profile(pts, roles=roles, outlier_method=method)
    viol = dk.violations(pts, specs)
    levels, descs = _level_map(project), _desc_map(project)
    reasons = _reason_map(project)

    # 规范 §2-② 要求「问题数」；§3.5 要求逐字段写清角色 / 等级判定依据
    out_by_field = (prof.outliers["field"].value_counts().to_dict()
                    if len(prof.outliers) else {})
    viol_by_field = (viol.groupby("field")["violations"].sum().to_dict()
                     if len(viol) else {})

    def _n_issues(name: str, null_count: int) -> int:
        n = 0
        n += 1 if null_count and null_count > 0 else 0
        n += 1 if out_by_field.get(name, 0) > 0 else 0
        n += 1 if viol_by_field.get(name, 0) > 0 else 0
        return n

    out_dir = project.stage_output(STAGE) / ds
    out_dir.mkdir(parents=True, exist_ok=True)
    fields_df = pd.DataFrame([{
        **f.to_dict(),
        "level": levels.get(f.name, "optional"),
        "description": descs.get(f.name, ""),
        "level_reason": reasons.get(f.name, "字段未登记：默认按 optional 处理，需人工确认等级"),
        "n_issues": _n_issues(f.name, f.null_count),
    } for f in prof.fields])
    dk.write_csv(out_dir, "fields", fields_df)
    dk.write_csv(out_dir, "nulls", prof.nulls)

    outliers = prof.outliers
    dk.write_csv(out_dir, "outliers", outliers.head(OUTLIER_ROW_CAP) if len(outliers) else outliers)
    dk.write_csv(out_dir, "violations", viol)

    by_field = (outliers["field"].value_counts().to_dict() if len(outliers) else {})
    missing = dk.missing_fields(pts, specs)
    unregistered = dk.unregistered_fields(pts, specs)
    per = ((project.config("schema") or {}).get("per_dataset") or {}).get(ds) or {}

    report = {
        "dataset": ds,
        "profiled_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "license": {"role": per.get("role"), "license": per.get("license"),
                    "restriction": per.get("note")},
        "value_semantics": VALUE_SEMANTICS.get(ds),
        "fingerprint": fp,
        "summary": prof.summary,
        "outlier_method": method,
        "outliers_by_field": {k: int(v) for k, v in by_field.items()},
        "outlier_row_cap": OUTLIER_ROW_CAP,
        "fields": [{k: v for k, v in row.items() if k != "quantiles"}
                   for row in fields_df.to_dict("records")],
        "nulls": [] if prof.nulls.empty else prof.nulls.to_dict("records"),
        "level_distribution": {
            lv: int((fields_df["level"] == lv).sum()) for lv in ("required", "important", "optional", "ignore")
        },
        "violation_count": int(len(viol)),
        "violations": [] if viol.empty else viol.to_dict("records"),
        "missing_fields": missing,          # 规格声明了但数据里没有
        "unregistered_fields": unregistered,  # 数据里有但规格未登记
    }
    dk.write_yaml(out_dir, "profile", report)
    dk.write_markdown(out_dir, "profile", _markdown(report, fields_df, viol, outliers))

    project.log(f"[{STAGE}] {ds}: {prof.summary['rows']:,} 行 / {prof.summary['columns']} 列；"
                f"空单元格 {prof.summary['null_cells']:,}（{prof.summary['null_rate']:.2%}）；"
                f"极端值 {prof.summary['outlier_count']:,}；违规 {len(viol)}")
    return {
        "dataset": ds,
        "rows": int(prof.summary["rows"]),
        "null_rate": round(float(prof.summary["null_rate"]), 6),
        "outliers": int(prof.summary["outlier_count"]),
        "violations": int(len(viol)),
    }


def _markdown(rep: dict, fields: pd.DataFrame, viol: pd.DataFrame, outliers: pd.DataFrame) -> str:
    s = rep["summary"]
    lines = [
        f"# ② 画像报告 · {rep['dataset']}",
        "",
        f"> 生成时间：{rep['profiled_at']}　异常值方法：`{rep['outlier_method']}`",
        "",
        f"**许可状态**：{rep['license'].get('license') or '—'}"
        + (f"　限制：{rep['license'].get('restriction')}" if rep['license'].get('restriction') else ""),
        f"　**度量语义**：{rep.get('value_semantics') or '—'}",
        "",
        "## 概要",
        "",
        f"- 行数 {s['rows']:,}　列数 {s['columns']}　空单元格 {s['null_cells']:,}（{s['null_rate']:.2%}）",
        f"- 极端值 {s['outlier_count']:,}　规则违规 {rep['violation_count']}",
        f"- 等级分布：" + " / ".join(f"{k} {v}" for k, v in rep["level_distribution"].items() if v),
        "",
        "## 字段清单（含等级 / 问题数）",
        "",
        "| 字段 | 类型 | 角色 | 等级 | 非空 | 缺失率 | 唯一值 | 问题数 | 说明 |",
        "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for _, r in fields.iterrows():
        lines.append(f"| {r['name']} | {r['dtype']} | {r['role']} | {r['level']} | "
                     f"{int(r['non_null']):,} | {r['null_rate']:.2%} | {int(r['unique']):,} | "
                     f"{int(r['n_issues'])} | {r['description']} |")

    # 规范 §3.5：角色 / 等级的判定依据必须逐字段写明，不能只贴枚举
    lines += ["", "## 字段角色 / 等级判定依据（规范 §3.5）", "",
              "| 字段 | 角色 / 等级 | 说明 | 判定依据 |",
              "| --- | --- | --- | --- |"]
    for _, r in fields.iterrows():
        reason = str(r.get("level_reason", "") or "").replace("\n", " ").replace("|", "/")
        desc = str(r.get("description", "") or "").replace("|", "/")
        lines.append(f"| `{r['name']}` | {r['role']} / {r['level']} | {desc} | {reason} |")
    lines += ["", "## 空值语义（按角色）", "",
              "| 字段 | 空值数 | 缺失率 | 角色 | 语义 |", "| --- | ---: | ---: | --- | --- |"]
    nulls = pd.DataFrame(rep.get("nulls", []))
    lines += ["", "## 极端值（统计意义）", ""]
    if len(outliers):
        lines += ["| 字段 | 异常数 |", "| --- | ---: |"]
        for k, v in rep["outliers_by_field"].items():
            lines.append(f"| {k} | {v:,} |")
        lines.append(f"\n> 明细见 `outliers.csv`（截断 {rep['outlier_row_cap']:,} 条）。")
    else:
        lines.append("（无）")
    lines += ["", "## 规则违规（业务意义）", ""]
    if len(viol):
        lines += ["| 字段 | 等级 | 严重度 | 规则 | 违规数 | 占比 | 样本 |",
                  "| --- | --- | --- | --- | ---: | ---: | --- |"]
        for _, r in viol.iterrows():
            lines.append(f"| {r['field']} | {r['level']} | {r['severity']} | {r['rule']} | "
                         f"{int(r['violations']):,} | {r['rate']:.4%} | {r['samples']} |")
    else:
        lines.append("（无）")
    if rep["missing_fields"]:
        lines += ["", f"> ⚠️ 规格声明但数据中缺失的字段：{rep['missing_fields']}"]
    if rep["unregistered_fields"]:
        lines += ["", f"> ⚠️ 数据中存在但规格未登记的字段（按 optional 处理）：{rep['unregistered_fields']}"]
    lines.append("")
    return "\n".join(lines)


def run(project) -> dict:
    datasets = project.meta.get("datasets") or list(DATASETS)
    specs = dk.load_schema(project.config("schema"))
    summaries = [_run_one(project, ds, specs) for ds in datasets]
    total_rows = int(sum(s["rows"] for s in summaries))
    return {
        "stage": STAGE,
        "datasets": {s["dataset"]: s["rows"] for s in summaries},
        "rows": total_rows,
        "violations": int(sum(s["violations"] for s in summaries)),
    }


def main() -> None:
    import datakit as _dk
    root = Path(__file__).resolve().parent.parent
    print(run(_dk.Project.load(root)))


if __name__ == "__main__":
    main()
