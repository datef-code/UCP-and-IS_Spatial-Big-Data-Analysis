#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""serve.py 体检规则的单元测试（REVIEW §三-C.6）

覆盖：
  * detect_columns：中英文列名、x/y 误命中、手动覆盖优先级；
  * health_check：缺失集中度、坐标阈值、主键诊断；
  * ⑦ 目标泄漏体检（实体级常量 + 聚合/终值命名）；
  * ⑧ 空间口径稳健性（换 k / 换尺度重算 Moran's I）。

不依赖 pytest，直接跑：
    datakit/.venv/Scripts/python.exe portal/tests/test_serve.py
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PORTAL = Path(__file__).resolve().parent.parent
REPO = PORTAL.parent
sys.path.insert(0, str(REPO / "datakit"))

spec = importlib.util.spec_from_file_location("sdp_serve", PORTAL / "serve.py")
serve = importlib.util.module_from_spec(spec)
spec.loader.exec_module(serve)          # 仅导入函数定义，不启动服务

PASS, FAIL = [], []


def check(name, fn):
    try:
        fn()
        PASS.append(name)
        print(f"  ok   {name}")
    except AssertionError as e:
        FAIL.append((name, str(e)))
        print(f"  FAIL {name} :: {e}")
    except Exception as e:                                        # pragma: no cover
        FAIL.append((name, f"{type(e).__name__}: {e}"))
        print(f"  ERR  {name} :: {type(e).__name__}: {e}")


def _panel(n_ent=60, years=8, seed=1) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n_ent):
        y0 = 2010
        est = y0 - int(rng.integers(0, 6))
        closed_rate = float(rng.random())          # 实体级常量（全期聚合 → 泄漏嫌疑）
        last_dep = float(rng.integers(1e4, 1e6))   # 终期值（同样对实体恒定）
        for t in range(years):
            rows.append({
                "UNINUMBR": i, "year": y0 + t,
                "deposits": last_dep * (1 + 0.02 * rng.standard_normal()),
                "age": y0 + t - est,
                "bank_closed_rate": closed_rate,
                "dep_last": last_dep,
                "lat": 30 + 0.01 * (i % 10), "lng": 120 + 0.01 * (i // 10),
                "flag": int(rng.random() < 0.3),
            })
    return pd.DataFrame(rows)


def t_detect_columns():
    df = _panel()
    cols = serve.detect_columns(list(df.columns))
    assert cols["id"] == "UNINUMBR", cols
    assert cols["year"] == "year", cols
    assert cols["lat"] == "lat" and cols["lon"] == "lng", cols
    # 中文列名
    zh = serve.detect_columns(["网点编号", "年份", "纬度", "经度", "销售额"])
    assert zh["id"] == "网点编号" and zh["year"] == "年份"
    assert zh["lat"] == "纬度" and zh["lon"] == "经度"
    # x/y 别名不应把无关列吃掉：只有名为 x/y 的列才当坐标
    weird = serve.detect_columns(["id", "year", "x", "y"])
    assert weird["lat"] == "y" and weird["lon"] == "x", weird


def t_health_check_basic():
    df = _panel()
    cols = serve.detect_columns(list(df.columns))
    hc = serve.health_check(df, cols, {})
    keys = [c["key"] for c in hc["checks"]]
    for k in ("scale", "geo", "span", "panel", "key", "outcome"):
        assert k in keys, f"缺少体检项 {k}：{keys}"
    assert hc["years"]["min"] == 2010 and hc["years"]["n"] == 8
    assert hc["entity_stats"]["entities"] == 60


def t_coord_threshold():
    df = _panel()
    df.loc[df.index[: int(len(df) * 0.4)], "lat"] = np.nan      # 40% 缺失 > 20%
    cols = serve.detect_columns(list(df.columns))
    hc = serve.health_check(df, cols, {})
    geo = next(c for c in hc["checks"] if c["key"] == "geo")
    assert geo["level"] == "danger", geo


def t_missingness_concentration():
    df = _panel()
    mask = df["year"] == 2010
    df.loc[mask, "deposits"] = np.nan                           # 集中在一个年份
    cols = serve.detect_columns(list(df.columns))
    hc = serve.health_check(df, cols, {})
    miss = next(c for c in hc["checks"] if c["key"] == "missingness")
    assert miss["detail"], "应按年份给出缺失集中度明细"
    worst = max(r["worst_year"] for r in miss["detail"])
    assert worst > 0.5, f"应报出某字段最差年份缺失率≈1.0：{miss['detail']}"


def t_leakage_check():
    df = _panel()
    cols = serve.detect_columns(list(df.columns))
    hc = serve.health_check(df, cols, {})
    lk = next(c for c in hc["checks"] if c["key"] == "leakage")
    fields = {r["field"] for r in lk["detail"]}
    assert "bank_closed_rate" in fields, f"应命中关闭率：{fields}"
    assert "dep_last" in fields, f"应命中终期值列：{fields}"
    assert "age" not in fields, "age 不是实体级常量，不应命中"
    assert lk["level"] == "warn", lk


def t_spatial_robustness():
    df = _panel(n_ent=400, years=1, seed=7)
    # 让 value 具备空间结构，避免全随机时 Moran≈0 无法判断
    gx = (df["lng"] * 100).round().astype(int)
    df["deposits"] = 1000.0 + 500.0 * (gx % 7)
    cols = serve.detect_columns(list(df.columns))
    hc = serve.health_check(df, cols, {})
    sp = [c for c in hc["checks"] if c["key"] == "spatial_robust"]
    assert sp, "应产出空间口径稳健性项"
    assert sp[0]["level"] in ("ok", "warn", "danger")
    assert sp[0].get("detail"), "应给出各口径的 Moran's I"


def main() -> int:
    print("== serve.py 体检规则单测 ==")
    check("detect_columns（中英文 / x,y 别名）", t_detect_columns)
    check("health_check 基础项齐全", t_health_check_basic)
    check("坐标缺失阈值 > 20% 判 danger", t_coord_threshold)
    check("缺失按年份集中度", t_missingness_concentration)
    check("⑦ 目标泄漏体检", t_leakage_check)
    check("⑧ 空间口径稳健性", t_spatial_robustness)
    print(f"\n通过 {len(PASS)} / {len(PASS) + len(FAIL)}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
