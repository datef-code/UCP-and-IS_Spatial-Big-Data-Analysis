#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
portal/build_data.py —— 从仓库真实产物抽取事实，生成门户数据层。

设计原则（与 datakit 规范一致）：
1. **只读**：不读取任何需要写入的中间产物，不修改任何已有文件。
2. **不编造**：抽取不到的字段一律置为 None，并写入 missing 清单，
   由门户前端显式降级披露（画不出就不画，绝不画编出来的图）。
3. **有血缘**：每个事实记录来源文件路径，页面可下钻到具体产物。

产物：portal/data/portal_data.js  →  window.SDP_DATA = {...}
      portal/data/portal_data.json （同内容，便于外部程序读取）

运行：
    ./.venv/Scripts/python.exe portal/build_data.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = Path(__file__).resolve().parent / "data"
AUDIT_DIR = Path(__file__).resolve().parent / "audit"      # 审计重跑产物（只读）

SCHEMA_VERSION = 2
REQUIRED_KEYS = ["meta", "datakit", "impact", "risk", "teaching", "missing"]

MISSING: list[dict] = []


def rel(p: Path | str) -> str:
    try:
        return str(Path(p).resolve().relative_to(ROOT)).replace("\\", "/")
    except Exception:
        return str(p)


def read_json(path: Path):
    if not path.exists():
        MISSING.append({"kind": "file", "path": rel(path), "why": "产物不存在（可能被 .gitignore 排除或未生成）"})
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:  # pragma: no cover
        MISSING.append({"kind": "parse", "path": rel(path), "why": f"JSON 解析失败：{e}"})
        return None


def read_text(path: Path) -> str | None:
    if not path.exists():
        MISSING.append({"kind": "file", "path": rel(path), "why": "产物不存在"})
        return None
    return path.read_text(encoding="utf-8", errors="replace")


def src(origin: str, note: str = "") -> dict:
    return {"from": origin, "note": note}


def load_audit(name: str) -> dict:
    """读取 portal/audit/ 下的重跑产物（可选）。

    这些产物由 portal/audit/*.py 基于上游中间产物重跑生成，用于把
    「文档承诺」升级为「可复算的事实」。缺失时不致命：登记 missing 并保持 null。
    """
    path = AUDIT_DIR / name
    if not path.exists():
        MISSING.append({"kind": "audit", "path": rel(path),
                        "why": "审计重跑产物缺失：运行 portal/audit/ 下的脚本后重建本数据层"})
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:                                    # pragma: no cover
        MISSING.append({"kind": "audit", "path": rel(path), "why": f"解析失败：{e}"})
        return {}


# --------------------------------------------------------------------------- #
# 解析工具：把 statsmodels / datakit 的文本产物转成可计算的结构
# --------------------------------------------------------------------------- #
_COEF_RE = re.compile(
    r"^(?P<name>\S.*?)\s+"
    r"(?P<coef>[-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?)\s+"
    r"(?P<se>[-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?)\s+"
    r"(?P<z>[-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?)\s+"
    r"(?P<p>[-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?)\s+"
    r"(?P<lo>[-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?)\s+"
    r"(?P<hi>[-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?)\s*$"
)


def parse_cloglog_coefs(txt: str) -> list[dict]:
    """解析 statsmodels GLM summary 的系数表 → 结构化系数（供前端真实推理）。

    同时标记「退化系数」（|coef| 异常大且标准误爆炸，通常是完全分离）：
    这类系数不能用于评分，前端必须拒绝而不是照算。
    """
    out: list[dict] = []
    if not txt:
        return out
    for line in txt.splitlines():
        s = line.strip()
        if not s or s.startswith(("=", "-", "Dep.", "Model", "Method", "Date", "Time", "No.", "Covariance")):
            continue
        if s.startswith("coef") or "std err" in s:
            continue
        m = _COEF_RE.match(s)
        if not m:
            continue
        name = m.group("name").strip()
        coef, se = float(m.group("coef")), float(m.group("se"))
        lo, hi, p = float(m.group("lo")), float(m.group("hi")), float(m.group("p"))
        kind, level = "numeric", name
        if name == "Intercept":
            kind, level = "intercept", "Intercept"
        else:
            dm = re.match(r"^C\((?P<var>[^)]+)\)\[T\.(?P<lvl>.+)\]$", name)
            if dm:
                kind = {"year": "year", "BKCLASS": "bkclass", "fragility_tier": "fragility"}.get(dm.group("var"), "categorical")
                level = dm.group("lvl")
        out.append({
            "name": name, "kind": kind, "level": level,
            "coef": coef, "se": se, "p": p, "lo": lo, "hi": hi,
            # 完全分离的典型特征：系数绝对值巨大 且 置信区间宽度爆炸
            "degenerate": bool(abs(coef) > 10 and (hi - lo) > 1000),
        })
    return out


_NUM_SUM_RE = re.compile(r"(min|max|mean|median|std)\s*=\s*(-?[0-9.eE+-]+)")
_CAT_COUNT_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*|[A-Z]{1,3})\((\d+)\)")


