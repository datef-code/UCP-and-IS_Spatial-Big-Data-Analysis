import pandas as pd

import datakit as dk


def _df():
    return pd.DataFrame({
        "lat": [22.5, 23.0],
        "lng": [113.9, 114.1],
        "deposit": [100.0, 250.0],
        "cat": ["a", "b"],
    })


def test_map_rename_and_derive():
    scheme = dk.MappingScheme().rename({"lat": "latitude"}).derive("double", "deposit * 2")
    result = dk.map(_df(), scheme)
    assert "latitude" in result.dataset.columns
    assert result.dataset.frame["double"].tolist() == [200.0, 500.0]


def test_map_bin():
    scheme = dk.MappingScheme().bin("deposit", bins=[0, 150, 300], labels=["低", "高"])
    result = dk.map(_df(), scheme)
    assert "deposit_bin" in result.dataset.columns
    assert result.dataset.frame["deposit_bin"].tolist() == ["低", "高"]


def test_map_code():
    scheme = dk.MappingScheme().code("cat", {"a": 1, "b": 2})
    result = dk.map(_df(), scheme)
    assert result.dataset.frame["cat_code"].tolist() == [1, 2]


def test_map_from_spec():
    scheme = dk.MappingScheme.from_spec([
        {"op": "rename", "mapping": {"lat": "latitude"}},
        {"op": "derive", "name": "d2", "expr": "deposit + 1"},
    ])
    result = dk.map(_df(), scheme)
    assert "latitude" in result.dataset.columns
    assert "d2" in result.dataset.columns


def test_map_report_markdown():
    scheme = dk.MappingScheme().rename({"lat": "latitude"})
    result = dk.map(_df(), scheme)
    assert "映射" in result.to_markdown()
