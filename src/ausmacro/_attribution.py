"""Attribution text for data fetched with ausmacro."""
from __future__ import annotations

import datetime as dt
import warnings
from collections.abc import Sequence

import pandas as pd

from ausmacro import _registry
from ausmacro.errors import InvalidRequestError

# Wording from the ABS conditions of sale, "Creative commons attribution" section:
# https://www.abs.gov.au/about/legislation-and-policy/purchasing-data/abs-conditions-sale
# It also says users "must make clear to others the licence terms", hence the licence clause.
ABS_SOURCE = "Source: Australian Bureau of Statistics"
ABS_BASED_ON = "Based on Australian Bureau of Statistics data"
ABS_LICENCE = "Licensed under CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/)."
# The RBA copyright notice, section 3, requires "Source: Reserve Bank of Australia [year]"
# and gives no separate wording for modified data: https://www.rba.gov.au/copyright/
RBA_SOURCE = "Source: Reserve Bank of Australia"


def attribution(data: pd.DataFrame | str | Sequence[str], *, modified: bool = False) -> str:
    """Return the attribution text the ABS and RBA ask for, for a frame or series names.

    Use ``modified=True`` once you have changed ABS data in any way, for example
    rebased, averaged or computed growth rates. The ABS then asks for "Based on
    Australian Bureau of Statistics data" instead of "Source: ...". The RBA
    asks for the same wording either way.

    The RBA's wording includes a year. For a frame, that is the publication
    year of the table it came from. Called with series names, no table is
    fetched, so the year is the current year.

    If some of the RBA data comes from a third party, such as WM/Reuters for
    exchange rates, this also issues a warning: the RBA's terms say you need that
    party's consent to reuse it.

    pandas drops the source information on some operations, such as merges.
    If that happens, pass the series names instead of the frame.

    Example::

        >>> import ausmacro
        >>> print(ausmacro.attribution(["cpi", "wpi"]))
        Source: Australian Bureau of Statistics, Consumer Price Index, Australia (6401.0) and Wage Price Index, Australia (6345.0). Licensed under CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/).
    """
    sources = _sources(data)
    parts = []
    abs_sources = [s for s in sources if s["publisher"] == "abs"]
    if abs_sources:
        titles = list(dict.fromkeys(_title(s) for s in abs_sources))
        listed = titles[0] if len(titles) == 1 else ", ".join(titles[:-1]) + " and " + titles[-1]
        lead = f"{ABS_BASED_ON}: " if modified else f"{ABS_SOURCE}, "
        parts.append(f"{lead}{listed}. {ABS_LICENCE}")
    rba_sources = [s for s in sources if s["publisher"] == "rba"]
    if rba_sources:
        parts.append(f"{RBA_SOURCE} {max(s['year'] for s in rba_sources)}.")
        _warn_third_party(rba_sources)
    return " ".join(parts)


def _sources(data: pd.DataFrame | str | Sequence[str]) -> list[dict[str, str]]:
    if isinstance(data, pd.DataFrame):
        sources: list[dict[str, str]] = data.attrs.get("sources", [])
        if not sources:
            raise InvalidRequestError(
                "This DataFrame has lost its source information, which pandas drops on some "
                "operations. Pass the series names instead, for example attribution(['cpi'])."
            )
        return sources
    names = [data] if isinstance(data, str) else list(data)
    if not names:
        raise InvalidRequestError("Pass a DataFrame from ausmacro or at least one series name.")
    # Without a fetched table there is no publication date, so the RBA year is this year.
    return [
        {
            "publisher": s.publisher,
            "title": s.title,
            "catalogue": s.catalogue,
            "year": str(dt.date.today().year),
            "third_party": "",
        }
        for s in map(_registry.lookup, names)
    ]


def _title(source: dict[str, str]) -> str:
    if source["catalogue"]:
        return f"{source['title']} ({source['catalogue']})"
    return source["title"]


def _warn_third_party(sources: list[dict[str, str]]) -> None:
    listed = "; ".join(s["third_party"] for s in sources if s.get("third_party"))
    if not listed:
        return
    message = (
        f"Some RBA series come from a third party: {listed}. The RBA's terms say you need "
        "that party's consent to reuse them."
    )
    if "ABS" in listed:
        message += " Data from the ABS is licensed under CC BY 4.0, so credit the ABS for it as well."
    warnings.warn(message, stacklevel=3)
