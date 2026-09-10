# -*- coding: utf-8 -*-
"""09_interactive · 数据层：把上游产物读成「产品事实表」。

为什么单独拆一层
----------------
09 是**展示层**，本不该自己算指标。但上游格级/样本级 CSV
（``logit_coefficients.csv`` / ``test_predictions.csv`` / ``branch_panel.csv`` /
``cloglog_coefficients.csv``）受仓库根 ``.gitignore`` 约束**不入库**
（``*/*/*/*.csv``），重跑 ⑤⑥ 又要 1.58 GB 原始数据 —— **本仓库里跑 ⑨ 会直接
FileNotFoundError**（这就是本次改造要修的第一个真问题）。

因此这里定一条口径，和 project6 的 ⑧ 保持一致：

1. **入库产物为权威源**：``metrics.json`` / ``moran_i.json`` /
   ``replication_manifest.json`` / ``cloglog_summary.txt``（**完整系数表，可解析**）/
   ``train_report.md``（**SHAP 重要性表，可解析**）/ ``shap_force.json``（**3 个真实
   样本的 SHAP 分解**）/ ``08_conclude/output/conclusion_report.json``（8 条限制 + 5 条止损）/
   ``07_visualize/output/``（6 张真实静态图）/ ``05_map/output/map.md``（**字段真实取值区间**）。
2. **样本级 CSV 是可选增强**：在 → 出可交互 KM/ROC/动图/保真度自检；
   不在 → 相关面板降级为「上游静态图 + 说明」，**绝不让阶段失败**
   （本阶段 ``blocking: false``）。
3. 缺数据要**明说**，不画编出来的图。
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

# --------------------------------------------------------------------------- #
# 基础读取
# --------------------------------------------------------------------------- #
def _read_json(p: Path) -> dict | None:
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def _read_yaml(p: Path) -> dict | None:
    return (yaml.safe_load(p.read_text(encoding="utf-8")) or None) if p.exists() else None


# --------------------------------------------------------------------------- #
# ① cloglog 系数表（statsmodels 纯文本摘要 → 结构化）
# --------------------------------------------------------------------------- #
_ROW = re.compile(
    r"^(?P<name>.*?)\s{2,}"
    r"(?P<coef>-?[\d.]+(?:e[+-]?\d+)?)\s+"
    r"(?P<se>-?[\d.]+(?:e[+-]?\d+)?)\s+"
    r"(?P<z>-?[\d.]+(?:e[+-]?\d+)?)\s+"
    r"(?P<p>-?[\d.]+(?:e[+-]?\d+)?)\s+"
    r"(?P<lo>-?[\d.]+(?:e[+-]?\d+)?)\s+"
    r"(?P<hi>-?[\d.]+(?:e[+-]?\d+)?)\s*$")

# 完美分离（perfect separation）产生的退化行：系数 ~ -26、标准误 ~ 4e4、p≈1。
# 这些是数值伪影，不是真实效应 —— 必须剔除，否则森林图会被 -26 的量级压平。
_DEGENERATE_SE = 100.0
_DEGENERATE_ABS_COEF = 10.0


def parse_cloglog_summary(path: Path) -> list[dict]:
    """解析 ``cloglog_summary.txt`` 的系数表。

    返回 ``[{name, coef, se, z, p, lo, hi, degenerate}]``，已剔除完美分离的退化行。
    """
    if not path.exists():
        return []
    out: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        m = _ROW.match(line.rstrip())
        if not m:
            continue
        g = m.groupdict()
        try:
            row = {"name": g["name"].strip(),
                   "coef": float(g["coef"]), "se": float(g["se"]),
                   "z": float(g["z"]), "p": float(g["p"]),
                   "lo": float(g["lo"]), "hi": float(g["hi"])}
        except ValueError:
            continue
        row["degenerate"] = bool(abs(row["coef"]) > _DEGENERATE_ABS_COEF
                                 or row["se"] > _DEGENERATE_SE)
        out.append(row)
    return out


def coef_kind(name: str) -> str:
    """把 statsmodels 的哑变量名还原成可读分组。"""
    if name == "Intercept":
        return "截距"
    if name.startswith("C(year)"):
        return "年份"
    if name.startswith("C(BKCLASS)"):
        return "银行类别"
    if name.startswith("C(fragility_tier)"):
        return "银行脆弱性"
    return "网点特征"


def coef_label(name: str) -> str:
    """``C(year)[T.2010]`` → ``2010``；``C(fragility_tier)[T.L2_多网点地理分散]`` → ``L2_多网点地理分散``。"""
    m = re.match(r"^C\([^)]+\)\[T\.(.+)\]$", name)
    return m.group(1) if m else name


# --------------------------------------------------------------------------- #
# ② SHAP 重要性表（train_report.md → 结构化）
# --------------------------------------------------------------------------- #
_SHAP_ROW = re.compile(r"^\|\s*(\d+)\s*\|\s*([A-Za-z_][\w]*)\s*\|\s*([\d.]+)\s*\|\s*$")

FEATURE_LABEL = {
    "year": ("年份", "危机后整合窗口把风险整体抬高"),
    "bank_closed_rate": ("所属银行历史关闭率", "银行自身的历史裁撤倾向，最强单点因子"),
    "fragility_tier": ("银行脆弱性分层", "多网点且地理分散的银行更易被整合"),
    "BKCLASS": ("银行类别", "监管分类（N/NM/SM/SB/SA…）"),
    "log_depsumbr": ("存款规模（对数）", "规模是护城河：越大越长寿"),
    "lat": ("纬度", "地理基线（含未建模的本地因素）"),
    "neighbor_count": ("同格网点数（竞争强度）", "本地竞争密度"),
    "lng": ("经度", "地理基线（含未建模的本地因素）"),
    "age": ("网点年龄", "年龄效应被左截断污染，不宜直接解读"),
}


def parse_shap_table(path: Path) -> list[dict]:
    """解析 ``06_train/output/train_report.md`` 的 SHAP 重要性表。"""
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        m = _SHAP_ROW.match(line.strip())
        if not m:
            continue
        rank, feat, val = int(m.group(1)), m.group(2), float(m.group(3))
        lab, note = FEATURE_LABEL.get(feat, (feat, ""))
        rows.append({"rank": rank, "feature": feat, "label": lab,
                     "mean_abs_shap": val, "note": note})
    return rows


# --------------------------------------------------------------------------- #
# ③ 字段真实取值区间（05_map/output/map.md → 结构化）
# --------------------------------------------------------------------------- #
_FIELD_ROW = re.compile(r"^\|\s*(?P<name>\w+)\s*\|(?P<rest>.*)\|\s*$")
_KV = re.compile(r"(?P<k>[A-Za-z_]+)\s*=\s*(?P<v>-?[\d.eE+]+)")


def parse_field_stats(path: Path) -> dict[str, dict[str, float]]:
    """解析 ``map.md`` 的「映射后字段数据报告」表。

    这是**唯一入库的字段取值来源**：没有它，demo 的滑块区间就只能靠猜。
    """
    if not path.exists():
        return {}
    out: dict[str, dict[str, float]] = {}
    in_table = False
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s.startswith("## 映射后字段数据报告"):
            in_table = True
            continue
        if in_table and s.startswith("## ") and not s.startswith("## 映射后"):
            break
        if not in_table or not s.startswith("|"):
            continue
        m = _FIELD_ROW.match(s)
        if not m or m.group("name") in ("字段",):
            continue
        stats = {mm.group("k"): float(mm.group("v"))
                 for mm in _KV.finditer(m.group("rest"))}
        if stats:
            out[m.group("name")] = stats
    return out


def parse_profile_fields(path: Path) -> dict[str, dict[str, float]]:
    """解析 ``02_profile/output/profile.yaml`` 的字段统计（含 min / std）。

    ``map.md`` 只有 mean/median/max，**没有 min 也没有 std**；而 demo 滑块需要一个下界，
    经纬度还需要一个「正常区间」。所以 lat / lng 的区间取 ``mean ± 3σ``
    （σ 来自 ② 画像），并在页面上标注来源 —— 不猜、不写死。
    """
    y = _read_yaml(path)
    if not y:
        return {}
    out: dict[str, dict[str, float]] = {}
    for f in y.get("fields", []):
        try:
            out[str(f.get("field"))] = {
                k: float(f[k]) for k in ("min", "max", "mean", "std", "median")
                if f.get(k) is not None
            }
        except (TypeError, ValueError):
            continue
    return out


# --------------------------------------------------------------------------- #
# ④ 汇总
# --------------------------------------------------------------------------- #
CRISIS = (2009, 2014)          # 危机后整合窗口（07_visualize 的既有发现：关闭率翻倍）


def load_facts(root: Path) -> dict[str, Any]:
    """汇总成产品事实表（供所有交互件共用）。"""
    metrics = _read_json(root / "06_train" / "output" / "metrics.json") or {}
    moran = _read_json(root / "06_train" / "output" / "moran_i.json") or {}
    repl = _read_json(root / "06_train" / "output" / "replication_manifest.json") or {}
    concl = _read_json(root / "08_conclude" / "output" / "conclusion_report.json") or {}
    shap_force = _read_json(root / "09_interactive" / "output" / "shap_force.json")

    coefs = [c for c in parse_cloglog_summary(
        root / "06_train" / "output" / "cloglog_summary.txt") if not c["degenerate"]]
    shap_imp = parse_shap_table(root / "06_train" / "output" / "train_report.md")
    fields = parse_field_stats(root / "05_map" / "output" / "map.md")
    profile = parse_profile_fields(root / "02_profile" / "output" / "profile.yaml")

    # 07 静态图（教材/汇报配图，真实产物）
    figs = _read_json(root / "07_visualize" / "output" / "manifest.json") or {}
    return {
        "metrics": metrics, "moran": moran, "repl": repl, "concl": concl,
        "shap_force": shap_force, "coefs": coefs, "shap_imp": shap_imp,
        "fields": fields, "profile": profile, "viz": figs, "crisis": CRISIS,
        "test": metrics.get("test", {}), "train": metrics.get("train", {}),
        "key": concl.get("key_numbers", {}),
        "limits": concl.get("known_limits", []),
        "stops": concl.get("stop_conditions", []),
        "headline": concl.get("headline", ""),
    }


def csv_status(root: Path) -> dict[str, Any]:
    """样本级 CSV 是否可用（决定 KM/ROC/动图/保真度自检能否生成）。"""
    need = {
        "logit_coefficients": root / "06_train" / "output" / "logit_coefficients.csv",
        "test_predictions": root / "06_train" / "output" / "test_predictions.csv",
        "branch_panel": root / "05_map" / "output" / "data" / "branch_panel.csv",
        "cloglog_coefficients": root / "06_train" / "output" / "cloglog_coefficients.csv",
    }
    present = [k for k, p in need.items() if p.exists()]
    missing = [k for k, p in need.items() if not p.exists()]
    return {"available": bool(present), "present": present, "missing": missing,
            "demo_ready": ("logit_coefficients" in present and "test_predictions" in present)}


# --------------------------------------------------------------------------- #
# ⑤ 07_visualize 静态图复制到 output/assets/fig/（整体可拷走，不裂图）
# --------------------------------------------------------------------------- #
def collect_static_figs(root: Path, assets_dir: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    src_dir = root / "07_visualize" / "output" / "figures"
    if not src_dir.exists():
        return out
    assets_dir.mkdir(parents=True, exist_ok=True)
    for p in sorted(src_dir.glob("*.png")):
        dst = assets_dir / p.name
        if (not dst.exists()) or (p.stat().st_mtime > dst.stat().st_mtime):
            dst.write_bytes(p.read_bytes())
        out[p.stem] = dst.name
    return out
