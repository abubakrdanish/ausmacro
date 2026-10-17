from __future__ import annotations

import datetime as dt
import warnings

import pytest

import ausmacro
from ausmacro.errors import FormatChangedError, InvalidRequestError, NoDataError, SeriesNotFoundError

DATA = "https://data.api.abs.gov.au/rest/data/"
RBA = "https://www.rba.gov.au/statistics/tables/csv/"


def test_get_uses_the_registry_key_and_defaults(fake_http):
    fake_http.reply(fixture="SYNTHETIC_abs_cpi_quarterly.csv")
    df = ausmacro.get("cpi", region=["australia", "sydney"])

    assert fake_http.urls == [DATA + "ABS,CPI,2.0.0/1.10001.10.50+1.M"]  # CPI defaults to monthly
    assert list(df.columns) == [
        "series", "region", "freq", "adjustment", "date", "value", "unit", "source_id",
    ]
    assert set(df["series"]) == {"cpi"}
    assert sorted(df["region"].unique()) == ["Australia", "Sydney"]
    assert list(df.index) == list(range(len(df)))


def test_region_all_requests_every_region(fake_http):
    fake_http.reply(fixture="SYNTHETIC_abs_cpi_quarterly.csv")
    ausmacro.get("cpi", region="all", freq="Q")
    assert fake_http.urls == [DATA + "ABS,CPI,2.0.0/1.10001.10.50+1+2+3+4+5+6+7+8.Q"]


def test_region_names_are_case_insensitive(fake_http):
    fake_http.reply(fixture="SYNTHETIC_abs_wpi.csv")
    ausmacro.get("wpi", region="Australia", adjustment="trend")
    assert fake_http.urls == [DATA + "ABS,WPI,1.2.0/1.THRPEB.7.TOT.30.AUS.Q"]


def test_wpi_unit_comes_from_the_registry(fake_http):
    fake_http.reply(fixture="SYNTHETIC_abs_wpi.csv")
    df = ausmacro.get("wpi")
    assert set(df["unit"]) == {"Index Numbers (2008-09 = 100.0)"}


def test_start_and_end_are_inclusive_periods(fake_http):
    fake_http.reply(fixture="SYNTHETIC_abs_cpi_quarterly.csv")
    # end="2021-Q1" must keep the March quarter, dated 2021-03-31.
    df = ausmacro.get("cpi", freq="Q", start="2021", end="2021-Q1", region=["australia", "sydney"])
    assert list(df["date"].dt.strftime("%Y-%m-%d")) == ["2021-03-31", "2021-03-31"]


def test_start_accepts_a_date(fake_http):
    fake_http.reply(fixture="SYNTHETIC_abs_cpi_monthly.csv")
    df = ausmacro.get("cpi", freq="M", start=dt.date(2024, 2, 1))
    assert list(df["value"]) == [333.2]


def test_empty_date_range_says_what_exists(fake_http):
    fake_http.reply(fixture="SYNTHETIC_abs_cpi_quarterly.csv")
    with pytest.raises(NoDataError, match="runs from 2020-12-31 to 2021-03-31"):
        ausmacro.get("cpi", start="2030")


def test_several_series_in_one_frame(fake_http):
    fake_http.reply(fixture="SYNTHETIC_abs_cpi_quarterly.csv")
    fake_http.reply(fixture="SYNTHETIC_abs_wpi.csv")
    df = ausmacro.get(["cpi", "wpi"])
    assert list(df["series"].unique()) == ["cpi", "wpi"]
    assert [s["catalogue"] for s in df.attrs["sources"]] == ["6401.0", "6345.0"]


def test_missing_region_warns(fake_http):
    fake_http.reply(fixture="SYNTHETIC_abs_cpi_quarterly.csv")  # has Australia and Sydney only
    with pytest.warns(UserWarning, match="no cpi data for melbourne"):
        ausmacro.get("cpi", region=["australia", "melbourne"])


def test_no_records_mentions_the_series_notes(fake_http):
    fake_http.reply(404, body=b"NoRecordsFound")
    with pytest.raises(NoDataError, match="Quarterly .* for 'australia' only"):
        ausmacro.get("cpi_rents", region="sydney", freq="Q")


def test_unknown_name_suggests_the_closest():
    with pytest.raises(SeriesNotFoundError, match="Did you mean 'cpi'"):
        ausmacro.get("cpl")


def test_unknown_name_suggests_by_description():
    with pytest.raises(SeriesNotFoundError, match="Did you mean 'wpi'"):
        ausmacro.get("wage")


def test_state_for_a_city_series_suggests_the_capital():
    with pytest.raises(InvalidRequestError, match="capital city, so try 'sydney'"):
        ausmacro.get("cpi", region="nsw")


