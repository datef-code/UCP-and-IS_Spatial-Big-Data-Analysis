# -*- coding: utf-8 -*-
"""多数据集源数据加载器（项目侧口径，规范 §6）。

把 4 个源数据集统一读成 ``points`` 表：``lat`` / ``lon`` / ``value``，
并附带一份 ``fingerprint``（来源、文件数、体积、抽样口径、时间范围、MD5）。

约束：

* **只读** ``data_raw/``，本模块绝不写入源数据目录；
* 02_profile（画像）与 03_clean（清洗）共用本模块 —— 两阶段基于同一份源数据口径，
  阶段 3 不复用阶段 2 的内存数据（规范数据流向：``data_raw → 03_clean``）；
* 抽样参数（深圳单车抽样日）来自 ``config/schema.yaml``，改口径不改代码。
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd

DATASETS = ("fdic", "sz_bike", "snap_brightkite", "snap_gowalla")

#: 每个数据集的度量语义（写入报告，教学素材逐章标注）
VALUE_SEMANTICS = {
    "fdic": "网点是否关闭（0/1，按 UNINUMBR 聚合）",
    "sz_bike": "抽样日起点骑行次数（每次骑行计 1）",
    "snap_brightkite": "签到次数（每次签到计 1）",
    "snap_gowalla": "签到次数（每次签到计 1）",
}

_FDIC_COLS = {"UNINUMBR", "YEAR", "SIMS_ACQUIRED_DATE", "SIMS_LATITUDE", "SIMS_LONGITUDE"}


def md5_of(path: Path, cap_mb: float = 80.0) -> str | None:
    """小文件算 MD5 指纹；大文件返回 None（只记体积，成本可控）。"""
    if path.stat().st_size > cap_mb * 1024 * 1024:
        return None
    h = hashlib.md5()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def per_dataset_config(project, dataset: str) -> dict:
    """读 ``config/schema.yaml`` 的 ``per_dataset.<dataset>`` 口径。"""
    schema = project.config("schema") or {}
    return (schema.get("per_dataset") or {}).get(dataset) or {}


def sample_day(project, dataset: str = "sz_bike") -> str:
    """深圳单车抽样日（合成抽样参数，默认每月 15 日）。"""
    return str(per_dataset_config(project, dataset).get("sample_day", "15")).zfill(2)


def load_points(project, dataset: str, log=print) -> tuple[pd.DataFrame, dict]:
    """返回 ``(points[lat, lon, value], fingerprint)``。"""
    if dataset == "fdic":
        return _load_fdic(project, log)
    if dataset == "sz_bike":
        return _load_sz_bike(project, log)
    if dataset.startswith("snap_"):
        return _load_snap(project, dataset, log)
    raise ValueError(f"未知数据集：{dataset}")


# --------------------------------------------------------------------------- #
# fdic（主示例，公共领域可商用）
# --------------------------------------------------------------------------- #
def _load_fdic(project, log) -> tuple[pd.DataFrame, dict]:
    """优先复用项目1 的网点维度表；缺失时从原始 fdic_sod_*.csv 轻量重建。"""
    raw = project.source_root / "fdic"
    p1 = project.root.parent / "project1_fdic_spatial" / "output" / "data" / "branch_dim.csv"

    if p1.exists():
        b = pd.read_csv(p1, usecols=lambda c: c in {
            "UNINUMBR", "CERT", "BKCLASS", "MSABR", "event_type", "lat", "lng"})
        b = b.rename(columns={"lng": "lon", "event_type": "closed"})
        b["value"] = (b["closed"] == "closed_ma").astype(int)
        source = "复用 project1_fdic_spatial/output/data/branch_dim.csv（UNINUMBR 维度表）"
        files_n, total_bytes = 1, int(p1.stat().st_size)
    else:
        files = sorted(raw.glob("fdic_sod_*.csv"))
        if not files:
            raise FileNotFoundError(f"fdic 源数据缺失：{raw}")
        frames = []
        for i, f in enumerate(files, 1):
            d = pd.read_csv(f, usecols=lambda c: c in _FDIC_COLS, low_memory=False)
            for c in _FDIC_COLS - set(d.columns):
                d[c] = pd.NA
            d["acq"] = pd.to_datetime(d["SIMS_ACQUIRED_DATE"],
                                      format="%m/%d/%Y %I:%M:%S %p", errors="coerce")
            frames.append(d[["UNINUMBR", "YEAR", "acq", "SIMS_LATITUDE", "SIMS_LONGITUDE"]]
                          .rename(columns={"SIMS_LATITUDE": "lat", "SIMS_LONGITUDE": "lon"}))
            if i % 8 == 0 or i == len(files):
                log(f"    [fdic] 已读 {i}/{len(files)} 个源文件")
        long = pd.concat(frames, ignore_index=True)
        del frames
        long = long.dropna(subset=["UNINUMBR"]).sort_values(["UNINUMBR", "YEAR"], kind="stable")
        b = long.groupby("UNINUMBR", as_index=False).agg(
            value=("acq", lambda s: int(s.notna().any())),
            lat=("lat", "last"),
            lon=("lon", "last"),
        )
        source = "原始 fdic_sod_*.csv 重建（UNINUMBR last 口径；value=1 表示曾出现收购/关闭记录）"
        files_n, total_bytes = len(files), int(sum(f.stat().st_size for f in files))

    b["lat"] = pd.to_numeric(b["lat"], errors="coerce")
    b["lon"] = pd.to_numeric(b["lon"], errors="coerce")
    b["value"] = pd.to_numeric(b["value"], errors="coerce").fillna(0).astype("int64")
    pts = b[["lat", "lon", "value"]]
    fp = {
        "source": source,
        "files": files_n,
        "total_bytes": total_bytes,
        "md5": None,
        "note": "源数据 GB 级，只记录文件数与体积，不计算 MD5",
        "rows": int(len(pts)),
    }
    log(f"    [fdic] 网点 {len(pts):,} 个（value=1 共 {int(pts['value'].sum()):,}）")
    return pts, fp


# --------------------------------------------------------------------------- #
# sz_bike（辅助示例，研究用途，源已停更；全量 30 GB 只取抽样日）
# --------------------------------------------------------------------------- #
def _load_sz_bike(project, log) -> tuple[pd.DataFrame, dict]:
    raw = project.source_root / "sz_bike"
    day = sample_day(project, "sz_bike")
    files = sorted(raw.glob(f"bike_*{day}_p*.csv"))
    files = [f for f in files if f.name[11:13] == day]      # 精确校验「日」段
    if not files:
        raise FileNotFoundError(f"sz_bike 抽样日 {day} 无数据：{raw}")
    frames = []
    for i, f in enumerate(files, 1):
        d = pd.read_csv(f, usecols=lambda c: c in {"START_LAT", "START_LNG"})
        frames.append(d.rename(columns={"START_LAT": "lat", "START_LNG": "lon"}))
        if i % 200 == 0 or i == len(files):
            log(f"    [sz_bike] 已读 {i}/{len(files)} 个文件")
    pts = pd.concat(frames, ignore_index=True)
    del frames
    pts["lat"] = pd.to_numeric(pts["lat"], errors="coerce")
    pts["lon"] = pd.to_numeric(pts["lon"], errors="coerce")
    pts["value"] = 1
    days = sorted({f.name[5:13] for f in files})
    fp = {
        "source": f"data_raw/sz_bike/bike_*_{day}_p*.csv（每月 {day} 日抽样）",
        "files": len(files),
        "total_bytes": int(sum(f.stat().st_size for f in files)),
        "md5": None,
        "sample_days": days,
        "sampling": f"每月 {day} 日（合成抽样参数，非真实业务数据）",
        "rows": int(len(pts)),
    }
    log(f"    [sz_bike] 抽样日 {len(days)} 天、{len(files)} 个文件、{len(pts):,} 次骑行")
    return pts[["lat", "lon", "value"]], fp


# --------------------------------------------------------------------------- #
# SNAP（辅助示例，仅限研究用途，不允许商用）
# --------------------------------------------------------------------------- #
def _load_snap(project, dataset: str, log) -> tuple[pd.DataFrame, dict]:
    short = dataset.split("_", 1)[1]                       # brightkite / gowalla
    gz = project.source_root / dataset / f"loc-{short}_totalCheckins.txt.gz"
    if not gz.exists():
        raise FileNotFoundError(f"SNAP 源数据缺失：{gz}")
    pts = pd.read_csv(gz, sep="\t", header=None,
                      names=["user", "time", "lat", "lng", "loc_id"],
                      usecols=["time", "lat", "lng"])
    t = pd.to_datetime(pts["time"], format="%Y-%m-%dT%H:%M:%SZ", errors="coerce")
    pts = pts.drop(columns=["time"]).rename(columns={"lng": "lon"})
    pts["lat"] = pd.to_numeric(pts["lat"], errors="coerce")
    pts["lon"] = pd.to_numeric(pts["lon"], errors="coerce")
    pts["value"] = 1
    fp = {
        "source": f"data_raw/{dataset}/{gz.name}",
        "files": 1,
        "total_bytes": int(gz.stat().st_size),
        "md5": md5_of(gz),
        "rows": int(len(pts)),
        "time_range": {"min": str(t.min()), "max": str(t.max())},
        "era_note": "SNAP 数据年代 2010–2013（方案口径标注；实测范围见上）",
    }
    log(f"    [{dataset}] 签到 {len(pts):,} 条；时间范围 {fp['time_range']['min']} … {fp['time_range']['max']}")
    return pts[["lat", "lon", "value"]], fp