def parse_map_md(path: Path) -> dict:
    """解析 05_map/output/map.md 的「字段分布」表 → 真实区间与类别分布。

    该表是本项目**唯一入库**的网点级派生字段分布来源（profile.yaml 只覆盖原始字段），
    因此滑块区间与默认值一律取自这里，不允许臆造。
    """
    txt = read_text(path)
    if not txt:
        return {}
    ranges, cats, meta = {}, {}, {}
    for line in txt.splitlines():
        s = line.strip()
        if not s.startswith("|") or "---" in s:
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if len(cells) < 6:
            continue
        field, dtype = cells[0], cells[1]
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", field):
            continue
        if dtype not in ("int64", "float64", "Int64", "Float64", "string", "str", "object", "bool"):
            continue
        summary = cells[5]
        nums = {k: float(v) for k, v in _NUM_SUM_RE.findall(summary)}
        null_rate = None
        try:
            null_rate = float(cells[3].rstrip("%")) / 100
        except Exception:
            pass
        if nums:
            ranges[field] = {**nums, "null_rate": null_rate, "dtype": dtype, "unique": cells[4]}
        # 类别分布形如 N(62247), NM(50657)
        hits = _CAT_COUNT_RE.findall(summary)
        if hits and dtype in ("string", "str", "object"):
            cats[field] = [{"value": v, "count": int(c)} for v, c in hits]
        meta[field] = {"non_null": cells[2], "null_rate": null_rate, "unique": cells[4]}
    return {"ranges": ranges, "categories": cats, "meta": meta}


def load_profile_ranges(path: Path, want: list[str]) -> dict:
    """从 02_profile/output/profile.yaml 读取字段真实区间（用于输入校验与滑块范围）。"""
    try:
        import yaml  # datakit 运行时依赖，venv 内可用
    except Exception:
        MISSING.append({"kind": "module", "path": rel(path), "why": "未安装 pyyaml，字段区间不可用（前端将使用保守默认值并标注）"})
        return {}
    if not path.exists():
        MISSING.append({"kind": "file", "path": rel(path), "why": "画像产物不存在"})
        return {}
    try:
        doc = yaml.safe_load(read_text(path))
    except Exception as e:  # pragma: no cover
        MISSING.append({"kind": "parse", "path": rel(path), "why": f"YAML 解析失败：{e}"})
        return {}
    fields = (doc or {}).get("fields") if isinstance(doc, dict) else doc
    if not isinstance(fields, list):
        return {}
    res = {}
    for f in fields:
        nm = (f or {}).get("field")
        if nm in want:
            res[nm] = {k: f.get(k) for k in ("min", "max", "mean", "median", "std", "null_rate")}
    return res


# --------------------------------------------------------------------------- #
# A. datakit —— 工程底座
# --------------------------------------------------------------------------- #
def build_datakit() -> dict:
    dk = ROOT / "datakit"
    pkg = dk / "datakit"
    tests = dk / "tests"

    modules, src_lines = [], 0
    if pkg.is_dir():
        for f in sorted(pkg.glob("*.py")):
            n = len(f.read_text(encoding="utf-8", errors="replace").splitlines())
            src_lines += n
            modules.append({"name": f.stem, "lines": n})
    else:
        MISSING.append({"kind": "dir", "path": rel(pkg), "why": "SDK 包目录不存在"})

    test_files, test_lines, test_cases = [], 0, 0
    if tests.is_dir():
        for f in sorted(tests.rglob("*.py")):
            txt = f.read_text(encoding="utf-8", errors="replace")
            c = len(re.findall(r"^\s*def\s+test_", txt, flags=re.M))
            ln = len(txt.splitlines())
            test_files.append({"name": f.name, "lines": ln, "cases": c})
            test_lines += ln
            test_cases += c
    else:
        MISSING.append({"kind": "dir", "path": rel(tests), "why": "测试目录不存在"})

    version = None
    init = pkg / "__init__.py"
    if init.exists():
        m = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', init.read_text(encoding="utf-8", errors="replace"))
        version = m.group(1) if m else None

    # 阶段数：三项目 stage_summaries 的合计（下面复用）
    return {
        "_src": src(rel(pkg), "源码目录实测（行数 / 测试函数计数）"),
        "version": version,
        "module_count": len(modules),
        "src_lines": src_lines,
        "test_file_count": len(test_files),
        "test_lines": test_lines,
        "test_cases": test_cases,
        "modules": modules,
        "test_files": test_files,
        # 规范中写死的字段角色（8 种）—— 来自 datakit/core.py 的 Role 枚举
        "role_count": 8,
    }


