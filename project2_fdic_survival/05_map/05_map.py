# -*- coding: utf-8 -*-
"""05_map —— ⑤ 映射（生存分析数据底座）。

入口文件与目录同名（``05_map.py``），规范见 ``datakit/PROJECT_STRUCTURE.md`` §2-⑤。

回答「原始字段怎么变成分析字段」：

* **网点维度表**（每 ``UNINUMBR`` 一行）：出生年 / 死亡年 / 首末现年 /
  左截断 / 右删失 / 事件类型 / 存活年数 / 坐标 / 银行类别 —— 离散时间生存模型的骨架；
* **空间网格**：经纬度 → H3 R8（``dk.MappingScheme.geocode``），H3 不可用时降级
  0.01° 网格；同格网点数 = 本地竞争强度；
* **银行层共享脆弱性分层**（每 ``CERT`` 一行）：L0 单网点 / L1 多网点高集中 /
  L2 多网点地理分散。

口径常量与映射方案写在 ``config/mapping.yaml``（纯业务意图，全人写）。
"""
from __future__ import annotations

import datetime as _dt
from pathlib import Path

import numpy as np
import pandas as pd

import datakit as dk

STAGE = "05_map"
TITLE = "⑤ 映射（网点维度表 + 银行脆弱性 + 空间网格）"

ROOT = Path(__file__).resolve().parent.parent
OUT = Path(__file__).resolve().parent / "output"
DATA = OUT / "data"

H3_RES = 7                      # H3 R7：实测（h3 4.5.0）平均单元面积 5.161293 km²、平均边长 1.406476 km（与降级网格 0.01° ≈ 1.1 km 同尺度）
FALLBACK_GRID = 0.01            # 降级方案：0.01° 网格（≈ 1.1 km）


def _load_cleaned() -> pd.DataFrame:
    pq = ROOT / "03_clean" / "output" / "cleaned.parquet"
    if pq.exists():
        return pd.read_parquet(pq)
    return pd.read_csv(ROOT / "03_clean" / "output" / "cleaned.csv", low_memory=False)


def build_base_dim(cleaned: pd.DataFrame) -> pd.DataFrame:
    """按 UNINUMBR 聚合为网点维度骨架（首末观测 + 出生/死亡年 + 末期协变量）。

    口径要点（与 04_validate 一致）：

    * **出生年** = 该网点出现过的最早 ``SIMS_ESTABLISHED_DATE`` 年份；
    * **死亡年** = 该网点出现过的最晚 ``SIMS_ACQUIRED_DATE`` 年份 —— 该字段只在
      并购当年（及之后若干年）出现，若按「最后一行」取值会把已关闭网点误判为存活；
    * **所属银行 CERT 取首次观测值**：银行层共享脆弱性是「进入面板时的基线属性」，
      并购导致的 CERT 变更不追溯重标，避免用**事后归属**解释**事前风险**
      （若按末次 CERT 归属，已发生并购 / 关闭的结果会倒灌进协变量）；
    * 末期协变量（存款 / 坐标）取**末次有效值**（skipna），提高覆盖率。
    """
    long = cleaned.copy()
    long["_est_y"] = long["SIMS_ESTABLISHED_DATE"].dt.year
    long["_acq_y"] = long["SIMS_ACQUIRED_DATE"].dt.year
    g = long.sort_values(["UNINUMBR", "YEAR"]).groupby("UNINUMBR", sort=False)
    dim = pd.DataFrame({
        "CERT": g["CERT"].first(),
        "BKCLASS": g["BKCLASS"].first(),
        "first_year": g["YEAR"].min(),
        "last_year": g["YEAR"].max(),
        "est_year": g["_est_y"].min(),
        "acq_year": g["_acq_y"].max(),
        "DEPSUMBR_last": g["DEPSUMBR"].last(),
        "lat": g["SIMS_LATITUDE"].last(),
        "lng": g["SIMS_LONGITUDE"].last(),
    }).reset_index()
    dim["UNINUMBR"] = dim["UNINUMBR"].astype("int64")
    return dim


