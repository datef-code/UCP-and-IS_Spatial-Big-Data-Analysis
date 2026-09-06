import pandas as pd

import datakit as dk
from datakit.core import Dataset, DatasetMeta, Role, infer_roles


def test_version():
    assert isinstance(dk.__version__, str)


def test_dataset_wrapping():
    df = pd.DataFrame({"a": [1, 2], "b": ["x", "y"]})
    ds = Dataset(df, DatasetMeta(name="t", source="t.csv", format="csv"))
    assert ds.shape == (2, 2)
    assert list(ds.columns) == ["a", "b"]
    assert len(ds) == 2
    assert ds.meta.name == "t"


def test_with_frame_keeps_meta():
    df = pd.DataFrame({"a": [1, 2, 3]})
    ds = Dataset(df, DatasetMeta(source="s.csv", format="csv"))
    out = ds.with_frame(df.head(2))
    assert out.meta.source == "s.csv"
    assert out.meta.rows == 2


def test_role_enum():
    assert Role("event") is Role.EVENT
    assert Role.EVENT.value == "event"


def test_infer_roles_default():
    roles = infer_roles(["BRNUM", "CERT", "SIMS_ACQUIRED_DATE", "SIMS_LATITUDE", "amount"])
    assert roles["BRNUM"] == Role.KEY
    assert roles["CERT"] == Role.KEY
    assert roles["SIMS_ACQUIRED_DATE"] == Role.EVENT
    assert roles["SIMS_LATITUDE"] == Role.SPATIAL
    assert roles["amount"] == Role.NUMERIC


def test_infer_roles_override():
    roles = infer_roles(["amount"], overrides={"amount": "categorical"})
    assert roles["amount"] == Role.CATEGORICAL