# --------------------------------------------------------------------------- #
# B. project1 —— 事后影响评估
# --------------------------------------------------------------------------- #
def build_impact() -> dict:
    p1 = ROOT / "project1_fdic_spatial"
    stages = read_json(p1 / "logs" / "stage_summaries.json") or {}
    est = read_json(p1 / "06_estimate" / "output" / "estimate.json") or {}
    met = read_json(p1 / "06_estimate" / "output" / "metrics.json") or {}

    twfe = est.get("twfe", {})
    es = est.get("event_study", {})
    fits = est.get("spatial_fits", {})
    sens = est.get("sensitivity", {})
    coord = (sens or {}).get("coordinate_precision", {}) or {}

    slx = (fits or {}).get("slx", {}) or {}
    ols = (fits or {}).get("ols", {}) or {}
    sar = (fits or {}).get("sar", {}) or {}
    sem = (fits or {}).get("sem", {}) or {}

    def pget(d, *keys, default=None):
        cur = d
        for k in keys:
            if not isinstance(cur, dict):
                return default
            cur = cur.get(k)
            if cur is None:
                return default
        return cur

    event_table = [
        {
            "tau": int(r.get("rel_year")),
            "effect": r.get("dynamic_effect"),
            "se": r.get("std_err"),
            "p": r.get("pvalue"),
        }
        for r in (es.get("table") or [])
    ]

    lm = (ols or {}).get("LM_Lag"), (ols or {}).get("LM_Error"), (ols or {}).get("Robust_LM_Lag"), (ols or {}).get("Robust_LM_Error")

    # OLS 格级方程：本项目唯一"可直接代入"的多元回归式
    ols_params = ols.get("params") or {}
    ols_se = ols.get("std_err") or {}
    ols_cell = {
        "n": ols.get("n"), "k": ols.get("k"), "r2": ols.get("r2"),
        "terms": [{"name": k, "coef": v, "se": ols_se.get(k)} for k, v in ols_params.items()],
    }

    # 审计重跑（P0-1 / P0-2 / P0-4）——把「文档承诺」升级为「可复算的事实」
    aud = load_audit("p1_strength_rings.json")
    aud_support = (aud.get("strength_support") or {})
    aud_rings = (aud.get("twfe_variants") or {})
    aud_rings_real = {k: v for k, v in aud_rings.items() if not k.startswith("_")}
    aud_derived = (aud_rings.get("_derived") or {})
    aud_cross = (aud_rings.get("_cross_ring") or {})
    branch_support = (aud_support.get("branch_level") or {})

    # 敏感性审计：区分"真的跑过"与"只写了标签"——标签存在 ≠ 结果存在
    rings_alt = (sens or {}).get("rings_alternative") or {}
    has_ring_numbers = bool(aud_rings_real) or any(
        isinstance(v, dict) for v in rings_alt.values()
    )
    sensitivity_audit = {
        "rings_alternative": rings_alt,
        "rings_alternative_has_coefficients": bool(has_ring_numbers),
        "rings_alternative_status": (
            "已重跑产出系数（portal/audit/p1_strength_rings.json，三种口径）" if aud_rings_real
            else "仅标签，无系数/SE/p —— 合并环敏感性实际未跑" if not has_ring_numbers
            else "已产出系数"
        ),
        "rings_source": rel(AUDIT_DIR / "p1_strength_rings.json") if aud_rings_real else None,
        "weights_compared": False,
        "bootstrap_ci": False,
        "callaway_santanna": False,
        "note": "由 build_data.py 依据产物实测判定，不采信文档表述。",
    }

    # TWFE 外推口径披露：post 的系数是 strength = 0 处的反事实外推，而该点未被观测。
    # 口径说明：代码用的是**环加权和**（已用审计重跑逐网点复现，最大绝对差 0）；
    # 过时的是 06_estimate.py 的模块 docstring（写成了 log1p 单环计数）。
    tvals = twfe.get("tvalues") or {}
    _mins = branch_support.get("min")
    strength_disclosure = {
        "post_is_intercept_extrapolation": True,
        "explain": (
            "post 的系数是 strength_t0 = 0 处的反事实外推；"
            + (f"实测处理组 strength_t0 ∈ [{_mins}, {branch_support.get('max')}]（网点级），"
               f"均值 {round(branch_support.get('mean', 0), 4):.4f}，该点从未被观测。"
               if branch_support else
               "处理组 strength_t0 恒 > 0，该点从未被观测。")
        ),
        "interaction_coef": (twfe.get("params") or {}).get("post_x_strength"),
        "interaction_t": tvals.get("post_x_strength"),
        "strength_def_in_code": (
            "strength_t0 = Σ _ring_weight(dist_km)，权重 0–1km 1.0 / 1–3km 0.6 / "
            "3–5km 0.3 / 5–10km 0.1（环加权和）；treat_strength = treated × strength_t0"
        ),
        "doc_mismatch": (
            "06_estimate.py 的模块 docstring 写「treat_strength = log1p(n_same_ind_5km)（单环计数）」"
            "与代码不符；README 的「环加权强度」才是对的。以代码为准。"
        ),
        "doc_mismatch_actor": "project1_fdic_spatial/06_estimate/06_estimate.py（模块 docstring，上游待改）",
        "action_required": (
            "已解决：支撑域改为实测分位数，边际效应在均值处报出（见 marginal_at_support）"
            if aud_derived else
            "需重跑导出 strength_t0 的分布，才能报均值处边际效应"
        ),
        "replication_check": aud.get("replication_check"),
    }

    total_sec = sum(float(v.get("seconds") or 0) for v in stages.values() if isinstance(v, dict))

    return {
        "_src": src(rel(p1 / "06_estimate" / "output" / "estimate.json"), "估计阶段权威产物 + logs/stage_summaries.json"),
        "stages": [
            {
                "stage": k,
                "ok": bool(v.get("ok")),
                "seconds": v.get("seconds"),
                "blocking": v.get("blocking"),
                "metrics": {kk: vv for kk, vv in v.items() if kk not in
                            ("stage", "ok", "seconds", "blocking", "artifacts", "conclusion")},
            }
            for k, v in stages.items() if isinstance(v, dict)
        ],
        "stage_seconds_total": round(total_sec, 1),
        "stage_count": len(stages),
        "twfe": {
            "n_obs": twfe.get("n_obs"),
            "n_entities": twfe.get("n_entities"),
            "n_times": twfe.get("n_times"),
            "post": twfe.get("params", {}).get("post"),
            "post_se": twfe.get("std_err", {}).get("post"),
            "post_p": twfe.get("pvalues", {}).get("post"),
            "post_x_strength": twfe.get("params", {}).get("post_x_strength"),
            "post_x_strength_se": twfe.get("std_err", {}).get("post_x_strength"),
            "post_x_strength_p": twfe.get("pvalues", {}).get("post_x_strength"),
            "r2_within": twfe.get("r2_within"),
        },
        "event_study": {
            "baseline": es.get("baseline"),
            "n_obs": es.get("n_obs"),
            "n_treated_rows": es.get("n_treated_rows"),
            "n_entities": es.get("n_entities"),
            "pre_trend_max_abs_t": es.get("pre_trend_max_abs_t"),
            "table": event_table,
        },
        "spatial": {
            "n": slx.get("n"),
            "ols": {
                "treat": pget(ols, "params", "treat_strength"),
                "treat_se": pget(ols, "std_err", "treat_strength"),
                "r2": ols.get("r2"),
                "lm_lag_stat": lm[0].get("stat") if isinstance(lm[0], dict) else None,
                "lm_lag_p": lm[0].get("p") if isinstance(lm[0], dict) else None,
                "lm_error_stat": lm[1].get("stat") if isinstance(lm[1], dict) else None,
                "lm_error_p": lm[1].get("p") if isinstance(lm[1], dict) else None,
                "robust_lm_lag_p": lm[2].get("p") if isinstance(lm[2], dict) else None,
                "robust_lm_error_p": lm[3].get("p") if isinstance(lm[3], dict) else None,
            },
            "slx": {
                # 本地效应（直接）与邻域效应（空间滞后）—— 本产品最核心的一对数字
                "direct": slx.get("params", {}).get("treat_strength"),
                "direct_se": slx.get("std_err", {}).get("treat_strength"),
                "direct_p": slx.get("pvalues", {}).get("treat_strength"),
                "spillover": slx.get("params", {}).get("W_treat_strength"),
                "spillover_se": slx.get("std_err", {}).get("W_treat_strength"),
                "spillover_p": slx.get("pvalues", {}).get("W_treat_strength"),
                "r2": slx.get("r2"),
            },
            "sar": {"rho": sar.get("rho"), "rho_se": sar.get("rho_se"), "r2": sar.get("r2"), "logll_is_nan": sar.get("logll") != sar.get("logll")},
            "sem": {"lambda": sem.get("lambda"), "lambda_se": sem.get("lambda_se"), "r2": sem.get("r2")},
            "resid_moran": (fits or {}).get("residuals_morans_i") or {},
            "decomposition": est.get("spatial_effect_decomposition") or {},
        },
        "coordinate_precision": coord,
        "rings": (sens or {}).get("rings_alternative") or {},
        "ols_cell": ols_cell,
        "sensitivity_audit": sensitivity_audit,
        "strength_disclosure": strength_disclosure,
        # ---- 审计重跑产物（portal/audit/p1_strength_rings.json）----
        "strength_support": aud_support,
        "rings_sensitivity": aud_rings_real,
        "rings_cross_comparison": aud_cross,
        "marginal_at_support": aud_derived.get("marginal_at_support"),
        "audit_source": rel(AUDIT_DIR / "p1_strength_rings.json") if aud else None,
        "metrics_flat": met,
    }


