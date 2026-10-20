# Changelog

## 0.1.0

First release.

- `get()` fetches four named series as one long pandas DataFrame:
  - `cpi`: Consumer Price Index, all groups, monthly or quarterly, for Australia and the eight capital cities
  - `cpi_rents`: CPI rents, monthly or quarterly
  - `wpi`: Wage Price Index, quarterly, for Australia and the states and territories
  - `cash_rate`: RBA cash rate target, monthly average or daily
- `get_abs()` fetches any ABS Data API query by its raw dataflow and key.
- `get_rba()` fetches any RBA statistical table published as CSV, or some of its series.
- `series()` lists the named series with their defaults, units and notes.
- `attribution()` returns the attribution text the ABS and RBA ask for, with `modified=True` for changed data.
- Responses are cached on disk for 24 hours. `clear_cache()` empties the cache, and `cache=False` skips it for one call.
- Errors inherit from `AusMacroError`.
- Requires Python 3.10 or later, pandas 2.2.2 or later, requests, urllib3 and platformdirs.
