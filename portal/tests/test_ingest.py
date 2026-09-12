#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""ingest.py 泛化接入内核单测（不依赖 pytest）。

覆盖三条"锁死特定数据"的修复点：
  * 多文件 → 一份数据集（列并集拼接 + 覆盖差异）；
  * 字段不固定 → 内容级角色推断（**不看列名**也能认年份/坐标/实体）；
  * 形态不固定 → panel / event_log / network 路由。

跑法：
    datakit/.venv/Scripts/python.exe portal/tests/test_ingest.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

PORTAL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PORTAL))

import ingest as ing            # noqa: E402  （ingest.py 用了 dataclass，需正常导入才能注册到 sys.modules）

PASS, FAIL = [], []


def check(name, fn):
    try:
        fn()
        PASS.append(name)
        print(f"  ok   {name}")
    except AssertionError as e:
        FAIL.append((name, str(e)))
        print(f"  FAIL {name} :: {e}")
    except Exception as e:                                            # pragma: no cover
        FAIL.append((name, f"{type(e).__name__}: {e}"))
        print(f"  ERR  {name} :: {type(e).__name__}: {e}")


def _tmp() -> Path:
    d = Path(tempfile.mkdtemp(prefix="sdp_ingest_"))
    return d


def t_read_headerless_tsv():
    d = _tmp()
    (d / "a.tsv").write_text("0\t2010-10-17T01:48:53Z\t39.7\t-104.9\tabcdef0123456789\n"
                             "1\t2010-10-16T06:02:04Z\t39.8\t-105.0\tffffffffffffffff\n", encoding="utf-8")
    df, fmt = ing.read_any(d / "a.tsv")
    assert list(df.columns) == ["c0", "c1", "c2", "c3", "c4"], list(df.columns)
    assert len(df) == 2, len(df)


def t_multi_file_union():
    d = _tmp()
    pd.DataFrame({"id": [1, 2], "year": [2010, 2011], "v": [1.0, 2.0]}).to_csv(d / "x.csv", index=False)
    pd.DataFrame({"id": [3], "year": [2012], "extra": ["a"]}).to_csv(d / "y.csv", index=False)
    b = ing.load_sources([str(d)])
    assert b.rows == 3, b.rows
    assert "extra" in b.columns and "v" in b.columns
    diff = b.schema_diff()
    partial = {p["column"] for p in diff["partial_columns"]}
    assert "v" in partial and "extra" in partial, diff
    assert b.source_count == 2


def t_infer_roles_content_only():
    """列名刻意取怪名：角色必须靠内容认出来。"""
    rng = np.random.default_rng(0)
    n = 300
    df = pd.DataFrame({
        "k1": rng.integers(1, 50, n),                 # 实体（重复出现）
        "k2": rng.choice([2010, 2011, 2012, 2013, 2014, 2015], n),  # 年份
        "k3": rng.normal(40, 1, n),                    # 纬度
        "k4": rng.normal(-100, 1, n),                  # 经度
        "k5": rng.lognormal(10, 1, n),                 # 结果变量
    })
    m = ing.infer_mapping(df)
    assert m["time"] == "k2", m["time"]
    assert m["entity"] == "k1", m["entity"]
    assert m["lat"] == "k3" and m["lon"] == "k4", (m["lat"], m["lon"])
    assert m["value"] == "k5", m["value"]


def t_reject_fake_latitude():
    """落在 [-90,90] 的整数分类码不应被当纬度（FDIC BRSERTYP 的坑）。"""
    rng = np.random.default_rng(1)
    n = 500
    df = pd.DataFrame({
        "code": rng.integers(1, 20, n),                # 整数分类码，值域落在 [-90,90]
        "y": rng.uniform(30, 45, n),                   # 真纬度
        "x": rng.uniform(-120, -80, n),                # 真经度
    })
    m = ing.infer_mapping(df)
    assert m["lat"] == "y" and m["lon"] == "x", (m["lat"], m["lon"])


def t_shape_routing():
    rng = np.random.default_rng(2)
    n = 600
    panel = pd.DataFrame({"e": np.repeat(np.arange(60), 10), "t": np.tile(np.arange(2000, 2010), 60),
                          "v": rng.random(n)})
    assert ing.detect_shape(panel, {"entity": "e", "time": "t", "value": "v"})["kind"] == "panel"

    ev = pd.DataFrame({"e": rng.integers(0, 50, n), "ts": pd.date_range("2020-01-01", periods=n, freq="h"),
                       "v": rng.random(n)})
    assert ing.detect_shape(ev, {"entity": "e", "event_time": "ts", "value": "v"})["kind"] == "event_log"

    edges = pd.DataFrame({"src": rng.integers(0, 2000, n), "dst": rng.integers(0, 2000, n)})
    assert ing.detect_shape(edges, {"entity": "src"})["kind"] == "network"


def t_templates_roundtrip():
    ing.TEMPLATE_DIR = _tmp() / "tpl"
    p = ing.save_template("某客户映射", {"entity": "网点", "time": "年份"}, {"kind": "panel"}, ["网点", "年份"])
    assert p.exists()
    lst = ing.list_templates()
    assert any(x["name"] == "某客户映射" for x in lst), lst


def main() -> int:
    print("== ingest.py 泛化接入单测 ==")
    check("无表头 TSV 自动识别", t_read_headerless_tsv)
    check("多文件按列并集拼接 + 覆盖差异", t_multi_file_union)
    check("内容级角色推断（不看列名）", t_infer_roles_content_only)
    check("拒绝把分类码误判为纬度", t_reject_fake_latitude)
    check("形态路由 panel / event_log / network", t_shape_routing)
    check("映射模板存取", t_templates_roundtrip)
    print(f"\n通过 {len(PASS)} / {len(PASS) + len(FAIL)}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
