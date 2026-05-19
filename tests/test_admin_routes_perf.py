# -*- coding: utf-8 -*-
"""Tests for /admin/api/performance-detail new additive keys (AC-5, AC-6, AC-7)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from mes_dashboard.app import create_app


@pytest.fixture
def app():
    app = create_app("testing")
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def auth_patches():
    with patch("mes_dashboard.app.is_admin_logged_in", return_value=True), \
         patch("mes_dashboard.app.is_user_logged_in", return_value=True), \
         patch("mes_dashboard.core.permissions.is_admin_logged_in", return_value=True), \
         patch("mes_dashboard.core.permissions.is_user_logged_in", return_value=True):
        yield


def _mock_redis_client(extra_info: dict = None, slowlog_entries: list = None):
    """Return a mock Redis client for performance-detail tests."""
    client = MagicMock()

    base_memory = {
        "used_memory_human": "1.00M",
        "used_memory": 1048576,
        "used_memory_peak_human": "2.00M",
        "used_memory_peak": 2097152,
        "maxmemory_human": "0B",
        "maxmemory": 0,
        "mem_fragmentation_ratio": 1.23,
    }
    if extra_info:
        base_memory.update(extra_info)

    base_stats = {
        "keyspace_hits": 100,
        "keyspace_misses": 10,
        "evicted_keys": 5,
        "expired_keys": 20,
    }

    base_clients = {"connected_clients": 3}

    def info_side_effect(section=None):
        if section == "memory":
            return base_memory
        if section == "stats":
            return base_stats
        if section == "clients":
            return base_clients
        return {}

    client.info.side_effect = info_side_effect
    client.scan.return_value = (0, [])
    client.slowlog_get.return_value = slowlog_entries if slowlog_entries is not None else []
    return client


def _get_perf_data(client, auth_patches):
    """Call /admin/api/performance-detail and return the data dict."""
    resp = client.get("/admin/api/performance-detail")
    assert resp.status_code == 200, (
        f"Expected 200, got {resp.status_code}: {resp.get_data(as_text=True)[:200]}"
    )
    payload = resp.get_json()
    assert payload["success"] is True
    return payload["data"]


# Patch applied to all Redis-enabled perf tests to prevent rq_monitor_service
# from calling real Redis (which would return MagicMock values in nested dicts).
_RQ_MONITOR_PATCH = patch(
    "mes_dashboard.services.rq_monitor_service.get_rq_monitor_summary",
    return_value={
        "rq_available": False,
        "workers": {"workers": [], "summary": {"total": 0, "busy": 0, "idle": 0}},
        "queues": {"queues": [], "total_queued": 0, "total_started": 0, "total_failed": 0},
        "slots": {"active": 0, "available": 2},
    },
)


# ── AC-5: Redis additive keys ─────────────────────────────────────────────────

def _redis_patches(mock_client):
    """Return a context manager stacking all Redis-related patches.

    Patches REDIS_ENABLED=True, the global cached client, get_redis_client,
    and _collect_redis_namespace_memory so no real Redis I/O happens.
    """
    return [
        patch("mes_dashboard.core.redis_client.REDIS_ENABLED", True),
        patch("mes_dashboard.core.redis_client._REDIS_CLIENT", mock_client),
        patch(
            "mes_dashboard.core.redis_client.get_redis_client",
            return_value=mock_client,
        ),
        patch(
            "mes_dashboard.routes.admin_routes._collect_redis_namespace_memory",
            return_value=[],
        ),
    ]


_RQ_MONITOR_STUB = {
    "rq_available": False,
    "workers": {"workers": [], "summary": {"total": 0, "busy": 0, "idle": 0}},
    "queues": {"queues": [], "total_queued": 0, "total_started": 0, "total_failed": 0},
    "slots": {"active": 0, "available": 2},
}


class TestPerfDetailRedisAdditiveKeys:
    """AC-5: Redis section must include additive keys from the fixed endpoint."""

    def _redis_ctx(self, mock_client):
        """Shared context stacking all patches needed to isolate Redis tests."""
        import contextlib
        return contextlib.ExitStack()

    def test_perf_detail_redis_evicted_keys_present(self, client, auth_patches):
        """Redis section must include evicted_keys when Redis is available (AC-5)."""
        mock_client = _mock_redis_client()

        with patch("mes_dashboard.core.redis_client.REDIS_ENABLED", True), \
             patch("mes_dashboard.core.redis_client._REDIS_CLIENT", mock_client), \
             patch("mes_dashboard.core.redis_client.get_redis_client", return_value=mock_client), \
             patch("mes_dashboard.routes.admin_routes._collect_redis_namespace_memory", return_value=[]), \
             patch("mes_dashboard.services.rq_monitor_service.get_rq_monitor_summary", return_value=_RQ_MONITOR_STUB):
            data = _get_perf_data(client, auth_patches)

        assert "redis" in data
        redis = data["redis"]
        assert redis is not None
        assert "evicted_keys" in redis
        assert redis["evicted_keys"] == 5

    def test_perf_detail_redis_expired_keys_present(self, client, auth_patches):
        """Redis section must include expired_keys when Redis is available (AC-5)."""
        mock_client = _mock_redis_client()

        with patch("mes_dashboard.core.redis_client.REDIS_ENABLED", True), \
             patch("mes_dashboard.core.redis_client._REDIS_CLIENT", mock_client), \
             patch("mes_dashboard.core.redis_client.get_redis_client", return_value=mock_client), \
             patch("mes_dashboard.routes.admin_routes._collect_redis_namespace_memory", return_value=[]), \
             patch("mes_dashboard.services.rq_monitor_service.get_rq_monitor_summary", return_value=_RQ_MONITOR_STUB):
            data = _get_perf_data(client, auth_patches)

        assert data["redis"]["expired_keys"] == 20

    def test_perf_detail_redis_fragmentation_present(self, client, auth_patches):
        """Redis section must include mem_fragmentation_ratio (AC-5)."""
        mock_client = _mock_redis_client()

        with patch("mes_dashboard.core.redis_client.REDIS_ENABLED", True), \
             patch("mes_dashboard.core.redis_client._REDIS_CLIENT", mock_client), \
             patch("mes_dashboard.core.redis_client.get_redis_client", return_value=mock_client), \
             patch("mes_dashboard.routes.admin_routes._collect_redis_namespace_memory", return_value=[]), \
             patch("mes_dashboard.services.rq_monitor_service.get_rq_monitor_summary", return_value=_RQ_MONITOR_STUB):
            data = _get_perf_data(client, auth_patches)

        assert "mem_fragmentation_ratio" in data["redis"]
        assert data["redis"]["mem_fragmentation_ratio"] == 1.23

    def test_perf_detail_redis_slowlog_top5(self, client, auth_patches):
        """Redis section must include slowlog list normalized to {id, duration_us, command} (AC-5)."""
        slowlog = [
            {"id": 1, "duration": 500, "command": [b"SET", b"key1", b"val1"]},
            {"id": 2, "duration": 300, "command": [b"GET", b"key2"]},
        ]
        mock_client = _mock_redis_client(slowlog_entries=slowlog)

        with patch("mes_dashboard.core.redis_client.REDIS_ENABLED", True), \
             patch("mes_dashboard.core.redis_client._REDIS_CLIENT", mock_client), \
             patch("mes_dashboard.core.redis_client.get_redis_client", return_value=mock_client), \
             patch("mes_dashboard.routes.admin_routes._collect_redis_namespace_memory", return_value=[]), \
             patch("mes_dashboard.services.rq_monitor_service.get_rq_monitor_summary", return_value=_RQ_MONITOR_STUB):
            data = _get_perf_data(client, auth_patches)

        assert "slowlog" in data["redis"]
        sl = data["redis"]["slowlog"]
        assert isinstance(sl, list)
        assert len(sl) == 2
        assert sl[0]["id"] == 1
        assert sl[0]["duration_us"] == 500
        assert "SET" in sl[0]["command"]

    def test_perf_detail_redis_null_when_unavailable(self, client, auth_patches):
        """Redis section is None when Redis is disabled/unavailable (AC-5)."""
        with patch(
            "mes_dashboard.core.redis_client.REDIS_ENABLED", False
        ), patch(
            "mes_dashboard.services.rq_monitor_service.get_rq_monitor_summary",
            return_value=_RQ_MONITOR_STUB,
        ):
            data = _get_perf_data(client, auth_patches)

        assert data["redis"] is None


# ── AC-6: DuckDB telemetry ────────────────────────────────────────────────────

class TestPerfDetailDuckdb:

    def test_perf_detail_duckdb_temp_dir_bytes(self, client, auth_patches):
        """duckdb section must include temp_dir_bytes (AC-6)."""
        mock_telemetry = {
            "temp_dir_bytes": 4096,
            "memory_limit_state": {
                "memory_limit": "512MB",
                "threads": 2,
                "temp_dir": "/tmp/duckdb",
                "connection_ok": True,
            },
        }

        with patch(
            "mes_dashboard.core.redis_client.REDIS_ENABLED", False
        ), patch(
            "mes_dashboard.core.duckdb_runtime.get_duckdb_telemetry",
            return_value=mock_telemetry,
        ), patch(
            "mes_dashboard.services.rq_monitor_service.get_rq_monitor_summary",
            return_value=_RQ_MONITOR_STUB,
        ):
            data = _get_perf_data(client, auth_patches)

        assert "duckdb" in data
        assert data["duckdb"]["temp_dir_bytes"] == 4096

    def test_perf_detail_duckdb_memory_limit_state(self, client, auth_patches):
        """duckdb section must include memory_limit_state object (AC-6)."""
        mock_telemetry = {
            "temp_dir_bytes": None,
            "memory_limit_state": {
                "memory_limit": "256MB",
                "threads": 1,
                "temp_dir": None,
                "connection_ok": True,
            },
        }

        with patch(
            "mes_dashboard.core.redis_client.REDIS_ENABLED", False
        ), patch(
            "mes_dashboard.core.duckdb_runtime.get_duckdb_telemetry",
            return_value=mock_telemetry,
        ), patch(
            "mes_dashboard.services.rq_monitor_service.get_rq_monitor_summary",
            return_value=_RQ_MONITOR_STUB,
        ):
            data = _get_perf_data(client, auth_patches)

        mls = data["duckdb"]["memory_limit_state"]
        assert mls["memory_limit"] == "256MB"
        assert mls["connection_ok"] is True

    def test_perf_detail_duckdb_null_when_unavailable(self, client, auth_patches):
        """duckdb section contains error key (not a 500) when get_duckdb_telemetry raises (AC-6)."""
        with patch(
            "mes_dashboard.core.redis_client.REDIS_ENABLED", False
        ), patch(
            "mes_dashboard.core.duckdb_runtime.get_duckdb_telemetry",
            side_effect=RuntimeError("duckdb unavailable"),
        ), patch(
            "mes_dashboard.services.rq_monitor_service.get_rq_monitor_summary",
            return_value=_RQ_MONITOR_STUB,
        ):
            data = _get_perf_data(client, auth_patches)

        assert "duckdb" in data
        assert "error" in data["duckdb"]


# ── AC-7: resilience — no 500 when all externals off ─────────────────────────

class TestPerfDetailNoExternals:

    def test_perf_detail_no_500_all_externals_off(self, client, auth_patches):
        """Performance-detail returns 200 when MySQL, Redis, and DuckDB all unavailable (AC-7)."""
        with patch(
            "mes_dashboard.core.redis_client.REDIS_ENABLED", False
        ), patch(
            "mes_dashboard.core.duckdb_runtime.get_duckdb_telemetry",
            side_effect=Exception("unavailable"),
        ), patch(
            "mes_dashboard.services.rq_monitor_service.get_rq_monitor_summary",
            return_value=_RQ_MONITOR_STUB,
        ):
            resp = client.get("/admin/api/performance-detail")

        assert resp.status_code == 200
        payload = resp.get_json()
        assert payload["success"] is True
        data = payload["data"]
        assert data["redis"] is None
        assert "duckdb" in data
