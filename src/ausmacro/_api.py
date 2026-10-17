"""The public functions get, get_abs, get_rba, series and clear_cache."""
from __future__ import annotations

import datetime as dt
import difflib
import warnings
from collections.abc import Sequence
from typing import Union

import pandas as pd

from ausmacro import _abs, _cache, _rba, _registry
from ausmacro._registry import STATE_CAPITALS, Series
from ausmacro.errors import FormatChangedError, InvalidRequestError, NoDataError, SeriesNotFoundError

DateLike = Union[str, dt.date, None]


def get(
    names: str | Sequence[str],
    *,
    start: DateLike = None,
    end: DateLike = None,
    region: str | Sequence[str] = "australia",
    freq: str | None = None,
    adjustment: str | None = None,
    cache: bool = True,
) -> pd.DataFrame:
    """Fetch one or more series by name, as one long DataFrame.

    Each row is one observation. Dates are the last day of each period, so the
    June quarter 2026 is 2026-06-30. ``start`` and ``end`` are inclusive and take
    a year, month, quarter or date. ``region`` takes a name, a list of names, or
    ``"all"``.

    ``freq`` and ``adjustment`` default to each series' headline setting:
    monthly for ``cpi``, ``cpi_rents`` and ``cash_rate``, quarterly for ``wpi``,
    and original (not seasonally adjusted) for all of them. ``series()`` lists
    the defaults and every other choice.

    Responses are cached on disk for 24 hours. Pass ``cache=False`` to skip the
    cache for this call.

    Example::

        >>> import ausmacro
        >>> df = ausmacro.get("cpi", start="2025", region=["sydney", "melbourne"])
        >>> df.columns.tolist()
        ['series', 'region', 'freq', 'adjustment', 'date', 'value', 'unit', 'source_id']
        >>> df["freq"].unique().tolist()
        ['M']
    """
    wanted = [names] if isinstance(names, str) else list(dict.fromkeys(names))
    if not wanted:
        raise InvalidRequestError("Pass at least one series name, for example get('cpi').")
    lower, upper = _bounds(start, end)

    frames, sources = [], []
    for name in wanted:
        entry = _registry.lookup(name)
        frame, source = _fetch_series(entry, region, freq, adjustment, cache)
        frames.append(frame)
        sources.append(source)
    data = _between(pd.concat(frames, ignore_index=True), lower, upper, start, end)
    data.attrs["sources"] = sources
    return data


def get_abs(
    dataflow: str, key: str, *, start: DateLike = None, end: DateLike = None, cache: bool = True
) -> pd.DataFrame:
    """Fetch any ABS Data API query by its raw dataflow ID and key.

    Returns the same columns as ``get()``. The ``series`` column holds each
    series' key. The key has one position per dimension, separated by dots;
    leave a position blank for every value, and join values with ``+``.

    Example::

        >>> import ausmacro
        >>> df = ausmacro.get_abs("ABS,CPI,2.0.0", "1.10001.10.50+1.Q", start="2024")
        >>> sorted(df["series"].unique())
        ['1.10001.10.1.Q', '1.10001.10.50.Q']
    """
    lower, upper = _bounds(start, end)
    data = _abs.parse(_abs.fetch(dataflow, key, cache))
    data = _between(data, lower, upper, start, end)
    data.attrs["sources"] = [
        {"publisher": "abs", "title": f"ABS Data API dataflow {dataflow}", "catalogue": ""}
    ]
    return data


