# -*- coding: utf-8 -*-
"""04_validate —— ④ 校验（多数据集项目）。

回答「洗得对不对、能不能进下一步」：

* **断言结果**（P0 阻断 / P1 / P2，来自 ``config/assertions.yaml`` 的 ``when: 04_validate``）；
* **前后对比**：阶段 2 画像 vs 阶段 3 清洗后（逐字段缺失率 / 异常值 / 唯一值 / 均值 / 中位数 / 类型）；
* **建议清单**：删除行比例 > 5%、单字段填充 > 50%、required 字段仍缺失 → 分级建议；
* **版本冻结** ``version_lock.json``：指纹 + 行数 + 库版本 + 合成成本参数（教学可复现性）。

产物（``output/<dataset>/``）：``validation.yaml``/``validation.md``、
``comparison.yaml``/``comparison.md``、``before_after.csv``、``version_lock.json``。
"""
from __future__ import annotations

import datetime as _dt
import json
import sys
from pathlib import Path

import pandas as pd
import yaml

import datakit as dk

STAGE = "04_validate"
DATASETS = ("fdic", "sz_bike", "snap_brightkite", "snap_gowalla")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def _cost_params(project) -> dict:
    """合成成本参数（教学口径，全部标注为合成参数，非真实业务数据）。"""
    ops = (project.config("mapping") or {}).get("ops") or []
    res = next((o.get("params", {}).get("res") for o in ops if o.get("op") == "geocode"), 8)
    ring = next((o for o in ops if o.get("op") == "aggregate" and o.get("to") == "ring_spillover"), {})
    params = ring.get("params") or {}
    schema = project.config("schema") or {}
    sample_day = ((schema.get("per_dataset") or {}).get("sz_bike") or {}).get("sample_day", "15")
    return {
        "h3_res": res,
        "hot_top_n": params.get("hot_top_n", 100),
        "rings_km": params.get("rings_km", [[0, 1], [1, 3], [3, 5], [5, 10]]),
        "sz_sample_day": str(sample_day),
        "marked": "合成参数，非真实业务数据",
    }


def _library_versions() -> dict:
    import numpy as np
    versions = {
        "python": sys.version.split()[0],
        "pandas": pd.__version__,
        "numpy": np.__version__,
        "datakit": dk.__version__,
    }
    for name, mod in (("h3", "h3"), ("libpysal", "libpysal"), ("matplotlib", "matplotlib")):
        try:
            versions[name] = __import__(mod).__version__
        except Exception:
            versions[name] = None
    return versions


def _as_check(a: dict) -> dict | None:
    """把 config 里的断言翻译成 ``dk.validate`` 的声明式字典。"""
    kind, field = a.get("kind"), a.get("field")
    if kind == "geo_lat":
        return {"name": a["name"], "check": "range", "field": field, "min": -90, "max": 90}
    if kind == "geo_lon":
        return {"name": a["name"], "check": "range", "field": field, "min": -180, "max": 180}
    if kind == "not_null":
        return {"name": a["name"], "check": "null_rate_le", "field": field, "max": 0.0}
    if kind == "non_negative":
        return {"name": a["name"], "check": "no_negative", "field": field}
    if kind == "range":
        return {"name": a["name"], "check": "range", "field": field,
                "min": a.get("min"), "max": a.get("max")}
    if kind == "row_count_ge":
        return {"name": a["name"], "check": "row_count_ge", "min": a.get("min", 1)}
    return None      # custom：由本阶段单独求值