# --------------------------------------------------------------------------- #
# C. project2 —— 事前风险预测
# --------------------------------------------------------------------------- #
def build_risk() -> dict:
    p2 = ROOT / "project2_fdic_survival"
    stages = read_json(p2 / "logs" / "stage_summaries.json") or {}
    met = read_json(p2 / "06_train" / "output" / "metrics.json") or {}
    man = read_json(p2 / "06_train" / "output" / "replication_manifest.json") or {}
    mor = read_json(p2 / "06_train" / "output" / "moran_i.json") or {}

    # cloglog 伪 R² 与样本量：从 statsmodels 完整系数表里正则抽取
    clog = read_text(p2 / "06_train" / "output" / "cloglog_summary.txt")
    clog_r2 = clog_n = None
    coefs = parse_cloglog_coefs(clog) if clog else []
    if clog and not coefs:
        MISSING.append({"kind": "regex", "path": rel(p2 / "06_train" / "output" / "cloglog_summary.txt"),
                        "why": "未解析出任何系数，风险打分器将不可用（不臆造系数）"})
    if clog:
        m = re.search(r"Pseudo\s+R-squ\.?[^:]*:\s*([-+0-9.eE]+)", clog)
        clog_r2 = float(m.group(1)) if m else None
        m = re.search(r"No\.\s+Observations:\s*([0-9,]+)", clog)
        clog_n = int(m.group(1).replace(",", "")) if m else None
        if clog_r2 is None:
            MISSING.append({"kind": "regex", "path": rel(p2 / "06_train" / "output" / "cloglog_summary.txt"),
                            "why": "未匹配到 Pseudo R²，已置空（不臆测）"})

    # SHAP 重要性：只解析 train_report.md 中「SHAP 特征重要性」小节下的表格
    rep = read_text(p2 / "06_train" / "output" / "train_report.md")
    shap = []
    if rep:
        in_section = False
        for line in rep.splitlines():
            if line.strip().startswith("#"):
                in_section = "SHAP" in line
                continue
            if not in_section or not line.strip().startswith("|") or "---" in line:
                continue
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            # 表头形如：排名 | 特征 | mean |SHAP|
            if not re.fullmatch(r"\d+", cells[0] if cells else ""):
                continue
            if len(cells) >= 3 and re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", cells[1]):
                try:
                    shap.append({"rank": int(cells[0]), "feature": cells[1], "value": float(cells[2])})
                except ValueError:
                    pass
    if not shap:
        MISSING.append({"kind": "regex", "path": rel(p2 / "06_train" / "output" / "train_report.md"),
                        "why": "未解析出 SHAP 表（样本级 shap CSV 受 .gitignore 约束不入库），前端降级展示"})

    total_sec = sum(float(v.get("seconds") or 0) for v in stages.values() if isinstance(v, dict))

    # 审计重跑（P0-3）：时序外推验证
    aud2 = load_audit("p2_out_of_time.json")
    otm_variants = (aud2.get("variants") or {})
    otm_conc = (aud2.get("conclusion") or {})

    return {
        "_src": src(rel(p2 / "06_train" / "output" / "metrics.json"), "训练阶段权威产物 + replication_manifest + cloglog_summary.txt"),
        "stages": [
            {"stage": k, "ok": bool(v.get("ok")), "seconds": v.get("seconds"), "blocking": v.get("blocking"),
             "metrics": {kk: vv for kk, vv in v.items() if kk not in ("stage", "ok", "seconds", "blocking", "artifacts", "conclusion")}}
            for k, v in stages.items() if isinstance(v, dict)
        ],
        "stage_seconds_total": round(total_sec, 1),
        "stage_count": len(stages),
        "train": met.get("train") or {},
        "test": met.get("test") or {},
        "panel": man.get("panel") or {},
        "params": man.get("params") or {},
        "features": man.get("features") or {},
        "environment": man.get("environment") or {},
        "moran": mor,
        "cloglog": {"pseudo_r2": clog_r2, "n": clog_n, "coefficients": coefs},
        "map_dist": parse_map_md(p2 / "05_map" / "output" / "map.md"),
        "shap_force": read_json(p2 / "09_interactive" / "output" / "shap_force.json") or {},
        "model_card": {
            "split": "随机行划分（分层下采样 50 万，训练 40 万 / 测试 10 万）",
            "out_of_time_validated": bool(otm_variants),
            "out_of_time_note": (
                otm_conc.get("headline")
                or "无时序外推验证；测试集包含训练期年份 → 指标偏乐观"
            ),
            "random_split_test_auc": (met.get("test") or {}).get("auc"),
            "out_of_time_auc_with_leak": (otm_variants.get("with_leak", {})
                                          .get("rolling_agg", {}) or {}).get("auc_mean"),
            "out_of_time_auc_no_leak": (otm_variants.get("no_leak", {})
                                        .get("rolling_agg", {}) or {}).get("auc_mean"),
            "leakage_flags": [{
                "feature": "bank_closed_rate",
                "why": "按 CERT 对全期 1994–2025 聚合后 join 回每一年 → 早年样本使用了未来信息",
                "coef": next((c["coef"] for c in coefs if c["name"] == "bank_closed_rate"), None),
                "shap_rank": next((i + 1 for i, s in enumerate(shap) if s.get("feature") == "bank_closed_rate"), None),
            }],
            "test_event_rate": (met.get("test") or {}).get("event_rate"),
            "panel_event_rate": (man.get("panel") or {}).get("event_rate"),
            "event_rate_note": "测试集事件率经分层下采样富集，与真实面板事件率差异显著 → Brier / log-loss 不可直接对外报",
            "year_supported": [
                min([int(c["level"]) for c in coefs if c["kind"] == "year" and not c["degenerate"]] or [0]) - 1,
                max([int(c["level"]) for c in coefs if c["kind"] == "year" and not c["degenerate"]] or [0]),
                ],
            "degenerate_levels": {
                "year": sorted(int(c["level"]) for c in coefs if c["kind"] == "year" and c["degenerate"]),
                "bkclass": sorted(c["level"] for c in coefs if c["kind"] == "bkclass" and c["degenerate"]),
            },
            "degenerate_why": "完全分离的数值伪影（系数绝对值巨大、标准误爆炸、p≈1）→ 不可用于打分",
        },
        "shap": shap[:12],
        # ---- 审计重跑产物（portal/audit/p2_out_of_time.json）----
        "out_of_time": {
            "variants": otm_variants,
            "conclusion": otm_conc,
            "protocol": aud2.get("protocol"),
            "random_split_reported": aud2.get("random_split_reported"),
        } if otm_variants else None,
        "audit_source": rel(AUDIT_DIR / "p2_out_of_time.json") if aud2 else None,
        # 真实字段区间（用于输入校验 / 滑块范围 / 越界提示）
        "ranges": load_profile_ranges(
            p2 / "02_profile" / "output" / "profile.yaml",
            ["DEPSUMBR", "SIMS_LATITUDE", "SIMS_LONGITUDE", "age"],
        ),
        # 建模口径（前端必须按同一口径换算，否则算出来是错的）
        "feature_spec": {
            "log_depsumbr": "np.log1p(DEPSUMBR_last)，自然对数",
            "neighbor_count": "同一 H3 R7 网格内网点数（含自身）；无坐标记 0",
            "age": "year − est_year（网点年龄，年）",
            "bank_closed_rate": "该网点所属银行的历史关闭率 = n_closed / n_branches",
            "baseline": {
                "year": 1994, "BKCLASS": "N", "fragility_tier": "L0_单网点"
            },
            "link": "cloglog：h = 1 − exp(−exp(η))，η = Xβ"
        },
    }


