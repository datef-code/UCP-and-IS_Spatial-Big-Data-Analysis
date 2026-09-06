# -*- coding: utf-8 -*-
"""03_clean —— ③ 清洗（多数据集项目）。

回答「动了哪些数据、为什么动、动了多少」：按 ``config/clean_plan.yaml`` 执行，
产出决策日志与按字段 / 按操作的影响汇总。

产物（``output/<dataset>/``）：

* ``cleaned.csv`` —— 过程数据（交付 04/05）
* ``clean_report.md`` —— 决策 + 结果汇总
* ``decisions.yaml`` / ``decisions.md`` —— 决策日志
* ``impact.yaml`` —— 按操作 / 按字段的影响
* ``filled_by_field.csv`` / ``dropped_by_field.csv``

数据流向（规范 §1）：``data_raw/ → 03_clean``，与阶段 2 共用
``02_profile/loaders.py`` 的加载口径（数字前缀目录用 ``importlib`` 按文件路径加载）。
"""
from __future__ import annotations

import datetime as _dt
import importlib.util
import sys
from pathlib import Path

import pandas as pd

import datakit as dk

STAGE = "03_clean"
DATASETS = ("fdic", "sz_bike", "snap_brightkite", "snap_gowalla")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def _loaders(project):
    """按文件路径加载 02_profile/loaders.py（数字前缀目录不能 import）。"""
    path = project.root / "02_profile" / "loaders.py"
    spec = importlib.util.spec_from_file_location("_p6_loaders", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_p6_loaders"] = mod
    spec.loader.exec_module(mod)
    return mod


def _check_forbidden(project, plan: dk.CleanPlan) -> list[dict]:
    """机器反过来校验人的口径：配置里的 forbidden 是否被违反（规范 §3.4）。"""
    forbid = (project.config("clean_plan") or {}).get("forbidden") or []
    hits = []
    for rule in forbid:
        for action in plan.actions:
            fields = action.field if isinstance(action.field, list) else [action.field]
            if action.op == rule.get("op") and set(fields or []) & set(rule.get("fields") or []):
                hits.append({"op": action.op, "fields": sorted(set(fields) & set(rule["fields"])),
                             "reason": rule.get("reason", "")})
    return hits


def _impact(plan: dk.CleanPlan, result: dk.CleanResult, fields: list[str]) -> dict:
    """按操作 / 按字段汇总影响（规范 §2-③）。"""
    by_field = {f: {"filled": 0, "nulled": 0, "clipped": 0, "winsorized": 0,
                    "replaced": 0, "dropped_rows": 0, "type_change": ""} for f in fields}
    by_op: dict[str, dict] = {}
    records = result.decisions.records
    for step, action in enumerate(plan.actions, start=1):
        rec = next((r for r in records if r["step"] == step), None)
        affected = int(rec["affected_rows"]) if rec else 0
        op = by_op.setdefault(action.op, {"times": 0, "affected_rows": 0, "detail": []})
        op["times"] += 1
        op["affected_rows"] += affected
        op["detail"].append(f"step{step}:{action.label()}")

        targets = action.field if isinstance(action.field, list) else ([action.field] if action.field else [])
        for f in targets:
            if f not in by_field:
                continue
            if action.op == "fill":
                by_field[f]["filled"] += affected
            elif action.op == "clip":
                if action.params.get("on_violation") == "to_null":
                    by_field[f]["nulled"] += affected
                else:
                    by_field[f]["clipped"] += affected
            elif action.op == "winsorize":
                by_field[f]["winsorized"] += affected
            elif action.op == "replace":
                by_field[f]["replaced"] += affected
            elif action.op == "drop_na":
                by_field[f]["dropped_rows"] += affected
            elif action.op == "astype":
                by_field[f]["type_change"] = str(action.params.get("dtype"))
    return {"by_field": by_field, "by_op": by_op}


def _run_one(project, ds: str, loaders) -> dict:
    pts, fp = loaders.load_points(project, ds, log=project.log)
    before_rows, before_cols = len(pts), len(pts.columns)
    before_cells = int(pts.isna().sum().sum())

    plan = dk.CleanPlan.from_spec((project.config("clean_plan") or {}).get("steps") or [])
    forbidden_hits = _check_forbidden(project, plan)
    result = dk.clean(pts, plan)
    cleaned = result.dataset.frame
    after_cells = int(cleaned.isna().sum().sum())

    out_dir = project.stage_output(STAGE) / ds
    out_dir.mkdir(parents=True, exist_ok=True)
    cleaned.to_csv(out_dir / "cleaned.csv", index=False, float_format="%.6f", encoding="utf-8")

    decisions_df = result.decisions.to_frame()
    dk.write_csv(out_dir, "decisions", decisions_df)
    dk.write_yaml(out_dir, "decisions", {
        "dataset": ds,
        "shape_before": [before_rows, before_cols],
        "shape_after": list(cleaned.shape),
        "records": [{k: v for k, v in r.items() if k != "dropped_indices"} for r in result.decisions.records],
    })
    dk.write_markdown(out_dir, "decisions", result.decisions.to_markdown())

    impact = _impact(plan, result, list(pts.columns))
    dk.write_yaml(out_dir, "impact", {
        "dataset": ds,
        "shape": {"rows_before": before_rows, "rows_after": int(len(cleaned)),
                  "removed_rows": before_rows - len(cleaned),
                  "removed_rate": (before_rows - len(cleaned)) / before_rows if before_rows else 0.0,
                  "cols_before": before_cols, "cols_after": int(len(cleaned.columns))},
        "missing_cells": {"before": before_cells, "after": after_cells,
                          "filled": max(before_cells - after_cells, 0)},
        **impact,
        "forbidden_violations": forbidden_hits,
    })

    filled = pd.DataFrame([{"field": f, **v} for f, v in impact["by_field"].items()])
    dk.write_csv(out_dir, "filled_by_field", filled)
    dropped = pd.DataFrame([{"field": f, "dropped_rows": v["dropped_rows"],
                             "removed_rate": v["dropped_rows"] / before_rows if before_rows else 0.0}
                            for f, v in impact["by_field"].items()])
    dk.write_csv(out_dir, "dropped_by_field", dropped)

    stats = result.stats
    md = [
        f"# ③ 清洗报告 · {ds}",
        "",
        f"> 生成时间：{_dt.datetime.now().isoformat(timespec='seconds')}　口径：`config/clean_plan.yaml`",
        "",
        "## 形状变化",
        "",
        f"- 行数：{before_rows:,} → {len(cleaned):,}（删除 {before_rows - len(cleaned):,}，"
        f"{(before_rows - len(cleaned)) / before_rows if before_rows else 0:.2%}）",
        f"- 列数：{before_cols} → {len(cleaned.columns)}",
        f"- 空单元格：{before_cells:,} → {after_cells:,}（净减 {max(before_cells - after_cells, 0):,}）",
        "",
        "## 决策日志",
        "",
        "| 步骤 | 动作 | 字段 | 影响行 | 可逆 | 原因 |",
        "| ---: | --- | --- | ---: | --- | --- |",
    ]
    for _, r in decisions_df.iterrows():
        md.append(f"| {r['step']} | `{r['action']}` | {r['field']} | {int(r['affected_rows']):,} | "
                  f"{'是' if r['reversible'] else '否'} | {r['reason']} |")
    if decisions_df.empty:
        md.append("| — | — | — | — | — | （无清洗动作） |")
    md += [
        "## 按操作影响",
        "",
        "| 操作 | 次数 | 累计影响行数 |",
        "| --- | ---: | ---: |",
    ]
    for op, v in impact["by_op"].items():
        md.append(f"| {op} | {v['times']} | {v['affected_rows']:,} |")
    md += ["", "## 按字段影响", "",
           "| 字段 | 填充 | 置空 | 截断 | 因该字段删除行 | 类型转换 |",
           "| --- | ---: | ---: | ---: | ---: | --- |"]
    for f, v in impact["by_field"].items():
        md.append(f"| {f} | {v['filled']:,} | {v['nulled']:,} | {v['clipped']:,} | "
                  f"{v['dropped_rows']:,} | {v['type_change'] or '—'} |")
    if forbidden_hits:
        md += ["", "## ⚠️ 禁止项校验", ""]
        for h in forbidden_hits:
            md.append(f"- `{h['op']}` 作用于 {h['fields']}：**违反** config 的 forbidden 口径 —— {h['reason']}")
    else:
        md += ["", "## 禁止项校验", "", "- ✅ 未出现 config 中 forbidden 的清洗动作（坐标不做填充）"]
    md += ["", f"> 过程数据：`cleaned.csv`（{len(cleaned):,} 行，可重建）。", ""]
    dk.write_markdown(out_dir, "clean_report", "\n".join(md))

    project.log(f"[{STAGE}] {ds}: {before_rows:,} → {len(cleaned):,} 行"
                f"（删除 {before_rows - len(cleaned):,}）；空单元格 {before_cells:,} → {after_cells:,}")
    return {
        "dataset": ds,
        "rows_before": before_rows,
        "rows_after": int(len(cleaned)),
        "removed": before_rows - int(len(cleaned)),
        "removed_rate": round((before_rows - len(cleaned)) / before_rows if before_rows else 0.0, 6),
        "forbidden": len(forbidden_hits),
        "fingerprint": fp,
    }


def run(project) -> dict:
    datasets = project.meta.get("datasets") or list(DATASETS)
    loaders = _loaders(project)
    summaries = [_run_one(project, ds, loaders) for ds in datasets]
    before = int(sum(s["rows_before"] for s in summaries))
    after = int(sum(s["rows_after"] for s in summaries))
    return {
        "stage": STAGE,
        "rows_before": before,
        "rows_after": after,
        "removed_rate": round((before - after) / before if before else 0.0, 6),
        "datasets": {s["dataset"]: s["rows_after"] for s in summaries},
    }


def main() -> None:
    import datakit as _dk
    root = Path(__file__).resolve().parent.parent
    print(run(_dk.Project.load(root)))


if __name__ == "__main__":
    main()