def apply_mapping(dim: pd.DataFrame, first_panel_year: int, project) -> tuple[pd.DataFrame, list[dict], str]:
    """用 ``dk.MappingScheme`` 执行映射（口径见 config/mapping.yaml）。

    返回 ``(映射后网点维度表, datakit 操作报告, 空间方法)``。
    """
    scheme = dk.MappingScheme()
    geo_method = "grid_0p01"
    try:
        import h3  # noqa: F401
        scheme.geocode("lat", "lng", resolution=H3_RES,
                       reason=f"H3 R{H3_RES}（平均单元面积 5.161293 km²，平均边长 1.406476 km）作空间聚合单元")
        geo_method = f"h3_r{H3_RES}"
    except ImportError:
        project.log("    [⑤] h3 不可用，降级到 0.01° 网格（config/mapping.yaml 声明的降级方案）")

    scheme.derive("obs_end", lambda d: d["acq_year"].fillna(d["last_year"]),
                  reason="观察期终点：死亡年；仍存活则用最后一次出现年")
    scheme.derive("duration", lambda d: (d["obs_end"] - d["first_year"] + 1).clip(lower=1).astype(int),
                  reason="风险集内的存活年数（离散时间风险模型的 duration）")
    scheme.derive("right_censored", lambda d: d["acq_year"].isna().astype(int),
                  reason="右删失标记：无死亡年 = 仍存活")
    scheme.derive("event", lambda d: np.where(d["acq_year"].notna(), "closed", "alive"),
                  reason="事件类型（closed / alive）")
    scheme.derive("left_truncated",
                  lambda d: (d["est_year"] < first_panel_year).fillna(True).astype(int),
                  reason="左截断：出生早于面板首期（出生年缺失按左截断处理）")
    scheme.derive("age", lambda d: d["last_year"] - d["est_year"].fillna(d["first_year"]),
                  reason="网点年龄（末次观测年 − 出生年；出生年缺失用首次出现年代替）")
    scheme.derive("alive_years", lambda d: d["last_year"] - d["first_year"] + 1,
                  reason="在面板中出现的年数")

    mapped = dk.map(dim, scheme)
    dim = mapped.dataset.frame
    ops_report = list(mapped.report)

    # 空间网格键：H3 优先，否则 0.01° 网格
    if "h3" in dim.columns:
        dim["spatial_key"] = dim["h3"]
    else:
        lat_k = np.floor(dim["lat"].to_numpy(dtype="float64") / FALLBACK_GRID)
        lng_k = np.floor(dim["lng"].to_numpy(dtype="float64") / FALLBACK_GRID)
        dim["grid"] = pd.Series(
            [None if (np.isnan(a) or np.isnan(b)) else f"{a:.0f}_{b:.0f}"
             for a, b in zip(lat_k, lng_k)],
            index=dim.index, dtype="string")
        dim["spatial_key"] = dim["grid"]
        ops_report.append({"op": "geocode", "reason": "降级方案",
                           "detail": f"新增列 grid（{FALLBACK_GRID}° 网格）"})

    dim["neighbor_count"] = (dim.groupby("spatial_key")["UNINUMBR"]
                             .transform("count").fillna(0).astype(int))
    ops_report.append({"op": "derive", "reason": "本地竞争强度代理",
                       "detail": "新增列 neighbor_count（同网格网点数，含自身）"})
    return dim, ops_report, geo_method


def build_bank_fragility(branch: pd.DataFrame) -> pd.DataFrame:
    """银行层聚合：网点数 / 已关闭数 / 地理分散度 → 脆弱性分层。"""
    g = branch.groupby("CERT")
    bank = pd.DataFrame({
        "n_branches": g["UNINUMBR"].count(),
        "n_closed": g["event"].apply(lambda s: int((s == "closed").sum())),
        "lat_std": g["lat"].std(),
        "lng_std": g["lng"].std(),
        "DEPSUMBR_total": g["DEPSUMBR_last"].sum(min_count=1),
    }).reset_index()
    bank["geo_spread"] = (bank["lat_std"].pow(2) + bank["lng_std"].pow(2)).pow(0.5)
    median_spread = bank.loc[bank["n_branches"] > 1, "geo_spread"].median()
    bank["fragility_tier"] = np.select(
        [
            bank["n_branches"] == 1,
            (bank["n_branches"] > 1) & (bank["geo_spread"] < median_spread),
            (bank["n_branches"] > 1) & (bank["geo_spread"] >= median_spread),
        ],
        ["L0_单网点", "L1_多网点高集中", "L2_多网点地理分散"],
        default="L2_多网点地理分散",
    )
    bank["bank_closed_rate"] = (bank["n_closed"] / bank["n_branches"]).round(6)
    return bank


def _field_report(df: pd.DataFrame) -> list[dict]:
    """映射后字段数据报告（逐字段类型 / 非空 / 缺失率 / 唯一值 / 统计）。"""
    rows = []
    for col in df.columns:
        s = df[col]
        rec = {"field": col, "dtype": str(s.dtype), "non_null": int(s.notna().sum()),
               "null_rate": round(float(s.isna().mean()), 6), "unique": int(s.nunique(dropna=True))}
        if pd.api.types.is_numeric_dtype(s) and s.notna().any():
            v = s.dropna()
            rec.update({"min": float(v.min()), "max": float(v.max()),
                        "mean": float(v.mean()), "median": float(v.median())})
        else:
            top = s.dropna().astype(str).value_counts().head(5)
            rec["top"] = {k: int(c) for k, c in top.items()}
        rows.append(rec)
    return rows


