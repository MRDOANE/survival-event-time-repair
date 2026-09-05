import hashlib
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]


def test_frozen_mastitis_data_contract():
    path = ROOT / "data" / "mastitis.csv"
    assert hashlib.sha256(path.read_bytes()).hexdigest() == "b5ccf210b1ad826b79a7e85e5122c7fda3492825c59d00432cc29c1ea36916d3"
    frame = pd.read_csv(path)
    assert frame.shape == (400, 10)
    assert frame["cow"].nunique() == 100
    assert (frame.groupby("cow").size() == 4).all()
    assert frame["ul"].notna().sum() == 317
    assert frame["ul"].isna().sum() == 83
    assert frame["ll"].isna().sum() == 26
