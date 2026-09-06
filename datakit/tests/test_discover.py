import tempfile
from pathlib import Path

import datakit as dk


def _make(tmp: Path):
    (tmp / "fdic").mkdir(parents=True)
    (tmp / "bike").mkdir()
    (tmp / "fdic" / "fdic_sod_1994.csv").write_text("id,val\n1,10\n2,20\n", encoding="utf-8")
    (tmp / "fdic" / "fdic_sod_1995.csv").write_text("id,val\n1,11\n", encoding="utf-8")
    (tmp / "bike" / "bike_20200101_p00001.csv").write_text("u,t\n9,2020\n", encoding="utf-8")
    (tmp / "bike" / "bike_20200102_p00001.csv").write_text("u,t\n8,2020\n", encoding="utf-8")
    (tmp / "bike" / "_state.json").write_text('{"a":1}', encoding="utf-8")
    (tmp / "bike" / "readme.log").write_text("log", encoding="utf-8")


def test_scan_groups_and_ignores(tmp_path):
    _make(tmp_path)
    cat = dk.scan(tmp_path, count_rows=True)
    assert len(cat) == 4  # 忽略 _state.json 与 readme.log
    assert set(cat.groups.keys()) == {"fdic_sod_#", "bike_#_p#"}
    assert len(cat.groups["fdic_sod_#"]) == 2
    assert len(cat.groups["bike_#_p#"]) == 2


def test_scan_report_and_markdown(tmp_path):
    _make(tmp_path)
    cat = dk.scan(tmp_path)
    report = cat.to_report()
    assert report["file_count"] == 4
    assert report["group_count"] == 2
    md = cat.to_markdown()
    assert "数据集：fdic_sod_#" in md


def test_scan_columns_peek(tmp_path):
    _make(tmp_path)
    cat = dk.scan(tmp_path)
    src = cat.groups["fdic_sod_#"][0]
    assert src.cols == 2
    assert src.columns == ["id", "val"]


def test_scan_with_md5(tmp_path):
    _make(tmp_path)
    cat = dk.scan(tmp_path, with_md5=True)
    assert len(cat.groups["fdic_sod_#"][0].md5) == 32
