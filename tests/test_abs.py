from __future__ import annotations

import pandas as pd
import pytest

from ausmacro import _abs
from ausmacro.errors import (
    FormatChangedError,
    InvalidRequestError,
    NoDataError,
    SeriesNotFoundError,
    UpstreamError,
)


def test_parse_shapes_a_long_frame(fixture_bytes):
    frame = _abs.parse(fixture_bytes("SYNTHETIC_abs_cpi_quarterly.csv"))

    assert list(frame.columns) == _abs.COLUMNS + ["_region_code", "_base_period"]
    assert len(frame) == 4  # the row with a blank value is dropped
    assert frame["value"].dtype == "float64"
    assert frame["date"].dtype == "datetime64[ns]"
    first = frame.iloc[0]
    assert first["series"] == "1.10001.10.50.Q"
    assert first["source_id"] == "ABS,CPI,2.0.0/1.10001.10.50.Q"
    assert first["region"] == "Australia"
    assert first["adjustment"] == "Original"
    assert first["freq"] == "Q"
    assert first["unit"] == "Index Numbers (Sep 2025 = 100.0)"
    assert first["value"] == 111.1


def test_quarters_are_dated_at_quarter_end(fixture_bytes):
    frame = _abs.parse(fixture_bytes("SYNTHETIC_abs_cpi_quarterly.csv"))
    assert list(frame["date"][:2]) == [pd.Timestamp("2020-12-31"), pd.Timestamp("2021-03-31")]


def test_months_are_dated_at_month_end(fixture_bytes):
    frame = _abs.parse(fixture_bytes("SYNTHETIC_abs_cpi_monthly.csv"))
    # 2024 is a leap year, so February ends on the 29th.
    assert list(frame["date"]) == [pd.Timestamp("2024-01-31"), pd.Timestamp("2024-02-29")]


def test_wpi_column_order_and_blank_base_period(fixture_bytes):
    frame = _abs.parse(fixture_bytes("SYNTHETIC_abs_wpi.csv"))
    assert frame["series"].iloc[0] == "1.THRPEB.7.TOT.10.AUS.Q"
    assert frame["unit"].iloc[0] == "Index Numbers"
    assert frame["_region_code"].iloc[0] == "AUS"


def test_html_page_is_a_format_change():
    with pytest.raises(FormatChangedError, match="web page"):
        _abs.parse(b"<!DOCTYPE html><html><body>SYNTHETIC maintenance page</body></html>")


def test_missing_column_is_a_format_change(fixture_bytes):
    content = fixture_bytes("SYNTHETIC_abs_cpi_monthly.csv").replace(b"OBS_VALUE", b"VALUE")
    with pytest.raises(FormatChangedError, match="OBS_VALUE"):
        _abs.parse(content)


def test_non_numeric_value_is_a_format_change(fixture_bytes):
    content = fixture_bytes("SYNTHETIC_abs_cpi_monthly.csv").replace(b"333.1", b"n/a")
    with pytest.raises(FormatChangedError, match="non-numeric"):
        _abs.parse(content)


def test_unknown_frequency_is_reported(fixture_bytes):
    content = fixture_bytes("SYNTHETIC_abs_cpi_monthly.csv").replace(b"M: Monthly", b"S: Half-yearly")
    with pytest.raises(FormatChangedError, match="'S'"):
        _abs.parse(content)


def test_fetch_builds_the_query_url(fake_http):
    fake_http.reply(fixture="SYNTHETIC_abs_cpi_monthly.csv")
    _abs.fetch("ABS,CPI,2.0.0", "1.10001.10.50.M")
    assert fake_http.urls == ["https://data.api.abs.gov.au/rest/data/ABS,CPI,2.0.0/1.10001.10.50.M"]
    assert fake_http.accepts == ["application/vnd.sdmx.data+csv;labels=both"]


@pytest.mark.parametrize(
    ("status", "body", "error"),
    [
        (404, b"NoRecordsFound", NoDataError),
        (404, b"Could not find Dataflow and/or DSD related with this data request", SeriesNotFoundError),
        (422, b"Not enough key values in query, expecting 5 got 2", InvalidRequestError),
        (503, b"Service Unavailable", UpstreamError),
        (429, b"Too Many Requests", UpstreamError),
    ],
)
def test_fetch_maps_error_responses(fake_http, status, body, error):
    fake_http.reply(status, body=body)
    with pytest.raises(error):
        _abs.fetch("ABS,CPI,2.0.0", "1.10001.10.50.M")


def test_unexpected_dataflow_value_is_a_format_change(fixture_bytes):
    content = fixture_bytes("SYNTHETIC_abs_cpi_monthly.csv").replace(b"ABS:CPI(2.0.0)", b"CPI version 2")
    with pytest.raises(FormatChangedError, match="DATAFLOW"):
        _abs.parse(content)
