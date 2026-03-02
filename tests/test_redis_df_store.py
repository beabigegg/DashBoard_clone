# -*- coding: utf-8 -*-
"""Unit tests for redis_df_store module."""

import pytest
from unittest.mock import patch, MagicMock
from decimal import Decimal

import pandas as pd


class TestRedisStoreDf:
    """3.1 — round-trip store/load."""

    def test_round_trip(self):
        """Store a DF, load it back, verify equality."""
        import mes_dashboard.core.redis_df_store as rds

        mock_client = MagicMock()
        stored = {}

        def fake_setex(key, ttl, value):
            stored[key] = value

        def fake_get(key):
            return stored.get(key)

        mock_client.setex.side_effect = fake_setex
        mock_client.get.side_effect = fake_get

        df = pd.DataFrame({"A": [1, 2, 3], "B": ["x", "y", "z"]})

        with patch.object(rds, "REDIS_ENABLED", True), \
             patch.object(rds, "get_redis_client", return_value=mock_client):
            rds.redis_store_df("test:key", df, ttl=60)
            loaded = rds.redis_load_df("test:key")

        assert loaded is not None
        pd.testing.assert_frame_equal(loaded, df)

    def test_store_empty_df(self):
        """Round-trip with an empty DataFrame preserves schema."""
        import mes_dashboard.core.redis_df_store as rds

        mock_client = MagicMock()
        stored = {}
        mock_client.setex.side_effect = lambda k, t, v: stored.update({k: v})
        mock_client.get.side_effect = lambda k: stored.get(k)

        df = pd.DataFrame({"COL": pd.Series([], dtype="int64")})

        with patch.object(rds, "REDIS_ENABLED", True), \
             patch.object(rds, "get_redis_client", return_value=mock_client):
            rds.redis_store_df("test:empty", df, ttl=60)
            loaded = rds.redis_load_df("test:empty")

        assert loaded is not None
        assert len(loaded) == 0
        assert list(loaded.columns) == ["COL"]

    def test_decimal_object_column_round_trip(self):
        """Mixed-precision Decimal object columns should store without serialization errors."""
        import mes_dashboard.core.redis_df_store as rds

        mock_client = MagicMock()
        stored = {}
        mock_client.setex.side_effect = lambda k, t, v: stored.update({k: v})
        mock_client.get.side_effect = lambda k: stored.get(k)

        df = pd.DataFrame(
            {
                "REJECT_SHARE_PCT": [Decimal("12.345"), Decimal("1.2"), None],
                "REJECT_RATE_PCT": [Decimal("0.123456"), Decimal("10.9"), Decimal("9.000001")],
                "LABEL": ["A", "B", "C"],
            }
        )

        with patch.object(rds, "REDIS_ENABLED", True), \
             patch.object(rds, "get_redis_client", return_value=mock_client):
            assert rds.redis_store_df("test:decimal", df, ttl=60)
            loaded = rds.redis_load_df("test:decimal")

        assert loaded is not None
        assert loaded["REJECT_SHARE_PCT"].dtype.kind in ("f", "i")
        assert loaded["REJECT_RATE_PCT"].dtype.kind in ("f", "i")
        assert loaded.loc[0, "REJECT_SHARE_PCT"] == pytest.approx(12.345)
        assert loaded.loc[2, "REJECT_RATE_PCT"] == pytest.approx(9.000001)


class TestChunkHelpers:
    """3.2 — chunk-level helpers round-trip."""

    def test_chunk_round_trip(self):
        import mes_dashboard.core.redis_df_store as rds

        mock_client = MagicMock()
        stored = {}
        mock_client.setex.side_effect = lambda k, t, v: stored.update({k: v})
        mock_client.get.side_effect = lambda k: stored.get(k)
        mock_client.exists.side_effect = lambda k: 1 if k in stored else 0

        df = pd.DataFrame({"X": [10, 20]})

        with patch.object(rds, "REDIS_ENABLED", True), \
             patch.object(rds, "get_redis_client", return_value=mock_client):
            rds.redis_store_chunk("reject", "abc123", 0, df, ttl=60)
            assert rds.redis_chunk_exists("reject", "abc123", 0)
            loaded = rds.redis_load_chunk("reject", "abc123", 0)

        assert loaded is not None
        pd.testing.assert_frame_equal(loaded, df)

    def test_chunk_not_exists(self):
        import mes_dashboard.core.redis_df_store as rds

        mock_client = MagicMock()
        mock_client.exists.return_value = 0

        with patch.object(rds, "REDIS_ENABLED", True), \
             patch.object(rds, "get_redis_client", return_value=mock_client):
            assert not rds.redis_chunk_exists("reject", "abc123", 99)

    def test_clear_batch_removes_chunk_and_meta_keys(self):
        import mes_dashboard.core.redis_df_store as rds

        mock_client = MagicMock()
        deleted = {"keys": []}

        mock_client.keys.return_value = [
            "mes-dashboard:batch:reject:q123:chunk:0",
            "mes-dashboard:batch:reject:q123:chunk:1",
        ]
        mock_client.delete.side_effect = lambda *keys: deleted["keys"].extend(keys) or len(keys)

        with patch.object(rds, "REDIS_ENABLED", True), \
             patch.object(rds, "get_redis_client", return_value=mock_client):
            count = rds.redis_clear_batch("reject", "q123")

        assert count == 3
        assert any("chunk:0" in key for key in deleted["keys"])
        assert any("chunk:1" in key for key in deleted["keys"])
        assert any("meta" in key for key in deleted["keys"])


class TestRedisUnavailable:
    """3.3 — graceful fallback when Redis is unavailable."""

    def test_store_no_redis(self):
        """store returns without error when Redis disabled."""
        import mes_dashboard.core.redis_df_store as rds

        df = pd.DataFrame({"A": [1]})
        with patch.object(rds, "REDIS_ENABLED", False):
            rds.redis_store_df("key", df)  # no exception

    def test_load_no_redis(self):
        """load returns None when Redis disabled."""
        import mes_dashboard.core.redis_df_store as rds

        with patch.object(rds, "REDIS_ENABLED", False):
            result = rds.redis_load_df("key")
        assert result is None

    def test_chunk_exists_no_redis(self):
        import mes_dashboard.core.redis_df_store as rds

        with patch.object(rds, "REDIS_ENABLED", False):
            assert not rds.redis_chunk_exists("p", "h", 0)

    def test_store_client_none(self):
        """store returns without error when client is None."""
        import mes_dashboard.core.redis_df_store as rds

        df = pd.DataFrame({"A": [1]})
        with patch.object(rds, "REDIS_ENABLED", True), \
             patch.object(rds, "get_redis_client", return_value=None):
            rds.redis_store_df("key", df)  # no exception

    def test_load_client_none(self):
        """load returns None when client is None."""
        import mes_dashboard.core.redis_df_store as rds

        with patch.object(rds, "REDIS_ENABLED", True), \
             patch.object(rds, "get_redis_client", return_value=None):
            result = rds.redis_load_df("key")
        assert result is None
