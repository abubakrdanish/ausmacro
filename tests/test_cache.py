from __future__ import annotations

import os
import time

import platformdirs
import pytest

import ausmacro
from ausmacro import _cache


def test_second_call_is_served_from_the_cache(fake_http, cache_dir):
    fake_http.reply(fixture="SYNTHETIC_abs_cpi_quarterly.csv")
    first = ausmacro.get("cpi")
    # No second reply is queued, so a second request would fail.
    second = ausmacro.get("cpi", start="2021")
    assert len(fake_http.urls) == 1
    assert len(list(cache_dir.iterdir())) == 1
    assert set(second["date"]) <= set(first["date"])


def test_cache_false_neither_reads_nor_writes(fake_http, cache_dir):
    fake_http.reply(fixture="SYNTHETIC_rba_f1.1.csv")
    fake_http.reply(fixture="SYNTHETIC_rba_f1.1.csv")
    ausmacro.get("cash_rate", cache=False)
    ausmacro.get_rba("F1.1", cache=False)
    assert len(fake_http.urls) == 2
    assert not cache_dir.exists()


def test_entries_expire_after_a_day(fake_http):
    fake_http.reply(fixture="SYNTHETIC_abs_cpi_quarterly.csv")
    fake_http.reply(fixture="SYNTHETIC_abs_cpi_quarterly.csv")
    ausmacro.get_abs("ABS,CPI,2.0.0", "1.10001.10.50.Q")
    path = next(_cache.directory().iterdir())
    old = time.time() - _cache.MAX_AGE - 60
    os.utime(path, (old, old))
    ausmacro.get_abs("ABS,CPI,2.0.0", "1.10001.10.50.Q")
    assert len(fake_http.urls) == 2


def test_errors_are_not_cached(fake_http):
    fake_http.reply(503, body=b"SYNTHETIC outage")
    fake_http.reply(fixture="SYNTHETIC_rba_f1.csv")
    with pytest.raises(ausmacro.UpstreamError):
        ausmacro.get_rba("F1")
    ausmacro.get_rba("F1")
    assert len(fake_http.urls) == 2


def test_clear_cache_removes_only_its_files(fake_http, cache_dir):
    fake_http.reply(fixture="SYNTHETIC_rba_f1.csv")
    ausmacro.get_rba("F1")
    (cache_dir / "notes.txt").write_text("not ours")
    assert ausmacro.clear_cache() == 1
    assert [p.name for p in cache_dir.iterdir()] == ["notes.txt"]


def test_unwritable_cache_warns_and_still_returns_data(fake_http, cache_dir):
    cache_dir.write_text("SYNTHETIC: a file where the cache folder should be")
    fake_http.reply(fixture="SYNTHETIC_rba_f1.csv")
    with pytest.warns(UserWarning, match="could not write its cache"):
        df = ausmacro.get_rba("F1")
    assert not df.empty


def test_default_folder_is_the_user_cache(monkeypatch):
    monkeypatch.delenv("AUSMACRO_CACHE_DIR")
    assert _cache.directory() == platformdirs.user_cache_path("ausmacro")


def test_rba_tables_are_cached_too(fake_http):
    fake_http.reply(fixture="SYNTHETIC_rba_f1.csv")
    ausmacro.get_rba("F1")
    ausmacro.get("cash_rate", freq="D")
    assert len(fake_http.urls) == 1
