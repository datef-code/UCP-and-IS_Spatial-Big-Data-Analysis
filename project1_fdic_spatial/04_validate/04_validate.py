# -*- coding: utf-8 -*-
"""04_validate —— ④ 校验。

入口文件与目录同名（``04_validate.py``），规范见 ``datakit/PROJECT_STRUCTURE.md`` §2-④。

回答「洗得对不对、能不能进下一步」：

* 断言结果（``config/assertions.yaml``，按 P0 阻断 / P1 / P2 分级）；
* 整体与**逐字段前后对比**（② 画像 vs ③ 清洗后）；
* 清洗效果评估、必要字段核验、**分级可操作建议清单**；
* 项目专属校验：前置验证③（BRNUM 跨年重编号）、坐标精度、归因对照覆盖、平行趋势数据侧准备。
"""
from __future__ import annotations

import datetime as _dt
from pathlib import Path

import numpy as np
import pandas as pd

import datakit as dk

STAGE = "04_validate"
TITLE = "④ 校验（断言 + 前后对比 + 建议）"

ROOT = Path(__file__).resolve().parent.parent
OUT = Path(__file__).resolve().parent / "output"

FIRST_YEAR_DEFAULT = 1994

_KIND_TO_CHECK = {
    "not_null": lambda a: {"check": "null_rate_le", "field": a.get("field"), "max": 0.0},
    "non_negative": lambda a: {"check": "no_negative", "field": a.get("field")},
    "geo_lat": lambda a: {"check": "range", "field": a.get("field"), "min": -90, "max": 90},
    "geo_lon": lambda a: {"check": "range", "field": a.get("field"), "min": -180, "max": 180},
}


# --------------------------------------------------------------------------- #
# 断言
# --------------------------------------------------------------------------- #
def build_assertions(cfg: dict) -> tuple[list[dict], dict[str, dict]]:
    """把 ``assertions.yaml`` 编译成 datakit 可执行断言，并保留元信息（严重度/字段）。

    ``kind: custom`` 的断言不在此编译，由 :func:`_custom_checks` 单独处理。
    """
    specs: list[dict] = []
    meta: dict[str, dict] = {}
    for a in cfg.get("assertions") or []:
        kind = a.get("kind")
        if kind == "custom":
            continue
        name = a.get("name", kind)
        if kind == "unique":
            fields = a.get("fields") or [a.get("field")]
            specs.append({"name": name, "check": "no_duplicates", "subset": fields})
            field_txt = ",".join(fields)
        elif kind in _KIND_TO_CHECK:
            spec = _KIND_TO_CHECK[kind](a)
            spec["name"] = name
            specs.append(spec)
            field_txt = a.get("field")
        else:
            continue
        meta[name] = {"severity": a.get("severity", "P2"), "kind": kind, "field": field_txt,
                      "message": a.get("message", "")}
    return specs, meta


def _custom_checks(branch: pd.DataFrame, long: pd.DataFrame, project) -> list[dict]:
    """项目专属校验（规范 §2-④ 的业务口径）。"""
    out = []

    # --- 前置验证③：并购关闭网点的 BRNUM 是否跨年重编号 ---
    acq = branch[branch["acq_year"].notna() & branch["BRNUM_first"].notna()
                 & branch["BRNUM_last"].notna()]
    renumbered = int((acq["BRNUM_first"] != acq["BRNUM_last"]).sum())
    rate = renumbered / max(len(acq), 1)
    out.append({
        "name": "brnum_not_tracking_key", "severity": "P1", "kind": "custom",
        "passed": rate > 0,            # 变化率 > 0 即证实「BRNUM 不可跨年连接」这一结论
        "actual": round(rate, 6), "expected": "> 0（存在重编号 → 必须用 UNINUMBR）",
        "message": f"并购关闭网点 {len(acq):,} 家中 {renumbered:,} 家 BRNUM 跨年变化（{rate:.2%}）"
                   f"→ 追踪主键固化为 UNINUMBR",
    })

    # --- 坐标精度：SIMS_PROJECTION = EXACT 占比 ---
    proj = branch["projection"].dropna()
    exact = float((proj.astype(str).str.upper() == "EXACT").mean()) if len(proj) else 0.0
    out.append({
        "name": "coordinate_exact_ratio", "severity": "P2", "kind": "custom",
        "passed": True, "actual": round(exact, 6), "expected": "—（信息性断言）",
        "message": f"SIMS_PROJECTION=EXACT 占 {exact:.2%}"
                   f"{'→ <100%，<1 km 环有系统性失真，须同时产出合并环敏感性结果' if exact < 1 else ''}",
    })

    # --- 归因对照覆盖：每起关闭事件是否有同 MSABR 存活网点作对照 ---
    alive = branch[branch["event_type"] == "alive_censored"]
    ev = branch[branch["event_type"] == "closed_ma"]
    by_msa = alive.groupby("MSABR")["UNINUMBR"].count()
    cov = float((ev["MSABR"].map(by_msa).fillna(0) > 0).mean()) if len(ev) else 0.0
    out.append({
        "name": "control_coverage", "severity": "P1", "kind": "custom",
        "passed": cov >= 0.5, "actual": round(cov, 6), "expected": ">= 0.50",
        "message": f"关闭事件 {len(ev):,} 起，同城（同 MSABR）对照覆盖 {cov:.2%}",
    })
    return out


