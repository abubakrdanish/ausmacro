from __future__ import annotations

import socket
from pathlib import Path

import pytest
import requests

from ausmacro import _http

FIXTURES = Path(__file__).parent / "fixtures"


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption("--live", action="store_true", help="run the test that calls the real ABS and RBA")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if config.getoption("--live"):
        return
    skip = pytest.mark.skip(reason="calls the real ABS and RBA; run with --live")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(autouse=True)
def cache_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Give every test its own empty cache, never the user's real one."""
    path = tmp_path / "cache"
    monkeypatch.setenv("AUSMACRO_CACHE_DIR", str(path))
    return path


@pytest.fixture(autouse=True)
def block_network(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail any test that tries to open a socket, unless it is marked live."""
    if "live" in request.keywords:
        return

    def refuse(*args: object, **kwargs: object) -> None:
        raise RuntimeError("Network access is blocked in tests. Use the fake_http fixture.")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)
    monkeypatch.setattr(_http, "MIN_GAP", 0.0)


class FakeHTTP:
    """Stands in for _http.get: serves queued responses in order and records requested URLs."""

    def __init__(self) -> None:
        self.responses: list[tuple[int, bytes]] = []
        self.urls: list[str] = []
        self.accepts: list[str] = []

    def reply(self, status: int = 200, fixture: str | None = None, body: bytes = b"") -> None:
        content = (FIXTURES / fixture).read_bytes() if fixture else body
        self.responses.append((status, content))

    def __call__(self, url: str, accept: str) -> requests.Response:
        self.urls.append(url)
        self.accepts.append(accept)
        status, content = self.responses.pop(0)
        response = requests.Response()
        response.status_code = status
        response._content = content
        response.encoding = "utf-8"
        response.url = url
        return response


@pytest.fixture
def fake_http(monkeypatch: pytest.MonkeyPatch) -> FakeHTTP:
    fake = FakeHTTP()
    monkeypatch.setattr(_http, "get", fake)
    return fake


@pytest.fixture
def fixture_bytes() -> object:
    return lambda name: (FIXTURES / name).read_bytes()