def get_rba(
    table: str,
    series_id: str | Sequence[str] | None = None,
    *,
    start: DateLike = None,
    end: DateLike = None,
    cache: bool = True,
) -> pd.DataFrame:
    """Fetch an RBA statistical table, or some of its series, by table and series ID.

    Returns the same columns as ``get()``. The ``series`` column holds the RBA
    series ID, and ``region`` is empty. Only tables the RBA publishes as CSV are
    supported, not the historical .xls files.

    Example::

        >>> import ausmacro
        >>> df = ausmacro.get_rba("F1", "FIRMMCRTD", start="2026-01")
        >>> df["unit"].unique().tolist()
        ['Per cent']
    """
    lower, upper = _bounds(start, end)
    title, data = _rba.parse(_rba.fetch(table, cache), table)
    if series_id is not None:
        ids = [series_id] if isinstance(series_id, str) else list(series_id)
        known = list(data["series"].unique())
        for i in ids:
            if i not in known:
                close = difflib.get_close_matches(i, known, n=1)
                hint = f" Did you mean {close[0]!r}?" if close else ""
                raise SeriesNotFoundError(
                    f"Table {table} has no series {i!r} with data.{hint} "
                    f"Its series are: {', '.join(known)}."
                )
        data = data[data["series"].isin(ids)]
    source = _rba.source(title, data)
    data = _between(data, lower, upper, start, end)
    ranges = int(data["value"].isna().sum())
    if ranges:
        warnings.warn(
            f"{ranges} values in table {table} are published as ranges, such as "
            "'17.00 to 17.50', and are returned as NaN.",
            stacklevel=2,
        )
    data.attrs["sources"] = [source]
    return data


def series(search: str | None = None) -> pd.DataFrame:
    """List the series ``get()`` knows, with their defaults, optionally filtered by a word.

    Example::

        >>> import ausmacro
        >>> ausmacro.series("wage")[["name", "default_freq"]].values.tolist()
        [['wpi', 'Q']]
    """
    rows = [
        {
            "name": s.name,
            "publisher": s.publisher.upper(),
            "description": s.description,
            "unit": s.unit,
            "default_freq": s.defaults["freq"],
            "default_adjustment": s.defaults["adjustment"],
            "freqs": ", ".join(s.freqs),
            "regions": ", ".join(s.regions),
            "adjustments": ", ".join(s.adjustments),
            "notes": s.notes,
        }
        for s in _registry.load().values()
    ]
    table = pd.DataFrame(rows)
    if search:
        text = table["name"] + " " + table["description"]
        table = table[text.str.contains(search, case=False, regex=False)]
    return table.reset_index(drop=True)


def clear_cache() -> int:
    """Delete every cached response and return how many files were removed.

    Example::

        >>> import ausmacro
        >>> removed = ausmacro.clear_cache()
    """
    return _cache.clear()


def _fetch_series(
    entry: Series,
    region: str | Sequence[str],
    freq: str | None,
    adjustment: str | None,
    cache: bool,
) -> tuple[pd.DataFrame, dict[str, str]]:
    regions = _regions(entry, region)
    freq = freq or entry.defaults["freq"]
    adjustment = adjustment or entry.defaults["adjustment"]
    if freq not in entry.freqs:
        raise InvalidRequestError(
            f"{entry.name} has no frequency {freq!r}. Choose from: {', '.join(entry.freqs)}."
        )
    if adjustment not in entry.adjustments:
        raise InvalidRequestError(
            f"{entry.name} has no adjustment {adjustment!r}. "
            f"Choose from: {', '.join(entry.adjustments)}."
        )
    if entry.publisher == "rba":
        return _fetch_rba_series(entry, freq, cache)

    key = entry.key.format(
        adjustment=entry.adjustments[adjustment],
        region="+".join(entry.regions[r] for r in regions),
        freq=freq,
    )
    asked = f"region={', '.join(regions)}, freq={freq!r}, adjustment={adjustment!r}"
    try:
        data = _abs.parse(_abs.fetch(entry.dataflow, key, cache))
    except NoDataError:
        raise NoDataError(f"The ABS has no {entry.name} data for {asked}. {entry.notes}") from None

    if region != "all":
        found = set(data["_region_code"])
        absent = [r for r in regions if entry.regions[r] not in found]
        if absent:
            warnings.warn(
                f"The ABS has no {entry.name} data for {', '.join(absent)} with freq={freq!r} "
                f"and adjustment={adjustment!r}. {entry.notes}",
                stacklevel=3,
            )
    # The WPI response has no base period, so fall back to the one in the registry.
    data["unit"] = data["unit"].where(data["_base_period"] != "", entry.unit)
    data["series"] = entry.name
    source = {"publisher": "abs", "title": entry.title, "catalogue": entry.catalogue}
    return data.drop(columns=["_region_code", "_base_period"]), source