def _lineage_rows(geo_method: str) -> list[dict]:
    """字段血缘：输出字段 ← 来源字段 / 表达式 / 映射方式。"""
    return [
        {"output": "est_year", "sources": "SIMS_ESTABLISHED_DATE",
         "expr": "min(year(SIMS_ESTABLISHED_DATE)) over UNINUMBR", "op": "aggregate"},
        {"output": "acq_year", "sources": "SIMS_ACQUIRED_DATE",
         "expr": "max(year(SIMS_ACQUIRED_DATE)) over UNINUMBR（该字段只在并购当年及之后若干年出现，"
                 "取 max 而非末行，否则会把已关闭网点误判为存活）", "op": "aggregate"},
        {"output": "first_year / last_year", "sources": "YEAR",
         "expr": "min(YEAR) / max(YEAR) over UNINUMBR", "op": "aggregate"},
        {"output": "obs_end", "sources": "acq_year, last_year",
         "expr": "acq_year.fillna(last_year)", "op": "derive"},
        {"output": "duration", "sources": "obs_end, first_year",
         "expr": "(obs_end - first_year + 1).clip(lower=1)", "op": "derive"},
        {"output": "event", "sources": "acq_year",
         "expr": "closed if acq_year notnull else alive", "op": "derive"},
        {"output": "right_censored", "sources": "acq_year",
         "expr": "int(acq_year is null)", "op": "derive"},
        {"output": "left_truncated", "sources": "est_year",
         "expr": "int(est_year < 首期年份)；出生年缺失记为 1", "op": "derive"},
        {"output": "age", "sources": "last_year, est_year, first_year",
         "expr": "last_year - est_year.fillna(first_year)", "op": "derive"},
        {"output": "spatial_key", "sources": "SIMS_LATITUDE, SIMS_LONGITUDE",
         "expr": (f"h3.latlng_to_cell(lat, lng, {H3_RES})" if geo_method.startswith("h3")
                  else "floor(lat/0.01)_floor(lng/0.01)"),
         "op": "geocode"},
        {"output": "CERT", "sources": "CERT",
         "expr": "first(CERT) over UNINUMBR（基线所属银行；并购后不追溯重标）", "op": "aggregate"},
        {"output": "neighbor_count", "sources": "spatial_key, UNINUMBR",
         "expr": "groupby(spatial_key)[UNINUMBR].transform(count)（无坐标记 0）", "op": "derive"},
        {"output": "n_branches / n_closed / bank_closed_rate", "sources": "UNINUMBR, event",
         "expr": "groupby(CERT) 聚合", "op": "aggregate"},
        {"output": "fragility_tier", "sources": "n_branches, geo_spread",
         "expr": "L0 单网点 / L1 多网点高集中 / L2 多网点地理分散（以多网点银行 geo_spread 中位数分界）",
         "op": "aggregate"},
        {"output": "BRNUM", "sources": "BRNUM", "expr": "—（跨年重编号，不进入下游）", "op": "drop"},
    ]