def test_city_for_a_state_series_suggests_the_state():
    with pytest.raises(InvalidRequestError, match="by state, so try 'nsw'"):
        ausmacro.get("wpi", region="sydney")


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"freq": "M"}, "no frequency 'M'"),
        ({"adjustment": "seasonally_adjusted"}, "no adjustment 'seasonally_adjusted'. Choose from: original."),
        ({"start": "last year"}, "Could not read 'last year'"),
        ({"start": "2022", "end": "2021"}, "after end"),
    ],
)
def test_bad_arguments_are_explained(kwargs, message):
    name = "wpi" if "adjustment" not in kwargs else "cpi"
    with pytest.raises(InvalidRequestError, match=message):
        ausmacro.get(name, **kwargs)


def test_get_abs_keeps_raw_series_keys(fake_http):
    fake_http.reply(fixture="SYNTHETIC_abs_cpi_quarterly.csv")
    df = ausmacro.get_abs("ABS,CPI,2.0.0", "1.10001.10.50+1.Q", start="2021")
    assert fake_http.urls == [DATA + "ABS,CPI,2.0.0/1.10001.10.50+1.Q"]
    assert sorted(df["series"]) == ["1.10001.10.1.Q", "1.10001.10.50.Q"]
    assert df.attrs["sources"][0]["title"] == "ABS Data API dataflow ABS,CPI,2.0.0"


def test_series_lists_the_registry_with_defaults():
    table = ausmacro.series().set_index("name")
    assert list(table.index) == ["cpi", "cpi_rents", "wpi", "cash_rate"]
    assert table.loc["cpi", "default_freq"] == "M"
    assert table.loc["wpi", "default_freq"] == "Q"
    assert set(table["default_adjustment"]) == {"original"}
    assert list(ausmacro.series("rents")["name"]) == ["cpi_rents"]


def test_cash_rate_monthly_comes_from_f1_1(fake_http):
    fake_http.reply(fixture="SYNTHETIC_rba_f1.1.csv")
    df = ausmacro.get("cash_rate")
    assert fake_http.urls == [RBA + "f1.1-data.csv"]
    assert set(df["series"]) == {"cash_rate"}
    assert set(df["region"]) == {"Australia"}
    assert list(df["value"]) == [7.71, 7.72]
    assert df.attrs["sources"][0]["year"] == "2024"


def test_cash_rate_daily_comes_from_f1(fake_http):
    fake_http.reply(fixture="SYNTHETIC_rba_f1.csv")
    df = ausmacro.get("cash_rate", freq="D")
    assert fake_http.urls == [RBA + "f1-data.csv"]
    assert list(df["source_id"].unique()) == ["RBA,F1/FIRMMCRTD"]
    assert list(df["value"]) == [9.11, 9.12, 9.13]


def test_cash_rate_missing_from_table_is_a_format_change(fake_http):
    fake_http.reply(fixture="SYNTHETIC_rba_fx.csv")
    with pytest.raises(FormatChangedError, match="no longer has series FIRMMCRT"):
        ausmacro.get("cash_rate")


def test_abs_and_rba_in_one_frame(fake_http):
    fake_http.reply(fixture="SYNTHETIC_abs_cpi_monthly.csv")
    fake_http.reply(fixture="SYNTHETIC_rba_f1.1.csv")
    df = ausmacro.get(["cpi", "cash_rate"])
    assert list(df["series"].unique()) == ["cash_rate", "cpi"]
    assert [s["publisher"] for s in df.attrs["sources"]] == ["abs", "rba"]


def test_get_rba_filters_series(fake_http):
    fake_http.reply(fixture="SYNTHETIC_rba_f1.csv")
    df = ausmacro.get_rba("f1", "FIRMMCRTD", start="2025")
    assert fake_http.urls == [RBA + "f1-data.csv"]
    assert list(df["value"]) == [9.13]
    assert df["region"].isna().all()


def test_get_rba_warns_about_ranges_it_returns(fake_http):
    fake_http.reply(fixture="SYNTHETIC_rba_a2.csv")
    with pytest.warns(UserWarning, match="2 values in table A2 are published as ranges"):
        ausmacro.get_rba("A2")


def test_get_rba_is_quiet_when_ranges_are_filtered_out(fake_http):
    fake_http.reply(fixture="SYNTHETIC_rba_a2.csv")
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        df = ausmacro.get_rba("A2", "ARBAMPCNCRT", start="2000")
    assert list(df["value"]) == [6.99]


def test_get_rba_unknown_series_suggests_one(fake_http):
    fake_http.reply(fixture="SYNTHETIC_rba_f1.csv")
    with pytest.raises(SeriesNotFoundError, match="Did you mean 'FIRMMCRTD'"):
        ausmacro.get_rba("F1", "FIRMMCRT")
