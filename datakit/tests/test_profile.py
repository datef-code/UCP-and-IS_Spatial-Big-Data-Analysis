import pandas as pd

import datakit as dk


def _df():
    return pd.DataFrame({
        "id": [1, 2, 3, 4, 5],
        "amount": [10.0, 20.0, 30.0, 1000.0, 40.0],  # 1000 为异常
        "cat": ["a", "b", "a", None, "a"],
        "closed": ["2020-01-01", None, "2019-01-01", None, "2021-01-01"],
    })


def test_profile_fields():
    p = dk.profile(_df())
    names = {f.name for f in p.fields}
    assert names == {"id", "amount", "cat", "closed"}
    amt = next(f for f in p.fields if f.name == "amount")
    assert amt.stats["mean"] > 0


def test_profile_nulls_with_roles():
    p = dk.profile(_df(), roles={"closed": dk.Role.EVENT, "cat": dk.Role.CATEGORICAL})
    nulls = {r["field"]: r for r in p.nulls.to_dict("records")}
    assert nulls["closed"]["semantic"].startswith("信息")
    assert nulls["cat"]["semantic"].startswith("可重编码")


def test_detect_outliers_iqr():
    outliers = dk.detect_outliers(_df(), method="iqr")
    assert not outliers.empty
    assert set(outliers["field"]) == {"amount"}
    assert 1000.0 in outliers["value"].values


def test_detect_outliers_zscore():
    outliers = dk.detect_outliers(_df(), method="zscore", threshold=1.5)
    assert set(outliers["field"]) == {"amount"}


def test_profile_report_and_markdown():
    p = dk.profile(_df())
    r = p.to_report()
    assert r["summary"]["rows"] == 5
    assert "字段画像" in p.to_markdown()
