from __future__ import annotations

import pytest
import requests

import ausmacro
from ausmacro import _http
from ausmacro.errors import UpstreamError


@pytest.fixture
def fresh_http(monkeypatch):
    monkeypatch.setattr(_http, "_session", None)
    monkeypatch.setattr(_http, "_last_request", 0.0)


def test_user_agent_names_the_library(fresh_http):
    assert _http.session().headers["User-Agent"] == (
        f"ausmacro/{ausmacro.__version__} (+https://pypi.org/project/ausmacro/)"
    )


def test_retries_rate_limits_and_server_errors(fresh_http):
    retry = _http.session().get_adapter("https://data.api.abs.gov.au").max_retries
    assert set(retry.status_forcelist) == {429, 500, 502, 503, 504}
    assert retry.respect_retry_after_header
    assert retry.backoff_factor == 1
    assert retry.total == 4


def test_waits_for_the_minimum_gap(fresh_http, monkeypatch):
    clock = iter([100.0, 100.2, 100.2])  # wait check, then the two "after request" stamps
    sleeps = []
    monkeypatch.setattr(_http, "MIN_GAP", 1.0)
    monkeypatch.setattr(_http, "_last_request", 99.6)
    monkeypatch.setattr(_http.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(_http.time, "sleep", sleeps.append)
    monkeypatch.setattr(requests.Session, "get", lambda self, url, **kw: requests.Response())

    _http.get("https://example.invalid/", "text/csv")
    assert sleeps == [pytest.approx(0.6)]


def test_sends_a_timeout(fresh_http, monkeypatch):
    seen = {}

    def fake_get(self, url, **kwargs):
        seen.update(kwargs)
        return requests.Response()

    monkeypatch.setattr(requests.Session, "get", fake_get)
    _http.get("https://example.invalid/", "text/csv")
    assert seen["timeout"] == (10, 60)
    assert seen["headers"] == {"Accept": "text/csv"}


def test_network_failure_becomes_upstream_error(fresh_http, monkeypatch):
    def fail(self, url, **kwargs):
        raise requests.ConnectionError("SYNTHETIC connection refused")

    monkeypatch.setattr(requests.Session, "get", fail)
    with pytest.raises(UpstreamError, match="Check your connection"):
        _http.get("https://example.invalid/", "text/csv")
