# -*- coding: utf-8 -*-
"""Unit tests for Redis client module.

Tests Redis connection management with mocked Redis.
"""

import pytest
from unittest.mock import patch, MagicMock
import importlib


class TestRedisClient:
    """Test Redis client connection management."""

    @pytest.fixture(autouse=True)
    def reset_module(self):
        """Reset module state before each test."""
        import mes_dashboard.core.redis_client as rc
        rc._REDIS_CLIENT = None
        yield
        rc._REDIS_CLIENT = None

    def test_get_redis_client_success(self, reset_module):
        """Test successful Redis client creation."""
        import mes_dashboard.core.redis_client as rc

        with patch.object(rc, 'REDIS_ENABLED', True):
            with patch.object(rc.redis.Redis, 'from_url') as mock_from_url:
                mock_client = MagicMock()
                mock_client.ping.return_value = True
                mock_from_url.return_value = mock_client

                client = rc.get_redis_client()

                assert client is mock_client
                mock_from_url.assert_called_once()

    def test_get_redis_client_disabled(self, reset_module):
        """Test Redis client returns None when disabled."""
        import mes_dashboard.core.redis_client as rc

        with patch.object(rc, 'REDIS_ENABLED', False):
            client = rc.get_redis_client()
            assert client is None

    def test_get_redis_client_connection_error(self, reset_module):
        """Test Redis client handles connection errors gracefully."""
        import mes_dashboard.core.redis_client as rc
        import redis as redis_lib

        with patch.object(rc, 'REDIS_ENABLED', True):
            with patch.object(rc.redis.Redis, 'from_url') as mock_from_url:
                mock_from_url.side_effect = redis_lib.RedisError("Connection refused")

                client = rc.get_redis_client()

                assert client is None

    def test_redis_available_true(self, reset_module):
        """Test redis_available returns True when Redis is connected."""
        import mes_dashboard.core.redis_client as rc

        with patch.object(rc, 'REDIS_ENABLED', True):
            with patch.object(rc.redis.Redis, 'from_url') as mock_from_url:
                mock_client = MagicMock()
                mock_client.ping.return_value = True
                mock_from_url.return_value = mock_client

                assert rc.redis_available() is True

    def test_redis_available_disabled(self, reset_module):
        """Test redis_available returns False when disabled."""
        import mes_dashboard.core.redis_client as rc

        with patch.object(rc, 'REDIS_ENABLED', False):
            assert rc.redis_available() is False

    def test_get_key_with_prefix(self):
        """Test get_key adds prefix correctly."""
        import mes_dashboard.core.redis_client as rc

        with patch.object(rc, 'REDIS_KEY_PREFIX', 'test_prefix'):
            key = rc.get_key('mykey')
            assert key == 'test_prefix:mykey'

    def test_get_key_without_prefix(self):
        """Test get_key works with empty prefix."""
        import mes_dashboard.core.redis_client as rc

        with patch.object(rc, 'REDIS_KEY_PREFIX', ''):
            key = rc.get_key('mykey')
            assert key == ':mykey'

    def test_redact_connection_url_masks_password(self):
        import mes_dashboard.core.redis_client as rc

        redacted = rc.redact_connection_url("redis://user:secret@localhost:6379/0")
        assert redacted == "redis://user:***@localhost:6379/0"

    def test_redact_connection_url_without_credentials(self):
        import mes_dashboard.core.redis_client as rc

        redacted = rc.redact_connection_url("redis://localhost:6379/0")
        assert redacted == "redis://localhost:6379/0"

    def test_get_redis_client_logs_redacted_url(self, reset_module):
        import mes_dashboard.core.redis_client as rc

        with patch.object(rc, 'REDIS_ENABLED', True):
            with patch.object(rc, 'REDIS_URL', 'redis://user:secret@localhost:6379/0'):
                with patch.object(rc.redis.Redis, 'from_url') as mock_from_url:
                    with patch.object(rc.logger, 'info') as mock_info:
                        mock_client = MagicMock()
                        mock_client.ping.return_value = True
                        mock_from_url.return_value = mock_client

                        rc.get_redis_client()

                        logged_url = mock_info.call_args.args[1]
                        assert logged_url == 'redis://user:***@localhost:6379/0'


class TestRedisClientSingleton:
    """Test Redis client singleton behavior."""

    @pytest.fixture(autouse=True)
    def reset_module(self):
        """Reset module state before each test."""
        import mes_dashboard.core.redis_client as rc
        rc._REDIS_CLIENT = None
        yield
        rc._REDIS_CLIENT = None

    def test_client_is_singleton(self, reset_module):
        """Test that get_redis_client returns same instance."""
        import mes_dashboard.core.redis_client as rc

        with patch.object(rc, 'REDIS_ENABLED', True):
            with patch.object(rc.redis.Redis, 'from_url') as mock_from_url:
                mock_client = MagicMock()
                mock_client.ping.return_value = True
                mock_from_url.return_value = mock_client

                client1 = rc.get_redis_client()
                client2 = rc.get_redis_client()

                assert client1 is client2
                # from_url should only be called once
                assert mock_from_url.call_count == 1


class TestCloseRedis:
    """Test Redis client cleanup."""

    @pytest.fixture(autouse=True)
    def reset_module(self):
        """Reset module state before each test."""
        import mes_dashboard.core.redis_client as rc
        rc._REDIS_CLIENT = None
        yield
        rc._REDIS_CLIENT = None

    def test_close_redis(self, reset_module):
        """Test close_redis properly closes connection."""
        import mes_dashboard.core.redis_client as rc

        with patch.object(rc, 'REDIS_ENABLED', True):
            with patch.object(rc.redis.Redis, 'from_url') as mock_from_url:
                mock_client = MagicMock()
                mock_client.ping.return_value = True
                mock_from_url.return_value = mock_client

                # Get client first
                client = rc.get_redis_client()
                assert client is not None

                # Close it
                rc.close_redis()

                # Verify close was called
                mock_client.close.assert_called_once()
                assert rc._REDIS_CLIENT is None

    def test_close_redis_when_none(self, reset_module):
        """Test close_redis does nothing when no client."""
        import mes_dashboard.core.redis_client as rc

        # Should not raise any errors
        rc.close_redis()
        assert rc._REDIS_CLIENT is None