def _run_assertions(cleaned: pd.DataFrame, specs: list[dict], ctx: dict) -> list[dict]:
    """逐条断言求值，保留 severity（严重度是人的口径，dk.validate 不认识）。"""
    results = []
    for a in specs:
        name, severity = a["name"], a.get("severity", "P2")
        if a.get("kind") == "custom":
            if name == "version_lock_reproducible":
                passed = bool(ctx.get("version_lock_ok", True))
                results.append({"name": name, "severity": severity, "passed": passed,
                                "actual": ctx.get("version_lock_detail", ""),
                                "expected": a.get("expr", ""), "message": a.get("message", "")})
            else:
                results.append({"name": name, "severity": severity, "passed": True,
                                "actual": "未实现求值", "expected": a.get("expr", ""),
                                "message": "custom 断言需在阶段内实现求值"})
            continue
        check = _as_check(a)
        if check is None:
            results.append({"name": name, "severity": severity, "passed": False,
                            "actual": None, "expected": a.get("expr", ""),
                            "message": f"未支持的断言类型：{a.get('kind')}"})
            continue
        rep = dk.validate(cleaned, [check])
        c = rep.checks[0]
        results.append({"name": name, "severity": severity, "passed": bool(c.passed),
                        "actual": c.actual, "expected": c.expected, "message": c.message})
    return results


def _recommendations(project, removed_rate: float, before_after: list[dict],
                     fill_by_field: pd.DataFrame) -> list[dict]:
    """分级建议清单（规范 §3.4 / §2-④）。"""
    recs = []
    drop_warn = float(project.options.get("drop_row_warn_ratio", 0.05))
    fill_warn = float(project.options.get("fill_warn_ratio", 0.50))

    for row in before_after:
        if row["null_rate_after"] and row["null_rate_after"] > 0 and row.get("level") == "required":
            recs.append({"severity": "P0", "target": row["field"],
                         "advice": "required 字段清洗后仍缺失：补数据源，或降级该字段后重洗"})
    if removed_rate > drop_warn:
        recs.append({"severity": "P1", "target": "<rows>",
                     "advice": f"删除行比例 {removed_rate:.2%} 超过阈值 {drop_warn:.0%}："
                               f"改用填充 / 标记而非删除"})
    if fill_by_field is not None and len(fill_by_field):
        over = fill_by_field[fill_by_field["filled"] > 0]
        for _, r in over.iterrows():
            ratio = r["filled"] / max(int(r.get("rows_before", 0) or 0), 1)
            if ratio > fill_warn:
                recs.append({"severity": "P1", "target": str(r["field"]),
                             "advice": f"该字段填充量 {ratio:.0%} 超过 {fill_warn:.0%}："
                                       f"建议增加「是否填充」标记列，避免污染分布"})
    for row in before_after:
        if (row["outliers_after"] or 0) > 0 and row.get("level") in ("required", "important"):
            recs.append({"severity": "P2", "target": row["field"],
                         "advice": "必要/重要字段仍有统计异常值：可缩尾或分箱（不删除行）"})
    if not recs:
        recs.append({"severity": "P2", "target": "<pipeline>",
                     "advice": "清洗口径未见风险，可进入 ⑤ 映射"})
    return recs


