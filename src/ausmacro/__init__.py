"""Australian macroeconomic series from the ABS and RBA, as tidy pandas DataFrames."""
from importlib.metadata import version

from ausmacro._api import clear_cache, get, get_abs, get_rba, series
from ausmacro._attribution import attribution
from ausmacro.errors import (
    AusMacroError,
    FormatChangedError,
    InvalidRequestError,
    NoDataError,
    SeriesNotFoundError,
    UpstreamError,
)

__version__ = version("ausmacro")

__all__ = [
    "AusMacroError",
    "FormatChangedError",
    "InvalidRequestError",
    "NoDataError",
    "SeriesNotFoundError",
    "UpstreamError",
    "attribution",
    "clear_cache",
    "get",
    "get_abs",
    "get_rba",
    "series",
]
