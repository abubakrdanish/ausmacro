from __future__ import annotations

import datetime as dt
import warnings

import pandas as pd
import pytest

import ausmacro
from ausmacro.errors import InvalidRequestError, SeriesNotFoundError

LICENCE = "Licensed under CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/)."


def test_unmodified_wording():
    assert ausmacro.attribution("cpi") == (
        f"Source: Australian Bureau of Statistics, Consumer Price Index, Australia (6401.0). {LICENCE}"
    )


def test_modified_wording():
    assert ausmacro.attribution("wpi", modified=True) == (
        "Based on Australian Bureau of Statistics data: Wage Price Index, Australia (6345.0). "
        + LICENCE
    )


def test_same_publication_is_named_once():
    text = ausmacro.attribution(["cpi", "cpi_rents", "wpi"])
    assert text.count("Consumer Price Index") == 1
    assert "(6401.0) and Wage Price Index, Australia (6345.0)." in text


def test_frame_from_get(fake_http):
    fake_http.reply(fixture="SYNTHETIC_abs_cpi_quarterly.csv")
    df = ausmacro.get("cpi")
    assert ausmacro.attribution(df) == ausmacro.attribution("cpi")


def test_frame_from_get_abs_names_the_dataflow(fake_http):
    fake_http.reply(fixture="SYNTHETIC_abs_cpi_quarterly.csv")
    df = ausmacro.get_abs("ABS,CPI,2.0.0", "1.10001.10.50.Q")
    assert ausmacro.attribution(df).startswith(
        "Source: Australian Bureau of Statistics, ABS Data API dataflow ABS,CPI,2.0.0."
    )


def test_frame_without_sources_says_what_to_do():
    with pytest.raises(InvalidRequestError, match="Pass the series names"):
        ausmacro.attribution(pd.DataFrame({"value": [1.0]}))


def test_unknown_name():
    with pytest.raises(SeriesNotFoundError):
        ausmacro.attribution("gdp")


def test_rba_wording_uses_the_publication_year(fake_http):
    fake_http.reply(fixture="SYNTHETIC_rba_f1.1.csv")
    df = ausmacro.get("cash_rate")
    with warnings.catch_warnings():
        warnings.simplefilter("error")  # F1.1's cash rate is RBA-sourced, so no warning
        assert ausmacro.attribution(df) == "Source: Reserve Bank of Australia 2024."


def test_rba_wording_by_name_uses_this_year():
    year = dt.date.today().year
    assert ausmacro.attribution("cash_rate") == f"Source: Reserve Bank of Australia {year}."


def test_abs_and_rba_together_and_modified(fake_http):
    fake_http.reply(fixture="SYNTHETIC_abs_cpi_monthly.csv")
    fake_http.reply(fixture="SYNTHETIC_rba_f1.1.csv")
    df = ausmacro.get(["cpi", "cash_rate"])
    assert ausmacro.attribution(df, modified=True) == (
        "Based on Australian Bureau of Statistics data: Consumer Price Index, Australia (6401.0). "
        f"{LICENCE} Source: Reserve Bank of Australia 2024."
    )


def test_third_party_rba_series_warn(fake_http):
    fake_http.reply(fixture="SYNTHETIC_rba_fx.csv")
    df = ausmacro.get_rba("F11.1")
    with pytest.warns(UserWarning, match=r"FXRUSD \(WM/Reuters\).*consent"):
        text = ausmacro.attribution(df)
    assert text == "Source: Reserve Bank of Australia 2023."


def test_third_party_warning_skips_series_you_did_not_fetch(fake_http):
    fake_http.reply(fixture="SYNTHETIC_rba_fx.csv")
    df = ausmacro.get_rba("F11.1", "FXRTWI")
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        ausmacro.attribution(df)
