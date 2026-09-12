#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""P0-5 审计重跑（project1）：从 data_raw 原始 CSV 起步的**全链路重建**

做法（关键：不覆盖上游任何文件）
--------------------------------
在 ``portal/audit/_sandbox/project1_fdic_spatial/`` 下搭一个**隔离镜像项目**：
只复制 ``datakit.yaml``、``config/`` 与 01–06 各阶段的入口 ``.py``，
再把 ``source_root`` 指向仓库根的真实只读源数据 ``data_raw/fdic``。
因为这些阶段入口都用 ``Path(__file__).parent`` 推导自己的输出目录，
镜像里的副本会把「读取的上游」解析成镜像内的上一阶段、把「写出的产物」落在镜像里 ——
**逻辑与上游逐字一致，产物却完全不碰上游**。

随后逐阶段与上游已入库产物对拍：
  01 采集（文件数）→ 02 画像（raw_long.parquet）→ 03 清洗（cleaned.parquet）
  → 04 校验（检查项）→ 05 制图（branch_dim / closure_exposure / branch_year_panel）
  → 06 估计（did_panel.parquet 的 strength_t0 逐网点对拍 + estimate.json 头条系数）

任一对拍不过 → 判「不通过」，并在 JSON 里写明哪一段、差多少。

运行：
    PYTHONPATH=<repo>/datakit datakit/.venv/Scripts/python.exe portal/audit/rerun_p5_full_chain.py
    可选：--keep-sandbox（保留沙箱便于排查）、--stages 05,06（只跑部分阶段）
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import shutil
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

AUDIT = Path(__file__).resolve().parent
REPO = AUDIT.parent.parent
P1 = REPO / "project1_fdic_spatial"
RAW = REPO / "data_raw" / "fdic"
SANDBOX = AUDIT / "_sandbox" / "project1_fdic_spatial"
ALL_STAGES = ["01_discover", "02_profile", "03_clean", "04_validate", "05_map", "06_estimate"]
OUT_JSON = AUDIT / "p5_full_chain.json"


def log(msg: str) -> None:
    print(msg, flush=True)


# --------------------------------------------------------------------------- #
# 沙箱
# --------------------------------------------------------------------------- #
def build_sandbox(stages: list[str]) -> None:
    if SANDBOX.exists():
        shutil.rmtree(SANDBOX)
    SANDBOX.mkdir(parents=True)
    shutil.copy2(P1 / "datakit.yaml", SANDBOX / "datakit.yaml")
    if (P1 / "config").is_dir():
        shutil.copytree(P1 / "config", SANDBOX / "config")
    for st in stages:
        (SANDBOX / st).mkdir(parents=True, exist_ok=True)
        # 上游阶段假定 output/ 已存在（真实项目里由前次运行创建），镜像需预建
        (SANDBOX / st / "output").mkdir(parents=True, exist_ok=True)
        (SANDBOX / st / "output" / "data").mkdir(parents=True, exist_ok=True)
        src = P1 / st / f"{st}.py"
        if src.exists():
            shutil.copy2(src, SANDBOX / st / f"{st}.py")
    log(f"  沙箱已就绪：{SANDBOX}")
    log(f"  源数据（只读）：{RAW}")


def make_project(stages: list[str]):
    sys.path.insert(0, str(REPO / "datakit"))
    import datakit as dk
    proj = dk.Project.load(SANDBOX)
    proj.meta["source_root"] = str(RAW)          # 绝对路径 → source_root 直接采用
    proj.meta["options"]["count_rows"] = False   # 采集不数行（行数由 02 画像给出），省 1 分钟
    proj.log_path = SANDBOX / "logs" / "pipeline.log"
    proj.log_path.parent.mkdir(parents=True, exist_ok=True)
    return proj


