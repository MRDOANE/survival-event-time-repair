import hashlib
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]


def test_frozen_hiv_data_contract():
    path = ROOT / "data" / "hiv.csv"
    assert hashlib.sha256(path.read_bytes()).hexdigest() == "1b99a4485e20921eb1f3fc154d324e0f6b2879f2183f0d04d392218dca68afc6"
    frame = pd.read_csv(path)
    assert frame.shape == (368, 4)
    assert frame["id"].nunique() == 368
    assert frame["upp"].notna().sum() == 103
    assert frame["upp"].isna().sum() == 265
    assert set(frame["treat"]) == {"no", "low dose"}
