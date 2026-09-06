# -*- coding: utf-8 -*-
"""03_clean —— ③ 清洗。

入口文件与目录同名（``03_clean.py``），规范见 ``datakit/PROJECT_STRUCTURE.md`` §2-③。

回答「动了哪些数据、为什么动、动了多少」：形状变化、缺失单元格前后、
**按字段影响**（填充 / 越界置空 / 替换 / 因该字段删除的行数 / 类型转换）、
按操作影响，以及逐条可审计的决策日志。

生存分析的两条硬口径（写在 ``config/clean_plan.yaml`` 的 ``forbidden``）：

* **死亡日期缺失 = 右删失，禁止填充**（填充会摧毁事件信息）；
* **出生日期、经纬度禁止填充**（缺失分别按左截断、不入网格处理）。

口径全部来自配置（改口径不改代码）；清洗算法由 ``dk.clean`` 提供。
输入优先复用 ② 的过程数据 ``raw_long.parquet``，缺失时回退到只读源数据重跑。
"""
from __future__ import annotations

import datetime as _dt
from pathlib import Path

import pandas as pd

import datakit as dk

STAGE = "03_clean"
TITLE = "③ 清洗（主键剔除 + 去重 + 越界置空，绝不填充生存字段）"

ROOT = Path(__file__).resolve().parent.parent
OUT = Path(__file__).resolve().parent / "output"

_DROPPED_INDEX_SAMPLE = 50      # 决策日志里保留的被删行索引样本条数（全量索引太大）


def _load_input(project) -> pd.DataFrame:
    """读上游过程数据；没有则回退到源数据（源数据只读）。"""
    cached = ROOT / "02_profile" / "output" / "raw_long.parquet"
    if cached.exists():
        project.log(f"    [③] 读入上游过程数据 {cached.name}")
        return pd.read_parquet(cached)
    project.log("    [③] 未找到 ② 的过程数据，回退：从源数据逐年读取")
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "_stage_02_profile", ROOT / "02_profile" / "02_profile.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.read_source(project)


def _impact(decisions: pd.DataFrame, before: pd.DataFrame, after: pd.DataFrame) -> dict:
    """按操作 / 按字段的影响汇总（规范 §2-③）。"""
    by_op = (decisions.groupby("action")
             .agg(executions=("step", "size"), affected_rows=("affected_rows", "sum"))
             .reset_index().to_dict("records"))

    by_field: dict[str, dict] = {}
    for col in before.columns:
        by_field[col] = {"filled": 0, "clipped_to_null": 0, "clipped": 0,
                         "replaced": 0, "winsorized": 0, "dropped_rows": 0,
                         "dtype_before": str(before[col].dtype),
                         "dtype_after": str(after[col].dtype)}
    for _, r in decisions.iterrows():
        fields = [f.strip() for f in str(r.get("field") or "").split(",") if f.strip()]
        n = int(r.get("affected_rows") or 0)
        act = r["action"]
        for f in fields:
            if f not in by_field:
                continue
            if act == "fill":
                by_field[f]["filled"] += n
            elif act == "clip":
                on_null = "to_null" in str(r.get("detail") or "")
                by_field[f]["clipped_to_null" if on_null else "clipped"] += n
            elif act == "replace":
                by_field[f]["replaced"] += n
            elif act == "winsorize":
                by_field[f]["winsorized"] += n
            elif act in ("drop_na", "drop_duplicates", "filter"):
                by_field[f]["dropped_rows"] += n
            elif act == "astype":
                pass
    return {"by_operation": by_op, "by_field": by_field}


