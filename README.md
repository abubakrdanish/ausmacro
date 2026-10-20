# ausmacro

ausmacro is a small Python library for a few headline Australian economic series from the Australian Bureau of Statistics (ABS) and the Reserve Bank of Australia (RBA). It returns them as tidy pandas DataFrames, and it gives you the attribution text each publisher asks for.

It is deliberately small, with four named series. If you need full ABS coverage, any table from any release, or earlier versions of revised data, use [readabs](https://github.com/bpalmer4/readabs) instead. readabs also reads RBA tables. For direct access to the ABS Data API, see [sdmxabs](https://github.com/bpalmer4/sdmxabs) or [sdmx1](https://github.com/khaeru/sdmx).

## Install

```
pip install ausmacro
```

ausmacro supports Python 3.10 to 3.14 on Linux, macOS and Windows, and is tested on each of them. It depends on pandas (2.2.2 or later), requests, urllib3 and platformdirs.

## Use

```python
import ausmacro

df = ausmacro.get(["cpi", "cash_rate"], start="2020")
print(ausmacro.attribution(df))
```

Every call returns one long DataFrame, with one row per observation:

| column | meaning |
|---|---|
| `series` | the name you asked for, such as `cpi`, or the raw ID from `get_abs` and `get_rba` |
| `region` | the ABS label, such as `Sydney` or `New South Wales`; `Australia` for the cash rate |
| `freq` | `M` monthly, `Q` quarterly or `D` daily; empty for irregular RBA series |
| `adjustment` | `Original`, `Seasonally Adjusted` or `Trend` |
| `date` | the last day of the period, so the June quarter 2026 is 2026-06-30 |
| `value` | the number, as a float |
| `unit` | for example `Index Numbers (Sep 2025 = 100.0)` or `Per cent` |
| `source_id` | where the row came from, such as `ABS,CPI,2.0.0/1.10001.10.50.M` or `RBA,F1.1/FIRMMCRT` |

To get a wide table, pivot it: `df.pivot(index="date", columns="series", values="value")`.

## Series

| name | what it is | regions | default | other frequencies |
|---|---|---|---|---|
| `cpi` | Consumer Price Index, all groups | Australia and the eight capital cities | monthly, from April 2024 | quarterly, from 1948 |
| `cpi_rents` | CPI rents | Australia and the eight capital cities | monthly, from July 2022 | quarterly for Australia only, from 1972 |
| `wpi` | Wage Price Index, total hourly rates of pay excluding bonuses | Australia, states and territories | quarterly, from 1997 | none |
| `cash_rate` | RBA cash rate target | Australia | monthly average, from August 1990 (table F1.1) | daily, from January 2011 (table F1) |

Every series defaults to original (not seasonally adjusted) data. `ausmacro.series()` lists each series with its defaults, units and notes.

The CPI is published by capital city and the WPI by state. ausmacro does not map one onto the other, so `region="nsw"` is an error for `cpi`, and the message suggests `"sydney"`.

CPI rents are measured net of Commonwealth Rent Assistance, so they do not track market asking rents.

Quarterly CPI carries the label `Sep 2025 = 100.0`, but the September quarter 2025 reads 99.73, not 100.0. It is the monthly series that reads 100.0 in September 2025, and 99.73 is the average of the July, August and September monthly values. Both the values and the label come from the ABS, and ausmacro passes them through unchanged.

The monthly cash rate is the average of the daily target over the month. A month with a change shows a blend: September 2026 is 4.36, between 4.35 and 4.60. For the exact dates of changes, use `get_rba("A2", "ARBAMPCNCRT")`. A2 dates each change on the day it takes effect.

## Functions

- `get(names, *, start=None, end=None, region="australia", freq=None, adjustment=None, cache=True)` fetches series by name. `start` and `end` are inclusive and take a year (`"2020"`), month (`"2020-03"`), quarter (`"2020-Q1"`) or date. `region` takes a name, a list, or `"all"`.
- `get_abs(dataflow, key, *, start=None, end=None, cache=True)` fetches any ABS Data API query by its raw IDs, for example `get_abs("ABS,CPI,2.0.0", "1.10001.10.50.Q")`.
- `get_rba(table, series_id=None, *, start=None, end=None, cache=True)` fetches an RBA statistical table, or some of its series, for example `get_rba("F1", "FIRMMCRTD")`.
- `series(search=None)` lists the series `get` knows.
- `attribution(data, *, modified=False)` returns the attribution text for a frame or for series names.
- `clear_cache()` deletes cached responses.

`get_abs` and `get_rba` return the same columns as `get`.

## Attribution

```python
>>> ausmacro.attribution(["cpi", "cash_rate"])
'Source: Australian Bureau of Statistics, Consumer Price Index, Australia. Licensed under CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/). Source: Reserve Bank of Australia 2026.'
```

ABS data is licensed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). The [ABS conditions of sale](https://www.abs.gov.au/about/legislation-and-policy/purchasing-data/abs-conditions-sale) ask for "Source: Australian Bureau of Statistics" for unchanged data. Once you have changed the data in any way, for example by rebasing it or computing growth rates, they ask for "Based on Australian Bureau of Statistics data". Pass `modified=True` to get that wording.

The [RBA copyright notice](https://www.rba.gov.au/copyright/) excludes cash-rate and financial data from its CC BY licence and gives them separate permissions. It allows personal and commercial use as long as you do not suggest the RBA endorses it. It requires the attribution "Source: Reserve Bank of Australia [year]". ausmacro uses the table's publication year.

The ABS now describes 6401.0 and 6345.0 as previous catalogue numbers for the CPI and WPI releases, so ausmacro does not include them in current attribution text.

Some RBA series come from third parties. For example, the AUD/USD rate in table F11.1 comes from WM/Reuters. The RBA says you need the third party's consent to reuse such data. `attribution()` warns when a frame includes one of these series.

pandas drops the source information on some operations, such as merges. If `attribution(df)` says so, pass the series names instead.

ausmacro contains no ABS or RBA data. Everything is downloaded when you ask for it.

## Caching

Downloaded responses are kept on disk for 24 hours, so repeated calls are fast and do not hit the ABS or RBA again. The cache holds the raw responses, not DataFrames, and dates are filtered after reading, so one cached file serves every date range.

- Location: your user cache folder, as chosen by [platformdirs](https://pypi.org/project/platformdirs/); on macOS that is `~/Library/Caches/ausmacro`. Set `AUSMACRO_CACHE_DIR` to use another folder.
- Skip it for one call with `cache=False`. That call neither reads nor writes the cache.
- Empty it with `ausmacro.clear_cache()`.

If the cache folder cannot be written, ausmacro warns and carries on without it.

## Errors

Every error inherits from `ausmacro.AusMacroError`:

- `SeriesNotFoundError`: an unknown name, ABS dataflow, RBA table or RBA series. The message suggests the closest match.
- `InvalidRequestError`: a region, frequency, adjustment or date the series does not have. The message lists the valid choices.
- `NoDataError`: the request is valid, but there are no observations for it.
- `UpstreamError`: the network failed, or the ABS or RBA returned an error after retries. The ABS Data API is in beta and is sometimes unavailable.
- `FormatChangedError`: the ABS or RBA returned something ausmacro cannot read. Please report it.

If you ask for several regions and some have no data, `get` returns the rest and issues a warning naming the missing ones.

## Network use

ausmacro identifies itself with a `User-Agent` header. It waits at least one second between requests, and it retries on rate limits (HTTP 429) and server errors with backoff, following `Retry-After`. It downloads a whole series or table and filters dates locally; the largest file it fetches, RBA table F1, is about 300 KB.

## Limitations

- The ABS marks revised observations in a column called `OBS_STATUS`. ausmacro 0.1 does not expose it, so you cannot tell a revised value from an original one.
- ausmacro gets the latest release only. For earlier versions of revised data, use readabs.
- Only RBA tables published as CSV are supported. Historical tables the RBA publishes only as .xls files, such as daily cash rates before 2011, are not.
- Some early values in RBA table A2 are ranges, such as "17.00 to 17.50". They are returned as NaN, with a warning.

## Development

```
git clone https://github.com/abubakrdanish/ausmacro.git
cd ausmacro
python -m venv .venv
.venv/bin/pip install -r requirements-dev.lock -e .
.venv/bin/pytest            # offline; the network is blocked
.venv/bin/pytest --live     # also runs the one test against the real ABS and RBA
.venv/bin/mypy src
```

`requirements-dev.lock` pins every development dependency for Python 3.10 to 3.14 on any operating system. It is made with [uv](https://docs.astral.sh/uv/). After changing the dependencies in `pyproject.toml`, regenerate it with:

```
uv pip compile pyproject.toml --extra dev --universal --python-version 3.10 --output-file requirements-dev.lock
```

The tests also run the examples in the public docstrings, against synthetic fixtures. Test fixtures are small synthetic files, with SYNTHETIC in their names and contents. Tests use a temporary cache folder, never your real one.

GitHub Actions runs the tests and mypy on Linux, macOS and Windows with Python 3.10 to 3.14, once more with the oldest dependency versions `pyproject.toml` allows, and in an explicit pandas 3 job. The workflow is in `.github/workflows/ci.yml`.

## Licence

MIT. The licence covers the code only. Data you download is under the publisher's terms.