def _fetch_rba_series(entry: Series, freq: str, cache: bool) -> tuple[pd.DataFrame, dict[str, str]]:
    table, series_id = entry.rba[freq]
    title, data = _rba.parse(_rba.fetch(table, cache), table)
    data = data[data["series"] == series_id].copy()
    if data.empty:
        raise FormatChangedError(
            f"RBA table {table} no longer has series {series_id}, which {entry.name} needs. "
            "Please report this at the ausmacro issue tracker."
        )
    source = _rba.source(title, data)
    # RBA series are national; label them so they line up with ABS rows.
    data["region"] = "Australia"
    data["series"] = entry.name
    return data.drop(columns=["_source", "_published"]), source


def _regions(entry: Series, region: str | Sequence[str]) -> list[str]:
    if region == "all":
        return list(entry.regions)
    asked = [region] if isinstance(region, str) else list(region)
    regions = []
    for r in asked:
        r = r.lower()
        if r not in entry.regions:
            raise InvalidRequestError(
                f"{entry.name} has no region {r!r}.{_region_hint(entry, r)} "
                f"Choose from: {', '.join(entry.regions)}, or 'all'."
            )
        regions.append(r)
    return regions


def _region_hint(entry: Series, region: str) -> str:
    capital = STATE_CAPITALS.get(region)
    if capital in entry.regions:
        return f" It is published by capital city, so try {capital!r}."
    state = {c: s for s, c in STATE_CAPITALS.items()}.get(region)
    if state in entry.regions:
        return f" It is published by state, so try {state!r}."
    close = difflib.get_close_matches(region, entry.regions, n=1)
    return f" Did you mean {close[0]!r}?" if close else ""


def _bounds(start: DateLike, end: DateLike) -> tuple[pd.Timestamp | None, pd.Timestamp | None]:
    """Turn inclusive start and end values into the first and last day they cover."""
    lower = _period(start).start_time if start is not None else None
    upper = _period(end).end_time.normalize() if end is not None else None
    if lower is not None and upper is not None and lower > upper:
        raise InvalidRequestError(f"start ({start}) is after end ({end}).")
    return lower, upper


def _period(value: str | dt.date) -> pd.Period:
    try:
        if isinstance(value, str):
            # pd.Period infers the span: '2020' is a year, '2020-Q1' a quarter.
            return pd.Period(value)
        return pd.Period(value, freq="D")
    except (ValueError, TypeError):
        raise InvalidRequestError(
            f"Could not read {value!r} as a date. Use a year ('2020'), a month ('2020-03'), "
            "a quarter ('2020-Q1') or a date ('2020-03-15')."
        ) from None


def _between(
    data: pd.DataFrame,
    lower: pd.Timestamp | None,
    upper: pd.Timestamp | None,
    start: DateLike,
    end: DateLike,
) -> pd.DataFrame:
    # Dates are filtered here, not by the API, so one cached response serves every date range.
    keep = pd.Series(True, index=data.index)
    if lower is not None:
        keep &= data["date"] >= lower
    if upper is not None:
        keep &= data["date"] <= upper
    if not keep.any():
        raise NoDataError(
            f"No observations between {start or 'the start'} and {end or 'the end'}. "
            f"The data runs from {data['date'].min():%Y-%m-%d} to {data['date'].max():%Y-%m-%d}."
        )
    data = data[keep].sort_values(["series", "region", "adjustment", "freq", "date"])
    return data[_abs.COLUMNS].reset_index(drop=True)