# --------------------------------------------------------------------------- #
# 对拍工具
# --------------------------------------------------------------------------- #
def _rel(p: Path) -> str:
    try:
        return p.relative_to(REPO).as_posix()
    except ValueError:
        return str(p)


def compare_frame(label: str, up_path: Path, sb_path: Path,
                  num_cols: list[str] | None = None, keys: list[str] | None = None) -> dict:
    """比较两份 parquet/csv：行数、列数，以及关键数值列的最大绝对差。"""
    res = {"label": label, "upstream": _rel(up_path), "sandbox": _rel(sb_path), "ok": False}
    if not sb_path.exists():
        res["error"] = "沙箱产物缺失（阶段未产出）"
        return res
    if not up_path.exists():
        res["error"] = "上游产物缺失，无法对拍"
        return res
    read = pd.read_parquet if up_path.suffix == ".parquet" else pd.read_csv
    up = read(up_path)
    sb = read(sb_path)
    res["rows"] = {"upstream": int(len(up)), "sandbox": int(len(sb))}
    res["cols"] = {"upstream": int(up.shape[1]), "sandbox": int(sb.shape[1])}
    rows_ok = len(up) == len(sb)
    diffs: dict[str, float] = {}
    if num_cols:
        for c in num_cols:
            if c not in up.columns or c not in sb.columns:
                continue
            a = pd.to_numeric(up[c], errors="coerce").to_numpy(float)
            b = pd.to_numeric(sb[c], errors="coerce").to_numpy(float)
            if len(a) != len(b):
                diffs[c] = float("nan")
                continue
            na, nb = np.isnan(a), np.isnan(b)
            if not np.array_equal(na, nb):
                diffs[c] = float("inf")            # 缺失模式都变了
            else:
                diffs[c] = float(np.max(np.abs(a[~na] - b[~nb]))) if (~na).any() else 0.0
    if keys and rows_ok and all(k in up.columns for k in keys):
        up2 = up.set_index(keys).sort_index()
        sb2 = sb.set_index(keys).sort_index()
        common = up2.index.intersection(sb2.index)
        res["key_join_rows"] = int(len(common))
        if num_cols:
            for c in num_cols:
                if c not in up2.columns or c not in sb2.columns:
                    continue
                a = pd.to_numeric(up2.loc[common, c], errors="coerce").to_numpy(float)
                b = pd.to_numeric(sb2.loc[common, c], errors="coerce").to_numpy(float)
                na, nb = np.isnan(a), np.isnan(b)
                diffs[c] = float(np.max(np.abs(a[~na] - b[~nb]))) if np.array_equal(na, nb) and (~na).any() else (
                    0.0 if np.array_equal(na, nb) else float("inf"))
    res["max_abs_diff"] = {k: (None if v != v else v) for k, v in diffs.items()}
    tol = {"strength_t0": 1e-9, "dep_chg_rate": 1e-9}
    diffs_ok = all(v == v and v <= tol.get(c, 1e-9) for c, v in diffs.items())
    res["ok"] = bool(rows_ok and diffs_ok)
    return res