def _branch_dim(long: pd.DataFrame, last_year: int) -> pd.DataFrame:
    """网点维度表（每 UNINUMBR 一行）——校验口径需要，⑤ 会再建一份完整版。"""
    g = long.sort_values(["UNINUMBR", "YEAR"]).groupby("UNINUMBR", sort=False)
    first, last = g.first(), g.tail(1).set_index("UNINUMBR")
    branch = pd.DataFrame({
        "CERT": last["CERT"], "BKCLASS": last["BKCLASS"], "MSABR": last["MSABR"],
        "first_year": first["YEAR"], "last_year": last["YEAR"],
        "est_year": first["SIMS_ESTABLISHED_DATE"].dt.year,
        "acq_year": last["SIMS_ACQUIRED_DATE"].dt.year,
        "BRNUM_first": first["BRNUM"], "BRNUM_last": last["BRNUM"],
        "lat": last["SIMS_LATITUDE"], "lng": last["SIMS_LONGITUDE"],
        "projection": last["SIMS_PROJECTION"],
    }).reset_index()
    acquired = branch["acq_year"].notna()
    branch["event_type"] = np.select(
        [acquired, branch["last_year"] >= last_year],
        ["closed_ma", "alive_censored"], default="attrition_missing")
    return branch


def _recommendations(checks: list[dict], report_ctx: dict, project) -> list[dict]:
    """分级可操作建议（规范 §3.4）。"""
    recs = []
    opts = project.options
    drop_warn = float(opts.get("drop_row_warn_ratio", 0.05))
    fill_warn = float(opts.get("fill_warn_ratio", 0.50))

    removed_rate = report_ctx.get("removed_rate", 0.0)
    if removed_rate > drop_warn:
        recs.append({"severity": "P1", "item": "删除行比例过高",
                     "evidence": f"删除 {removed_rate:.2%} > 阈值 {drop_warn:.2%}",
                     "action": "改用填充 / 标记而非删除（本项目仅剔主键缺失，属可接受范围）"})

    for c in checks:
        if c.get("passed"):
            continue
        sev = c.get("severity", "P2")
        if sev == "P0":
            recs.append({"severity": "P0", "item": c["name"],
                         "evidence": f"实际={c.get('actual')} 期望={c.get('expected')}",
                         "action": "阻断：补数据源或降级该字段后再进入 ⑤ 映射"})
        elif sev == "P1":
            recs.append({"severity": "P1", "item": c["name"],
                         "evidence": c.get("message", ""),
                         "action": "复核口径：确认是否需要在 ③ 补一步处理"})
        else:
            recs.append({"severity": "P2", "item": c["name"],
                         "evidence": c.get("message", ""),
                         "action": "记入已知限制；必要时缩尾或分箱"})

    for f in report_ctx.get("required_fields_with_nulls", []):
        recs.append({"severity": "P0", "item": f"required 字段 {f} 清洗后仍缺失",
                     "evidence": report_ctx["required_fields_with_nulls"][f],
                     "action": "补数据源或降级该字段；不要靠填充掩盖"})
    if report_ctx.get("exact_rate", 1.0) < 1.0:
        recs.append({"severity": "P2", "item": "坐标存在插值",
                     "evidence": f"EXACT 占 {report_ctx['exact_rate']:.2%}",
                     "action": "<1 km 环结果只作参考，主表用 5 km 中等环并始终给出合并环敏感性"})
    return recs


