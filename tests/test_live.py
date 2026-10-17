from __future__ import annotations

import pandas as pd
import pytest

import ausmacro


@pytest.mark.live
def test_cpi_and_cash_rate_from_the_real_sources():
    df = ausmacro.get(["cpi", "cash_rate"], start="2024")
    recent = pd.Timestamp.now() - pd.DateOffset(months=6)
    for name in ("cpi", "cash_rate"):
        assert df.loc[df["series"] == name, "date"].max() > recent
    assert ausmacro.attribution(df).startswith("Source: Australian Bureau of Statistics")