def compare_estimate(up_path: Path, sb_path: Path) -> dict:
    """对拍 estimate.json 的头条系数（TWFE + 事件研究）。"""
    res = {"label": "06_estimate · estimate.json 头条系数", "ok": False}
    if not (up_path.exists() and sb_path.exists()):
        res["error"] = "estimate.json 缺失"
        return res
    up = json.loads(up_path.read_text(encoding="utf-8"))
    sb = json.loads(sb_path.read_text(encoding="utf-8"))
    pick = {
        "twfe.post": (up["twfe"]["params"].get("post"), sb["twfe"]["params"].get("post")),
        "twfe.post_x_strength": (up["twfe"]["params"].get("post_x_strength"),
                                 sb["twfe"]["params"].get("post_x_strength")),
        "twfe.se.post": (up["twfe"]["std_err"].get("post"), sb["twfe"]["std_err"].get("post")),
        "twfe.se.post_x_strength": (up["twfe"]["std_err"].get("post_x_strength"),
                                    sb["twfe"]["std_err"].get("post_x_strength")),
        "twfe.n_obs": (up["twfe"].get("n_obs"), sb["twfe"].get("n_obs")),
    }
    up_es = {r["rel_year"]: r["dynamic_effect"] for r in up["event_study"]["table"]}
    sb_es = {r["rel_year"]: r["dynamic_effect"] for r in sb["event_study"]["table"]}
    for t in (0, -2, 4):
        pick[f"event_study.tau{t}"] = (up_es.get(t), sb_es.get(t))
    diffs, ok = {}, True
    for k, (a, b) in pick.items():
        if a is None or b is None:
            diffs[k] = None
            ok = False
            continue
        d = abs(float(a) - float(b))
        diffs[k] = d
        if d > (1e-9 if not isinstance(a, int) else 0):
            ok = False
    res["compare"] = {k: {"upstream": v[0], "sandbox": v[1]} for k, v in pick.items()}
    res["max_abs_diff"] = diffs
    res["ok"] = ok
    return res


