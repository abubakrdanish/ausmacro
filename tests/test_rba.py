from __future__ import annotations

import math

import pandas as pd
import pytest

from ausmacro import _rba
from ausmacro.errors import FormatChangedError, SeriesNotFoundError, UpstreamError


def test_daily_table_with_named_months(fixture_bytes):
    title, frame = _rba.parse(fixture_bytes("SYNTHETIC_rba_f1.csv"), "F1")

    assert title == "F1 SYNTHETIC TEST TABLE – MONEY MARKET"
    # N/A, blank cells and the padding rows at the end are all dropped.
    assert len(frame) == 4
    cash = frame[frame["series"] == "FIRMMCRTD"]
    assert list(cash["date"]) == [
        pd.Timestamp("2024-12-30"), pd.Timestamp("2024-12-31"), pd.Timestamp("2025-01-02"),
    ]
    first = cash.iloc[0]
    assert first["freq"] == "D"
    assert first["adjustment"] == "Original"
    assert first["unit"] == "Per cent"
    assert first["source_id"] == "RBA,F1/FIRMMCRTD"
    assert frame["value"].dtype == "float64"
    assert frame["date"].dtype == "datetime64[ns]"


def test_monthly_table_with_slashed_dates_is_dated_at_month_end(fixture_bytes):
    _, frame = _rba.parse(fixture_bytes("SYNTHETIC_rba_f1.1.csv"), "F1.1")
    # 2024 is a leap year, and the mid-month date moves to the end of February.
    assert list(frame["date"]) == [pd.Timestamp("2024-01-31"), pd.Timestamp("2024-02-29")]
    assert set(frame["freq"]) == {"M"}


def test_ranges_become_nan(fixture_bytes):
    _, frame = _rba.parse(fixture_bytes("SYNTHETIC_rba_a2.csv"), "A2")
    early = frame[frame["date"] == pd.Timestamp("1999-02-01")]
    assert len(early) == 2
    assert early["value"].map(math.isnan).all()
    # "As announced" is not a regular frequency.
    assert frame["freq"].isna().all()


def test_source_lists_third_parties(fixture_bytes):
    title, frame = _rba.parse(fixture_bytes("SYNTHETIC_rba_fx.csv"), "F11.1")
    source = _rba.source(title, frame)
    assert source["third_party"] == "FXRUSD (WM/Reuters)"
    assert source["year"] == "2023"


def test_two_sources_in_one_cell(fixture_bytes):
    content = fixture_bytes("SYNTHETIC_rba_f1.1.csv").replace(b"Source,RBA", b"Source,ABS / RBA")
    title, frame = _rba.parse(content, "F1.1")
    assert _rba.source(title, frame)["third_party"] == "FIRMMCRT (ABS)"


def test_html_page_is_a_format_change():
    with pytest.raises(FormatChangedError, match="web page"):
        _rba.parse(b"<html><body>SYNTHETIC error page</body></html>", "F1")


def test_missing_series_id_row_is_a_format_change(fixture_bytes):
    content = fixture_bytes("SYNTHETIC_rba_f1.csv").replace(b"Series ID", b"Mnemonic")
    with pytest.raises(FormatChangedError, match="no 'Series ID' row"):
        _rba.parse(content, "F1")


def test_unreadable_date_is_a_format_change(fixture_bytes):
    content = fixture_bytes("SYNTHETIC_rba_f1.csv").replace(b"30-Dec-2024", b"2024-12-30")
    with pytest.raises(FormatChangedError, match="date"):
        _rba.parse(content, "F1")


def test_fetch_uses_the_lowercase_csv_url(fake_http):
    fake_http.reply(fixture="SYNTHETIC_rba_f1.1.csv")
    _rba.fetch("F1.1")
    assert fake_http.urls == ["https://www.rba.gov.au/statistics/tables/csv/f1.1-data.csv"]


@pytest.mark.parametrize(
    ("status", "error"), [(404, SeriesNotFoundError), (503, UpstreamError), (429, UpstreamError)]
)
def test_fetch_maps_error_responses(fake_http, status, error):
    fake_http.reply(status, body=b"<html>SYNTHETIC</html>")
    with pytest.raises(error):
        _rba.fetch("ZZ9")


def test_bad_date_in_a_known_style_is_a_format_change(fixture_bytes):
    content = fixture_bytes("SYNTHETIC_rba_f1.csv").replace(b"31-Dec-2024", b"31-Foo-2024")
    with pytest.raises(FormatChangedError, match="date"):
        _rba.parse(content, "F1")


def test_non_numeric_value_is_a_format_change(fixture_bytes):
    content = fixture_bytes("SYNTHETIC_rba_f1.csv").replace(b"9.12", b"n.a.")
    with pytest.raises(FormatChangedError, match="non-numeric"):
        _rba.parse(content, "F1")


def test_table_with_no_rows_parses_empty(fixture_bytes):
    content = fixture_bytes("SYNTHETIC_rba_fx.csv").replace(b"03-Jan-2023,0.1111,11.1\n", b"")
    _, frame = _rba.parse(content, "F11.1")
    assert frame.empty
