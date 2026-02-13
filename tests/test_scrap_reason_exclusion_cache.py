# -*- coding: utf-8 -*-
"""Tests for scrap_reason_exclusion_cache service."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pandas as pd

from mes_dashboard.services import scrap_reason_exclusion_cache as cache


def _reset_cache_state():
    with cache._CACHE_LOCK:
        cache._CACHE["reasons"] = set()
        cache._CACHE["updated_at"] = None
        cache._CACHE["loaded"] = False
        cache._CACHE["source"] = None


def test_refresh_cache_loads_enabled_reason_codes(monkeypatch):
    _reset_cache_state()

    monkeypatch.setattr(cache, "try_acquire_lock", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(cache, "release_lock", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cache, "get_redis_client", lambda: None)
    monkeypatch.setattr(
        cache,
        "read_sql_df",
        lambda _sql: pd.DataFrame({"REASON_NAME": ["358", " 160 ", "bonus_adjust"]}),
    )

    assert cache.refresh_cache(force=True) is True
    assert cache.get_excluded_reasons() == {"358", "160", "BONUS_ADJUST"}


def test_refresh_cache_falls_back_to_redis_when_oracle_fails(monkeypatch):
    _reset_cache_state()

    redis_client = MagicMock()
    redis_client.get.side_effect = [json.dumps(["A01", "b02"]), "2026-02-13T00:00:00"]

    monkeypatch.setattr(cache, "try_acquire_lock", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(cache, "release_lock", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cache, "get_redis_client", lambda: redis_client)

    def _raise(_sql):
        raise RuntimeError("oracle unavailable")

    monkeypatch.setattr(cache, "read_sql_df", _raise)

    assert cache.refresh_cache(force=True) is True
    assert cache.get_excluded_reasons() == {"A01", "B02"}


def test_get_excluded_reasons_uses_redis_for_lazy_bootstrap(monkeypatch):
    _reset_cache_state()

    redis_client = MagicMock()
    redis_client.get.side_effect = [json.dumps(["X1", "x2"]), "2026-02-13T12:00:00"]
    monkeypatch.setattr(cache, "get_redis_client", lambda: redis_client)
    monkeypatch.setattr(cache, "refresh_cache", lambda force=False: True)

    reasons = cache.get_excluded_reasons(force_refresh=False)

    assert reasons == {"X1", "X2"}