def run(project) -> dict:
    """执行断言、前后对比与建议生成。"""
    project.log(f"[{STAGE}] {TITLE}")

    cleaned_pq = ROOT / "03_clean" / "output" / "cleaned.parquet"
    cleaned_csv = ROOT / "03_clean" / "output" / "cleaned.csv"
    if cleaned_pq.exists():
        cleaned = pd.read_parquet(cleaned_pq)
    else:
        cleaned = pd.read_csv(cleaned_csv, low_memory=False)

    # 清洗前的字段画像（② 产出）
    before_fields = pd.read_csv(ROOT / "02_profile" / "output" / "fields.csv")
    schema = dk.load_schema(project.config("schema"))
    level_by_field = {s.name: s.level for s in schema}

    # --- 清洗后画像（全量，用于逐字段前后对比） ---
    prof_after = dk.profile(cleaned, roles=dk.schema_roles(schema),
                            outlier_method=str(project.options.get("outlier_method", "iqr")))
    after_fields = pd.DataFrame([{
        "field": f.name, "dtype": f.dtype, "role": f.role,
        "null_rate": f.null_rate, "null_count": f.null_count,
        "unique": f.unique, **{k: v for k, v in f.stats.items()
                               if k in ("mean", "median", "min", "max", "std", "negative_rate", "zero_rate")},
    } for f in prof_after.fields])

    # --- 逐字段前后对比 ---
    b = before_fields.set_index("field")
    a = after_fields.set_index("field")
    rows = []
    for name in b.index:
        if name not in a.index:
            continue
        bb, aa = b.loc[name], a.loc[name]
        rec = {
            "field": name,
            "level": level_by_field.get(name, "optional"),
            "dtype_before": bb.get("dtype"), "dtype_after": aa.get("dtype"),
            "null_rate_before": round(float(bb["null_rate"]), 6),
            "null_rate_after": round(float(aa["null_rate"]), 6),
            "null_rate_diff": round(float(aa["null_rate"]) - float(bb["null_rate"]), 6),
            "unique_before": int(bb["unique"]), "unique_after": int(aa["unique"]),
            "mean_before": bb.get("mean"), "mean_after": aa.get("mean"),
            "median_before": bb.get("median"), "median_after": aa.get("median"),
        }
        if pd.notna(rec["mean_before"]) and pd.notna(rec["mean_after"]):
            rec["mean_diff"] = float(rec["mean_after"]) - float(rec["mean_before"])
        rows.append(rec)
    before_after = pd.DataFrame(rows)

    # --- 断言 ---
    cfg = project.config("assertions")
    specs, meta_by_name = build_assertions(cfg)
    vr = dk.validate(cleaned, specs)

    # 项目专属断言（需要网点维度，见规范 §2-④ 的业务口径）
    last_year = int(cleaned["YEAR"].max())
    branch = _branch_dim(cleaned, last_year)
    customs = _custom_checks(branch, cleaned, project)

    all_checks = []
    for c in vr.checks:
        m = meta_by_name.get(c.name, {})
        all_checks.append({
            "name": c.name, "severity": m.get("severity", "P2"),
            "kind": m.get("kind", "datakit"), "field": m.get("field"),
            "passed": bool(c.passed), "actual": c.actual, "expected": c.expected,
            "message": c.message or m.get("message", ""),
        })
    all_checks += customs

    # --- 必要字段核验 ---
    required = [s.name for s in schema if s.level == "required"]
    req_null = {}
    for f in required:
        if f in cleaned.columns:
            rate = float(cleaned[f].isna().mean())
            if rate > 0:
                req_null[f] = f"缺失率 {rate:.2%}"

    # --- 平行趋势（数据侧准备） ---
    dep = cleaned.dropna(subset=["DEPSUMBR"]).copy()
    g = dep.sort_values(["UNINUMBR", "YEAR"]).groupby("UNINUMBR", sort=False)
    dep["dep_chg_rate"] = g["DEPSUMBR"].pct_change().replace([np.inf, -np.inf], np.nan)
    # 与 ⑥ 同一口径：clip ±50pp —— 网点级同比存在极端值（新设网点从 0 起步），
    # 不 clip 会让均值被个别观测支配（可达数百个百分点）。
    dep["dep_chg_rate_c"] = dep["dep_chg_rate"].clip(-0.5, 0.5)
    last_map = branch.set_index("UNINUMBR")["last_year"]
    ev_ids = set(branch[branch["event_type"] == "closed_ma"]["UNINUMBR"])
    pre = dep[dep["UNINUMBR"].isin(ev_ids)]
    pre = pre[pre["YEAR"].astype("float64") <= pre["UNINUMBR"].map(last_map).astype("float64") - 1]
    ctl_ids = set(branch[branch["event_type"] == "alive_censored"]["UNINUMBR"])
    ctl = dep[dep["UNINUMBR"].isin(ctl_ids)]
    pt = {
        "clip": "dep_chg_rate clip 到 ±50pp（与 ⑥ 估计同一口径）",
        "treated_pre_growth_mean": float(pre["dep_chg_rate_c"].dropna().mean()) if len(pre) else None,
        "treated_pre_growth_median": float(pre["dep_chg_rate_c"].dropna().median()) if len(pre) else None,
        "control_growth_mean": float(ctl["dep_chg_rate_c"].dropna().mean()),
        "control_growth_median": float(ctl["dep_chg_rate_c"].dropna().median()),
        "note": "数据侧准备：事件前增长 vs 对照增长；正式平行趋势检验在 ⑥ 估计阶段做事件研究",
    }
    if pt["treated_pre_growth_mean"] is not None:
        pt["pre_trend_gap"] = pt["treated_pre_growth_mean"] - pt["control_growth_mean"]

    exact_rate = next((c["actual"] for c in customs if c["name"] == "coordinate_exact_ratio"), 1.0)
    clean_report = _read_yaml(ROOT / "03_clean" / "output" / "clean_report.yaml")
    removed_rate = float(((clean_report.get("shape") or {}).get("removed_rate")) or 0.0)

    ctx = {"removed_rate": removed_rate, "exact_rate": exact_rate,
           "required_fields_with_nulls": req_null}
    recs = _recommendations(all_checks, ctx, project)

    sev_count = {"P0": 0, "P1": 0, "P2": 0}
    failed_by_sev = {"P0": 0, "P1": 0, "P2": 0}
    for c in all_checks:
        sev_count[c["severity"]] = sev_count.get(c["severity"], 0) + 1
        if not c["passed"]:
            failed_by_sev[c["severity"]] = failed_by_sev.get(c["severity"], 0) + 1
    blocking = failed_by_sev["P0"] > 0

    validation = {
        "stage": STAGE,
        "validated_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "summary": {
            "total": len(all_checks), "passed": sum(1 for c in all_checks if c["passed"]),
            "failed": sum(1 for c in all_checks if not c["passed"]),
            "by_severity": sev_count, "failed_by_severity": failed_by_sev,
            "blocking": blocking,
        },
        "checks": all_checks,
        "required_fields": {
            "fields": required,
            "with_nulls": req_null,
            "can_proceed": not req_null,
        },
        "parallel_trend_prep": pt,
        "recommendations": recs,
    }
    prof_before_yaml = _read_yaml(ROOT / "02_profile" / "output" / "profile.yaml")
    comparison = {
        "stage": STAGE,
        "overall": {
            "rows_before": int((clean_report.get("shape") or {}).get("rows_before", 0)),
            "rows_after": int(len(cleaned)),
            "null_cells_before": int(((clean_report.get("missing_cells") or {}).get("before", 0)) or 0),
            "null_cells_after": int(cleaned.isna().sum().sum()),
            "outliers_before": int((((prof_before_yaml.get("outliers") or {}).get("total")) or 0)),
            "outliers_after": int(len(prof_after.outliers)),
        },
        "before_after": before_after.to_dict("records"),
        "cleaning_effect": {
            "removed_rate": removed_rate,
            "filled_cells": ((clean_report.get("missing_cells") or {}).get("filled", 0)) or 0,
            "forbidden_violations": ((clean_report.get("forbidden_check") or {}).get("violated")) or [],
            "assessment": _assess(removed_rate, req_null),
        },
    }

    project.write_stage(STAGE, "validation", validation, markdown=_md_validation(validation))
    project.write_stage(STAGE, "comparison", comparison,
                        tables={"before_after": before_after},
                        markdown=_md_comparison(comparison, before_after))
    project.log(f"    [④] 断言 {validation['summary']['passed']}/{validation['summary']['total']} 通过；"
                f"阻断项={blocking}；建议 {len(recs)} 条")
    return {
        "stage": STAGE,
        "checks": len(all_checks),
        "passed": validation["summary"]["passed"],
        "blocking": blocking,
        "recommendations": len(recs),
        "control_coverage": next((c["actual"] for c in customs if c["name"] == "control_coverage"), None),
    }