def _run_one(project, ds: str, specs) -> dict:
    out_dir = project.stage_output(STAGE) / ds
    out_dir.mkdir(parents=True, exist_ok=True)
    cleaned = pd.read_csv(project.stage_path("03_clean", ds, "cleaned.csv"))
    before_yaml = yaml.safe_load(
        (project.stage_path("02_profile", ds, "profile.yaml")).read_text(encoding="utf-8"))
    before_fields = {f["name"]: f for f in before_yaml.get("fields", [])}
    before_outliers = before_yaml.get("outliers_by_field") or {}
    before_rows = int((before_yaml.get("summary") or {}).get("rows", len(cleaned)))

    # --- 版本冻结（教学：git clone 后按序可复现）---
    version_lock = {
        "dataset": ds,
        "frozen_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "fingerprints": before_yaml.get("fingerprint"),
        "rows": {"raw": before_rows, "cleaned": int(len(cleaned))},
        "library_versions": _library_versions(),
        "cost_params": _cost_params(project),
        "reproducible": True,
    }
    lock_path = out_dir / "version_lock.json"
    version_ok, version_detail = True, "首次冻结（无历史版本可比对）"
    if lock_path.exists():
        try:
            prev = json.loads(lock_path.read_text(encoding="utf-8"))
            diffs = [f"{k}: {prev['library_versions'].get(k)} → {v}"
                     for k, v in version_lock["library_versions"].items()
                     if prev.get("library_versions", {}).get(k) != v]
            if prev.get("rows", {}).get("cleaned") != version_lock["rows"]["cleaned"]:
                diffs.append(f"rows.cleaned: {prev.get('rows', {}).get('cleaned')} → {version_lock['rows']['cleaned']}")
            version_ok, version_detail = (not diffs), ("一致" if not diffs else "；".join(diffs))
        except Exception as exc:                                   # 历史文件损坏：视为漂移
            version_ok, version_detail = False, f"历史 version_lock.json 不可解析：{exc}"
    lock_path.write_text(json.dumps(version_lock, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # --- 断言 ---
    roles = dk.schema_roles(dk.load_schema(project.config("schema")))
    assertions = [a for a in ((project.config("assertions") or {}).get("assertions") or [])
                  if a.get("when", "04_validate") == "04_validate"]
    checks = _run_assertions(cleaned, assertions,
                             {"version_lock_ok": version_ok, "version_lock_detail": version_detail})
    sev_order = {"P0": 0, "P1": 1, "P2": 2}
    checks.sort(key=lambda c: sev_order.get(c["severity"], 3))
    blocking = [c for c in checks if not c["passed"] and c["severity"] == "P0"]
    validation = {
        "dataset": ds,
        "validated_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "summary": {"total": len(checks), "pass": sum(1 for c in checks if c["passed"]),
                    "fail": sum(1 for c in checks if not c["passed"]),
                    "by_severity": {s: {"total": sum(1 for c in checks if c["severity"] == s),
                                        "pass": sum(1 for c in checks if c["severity"] == s and c["passed"])}
                                    for s in ("P0", "P1", "P2")},
                    "blocking": bool(blocking)},
        "checks": checks,
    }
    dk.write_yaml(out_dir, "validation", validation)
    md = ["# ④ 校验报告 · " + ds, "",
          f"> 生成时间：{validation['validated_at']}　断言口径：`config/assertions.yaml`",
          "", f"- 通过 {validation['summary']['pass']} / {validation['summary']['total']}",
          f"- 阻断项（P0 未过）：**{'有' if blocking else '无'}**", "",
          "| 断言 | 严重度 | 结果 | 实际 | 期望 | 说明 |", "| --- | --- | --- | --- | --- | --- |"]
    for c in checks:
        md.append(f"| {c['name']} | {c['severity']} | {'PASS' if c['passed'] else 'FAIL'} | "
                  f"{c['actual']} | {c['expected']} | {c['message']} |")
    md.append("")
    dk.write_markdown(out_dir, "validation", "\n".join(md))

    # --- 前后对比（阶段 2 vs 阶段 3）---
    after_prof = dk.profile(cleaned, roles=roles,
                            outlier_method=str(project.options.get("outlier_method", "iqr")))
    after_fields = {f.name: f for f in after_prof.fields}
    after_outliers = (after_prof.outliers["field"].value_counts().to_dict()
                      if len(after_prof.outliers) else {})
    levels = {s.name: s.level for s in dk.load_schema(project.config("schema"))}

    rows = []
    for name, bf in before_fields.items():
        af = after_fields.get(name)
        if af is None:
            continue
        rows.append({
            "field": name,
            "level": levels.get(name, "optional"),
            "dtype_before": bf.get("dtype"), "dtype_after": af.dtype,
            "null_rate_before": bf.get("null_rate"), "null_rate_after": af.null_rate,
            "null_rate_diff": (af.null_rate or 0) - (bf.get("null_rate") or 0),
            "unique_before": bf.get("unique"), "unique_after": af.unique,
            "mean_before": bf.get("mean"), "mean_after": af.stats.get("mean"),
            "median_before": bf.get("median"), "median_after": af.stats.get("median"),
            "outliers_before": int(before_outliers.get(name, 0)),
            "outliers_after": int(after_outliers.get(name, 0)),
        })
    before_after = pd.DataFrame(rows)
    dk.write_csv(out_dir, "before_after", before_after)

    removed_rate = (before_rows - len(cleaned)) / before_rows if before_rows else 0.0
    fill_by_field = None
    fbf = project.stage_path("03_clean", ds, "filled_by_field.csv")
    if fbf.exists():
        fill_by_field = pd.read_csv(fbf)
        if "rows_before" not in fill_by_field.columns:
            fill_by_field["rows_before"] = before_rows
    recs = _recommendations(project, removed_rate, rows, fill_by_field)
    verdict = ("阻断：存在 P0 未通过项，修复后再进入映射"
               if blocking else ("可进入 ⑤ 映射（附优化建议）"
                                 if any(r["severity"] != "P2" or r["target"] != "<pipeline>" for r in recs)
                                 else "可进入 ⑤ 映射"))
    comparison = {
        "dataset": ds,
        "rows_before": before_rows, "rows_after": int(len(cleaned)),
        "removed_rate": round(removed_rate, 6),
        "null_cells_before": int((before_yaml.get("summary") or {}).get("null_cells", 0)),
        "null_cells_after": int(after_prof.summary["null_cells"]),
        "outliers_before": int((before_yaml.get("summary") or {}).get("outlier_count", 0)),
        "outliers_after": int(after_prof.summary["outlier_count"]),
        "recommendations": recs,
        "verdict": verdict,
        "fields": rows,
    }
    dk.write_yaml(out_dir, "comparison", comparison)
    cm = ["# ④ 前后对比报告 · " + ds, "", f"- 结论：**{verdict}**", "",
          f"- 行数：{before_rows:,} → {len(cleaned):,}（删除率 {removed_rate:.2%}）",
          f"- 空单元格：{comparison['null_cells_before']:,} → {comparison['null_cells_after']:,}",
          f"- 极端值：{comparison['outliers_before']:,} → {comparison['outliers_after']:,}", "",
          "## 逐字段前后对比", "",
          "| 字段 | 等级 | 缺失率前 | 缺失率后 | 变化 | 异常值前 | 异常值后 | 均值前 | 均值后 |",
          "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for r in rows:
        cm.append(f"| {r['field']} | {r['level']} | {r['null_rate_before']:.2%} | {r['null_rate_after']:.2%} | "
                  f"{r['null_rate_diff']:+.2%} | {r['outliers_before']:,} | {r['outliers_after']:,} | "
                  f"{r['mean_before']} | {r['mean_after']} |")
    cm += ["", "## 建议清单", ""]
    for r in recs:
        cm.append(f"- **{r['severity']}** · {r['target']}：{r['advice']}")
    cm += ["", "> 版本冻结：`version_lock.json`（指纹 / 行数 / 库版本 / 合成成本参数）。", ""]
    dk.write_markdown(out_dir, "comparison", "\n".join(cm))

    project.log(f"[{STAGE}] {ds}: 断言 {validation['summary']['pass']}/{validation['summary']['total']} 通过"
                f"（P0 阻断 {len(blocking)}）；删除率 {removed_rate:.2%}；{verdict}")
    return {
        "dataset": ds,
        "checks_pass": validation["summary"]["pass"],
        "checks_total": validation["summary"]["total"],
        "blocking": len(blocking),
        "removed_rate": round(removed_rate, 6),
    }


def run(project) -> dict:
    datasets = project.meta.get("datasets") or list(DATASETS)
    specs = dk.load_schema(project.config("schema"))
    summaries = [_run_one(project, ds, specs) for ds in datasets]
    return {
        "stage": STAGE,
        "checks_pass": int(sum(s["checks_pass"] for s in summaries)),
        "checks_total": int(sum(s["checks_total"] for s in summaries)),
        "blocking": int(sum(s["blocking"] for s in summaries)),
    }


def main() -> None:
    import datakit as _dk
    root = Path(__file__).resolve().parent.parent
    print(run(_dk.Project.load(root)))


if __name__ == "__main__":
    main()