def run(project) -> dict:
    """按 clean_plan.yaml 清洗，产出决策日志与影响报告。"""
    project.log(f"[{STAGE}] {TITLE}")
    plan_cfg = project.config("clean_plan")
    plan = dk.CleanPlan.from_spec(plan_cfg.get("steps") or [])

    long = _load_input(project)
    before_rows, before_cols = long.shape
    before_nulls = int(long.isna().sum().sum())

    res = dk.clean(long, plan)
    cleaned = res.dataset.frame
    after_rows, after_cols = cleaned.shape
    after_nulls = int(cleaned.isna().sum().sum())

    decisions = res.decisions.to_frame()
    if len(decisions) and "dropped_indices" in decisions.columns:
        decisions["dropped_indices"] = decisions["dropped_indices"].map(
            lambda v: list(v)[:_DROPPED_INDEX_SAMPLE] if isinstance(v, list) else v)

    impact = _impact(decisions, long, cleaned)
    filled_df = pd.DataFrame(
        [{"field": f, "filled": v["filled"], "clipped_to_null": v["clipped_to_null"],
          "clipped": v["clipped"], "replaced": v["replaced"], "winsorized": v["winsorized"]}
         for f, v in impact["by_field"].items()
         if any(v[k] for k in ("filled", "clipped_to_null", "clipped", "replaced", "winsorized"))])
    dropped_df = pd.DataFrame(
        [{"field": f, "dropped_rows": v["dropped_rows"],
          "dtype_before": v["dtype_before"], "dtype_after": v["dtype_after"]}
         for f, v in impact["by_field"].items() if v["dropped_rows"]])

    removed = before_rows - after_rows
    report = {
        "stage": STAGE,
        "cleaned_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "shape": {
            "rows_before": int(before_rows), "rows_after": int(after_rows),
            "rows_removed": int(removed),
            "removed_rate": (removed / before_rows) if before_rows else 0.0,
            "cols_before": int(before_cols), "cols_after": int(after_cols),
            "cols_dropped": [c for c in long.columns if c not in cleaned.columns],
        },
        "missing_cells": {
            "before": before_nulls, "after": after_nulls,
            "filled": max(before_nulls - after_nulls, 0),
            "note": "清洗只做删除与越界置空，**不做任何填充**（见 clean_plan.forbidden）；"
                    "空单元格增加来自越界值置空",
        },
        "impact": impact,
        "decisions": decisions.to_dict("records"),
        "forbidden_check": {
            "declared": plan_cfg.get("forbidden") or [],
            "violated": _check_forbidden(plan_cfg.get("forbidden") or [], decisions),
        },
        "outputs": ["cleaned.csv", "cleaned.parquet"],
    }

    cleaned.to_csv(OUT / "cleaned.csv", index=False)
    cleaned.to_parquet(OUT / "cleaned.parquet", index=False)

    project.write_stage(STAGE, "decisions", {"stage": STAGE, "decisions": report["decisions"]},
                        markdown=res.decisions.to_markdown())
    project.write_stage(STAGE, "impact", impact)
    project.write_stage(STAGE, "clean_report", report,
                        tables={"filled_by_field": filled_df, "dropped_by_field": dropped_df},
                        markdown=_to_markdown(report, decisions))
    project.log(f"    [③] {before_rows:,} → {after_rows:,} 行（删除 {removed:,}，"
                f"{report['shape']['removed_rate']:.2%}）；空单元格 {before_nulls:,} → {after_nulls:,}")
    return {
        "stage": STAGE,
        "rows_before": int(before_rows),
        "rows_after": int(after_rows),
        "removed_rate": f"{report['shape']['removed_rate']:.2%}",
        "steps": int(len(decisions)),
    }


def _check_forbidden(forbidden: list, decisions: pd.DataFrame) -> list[dict]:
    """复核「明令禁止的动作」是否真的没被执行。"""
    out = []
    done = decisions.set_index("step") if len(decisions) else pd.DataFrame()
    for item in forbidden:
        fields = item.get("field") or []
        fields = fields if isinstance(fields, list) else [fields]
        op = item.get("op")
        hit = done[(done["action"] == op) &
                   done["field"].fillna("").map(lambda s: any(f in s for f in fields))] if len(done) else pd.DataFrame()
        if len(hit):
            out.append({**item, "executed_steps": hit.index.tolist()})
    return out


def _to_markdown(report: dict, decisions: pd.DataFrame) -> str:
    """人读清洗报告（规范 §2-③ 的报告块）。"""
    sh, mc = report["shape"], report["missing_cells"]
    lines = [
        "# ③ 清洗报告", "",
        f"- 清洗时间：{report['cleaned_at']}",
        "",
        "## 形状变化",
        "",
        "| 项 | 前 | 后 | 变化 |",
        "| --- | --- | --- | --- |",
        f"| 行数 | {sh['rows_before']:,} | {sh['rows_after']:,} | -{sh['rows_removed']:,}（{sh['removed_rate']:.2%}） |",
        f"| 列数 | {sh['cols_before']} | {sh['cols_after']} | {sh['cols_dropped'] or '无删除'} |",
        f"| 空单元格 | {mc['before']:,} | {mc['after']:,} | 填充 {mc['filled']:,} |",
        "",
        "## 决策日志",
        "",
        "| 步骤 | 动作 | 字段 | 影响行 | 可逆 | 原因 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for _, r in decisions.iterrows():
        lines.append(f"| {r['step']} | `{r['action']}` | {r['field']} | {int(r['affected_rows']):,} | "
                     f"{'是' if r['reversible'] else '否'} | {r['reason']} |")

    lines += ["", "## 按操作影响", "", "| 动作 | 执行次数 | 累计影响行 |", "| --- | --- | --- |"]
    for r in report["impact"]["by_operation"]:
        lines.append(f"| {r['action']} | {r['executions']} | {int(r['affected_rows']):,} |")

    lines += ["", "## 按字段影响", "",
              "| 字段 | 填充 | 越界置空 | 截断 | 替换 | 因该字段删除行 | 类型 前→后 |",
              "| --- | --- | --- | --- | --- | --- | --- |"]
    for f, v in report["impact"]["by_field"].items():
        if not any([v["filled"], v["clipped_to_null"], v["clipped"], v["replaced"], v["dropped_rows"]]):
            continue
        dtype_chg = "" if v["dtype_before"] == v["dtype_after"] else f"{v['dtype_before']} → {v['dtype_after']}"
        lines.append(f"| {f} | {v['filled']:,} | {v['clipped_to_null']:,} | {v['clipped']:,} | "
                     f"{v['replaced']:,} | {v['dropped_rows']:,} | {dtype_chg or '—'} |")

    fb = report["forbidden_check"]
    lines += ["", "## 禁止动作复核（生存口径红线）", "",
              f"- 声明的禁止动作：{len(fb['declared'])} 条",
              f"- 实际违反：**{len(fb['violated'])} 条**"
              + (f" → {fb['violated']}" if fb["violated"] else "（全部遵守：右删失 / 左截断 / 坐标均未被填充）")]
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    project = dk.Project.load(ROOT)
    print(run(project))


if __name__ == "__main__":
    main()
