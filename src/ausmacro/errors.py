"""Exceptions raised by ausmacro. All of them inherit from AusMacroError."""
from __future__ import annotations


class AusMacroError(Exception):
    """Base class for every error ausmacro raises."""


class SeriesNotFoundError(AusMacroError, KeyError):
    """The series name or ABS dataflow does not exist."""

    # KeyError would otherwise print the message wrapped in quotes.
    def __str__(self) -> str:
        return str(self.args[0]) if self.args else ""


class InvalidRequestError(AusMacroError, ValueError):
    """An argument is not valid, such as a region the series does not cover or an unreadable date."""


class NoDataError(AusMacroError):
    """The request was valid, but the source has no observations for it."""


class UpstreamError(AusMacroError):
    """The network failed or the source returned an error, even after retries."""


class FormatChangedError(AusMacroError):
    """The source returned something ausmacro cannot parse, such as an HTML page."""
