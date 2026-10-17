"""The readable-name registry, loaded from series.json."""
from __future__ import annotations

import difflib
import json
from dataclasses import dataclass, field
from functools import lru_cache
from importlib import resources

from ausmacro.errors import SeriesNotFoundError

# CPI is published by capital city and WPI by state, so a state name given for a
# CPI series gets a hint rather than a silent mapping.
STATE_CAPITALS = {
    "nsw": "sydney",
    "vic": "melbourne",
    "qld": "brisbane",
    "sa": "adelaide",
    "wa": "perth",
    "tas": "hobart",
    "nt": "darwin",
    "act": "canberra",
}


@dataclass(frozen=True)
class Series:
    """One entry in series.json.

    ABS entries have a dataflow and a key template. RBA entries map each
    frequency to a [table, series ID] pair in ``rba``.
    """

    name: str
    publisher: str
    description: str
    title: str
    unit: str
    freqs: tuple[str, ...]
    adjustments: dict[str, str]
    regions: dict[str, str]
    defaults: dict[str, str]
    notes: str
    catalogue: str = ""
    dataflow: str = ""
    key: str = ""
    rba: dict[str, list[str]] = field(default_factory=dict)


@lru_cache(maxsize=1)
def load() -> dict[str, Series]:
    """Read series.json once."""
    text = resources.files("ausmacro").joinpath("series.json").read_text(encoding="utf-8")
    return {
        name: Series(name=name, **{**fields, "freqs": tuple(fields["freqs"])})
        for name, fields in json.loads(text).items()
    }


def lookup(name: str) -> Series:
    """Return a series by name, or raise with the closest match."""
    registry = load()
    if name in registry:
        return registry[name]
    message = f"No series named {name!r}."
    suggestions = difflib.get_close_matches(name.lower(), registry, n=1, cutoff=0.6) or [
        s.name for s in registry.values() if name.lower() in s.description.lower()
    ]
    if suggestions:
        message += f" Did you mean {suggestions[0]!r}?"
    message += " Call ausmacro.series() to list every series."
    raise SeriesNotFoundError(message)