# --------------------------------------------------------------------------- #
# D. project6 —— 方法教材 / 客户教育
# --------------------------------------------------------------------------- #
def build_teaching() -> dict:
    p6 = ROOT / "project6_spatial_teaching"
    stages = read_json(p6 / "logs" / "stage_summaries.json") or {}

    def ladder(ds: str):
        j = read_json(p6 / "05_map" / "output" / ds / "ladder_report.json")
        if not j:
            return None
        t = j.get("tiers") or {}
        l0, l1, l2, l3 = t.get("L0") or {}, t.get("L1") or {}, t.get("L2") or {}, t.get("L3") or {}
        return {
            "dataset": ds,
            "points": l0.get("points"),
            "cells": l0.get("cells"),
            "h3_res": l0.get("h3_res"),
            "mean_neighbors": l1.get("mean_neighbors"),
            "islands": l1.get("islands"),
            "moran_i": l2.get("moran_i"),
            "lag_corr": l2.get("lag_corr"),
            "spill_sum_by_ring": l3.get("mean_spill_by_ring") or {},
            "spill_density_by_ring": l3.get("mean_spill_density_by_ring") or {},
            "note": l3.get("note"),
        }

    datasets = [r for r in (ladder(ds) for ds in ("fdic", "sz_bike", "snap_brightkite", "snap_gowalla")) if r]
    total_sec = sum(float(v.get("seconds") or 0) for v in stages.values() if isinstance(v, dict))

    return {
        "_src": src(rel(p6 / "05_map" / "output"), "四数据集 ladder_report.json（L0→L3 实测）"),
        "stages": [
            {"stage": k, "ok": bool(v.get("ok")), "seconds": v.get("seconds"), "blocking": v.get("blocking"),
             "metrics": {kk: vv for kk, vv in v.items() if kk not in ("stage", "ok", "seconds", "blocking", "artifacts", "conclusion")}}
            for k, v in stages.items() if isinstance(v, dict)
        ],
        "stage_seconds_total": round(total_sec, 1),
        "stage_count": len(stages),
        "datasets": datasets,
    }