def run(project) -> dict:
    """构建网点维度表 + 银行脆弱性，产出映射报告与下游数据。"""
    project.log(f"[{STAGE}] {TITLE}")
    cfg = project.config("mapping")
    DATA.mkdir(parents=True, exist_ok=True)

    cleaned = _load_cleaned()
    first_panel_year = int(cleaned["YEAR"].min())
    last_panel_year = int(cleaned["YEAR"].max())
    project.log(f"    [⑤] 清洗后长表 {len(cleaned):,} 行（{first_panel_year}–{last_panel_year}）")

    dim = build_base_dim(cleaned)
    branch, ops_report, geo_method = apply_mapping(dim, first_panel_year, project)
    bank = build_bank_fragility(branch)

    branch.to_csv(DATA / "branch_panel.csv", index=False)
    bank.to_csv(DATA / "bank_fragility.csv", index=False)
    branch.to_csv(OUT / "mapped.csv", index=False)

    event_dist = branch["event"].value_counts().to_dict()
    tier_dist = bank["fragility_tier"].value_counts().to_dict()
    lineage = pd.DataFrame(_lineage_rows(geo_method))
    mapped_fields = _field_report(branch)

    report = {
        "stage": STAGE,
        "mapped_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "scheme": {"source": "config/mapping.yaml", "ops": cfg.get("ops") or []},
        "operations": ops_report + [
            {"op": "aggregate", "detail": "长表 → 网点维度表（按 UNINUMBR 聚合）",
             "reason": "离散时间生存模型的风险集骨架：每网点一行"},
            {"op": "aggregate", "detail": f"银行脆弱性分层（按 CERT，{len(bank):,} 家）",
             "reason": "银行层共享脆弱性：L0/L1/L2"},
        ],
        "shape": {
            "long_rows": int(len(cleaned)),
            "branch_panel_rows": int(len(branch)),
            "branch_panel_cols": int(branch.shape[1]),
            "bank_rows": int(len(bank)),
            "spatial_cells": int(branch["spatial_key"].nunique(dropna=True)),
        },
        "panel_scope": {"first_year": first_panel_year, "last_year": last_panel_year},
        "geo_method": geo_method,
        "cert_attribution": {
            "rule": "首次观测所属银行（CERT.first()）",
            "why": "银行层共享脆弱性按基线归属；并购导致的 CERT 变更不追溯重标，"
                   "避免把事后结果倒灌进事前协变量",
        },
        "event_dist": {k: int(v) for k, v in event_dist.items()},
        "right_censored_rate": float(branch["right_censored"].mean()),
        "closed_rate": float((branch["event"] == "closed").mean()),
        "left_truncated_rate": float(branch["left_truncated"].mean()),
        "fragility_dist": {k: int(v) for k, v in tier_dist.items()},
        "mapped_fields": mapped_fields,
        "outputs": ["mapped.csv", "data/branch_panel.csv", "data/bank_fragility.csv"],
    }
    project.write_stage(STAGE, "map", report,
                        tables={"lineage": lineage, "fields": pd.DataFrame(mapped_fields)},
                        markdown=_md(report, lineage, bank))
    project.log(f"    [⑤] 网点 {len(branch):,}（{ {k: int(v) for k, v in event_dist.items()} }）；"
                f"银行 {len(bank):,}（{ {k: int(v) for k, v in tier_dist.items()} }）；空间方法 {geo_method}")
    return {
        "stage": STAGE,
        "branches": int(len(branch)),
        "banks": int(len(bank)),
        "closed_rate": round(float((branch["event"] == "closed").mean()), 4),
        "right_censored_rate": round(float(branch["right_censored"].mean()), 4),
        "geo_method": geo_method,
    }


def _md(report: dict, lineage: pd.DataFrame, bank: pd.DataFrame) -> str:
    sh = report["shape"]
    lines = [
        "# ⑤ 映射报告（生存分析数据底座）", "",
        f"- 映射时间：{report['mapped_at']}",
        f"- 面板范围：{report['panel_scope']['first_year']}–{report['panel_scope']['last_year']}",
        f"- 形状：长表 {sh['long_rows']:,} 行 → 网点维度表 {sh['branch_panel_rows']:,} 行 × "
        f"{sh['branch_panel_cols']} 列；银行层 {sh['bank_rows']:,} 行",
        f"- 空间方法：`{report['geo_method']}`（网格数 {sh['spatial_cells']:,}）",
        "",
        "## 操作明细", "", "| 操作 | 结果 | 原因 |", "| --- | --- | --- |",
    ]
    for r in report["operations"]:
        lines.append(f"| `{r['op']}` | {r['detail']} | {r.get('reason', '—')} |")

    lines += ["", "## 生存口径分布", "", "| 项 | 值 |", "| --- | --- |",
              f"| 关闭率（事件） | {report['closed_rate']:.2%} |",
              f"| 右删失率（仍存活） | {report['right_censored_rate']:.2%} |",
              f"| 左截断率 | {report['left_truncated_rate']:.2%} |"]
    for k, v in report["event_dist"].items():
        lines.append(f"| event={k} | {v:,} |")

    lines += ["", "## 银行脆弱性分层", "", "| 分层 | 银行数 |", "| --- | --- |"]
    for k, v in report["fragility_dist"].items():
        lines.append(f"| {k} | {v:,} |")

    lines += ["", "## 字段血缘", "", "| 输出字段 | 来源字段 | 表达式 / 方式 | 操作 |",
              "| --- | --- | --- | --- |"]
    for _, r in lineage.iterrows():
        lines.append(f"| {r['output']} | {r['sources']} | {r['expr']} | {r['op']} |")

    lines += ["", "## 映射后字段数据报告（网点维度表）", "",
              "| 字段 | 类型 | 非空 | 缺失率 | 唯一值 | 关键统计 |", "| --- | --- | --- | --- | --- | --- |"]
    for f in report["mapped_fields"]:
        key = "—"
        if "mean" in f:
            key = f"mean={f['mean']:.4g}, median={f['median']:.4g}, max={f['max']:.4g}"
        elif f.get("top"):
            key = ", ".join(f"{k}({v})" for k, v in list(f["top"].items())[:3])
        lines.append(f"| {f['field']} | {f['dtype']} | {f['non_null']:,} | {f['null_rate']:.2%} | "
                     f"{f['unique']:,} | {key} |")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    project = dk.Project.load(ROOT)
    print(run(project))


if __name__ == "__main__":
    main()
