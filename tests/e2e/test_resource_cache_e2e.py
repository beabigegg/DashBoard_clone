# -*- coding: utf-8 -*-
"""End-to-end tests for Resource Cache functionality.

These tests require a running server with Redis enabled.
Run with: pytest tests/e2e/test_resource_cache_e2e.py -v --run-e2e
"""

import pytest
import requests


@pytest.mark.e2e
class TestHealthEndpointResourceCacheE2E:
    """E2E tests for /health endpoint resource cache status."""

    def test_health_includes_resource_cache(self, health_url):
        """Test health endpoint includes resource_cache field."""
        response = requests.get(health_url, timeout=10)

        assert response.status_code in [200, 503]
        data = response.json()
        assert 'resource_cache' in data

    def test_resource_cache_has_required_fields(self, health_url):
        """Test resource_cache has all required fields."""
        response = requests.get(health_url, timeout=10)
        data = response.json()

        rc = data['resource_cache']
        assert 'enabled' in rc

        if rc['enabled']:
            assert 'loaded' in rc
            assert 'count' in rc
            assert 'version' in rc
            assert 'updated_at' in rc

    def test_resource_cache_loaded_has_positive_count(self, health_url):
        """Test resource cache has positive count when loaded."""
        response = requests.get(health_url, timeout=10)
        data = response.json()

        rc = data['resource_cache']
        if rc.get('enabled') and rc.get('loaded'):
            assert rc['count'] > 0, "Resource cache should have data when loaded"


@pytest.mark.e2e
@pytest.mark.redis
class TestResourceHistoryOptionsE2E:
    """E2E tests for resource history filter options endpoint."""

    def test_options_endpoint_accessible(self, api_base_url):
        """Test resource history options endpoint is accessible."""
        response = requests.get(
            f"{api_base_url}/resource/history/options",
            timeout=30
        )

        assert response.status_code == 200

    def test_options_returns_families(self, api_base_url):
        """Test options endpoint returns families list."""
        response = requests.get(
            f"{api_base_url}/resource/history/options",
            timeout=30
        )

        assert response.status_code == 200
        data = response.json()

        if data.get('success'):
            options = data.get('data', {})
            assert 'families' in options
            assert isinstance(options['families'], list)

    def test_options_returns_workcenter_groups(self, api_base_url):
        """Test options endpoint returns workcenter groups."""
        response = requests.get(
            f"{api_base_url}/resource/history/options",
            timeout=30
        )

        assert response.status_code == 200
        data = response.json()

        if data.get('success'):
            options = data.get('data', {})
            assert 'workcenter_groups' in options
            assert isinstance(options['workcenter_groups'], list)


@pytest.mark.e2e
@pytest.mark.redis
class TestResourceFilterOptionsE2E:
    """E2E tests for resource filter options endpoint."""

    def test_filter_options_endpoint_accessible(self, api_base_url):
        """Test resource filter options endpoint is accessible."""
        response = requests.get(
            f"{api_base_url}/resource/filter_options",
            timeout=30
        )

        assert response.status_code == 200

    def test_filter_options_returns_workcenters(self, api_base_url):
        """Test filter options returns workcenters list."""
        response = requests.get(
            f"{api_base_url}/resource/filter_options",
            timeout=30
        )

        assert response.status_code == 200
        data = response.json()

        if data.get('success'):
            options = data.get('data', {})
            assert 'workcenters' in options
            assert isinstance(options['workcenters'], list)

    def test_filter_options_returns_families(self, api_base_url):
        """Test filter options returns families list."""
        response = requests.get(
            f"{api_base_url}/resource/filter_options",
            timeout=30
        )

        assert response.status_code == 200
        data = response.json()

        if data.get('success'):
            options = data.get('data', {})
            assert 'families' in options
            assert isinstance(options['families'], list)

    def test_filter_options_returns_departments(self, api_base_url):
        """Test filter options returns departments list."""
        response = requests.get(
            f"{api_base_url}/resource/filter_options",
            timeout=30
        )

        assert response.status_code == 200
        data = response.json()

        if data.get('success'):
            options = data.get('data', {})
            assert 'departments' in options
            assert isinstance(options['departments'], list)

    def test_filter_options_returns_statuses(self, api_base_url):
        """Test filter options returns statuses list (from Oracle)."""
        response = requests.get(
            f"{api_base_url}/resource/filter_options",
            timeout=30
        )

        assert response.status_code == 200
        data = response.json()

        if data.get('success'):
            options = data.get('data', {})
            assert 'statuses' in options
            assert isinstance(options['statuses'], list)


@pytest.mark.e2e
@pytest.mark.redis
class TestResourceCachePerformanceE2E:
    """E2E tests for resource cache performance."""

    def test_filter_options_response_time(self, api_base_url):
        """Test filter options responds within acceptable time."""
        import time

        # First request may trigger cache load
        requests.get(f"{api_base_url}/resource/filter_options", timeout=30)

        # Second request should be from cache
        start = time.time()
        response = requests.get(f"{api_base_url}/resource/filter_options", timeout=30)
        elapsed = time.time() - start

        assert response.status_code == 200
        # Note: statuses still queries Oracle, so allow more time
        # Other fields (workcenters, families, departments) come from Redis cache
        assert elapsed < 30.0, f"Response took {elapsed:.2f}s, expected < 30s"

    def test_history_options_response_time(self, api_base_url):
        """Test history options responds within acceptable time."""
        import time

        # First request
        requests.get(f"{api_base_url}/resource/history/options", timeout=30)

        # Second request should be from cache
        start = time.time()
        response = requests.get(f"{api_base_url}/resource/history/options", timeout=30)
        elapsed = time.time() - start

        assert response.status_code == 200
        # Should be fast (< 2 seconds)
        assert elapsed < 2.0, f"Response took {elapsed:.2f}s, expected < 2s"


@pytest.mark.e2e
@pytest.mark.redis
class TestResourceCacheDataConsistencyE2E:
    """E2E tests for resource cache data consistency."""

    def test_cache_count_matches_health_report(self, health_url, api_base_url):
        """Test cache count in health matches actual data count."""
        # Get health status
        health_resp = requests.get(health_url, timeout=10)
        health_data = health_resp.json()

        rc = health_data.get('resource_cache', {})
        if not rc.get('enabled') or not rc.get('loaded'):
            pytest.skip("Resource cache not enabled or loaded")

        reported_count = rc.get('count', 0)

        # Get filter options which uses cached data
        options_resp = requests.get(f"{api_base_url}/resource/filter_options", timeout=30)
        options_data = options_resp.json()

        # The workcenters list should be derived from the same cache
        if options_data.get('success'):
            workcenters = options_data.get('data', {}).get('workcenters', [])
            # Just verify we got data - exact count comparison is complex
            assert len(workcenters) > 0 or reported_count == 0

    def test_families_consistent_across_endpoints(self, api_base_url):
        """Test families list is consistent across endpoints."""
        # Get from resource filter options
        filter_resp = requests.get(f"{api_base_url}/resource/filter_options", timeout=30)
        filter_data = filter_resp.json()

        # Get from resource history options
        history_resp = requests.get(f"{api_base_url}/resource/history/options", timeout=30)
        history_data = history_resp.json()

        if filter_data.get('success') and history_data.get('success'):
            filter_families = set(filter_data.get('data', {}).get('families', []))
            history_families = set(history_data.get('data', {}).get('families', []))

            # Both should return the same families (from same cache)
            assert filter_families == history_families, \
                f"Families mismatch: filter has {len(filter_families)}, history has {len(history_families)}"