def _assess(removed_rate: float, req_null: dict) -> str:
    if req_null:
        return "required 字段仍有缺失 → 不建议直接进入 ⑤"
    if removed_rate > 0.05:
        return "删除比例偏高，建议复核清洗策略"
    return "清洗幅度可控，可进入 ⑤ 映射"


def _read_yaml(path: Path) -> dict:
    import yaml
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _md_validation(v: dict) -> str:
    lines = ["# ④ 校验报告", "", f"- 校验时间：{v['validated_at']}",
             f"- 断言总数：{v['summary']['total']}，通过：{v['summary']['passed']}，失败：{v['summary']['failed']}",
             f"- **是否存在阻断项（P0 失败）：{'是' if v['summary']['blocking'] else '否'}**", "",
             "## 断言结果", "",
             "| 名称 | 严重度 | 结果 | 实际 | 期望 | 说明 |", "| --- | --- | --- | --- | --- | --- |"]
    for c in v["checks"]:
        lines.append(f"| {c['name']} | {c['severity']} | {'PASS' if c['passed'] else 'FAIL'} | "
                     f"{c.get('actual')} | {c.get('expected')} | {c.get('message') or '—'} |")

    rf = v["required_fields"]
    lines += ["", "## 必要字段核验", "",
              f"- required 字段：{', '.join(rf['fields']) or '无'}",
              f"- 清洗后仍有缺失：{rf['with_nulls'] or '无'}",
              f"- 能否进入下一步：**{'能' if rf['can_proceed'] else '不能'}**"]

    pt = v["parallel_trend_prep"]
    lines += ["", "## 平行趋势（数据侧准备）", "",
              f"- 口径：{pt['clip']}",
              f"- 处理组事件前增长：均值 {pt['treated_pre_growth_mean']:.4f} / 中位数 {pt['treated_pre_growth_median']:.4f}",
              f"- 对照组增长：均值 {pt['control_growth_mean']:.4f} / 中位数 {pt['control_growth_median']:.4f}",
              f"- 均值差：{pt.get('pre_trend_gap'):.4f}", "", f"> {pt['note']}"]

    lines += ["", "## 建议清单", ""]
    if v["recommendations"]:
        lines += ["| 严重度 | 事项 | 证据 | 建议动作 |", "| --- | --- | --- | --- |"]
        for r in v["recommendations"]:
            lines.append(f"| {r['severity']} | {r['item']} | {r['evidence']} | {r['action']} |")
    else:
        lines.append("（无建议）")
    lines.append("")
    return "\n".join(lines)


