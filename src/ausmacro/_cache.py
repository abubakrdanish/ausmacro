"""A disk cache of raw responses, keyed by URL.

Raw bytes are cached rather than parsed frames, so a parser fix in a new
version of ausmacro never needs the cache cleared.
"""
from __future__ import annotations

import hashlib
import os
import tempfile
import time
import warnings
from pathlib import Path

import platformdirs

MAX_AGE = 24 * 60 * 60  # seconds
SUFFIX = ".ausmacro-cache"


def directory() -> Path:
    """The cache folder: AUSMACRO_CACHE_DIR if set, else the user cache folder."""
    override = os.environ.get("AUSMACRO_CACHE_DIR")
    return Path(override) if override else platformdirs.user_cache_path("ausmacro")


def read(url: str) -> bytes | None:
    """Return the cached body for a URL, or None if it is missing or older than a day."""
    path = _path(url)
    try:
        if time.time() - path.stat().st_mtime > MAX_AGE:
            return None
        return path.read_bytes()
    except OSError:
        # Missing, or the folder is unreadable; either way, fetch from the source.
        return None


def write(url: str, content: bytes) -> None:
    """Store a body. A cache that cannot be written only costs a warning."""
    path = _path(url)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        # Write to a temporary file and rename it, so a crash or a second
        # process never leaves a half-written file under the real name.
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as tmp:
            tmp.write(content)
        os.replace(tmp.name, path)
    except OSError as exc:
        warnings.warn(f"ausmacro could not write its cache in {path.parent}: {exc}", stacklevel=2)


def clear() -> int:
    """Delete every cached file and return how many were removed."""
    removed = 0
    for path in directory().glob(f"*{SUFFIX}"):
        path.unlink(missing_ok=True)
        removed += 1
    return removed


def _path(url: str) -> Path:
    return directory() / (hashlib.sha256(url.encode()).hexdigest() + SUFFIX)
