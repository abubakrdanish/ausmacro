"""Polite HTTP: timeouts, retries with backoff, Retry-After, and a gap between requests."""
from __future__ import annotations

import threading
import time
from importlib.metadata import version

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from ausmacro.errors import UpstreamError

USER_AGENT = f"ausmacro/{version('ausmacro')} (+https://pypi.org/project/ausmacro/)"
TIMEOUT = (10, 60)  # seconds to connect, seconds to read
MIN_GAP = 1.0  # seconds between requests; neither the ABS nor the RBA publishes a rate limit

_lock = threading.Lock()
_last_request = 0.0
_session: requests.Session | None = None


def session() -> requests.Session:
    """A shared session that retries connection errors, 429 and 5xx."""
    global _session
    if _session is None:
        # Waits about 1, 2, 4, 8 seconds between tries, or what Retry-After says.
        retry = Retry(
            total=4,
            backoff_factor=1,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET"}),
            respect_retry_after_header=True,
            raise_on_status=False,
        )
        s = requests.Session()
        s.headers["User-Agent"] = USER_AGENT
        s.mount("https://", HTTPAdapter(max_retries=retry))
        _session = s
    return _session


def get(url: str, accept: str) -> requests.Response:
    """GET a URL after waiting for the minimum gap. Status codes are left to the caller."""
    global _last_request
    with _lock:
        wait = _last_request + MIN_GAP - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        try:
            response = session().get(url, headers={"Accept": accept}, timeout=TIMEOUT)
        except requests.RequestException as exc:
            raise UpstreamError(
                f"Could not reach {url}: {exc}. Check your connection and try again later."
            ) from exc
        finally:
            _last_request = time.monotonic()
    return response
