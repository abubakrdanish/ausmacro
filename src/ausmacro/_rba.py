"""Fetch and parse RBA statistical tables (the CSV versions).

Every table has the same layout: a title line, a header block (Title,
Description, Frequency, Type, Units, Source, Publication date, Series ID),
then one row per date with one column per series.
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import re

import pandas as pd

from ausmacro import _cache, _http
from ausmacro.errors import FormatChangedError, SeriesNotFoundError, UpstreamError

BASE_URL = "https://www.rba.gov.au/statistics/tables/csv"
FREQS = {"daily": "D", "weekly": "W", "monthly": "M", "quarterly": "Q", "annual": "A"}
PERIOD_FREQS = {"M": "M", "Q": "Q", "A": "Y"}
# Tables use either date style: F1 and A2 have 04-Jan-2011, F1.1 and G1 have 30/06/1969.
DATE_FORMATS = {r"\d{2}-[A-Za-z]{3}-\d{4}": "%d-%b-%Y", r"\d{2}/\d{2}/\d{4}": "%d/%m/%Y"}


def url(table: str) -> str:
    return f"{BASE_URL}/{table.lower()}-data.csv"


def fetch(table: str, cache: bool = True) -> bytes:
    """Download one table's CSV, turning RBA error responses into ausmacro errors."""
    address = url(table)
    if cache and (hit := _cache.read(address)) is not None:
        return hit
    response = _http.get(address, "text/csv")
    if response.status_code == 200:
        if cache:
            _cache.write(address, response.content)
        return response.content
    if response.status_code == 404:
        raise SeriesNotFoundError(
            f"The RBA has no table {table!r}. Table IDs look like 'F1' or 'F1.1'; the list is at "
            "https://www.rba.gov.au/statistics/tables/. Historical tables published only as "
            ".xls files are not supported."
        )
    raise UpstreamError(
        f"The RBA website returned HTTP {response.status_code} for {address}. Try again later."
    )


def parse(content: bytes, table: str) -> tuple[str, pd.DataFrame]:
    """Return a table's title and a long frame of its observations.

    The frame has ausmacro's columns plus _source and _published, taken from
    each series' Source and Publication date rows.
    """
    text = content.decode("utf-8-sig")
    if text.lstrip().startswith("<"):
        raise FormatChangedError(
            f"The RBA returned a web page instead of the CSV for table {table}. "
            "Its website may have changed; please report this at the ausmacro issue tracker."
        )
    rows = list(csv.reader(io.StringIO(text)))
    starts = [i for i, row in enumerate(rows) if row and row[0].strip() == "Series ID"]
    if not starts:
        raise FormatChangedError(f"Table {table} has no 'Series ID' row, so ausmacro cannot read it.")
    start = starts[0]
    ids = [s.strip() for s in rows[start][1:] if s.strip()]
    header = {row[0].strip(): _pad(row[1:], len(ids)) for row in rows[:start] if row and row[0]}
    title = " ".join(rows[0][0].split())

    # Files are padded with blank rows, and short rows leave trailing series empty.
    body = [row for row in rows[start + 1 :] if row and row[0].strip()]
    wide = pd.DataFrame([_pad(row[1:], len(ids)) for row in body], columns=ids, dtype=str)
    wide.insert(0, "_date", [row[0].strip() for row in body])
    long = wide.melt(id_vars="_date", var_name="series", value_name="raw")
    long["raw"] = long["raw"].str.strip()
    long = long[~long["raw"].isin(["", "N/A"])].reset_index(drop=True)

    meta = pd.DataFrame(
        {
            "series": ids,
            "freq": [FREQS.get(f.strip().lower()) for f in header.get("Frequency", _pad([], len(ids)))],
            "adjustment": header.get("Type", _pad([], len(ids))),
            "unit": header["Units"],
            "_source": header.get("Source", _pad([], len(ids))),
            "_published": header.get("Publication date", _pad([], len(ids))),
        }
    )
    long = long.merge(meta, on="series", how="left")
    frame = pd.DataFrame(
        {
            "series": long["series"],
            "region": None,
            "freq": long["freq"],
            "adjustment": long["adjustment"],
            "date": _period_end(_dates(long["_date"], table), long["freq"]),
            "value": _numbers(long["raw"], table),
            "unit": long["unit"],
            "source_id": f"RBA,{table.upper()}/" + long["series"],
            "_source": long["_source"],
            "_published": long["_published"],
        }
    )
    return title, frame.sort_values(["series", "date"]).reset_index(drop=True)


def source(title: str, frame: pd.DataFrame) -> dict[str, str]:
    """Describe the table for attribution: its title, year and any third-party series."""
    years = frame["_published"].str.extract(r"(\d{4})$", expand=False).dropna()
    third_party = []
    for series_id, cell in frame.groupby("series")["_source"].first().items():
        # "ABS / RBA" lists two sources; "WM/Reuters" (no spaces) is one.
        others = [part for part in cell.split(" / ") if part.strip() and part.strip() != "RBA"]
        if others:
            third_party.append(f"{series_id} ({' and '.join(others)})")
    return {
        "publisher": "rba",
        "title": title,
        "catalogue": "",
        "year": years.max() if not years.empty else str(dt.date.today().year),
        "third_party": "; ".join(third_party),
    }


def _pad(cells: list[str], width: int) -> list[str]:
    return (cells + [""] * width)[:width]


def _dates(cells: pd.Series, table: str) -> pd.Series:
    first = cells.iloc[0] if len(cells) else ""
    for pattern, fmt in DATE_FORMATS.items():
        if re.fullmatch(pattern, first):
            try:
                return pd.to_datetime(cells, format=fmt).astype("datetime64[ns]")
            except ValueError as exc:
                raise FormatChangedError(f"Table {table} has a date ausmacro cannot read: {exc}") from exc
    if not len(cells):
        return pd.Series(dtype="datetime64[ns]")
    raise FormatChangedError(f"Table {table} has a date ausmacro cannot read: {first!r}")


def _period_end(dates: pd.Series, freq: pd.Series) -> pd.Series:
    """Move monthly, quarterly and annual dates to the last day of their period."""
    dates = dates.copy()
    for code, pandas_freq in PERIOD_FREQS.items():
        mask = freq == code
        if mask.any():
            periods = dates[mask].dt.to_period(pandas_freq)
            dates.loc[mask] = periods.dt.end_time.dt.normalize().astype("datetime64[ns]")
    return dates


def _numbers(raw: pd.Series, table: str) -> pd.Series:
    # A2 gives early changes as ranges such as "17.00 to 17.50". They have no
    # single value, so they become NaN rather than a guessed midpoint. Blank and
    # N/A cells are already dropped, so a NaN value always means a range.
    ranges = raw.str.contains(" to ", regex=False)
    try:
        return pd.to_numeric(raw.where(~ranges)).astype("float64")
    except ValueError as exc:
        raise FormatChangedError(f"Table {table} has a non-numeric value: {exc}") from exc
