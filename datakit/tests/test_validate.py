import pandas as pd

import datakit as dk


def _df():
    return pd.DataFrame({
        "id": [1, 2, 3],
        "amount": [10.0, 20.0, -5.0],
        "cat": ["a", "b", "a"],
    })


def test_validate_unique_pass():
    r = dk.validate(_df(), [{"name": "id 唯一", "check": "unique", "field": "id"}])
    assert r.passed


def test_validate_no_negative_fail():
    r = dk.validate(_df(), [{"name": "非负", "check": "no_negative", "field": "amount"}])
    assert not r.passed
    assert r.fail_count == 1


def test_validate_allowed_values():
    r = dk.validate(_df(), [{"name": "类别合法", "check": "allowed_values", "field": "cat", "values": ["a", "b"]}])
    assert r.passed


def test_validate_custom_callable():
    r = dk.validate(_df(), [lambda f: (len(f) == 3, "rows ok")])
    assert r.passed


def test_compare_report():
    before = dk.profile(pd.DataFrame({"x": [1, 2, None]}))
    after = dk.profile(pd.DataFrame({"x": [1, 2, 3]}))
    cmp = dk.compare(before, after)
    f = cmp.fields[0]
    assert f["null_rate_before"] > 0
    assert f["null_rate_after"] == 0
    assert "建议" in cmp.to_markdown()


def test_compare_recommend_reclean_when_key_null():
    before = dk.profile(pd.DataFrame({"k": [1, None], "v": [1, 2]}))
    after = dk.profile(pd.DataFrame({"k": [1, None], "v": [1, 2]}))
    cmp = dk.compare(before, after, key_fields=["k"])
    assert "还原" in cmp.recommendation or "清洗" in cmp.recommendation