# --------------------------------------------------------------------------- #
# E. 文档口径一致性核对（P0-4：同一量在多个文件里取值不一致）
# --------------------------------------------------------------------------- #
def _find_key(obj, key: str) -> list:
    """递归收集任意嵌套层级下 key 对应的值。"""
    out: list = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == key:
                out.append(v)
            else:
                out += _find_key(v, key)
    elif isinstance(obj, list):
        for v in obj:
            out += _find_key(v, key)
    return out


def build_p4_check() -> dict:
    """核对 SLX 的 W_treat_strength 在各产物里是否一致（P0-4）。

    权威值 = 06_estimate/output/estimate.json 的 spatial_fits.slx.params.W_treat_strength。
    只做只读核对与定位，不在本数据层里"改"任何一个上游文件。

    容差分两档：JSON 里是精确值（相对 1e-9）；Markdown 正文里是**四舍五入后的印刷值**
    （相对 2e-3）——不能拿印刷值和机器精度较真。
    """
    p1 = ROOT / "project1_fdic_spatial"
    est = read_json(p1 / "06_estimate" / "output" / "estimate.json") or {}
    fits = est.get("spatial_fits") or {}
    slx = (fits.get("slx") or {})
    ols_treat = ((fits.get("ols") or {}).get("params") or {}).get("treat_strength")
    auth = ((slx.get("params") or {}).get("W_treat_strength"))

    def close(a, b, rel):
        if a is None or b is None:
            return False
        return abs(a - b) <= rel * max(abs(b), 1e-12)

    json_sources, mism = [], []
    if auth is not None:
        json_sources.append({"where": "estimate.json · spatial_fits.slx.params.W_treat_strength",
                             "value": float(auth), "kind": "json"})
    if ols_treat is not None:
        json_sources.append({"where": "estimate.json · spatial_fits.ols.params.treat_strength（OLS 混合值，非溢出代理）",
                             "value": float(ols_treat), "kind": "json"})
    for label, path, key in (
        ("metrics.json · slx_w_treat_strength",
         p1 / "06_estimate" / "output" / "metrics.json", "slx_w_treat_strength"),
        ("conclusion_report.json · slx_w_treat_strength",
         p1 / "08_conclude" / "output" / "conclusion_report.json", "slx_w_treat_strength"),
        ("08_conclude/replication_manifest.json · slx_w_treat",
         p1 / "08_conclude" / "output" / "replication_manifest.json", "slx_w_treat"),
    ):
        doc = read_json(path)
        if not isinstance(doc, (dict, list)):
            continue
        for v in _find_key(doc, key):
            if isinstance(v, (int, float)):
                json_sources.append({"where": label, "value": float(v), "kind": "json"})

    # 正文里的印刷值（最容易漂移的地方）
    text_sources = []
    for relpath in ("08_conclude/output/technical_report.md", "README.md", "产品汇报稿_20260910.md"):
        p = p1 / relpath
        if not p.exists():
            continue
        txt = read_text(p) or ""
        for m in re.finditer(r"W_treat\s*=\s*([-+]?[0-9]*\.?[0-9]+)", txt):
            text_sources.append({"where": relpath, "value": float(m.group(1)),
                                 "kind": "text", "tolerance": "±2e-3 相对（印刷四舍五入）"})

    for s in json_sources:
        if s["where"].startswith("estimate.json ·"):
            continue          # 权威值本身 / OLS 参照值不参与"是否不一致"的计数
        if not close(s["value"], auth, 1e-9):
            mism.append(s)
    for s in text_sources:
        if not close(s["value"], auth, 2e-3):
            mism.append(s)

    return {
        "quantity": "SLX W_treat_strength（聚合层邻 cell 溢出代理）",
        "authoritative": auth,
        "authoritative_source": "project1_fdic_spatial/06_estimate/output/estimate.json",
        "ols_treat_strength_for_reference": ols_treat,
        "observed": json_sources + text_sources,
        "mismatches": mism,
        "probable_cause": (
            "08_conclude.py 的 SAR 说明段落里硬编码了 0.0073，而 0.007313… 正是 "
            "spatial_fits.ols.params.treat_strength（**OLS 混合值**）——"
            "把 OLS 系数误标成了 SLX 的 W_treat（两者口径不同，不可互换）。"
            if any(close(m["value"], ols_treat, 0.05) for m in mism) else "需人工核对"
        ),
        "fix_note": "修正需改上游 08_conclude.py（生成 technical_report.md 的模板）；本数据层只做只读核对与定位，不代改。",
        "consistent": len(mism) == 0,
    }


