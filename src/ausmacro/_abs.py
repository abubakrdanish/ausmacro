"""Fetch and parse SDMX-CSV from the ABS Data API.

API guide: https://www.abs.gov.au/about/data-services/application-programming-interfaces-apis/data-api-user-guide
"""
from __future__ import annotations

import io
import re

import pandas as pd

from ausmacro import _cache, _http
from ausmacro.errors import (
    FormatChangedError,
    InvalidRequestError,
    NoDataError,
    SeriesNotFoundError,
    UpstreamError,
)

BASE_URL = "https://data.api.abs.gov.au/rest"
# labels=both gives cells like "50: Australia", so one request returns codes and labels.
CSV_ACCEPT = "application/vnd.sdmx.data+csv;labels=both"
REQUIRED = ("DATAFLOW", "FREQ", "TIME_PERIOD", "OBS_VALUE")
PANDAS_FREQ = {"A": "Y", "Q": "Q", "M": "M", "D": "D"}
COLUMNS = ["series", "region", "freq", "adjustment", "date", "value", "unit", "source_id"]


def fetch(dataflow: str, key: str, cache: bool = True) -> bytes:
    """Download one data query, turning ABS error responses into ausmacro errors."""
    url = f"{BASE_URL}/data/{dataflow}/{key}"
    if cache and (hit := _cache.read(url)) is not None:
        return hit
    response = _http.get(url, CSV_ACCEPT)
    status = response.status_code
    if status == 200:
        if cache:
            _cache.write(url, response.content)
        return response.content
    # The API answers errors with a short plain-text body, and uses 404 both for
    # "no such dataflow" and for a valid query that matches no observations.
    body = response.text.strip()[:200]
    if status == 404 and body == "NoRecordsFound":
        raise NoDataError(f"The ABS has no observations for {dataflow}/{key}.")
    if status == 404 and body.startswith("Could not find Dataflow"):
        raise SeriesNotFoundError(
            f"The ABS has no dataflow {dataflow!r}. Dataflow IDs look like 'ABS,CPI,2.0.0'; "
            "the ABS lists them at https://data.api.abs.gov.au/rest/dataflow/ABS."
        )
    if status in (400, 422):
        raise InvalidRequestError(f"The ABS rejected the query {dataflow}/{key}: {body}")
    raise UpstreamError(
        f"The ABS Data API returned HTTP {status} for {url}. "
        "The API is in beta and is sometimes unavailable, so try again later."
    )


def parse(content: bytes) -> pd.DataFrame:
    """Turn an SDMX-CSV response into a long frame with ausmacro's columns.

    Two private columns are added for the caller: _region_code and _base_period.
    """
    text = content.decode("utf-8-sig")
    if text.lstrip().startswith("<"):
        raise FormatChangedError(
            "The ABS returned a web page instead of CSV data. Its API may have changed; "
            "please report this at the ausmacro issue tracker."
        )
    raw = pd.read_csv(io.StringIO(text), dtype=str, keep_default_na=False)
    # Headers carry labels too ("TIME_PERIOD: Time Period"); keep only the code.
    raw.columns = [c.split(":", 1)[0].strip() for c in raw.columns]
    missing = [c for c in REQUIRED if c not in raw.columns]
    if missing:
        raise FormatChangedError(
            f"The ABS response is missing the columns {missing}. Its format may have changed; "
            "please report this at the ausmacro issue tracker."
        )
    raw = raw[raw["OBS_VALUE"] != ""]
    if raw.empty:
        raise NoDataError("The ABS response has no observations.")

    # In SDMX-CSV the dimensions sit between DATAFLOW and TIME_PERIOD, in key order.
    columns = list(raw.columns)
    dims = columns[1 : columns.index("TIME_PERIOD")]
    key = raw[dims].apply(lambda col: col.map(_code)).agg(".".join, axis=1)
    freq = raw["FREQ"].map(_code)
    blank = pd.Series("", index=raw.index)
    base = raw["BASE_PERIOD"].map(_label) if "BASE_PERIOD" in raw else blank
    unit = raw["UNIT_MEASURE"].map(_label) if "UNIT_MEASURE" in raw else blank

    frame = pd.DataFrame(
        {
            "series": key,
            "region": raw["REGION"].map(_label) if "REGION" in raw else None,
            "freq": freq,
            "adjustment": raw["TSEST"].map(_label) if "TSEST" in raw else None,
            "date": _period_end(raw["TIME_PERIOD"], freq),
            "value": _numbers(raw["OBS_VALUE"]),
            "unit": unit.where(base == "", unit + " (" + base + ")"),
            "source_id": raw["DATAFLOW"].map(_dataflow_id) + "/" + key,
            "_region_code": raw["REGION"].map(_code) if "REGION" in raw else None,
            "_base_period": base,
        }
    )
    return frame.reset_index(drop=True)


def _code(cell: str) -> str:
    return cell.split(":", 1)[0].strip()


def _label(cell: str) -> str:
    return cell.split(": ", 1)[1].strip() if ": " in cell else cell.strip()


def _dataflow_id(cell: str) -> str:
    """'ABS:CPI(2.0.0)' in the data -> 'ABS,CPI,2.0.0' as used in query URLs."""
    match = re.fullmatch(r"(\w+):(\w+)\(([\w.]+)\)", cell.strip())
    if not match:
        raise FormatChangedError(f"Unexpected DATAFLOW value {cell!r} in the ABS response.")
    return ",".join(match.groups())


def _numbers(values: pd.Series) -> pd.Series:
    try:
        return pd.to_numeric(values).astype("float64")
    except ValueError as exc:
        raise FormatChangedError(f"The ABS response has a non-numeric value: {exc}") from exc


def _period_end(periods: pd.Series, freq: pd.Series) -> pd.Series:
    """Date each observation at the last day of its period: 2026-Q2 -> 2026-06-30."""
    dates = pd.Series(pd.NaT, index=periods.index, dtype="datetime64[ns]")
    for code, idx in freq.groupby(freq).groups.items():
        if code not in PANDAS_FREQ:
            raise FormatChangedError(
                f"ausmacro cannot read time periods with frequency {code!r} yet."
            )
        index = pd.PeriodIndex(periods.loc[idx], freq=PANDAS_FREQ[code])
        dates.loc[idx] = index.end_time.normalize().astype("datetime64[ns]")
    return dates
