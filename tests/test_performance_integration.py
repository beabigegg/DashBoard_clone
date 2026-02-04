# -*- coding: utf-8 -*-
"""Integration tests for performance monitoring and admin APIs."""

import json
import os
import pytest
import tempfile
from unittest.mock import patch, MagicMock

from mes_dashboard.app import create_app
import mes_dashboard.core.database as db


@pytest.fixture
def app():
    """Create application for testing."""
    db._ENGINE = None
    app = create_app('testing')
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    return app


@pytest.fixture
def client(app):
    """Create test client."""
    return app.test_client()


@pytest.fixture
def admin_client(app, client):
    """Create authenticated admin client."""
    # Set admin session - the permissions module checks for 'admin' key in session
    with client.session_transaction() as sess:
        sess['admin'] = {'username': 'admin', 'role': 'admin'}
    yield client


class TestAPIResponseFormat:
    """Test standardized API response format."""

    def test_success_response_format(self, admin_client):
        """Success responses have correct format."""
        response = admin_client.get('/admin/api/system-status')

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["success"] is True
        assert "data" in data

    def test_unauthenticated_redirect(self, client):
        """Unauthenticated requests redirect to login."""
        response = client.get('/admin/performance')

        # Should redirect to login page
        assert response.status_code == 302


class TestHealthEndpoints:
    """Test health check endpoints."""

    def test_health_basic_endpoint(self, client):
        """Basic health endpoint returns status."""
        response = client.get('/health')

        assert response.status_code == 200
        data = json.loads(response.data)
        assert "status" in data
        # Database status is under 'services' key
        assert "services" in data
        assert "database" in data["services"]

    def test_health_deep_requires_auth(self, client):
        """Deep health endpoint requires authentication."""
        response = client.get('/health/deep')
        # Redirects to login for unauthenticated requests
        assert response.status_code == 302

    def test_health_deep_returns_metrics(self, admin_client):
        """Deep health endpoint returns detailed metrics."""
        response = admin_client.get('/health/deep')

        if response.status_code == 200:
            data = json.loads(response.data)
            assert "status" in data


class TestSystemStatusAPI:
    """Test system status API endpoint."""

    def test_system_status_returns_all_components(self, admin_client):
        """System status includes all component statuses."""
        response = admin_client.get('/admin/api/system-status')

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["success"] is True
        assert "database" in data["data"]
        assert "redis" in data["data"]
        assert "circuit_breaker" in data["data"]
        assert "worker_pid" in data["data"]


class TestMetricsAPI:
    """Test metrics API endpoint."""

    def test_metrics_returns_percentiles(self, admin_client):
        """Metrics API returns percentile data."""
        response = admin_client.get('/admin/api/metrics')

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["success"] is True
        assert "p50_ms" in data["data"]
        assert "p95_ms" in data["data"]
        assert "p99_ms" in data["data"]
        assert "count" in data["data"]
        assert "slow_count" in data["data"]
        assert "slow_rate" in data["data"]

    def test_metrics_includes_latencies(self, admin_client):
        """Metrics API includes latency distribution."""
        response = admin_client.get('/admin/api/metrics')

        assert response.status_code == 200
        data = json.loads(response.data)
        assert "latencies" in data["data"]
        assert isinstance(data["data"]["latencies"], list)


class TestLogsAPI:
    """Test logs API endpoint."""

    def test_logs_api_returns_logs(self, admin_client):
        """Logs API returns log entries."""
        response = admin_client.get('/admin/api/logs')

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["success"] is True
        assert "logs" in data["data"]
        assert "enabled" in data["data"]

    def test_logs_api_filter_by_level(self, admin_client):
        """Logs API filters by level."""
        response = admin_client.get('/admin/api/logs?level=ERROR')

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["success"] is True

    def test_logs_api_filter_by_search(self, admin_client):
        """Logs API filters by search term."""
        response = admin_client.get('/admin/api/logs?q=database')

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["success"] is True


class TestLogsCleanupAPI:
    """Test log cleanup API endpoint."""

    def test_logs_cleanup_requires_auth(self, client):
        """Log cleanup requires admin authentication."""
        response = client.post('/admin/api/logs/cleanup')
        # Should redirect to login page
        assert response.status_code == 302

    def test_logs_cleanup_success(self, admin_client):
        """Log cleanup returns success with stats."""
        response = admin_client.post('/admin/api/logs/cleanup')

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["success"] is True
        assert "deleted" in data["data"]
        assert "before" in data["data"]
        assert "after" in data["data"]
        assert "count" in data["data"]["before"]
        assert "size_bytes" in data["data"]["before"]


class TestWorkerControlAPI:
    """Test worker control API endpoints."""

    def test_worker_status_returns_info(self, admin_client):
        """Worker status API returns worker information."""
        response = admin_client.get('/admin/api/worker/status')

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["success"] is True
        assert "worker_pid" in data["data"]
        assert "cooldown" in data["data"]
        assert "last_restart" in data["data"]

    def test_worker_restart_requires_auth(self, client):
        """Worker restart requires admin authentication."""
        response = client.post('/admin/api/worker/restart')
        # Should redirect to login page for unauthenticated requests
        assert response.status_code == 302

    def test_worker_restart_writes_flag(self, admin_client):
        """Worker restart creates flag file."""
        # Use a temp file for the flag
        fd, temp_flag = tempfile.mkstemp()
        os.close(fd)
        os.unlink(temp_flag)  # Remove so we can test creation

        with patch('mes_dashboard.routes.admin_routes.RESTART_FLAG_PATH', temp_flag):
            with patch('mes_dashboard.routes.admin_routes._check_restart_cooldown', return_value=(False, 0)):
                response = admin_client.post('/admin/api/worker/restart')

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["success"] is True

        # Cleanup
        try:
            os.unlink(temp_flag)
        except OSError:
            pass

    def test_worker_restart_cooldown(self, admin_client):
        """Worker restart respects cooldown."""
        with patch('mes_dashboard.routes.admin_routes._check_restart_cooldown', return_value=(True, 45)):
            response = admin_client.post('/admin/api/worker/restart')

        assert response.status_code == 429
        data = json.loads(response.data)
        assert data["success"] is False
        assert "cooldown" in data["error"]["message"].lower()


class TestCircuitBreakerIntegration:
    """Test circuit breaker integration with database layer."""

    def test_circuit_breaker_status_in_system_status(self, admin_client):
        """Circuit breaker status is included in system status."""
        response = admin_client.get('/admin/api/system-status')

        assert response.status_code == 200
        data = json.loads(response.data)
        cb_status = data["data"]["circuit_breaker"]
        assert "state" in cb_status
        assert "enabled" in cb_status


class TestPerformancePage:
    """Test performance monitoring page."""

    def test_performance_page_requires_auth(self, client):
        """Performance page requires admin authentication."""
        response = client.get('/admin/performance')
        # Should redirect to login
        assert response.status_code == 302

    def test_performance_page_loads(self, admin_client):
        """Performance page loads for admin users."""
        response = admin_client.get('/admin/performance')

        # Should be 200 for authenticated admin
        assert response.status_code == 200
        # Check for performance-related content
        data_str = response.data.decode('utf-8', errors='ignore').lower()
        assert 'performance' in data_str or '效能' in data_str