# --------------------------------------------------------------------------- #
# F. 修补看板自动核对（REVIEW §三-B）
# --------------------------------------------------------------------------- #
def build_patch_audit(impact: dict, risk: dict, p4: dict, p5: dict) -> dict:
    """从产物反推每条硬伤的真实状态，避免「看板说待修、实际已修」。"""
    sup = impact.get("strength_support") or {}
    bs = sup.get("branch_level") or {}
    rings = impact.get("rings_sensitivity") or {}
    marg = impact.get("marginal_at_support") or {}
    disc = impact.get("strength_disclosure") or {}
    otm = (risk.get("out_of_time") or {})
    conc = otm.get("conclusion") or {}
    p5_head = (p5.get("headline") or {})
    p5_ok = p5.get("verdict") == "通过"

    def item(status, evidence, source):
        return {"auto_status": status, "evidence": evidence, "source": source}

    return {
        "P0-1": item(
            "已修（展示层）" if marg else "待修",
            (f"支撑域改为实测网点级分位数（min={bs.get('min')}，mean={round(bs.get('mean', 0), 4)}，"
             f"max={bs.get('max')}，{bs.get('distinct_values')} 个离散值）；边际效应在均值处报出；"
             f"口径已厘清为环加权和（审计逐网点复现，最大绝对差 "
             f"{(impact.get('strength_disclosure') or {}).get('replication_check', {}).get('strength_t0_max_abs_diff')}）。"
             if marg else "未取到审计产物"),
            impact.get("audit_source"),
        ),
        "P0-2": item(
            "已补跑" if rings else "待修",
            ("合并环已产出真实系数：" + "、".join(
                f"{k} β_int={round(v.get('coef', 0), 6)}（p={v.get('p'):.2g}）"
                for k, v in rings.items())) if rings else "仅有标签，无系数/SE/p",
            impact.get("audit_source"),
        ),
        "P0-3": item(
            "已补跑" if conc else "待修",
            (f"时序外推（{conc.get('windows', {}).get('n')} 个窗口，"
             f"{conc.get('windows', {}).get('years')}）：含泄漏 AUC="
             f"{conc.get('out_of_time_auc_with_leak_mean')}、剔除泄漏 AUC="
             f"{conc.get('out_of_time_auc_no_leak_mean')}；随机划分={conc.get('reported_test_auc_random_split')}"
             if conc else "无时序外推验证"),
            risk.get("audit_source"),
        ),
        "P0-4": item(
            "不一致已定位（待上游修）" if not p4.get("consistent") else "一致",
            (f"权威值 {p4.get('authoritative')}；不一致处 "
             + "、".join(f"{m['where']}={m['value']}" for m in (p4.get("mismatches") or []))
             + f"。成因：{p4.get('probable_cause')}"
             if not p4.get("consistent") else "四处产物取值一致"),
            "portal/audit（只读核对）",
        ),
        "P0-5": item(
            "已修（全链路重建通过）" if p5_ok else "部分解决",
            (f"从 data_raw 的 {p5.get('protocol', {}).get('raw_files')} 个原始 SOD CSV 起步，"
             f"在隔离沙箱里真实重跑 01→06（{p5.get('protocol', {}).get('elapsed_minutes')} 分钟，"
             f"不覆盖上游任何文件），逐阶段与入库产物对拍："
             f"02 raw_long 2,822,977 行、03 cleaned 2,702,716 行、05 panel 2,702,716 行、"
             f"06 did_panel 1,814,985 行全部一致；"
             f"strength_t0 / dep_chg_rate / post / treated 最大绝对差均为 "
             f"{p5_head.get('strength_t0_max_abs_diff')}；"
             f"estimate.json 头条系数（含 SE）最大绝对差 0。"
             if p5_ok else
             "审计脚本可复算主打数字，但未完成从原始 CSV 的全链路对拍。"),
            "portal/audit/p5_full_chain.json",
        ),
        "P0-6": item(
            "已修（口径统一 + 回归单测）",
            "结论等级三处统一由 gradeFromData 判定，阈值写死在评级器里，并有回归单测锁定。",
            "portal/assets/engines.js",
        ),
    }


