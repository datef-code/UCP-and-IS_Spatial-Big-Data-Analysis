import pandas as pd

import datakit as dk


def _df():
    return pd.DataFrame({
        "id": [1, 2, 3, None, 5],
        "amount": [10.0, None, 30.0, 1000.0, 40.0],
        "cat": ["a", "b", None, "d", "a"],
    })


def test_clean_drop_na_and_fill():
    plan = dk.CleanPlan().drop_na(["id"], reason="主键缺失").fill("amount", method="median")
    result = dk.clean(_df(), plan)
    assert result.dataset.shape[0] == 4          # 删除 1 行
    assert result.dataset.frame["amount"].notna().all()
    assert result.stats["removed_rows"] == 1


def test_clean_decision_log():
    plan = dk.CleanPlan().drop_na(["id"]).clip("amount", lower=0)
    result = dk.clean(_df(), plan)
    df = result.decisions.to_frame()
    assert list(df["action"]) == ["drop_na", "clip"]
    assert df.iloc[0]["affected_rows"] == 1
    assert "清洗决策日志" in result.decisions.to_markdown()


def test_clean_from_spec():
    plan = dk.CleanPlan.from_spec([
        {"op": "drop_na", "field": ["id"]},
        {"op": "fill", "field": "amount", "method": "constant", "value": 0},
    ])
    result = dk.clean(_df(), plan)
    assert result.dataset.frame["amount"].notna().all()


def test_clean_drop_duplicates():
    df = pd.DataFrame({"id": [1, 1, 2], "v": [1, 1, 2]})
    plan = dk.CleanPlan().drop_duplicates(["id"])
    result = dk.clean(df, plan)
    assert result.dataset.shape[0] == 2


def test_clean_winsorize():
    df = pd.DataFrame({"x": [1, 2, 3, 100]})
    plan = dk.CleanPlan().winsorize("x", quantile=0.25)
    result = dk.clean(df, plan)
    assert result.dataset.frame["x"].max() < 100
