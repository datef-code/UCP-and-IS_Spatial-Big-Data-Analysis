import json
import tempfile
from pathlib import Path

import pandas as pd
import pytest

import datakit as dk


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


def test_detect_format():
    assert dk.detect_format("a.csv") == "csv"
    assert dk.detect_format("a.csv.gz") == "csv"
    assert dk.detect_format("a.xlsx") == "xlsx"
    assert dk.detect_format("a.jsonl") == "jsonl"
    assert dk.detect_format("a.ttl") == "ttl"


def test_read_write_csv_roundtrip(tmp_dir):
    df = pd.DataFrame({"id": [1, 2], "name": ["甲", "乙"]})
    p = tmp_dir / "t.csv"
    dk.write(dk.Dataset(df), p)
    ds = dk.read(p)
    assert list(ds.columns) == ["id", "name"]
    assert ds.shape == (2, 2)


def test_read_json_lines(tmp_dir):
    p = tmp_dir / "t.jsonl"
    p.write_text('{"a":1}\n{"a":2}\n', encoding="utf-8")
    ds = dk.read(p)
    assert ds.shape == (2, 1)


def test_read_json_array(tmp_dir):
    p = tmp_dir / "t.json"
    p.write_text(json.dumps([{"a": 1}, {"a": 2}]), encoding="utf-8")
    ds = dk.read(p)
    assert ds.shape == (2, 1)


def test_read_xml(tmp_dir):
    p = tmp_dir / "t.xml"
    p.write_text(
        '<root><item name="a" val="1"/><item name="b" val="2"/></root>',
        encoding="utf-8",
    )
    ds = dk.read_xml(p)
    assert ds.shape == (2, 2)
    assert "@name" in ds.columns


def test_read_xlsx(tmp_dir):
    pd.DataFrame({"x": [1, 2], "y": [3, 4]}).to_excel(tmp_dir / "t.xlsx", index=False)
    ds = dk.read_xlsx(tmp_dir / "t.xlsx")
    assert ds.shape == (2, 2)


def test_read_rdf_optional_dependency(tmp_dir):
    p = tmp_dir / "t.ttl"
    p.write_text("@prefix : <http://ex/> . :a :p :b .", encoding="utf-8")
    try:
        import rdflib  # noqa: F401
        ds = dk.read_rdf(p)
        assert "subject" in ds.columns
    except ImportError:
        with pytest.raises(ImportError):
            dk.read_rdf(p)


def test_unsupported_format():
    with pytest.raises(dk.FormatNotSupportedError):
        dk.detect_format("t.xyz")