def _md_comparison(c: dict, ba: pd.DataFrame) -> str:
    o = c["overall"]
    lines = ["# ④ 清洗前后对比", "",
             "| 项 | 前 | 后 |", "| --- | --- | --- |",
             f"| 行数 | {o['rows_before']:,} | {o['rows_after']:,} |",
             f"| 空单元格 | {o['null_cells_before']:,} | {o['null_cells_after']:,} |", "",
             "## 逐字段对比", "",
             "| 字段 | 等级 | 缺失率 前→后 | 变化 | 唯一值 前→后 | 均值 前→后 | 类型 前→后 |",
             "| --- | --- | --- | --- | --- | --- | --- |"]
    for _, r in ba.iterrows():
        mean_txt = "—"
        if pd.notna(r.get("mean_before")) and pd.notna(r.get("mean_after")):
            mean_txt = f"{r['mean_before']:.4g} → {r['mean_after']:.4g}"
        lines.append(f"| {r['field']} | {r['level']} | {r['null_rate_before']:.2%} → {r['null_rate_after']:.2%} | "
                     f"{r['null_rate_diff']:+.2%} | {r['unique_before']:,} → {r['unique_after']:,} | "
                     f"{mean_txt} | {r['dtype_before']} → {r['dtype_after']} |")
    lines += ["", "## 清洗效果评估", "", f"- {c['cleaning_effect']['assessment']}",
              f"- 删除行比例：{c['cleaning_effect']['removed_rate']:.2%}",
              f"- 填充单元格：{c['cleaning_effect']['filled_cells']:,}",
              f"- 违反禁止动作：{c['cleaning_effect']['forbidden_violations'] or '无'}", ""]
    return "\n".join(lines)


def main() -> None:
    project = dk.Project.load(ROOT)
    print(run(project))


if __name__ == "__main__":
    main()