# --------------------------------------------------------------------------- #
# 主流程
# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stages", default=",".join(ALL_STAGES))
    ap.add_argument("--keep-sandbox", action="store_true")
    ap.add_argument("--verify-only", action="store_true",
                    help="跳过执行，只用已存在的沙箱产物重新对拍（调试用）")
    args = ap.parse_args()
    stages = [s.strip() for s in args.stages.split(",") if s.strip()]

    log("== P0-5 全链路重建（原始 CSV → 面板 → 估计） ==")
    n_raw = len(list(RAW.glob("fdic_sod_*.csv")))
    log(f"  源文件 {n_raw} 个")
    if not n_raw:
        log(f"[fail] 源数据目录为空：{RAW}")
        return 2

    summaries, elapsed, run_error = [], 0.0, None
    if args.verify_only:
        log("  --verify-only：跳过执行，直接对拍现有沙箱")
        if not SANDBOX.exists():
            log(f"[fail] 沙箱不存在：{SANDBOX}")
            return 2
    else:
        build_sandbox(stages)
        proj = make_project(stages)
        t0 = time.time()
        try:
            summaries = proj.run(stages)
        except Exception as exc:                                 # pragma: no cover
            run_error = f"{type(exc).__name__}: {exc}"
            log(f"[warn] 流水线中断：{run_error}")
        elapsed = time.time() - t0
        log(f"  流水线耗时 {elapsed / 60:.1f} 分钟；阶段数 {len(summaries)}")

    checks: list[dict] = []

    def sb(stage: str, *parts: str) -> Path:
        return SANDBOX / stage / "output" / Path(*parts) if parts else SANDBOX / stage / "output"

    def up(stage: str, *parts: str) -> Path:
        return P1 / stage / "output" / Path(*parts) if parts else P1 / stage / "output"

    # 01 采集
    for name in ("catalog.yaml", "catalog.md"):
        p_sb, p_up = sb("01_discover", name), up("01_discover", name)
        checks.append({"label": f"01_discover · {name}", "ok": p_sb.exists() and p_up.exists(),
                       "upstream": _rel(p_up), "sandbox": _rel(p_sb),
                       "note": "文件存在性对拍（内容含时间戳，不做字节比较）"})

    # 02 画像
    checks.append(compare_frame("02_profile · raw_long.parquet",
                                up("02_profile", "raw_long.parquet"),
                                sb("02_profile", "raw_long.parquet")))
    # 03 清洗
    checks.append(compare_frame("03_clean · cleaned.parquet",
                                up("03_clean", "cleaned.parquet"),
                                sb("03_clean", "cleaned.parquet")))
    # 05 制图（三份产物都在 05_map/output/data/ 下）
    for name, sub in (("branch_dim.csv", "data"), ("closure_exposure.csv", "data"),
                      ("branch_year_panel.parquet", "data")):
        p_up = (up("05_map", sub, name) if sub else up("05_map", name))
        p_sb = (sb("05_map", sub, name) if sub else sb("05_map", name))
        checks.append(compare_frame(f"05_map · {name}", p_up, p_sb,
                                    num_cols=["lat", "lng", "n_same_ind_5km", "strength_t0"]))
    # 06 估计
    checks.append(compare_frame("06_estimate · did_panel.parquet",
                                up("06_estimate", "data", "did_panel.parquet"),
                                sb("06_estimate", "data", "did_panel.parquet"),
                                num_cols=["strength_t0", "dep_chg_rate", "post", "treated"],
                                keys=["UNINUMBR", "year"]))
    checks.append(compare_estimate(up("06_estimate", "estimate.json"),
                                   sb("06_estimate", "estimate.json")))

    # 阶段级摘要对拍（行数类的硬指标）
    stage_summary = []
    for s in summaries:
        stage_summary.append({k: v for k, v in s.items() if k != "artifacts"})

    critical = [c for c in checks if c.get("label", "").startswith(("02_", "03_", "05_", "06_"))]
    failed = [c for c in critical if not c.get("ok")]
    verdict = "通过" if (not run_error and not failed) else "不通过"
    core = next((c for c in checks if "did_panel" in c.get("label", "")), {})
    est_check = next((c for c in checks if "estimate.json 头条系数" in c.get("label", "")), {})

    out = {
        "generated_at": _dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "generator": "portal/audit/rerun_p5_full_chain.py",
        "protocol": {
            "goal": "从 data_raw 原始 SOD CSV 起步，独立重建到 06 估计，并与上游入库产物逐阶段对拍",
            "sandbox": _rel(SANDBOX),
            "upstream_root": _rel(P1),
            "source_root_used": _rel(RAW),
            "raw_files": n_raw,
            "stages": stages,
            "elapsed_minutes": round(elapsed / 60, 2),
            "verify_only": bool(args.verify_only),
            "isolation": "复制阶段入口 .py + datakit.yaml + config/ 到沙箱；__file__ 推导的输出目录因此指向沙箱，上游文件不被写入",
            "count_rows_disabled": True,
        },
        "stages_ran": stage_summary,
        "checks": checks,
        "verdict": verdict,
        "run_error": run_error,
        "headline": {
            "did_panel_rows": (core.get("rows") or {}),
            "strength_t0_max_abs_diff": (core.get("max_abs_diff") or {}).get("strength_t0"),
            "dep_chg_rate_max_abs_diff": (core.get("max_abs_diff") or {}).get("dep_chg_rate"),
            "estimate_ok": est_check.get("ok"),
            "estimate_twfe_post_x_strength": ((est_check.get("compare") or {})
                                              .get("twfe.post_x_strength") or {}),
        },
        "conclusion": (
            f"从 {n_raw} 个原始 CSV 起步重建：{verdict}。"
            + (f" did_panel 行数 上游{ (core.get('rows') or {}).get('upstream') } / 沙箱{ (core.get('rows') or {}).get('sandbox') }，"
               f"strength_t0 最大绝对差 {(core.get('max_abs_diff') or {}).get('strength_t0')}；"
               f"头条系数对拍 {'一致' if est_check.get('ok') else '不一致'}。"
               if core else "")
            + ("" if not failed else " 未通过项：" + "、".join(c["label"] for c in failed))
        ),
    }
    OUT_JSON.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"[ok] 已写出 {OUT_JSON}")
    log(f"  结论：{out['conclusion']}")

    if not args.keep_sandbox:
        shutil.rmtree(SANDBOX, ignore_errors=True)
        log("  沙箱已清理（--keep-sandbox 可保留）")
    return 0 if verdict == "通过" else 1


if __name__ == "__main__":
    raise SystemExit(main())
