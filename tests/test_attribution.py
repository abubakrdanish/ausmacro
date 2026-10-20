from __future__ import annotations

import datetime as dt
import warnings

import pandas as pd
import pytest

import ausmacro
from ausmacro.errors import InvalidRequestError, SeriesNotFoundError

LICENCE = "Licensed under CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/)."


@pytest.mark.parametrize(
    ("data", "modified", "expected"),
    [
        pytest.param(
            "cpi",
            False,
            f"Source: Australian Bureau of Statistics, Consumer Price Index, Australia. {LICENCE}",
            id="single-abs",
        ),
        pytest.param(
            ["cpi", "cpi_rents", "wpi"],
            False,
            "Source: Australian Bureau of Statistics, Consumer Price Index, Australia and "
            f"Wage Price Index, Australia. {LICENCE}",
            id="multiple-abs",
        ),
        pytest.param(
            "cash_rate",
            False,
            f"Source: Reserve Bank of Australia {dt.date.today().year}.",
            id="rba",
        ),
        pytest.param(
            ["cpi", "cash_rate"],
            False,
            f"Source: Australian Bureau of Statistics, Consumer Price Index, Australia. {LICENCE} "
            f"Source: Reserve Bank of Australia {dt.date.today().year}.",
            id="abs-and-rba",
        ),
        pytest.param(
            "wpi",
            True,
            f"Based on Australian Bureau of Statistics data: Wage Price Index, Australia. {LICENCE}",
            id="modified-abs",
        ),
        pytest.param(
            ["cpi", "cash_rate"],
            True,
            "Based on Australian Bureau of Statistics data: Consumer Price Index, Australia. "
            f"{LICENCE} Source: Reserve Bank of Australia {dt.date.today().year}.",
            id="modified-abs-and-rba",
        ),
        pytest.param(
            "cash_rate",
            True,
            f"Source: Reserve Bank of Australia {dt.date.today().year}.",
            id="modified-rba",
        ),
    ],
)
def test_exact_wording_for_source_combinations(data, modified, expected):
    assert ausmacro.attribution(data, modified=modified) == expected


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


def test_no_names():
    with pytest.raises(InvalidRequestError, match="at least one series name"):
        ausmacro.attribution([])


def test_abs_sourced_rba_series_says_to_credit_the_abs(fake_http, fixture_bytes):
    content = fixture_bytes("SYNTHETIC_rba_f1.1.csv").replace(b"Source,RBA", b"Source,ABS / RBA")
    fake_http.reply(body=content)
    df = ausmacro.get_rba("F1.1")
    with pytest.warns(UserWarning, match="credit the ABS"):
        ausmacro.attribution(df)