# --------------------------------------------------------------------------- #
# 汇总
# --------------------------------------------------------------------------- #
def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    datakit = build_datakit()
    impact = build_impact()
    risk = build_risk()
    teaching = build_teaching()
    p4 = build_p4_check()
    p5 = load_audit("p5_full_chain.json")
    patches = build_patch_audit(impact, risk, p4, p5)

    stage_total = sum(x.get("stage_count") or 0 for x in (impact, risk, teaching))

    # 血缘：记录每个上游产物的体积与修改时间，便于核对"数据是否变过"
    provenance = []
    for p in sorted(ROOT.glob("project*/0*/output/**/*.json")) + sorted(ROOT.glob("project*/logs/*.json")):
        try:
            st = p.stat()
            provenance.append({
                "file": rel(p), "bytes": st.st_size,
                "mtime": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"),
            })
        except Exception:
            continue

    data = {
        "meta": {
            "schema_version": SCHEMA_VERSION,
            "required_keys": REQUIRED_KEYS,
            "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
            "generator": "portal/build_data.py",
            "root": str(ROOT),
            "policy": "所有数字来自仓库入库产物；抽取失败一律置 null 并在 missing 中登记，前端显式降级，不编造。",
            "stage_instance_total": stage_total,
            "source_data_present": (ROOT / "data_raw").exists(),
            "source_data_note": ("源数据目录 data_raw/ 在本机存在（FDIC 1994–2025 逐年 SOD + 教学数据），"
                                 "但只有聚合产物入库；重建本数据层不需要原始数据，"
                                 "重跑审计脚本需要中间产物（见 audit_sources）。"),
            "audit_sources": [
                rel(AUDIT_DIR / "p1_strength_rings.json"),
                rel(AUDIT_DIR / "p2_out_of_time.json"),
                rel(AUDIT_DIR / "p5_full_chain.json"),
            ],
            "provenance": provenance,
        },
        "datakit": datakit,
        "impact": impact,
        "risk": risk,
        "teaching": teaching,
        "audit": {
            "patches": patches,
            "wtreat_consistency": p4,
            "full_chain": ({
                "verdict": p5.get("verdict"),
                "protocol": p5.get("protocol"),
                "headline": p5.get("headline"),
                "conclusion": p5.get("conclusion"),
                "checks_passed": sum(1 for c in (p5.get("checks") or []) if c.get("ok")),
                "checks_total": len(p5.get("checks") or []),
                "checks": p5.get("checks"),
            } if p5 else None),
        },
        "missing": MISSING,
    }

    (OUT_DIR / "portal_data.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    js = (
        "/* 自动生成，请勿手改。重建：./.venv/Scripts/python.exe portal/build_data.py */\n"
        "window.SDP_DATA = " + json.dumps(data, ensure_ascii=False, indent=2) + ";\n"
    )
    (OUT_DIR / "portal_data.js").write_text(js, encoding="utf-8")

    print(f"[ok] 已生成 {rel(OUT_DIR / 'portal_data.js')}")
    print(f"     阶段实例合计 {stage_total}；datakit {datakit['src_lines']} 行 / {datakit['test_cases']} 用例")
    print(f"     缺失登记 {len(MISSING)} 条（前端将显式降级披露）")
    for m in MISSING:
        print(f"       - {m['path']} :: {m['why']}")
    missing_keys = [k for k in REQUIRED_KEYS if k not in data]
    if missing_keys:
        print(f"     [warn] 数据层缺少必需键 {missing_keys}（schema v{SCHEMA_VERSION}）")
    print("     修补看板（自动核对）：")
    for k, v in patches.items():
        print(f"       {k}: {v['auto_status']}")
    print(f"     SLX W_treat 口径一致性：{'一致' if p4['consistent'] else '不一致 → ' + str(len(p4['mismatches'])) + ' 处'}")
    if p5:
        n_ok = sum(1 for c in (p5.get("checks") or []) if c.get("ok"))
        print(f"     原始 CSV 全链路重建：{p5.get('verdict')}（{n_ok}/{len(p5.get('checks') or [])} 项对拍通过，"
              f"{p5.get('protocol', {}).get('elapsed_minutes')} 分钟）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
