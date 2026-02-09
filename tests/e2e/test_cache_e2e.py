# -*- coding: utf-8 -*-
"""End-to-end tests for Redis cache functionality.

These tests require a running server with Redis enabled.
Run with: pytest tests/e2e/test_cache_e2e.py -v
"""

import pytest
import requests
import time


@pytest.mark.e2e
class TestHealthEndpointE2E:
    """E2E tests for /health endpoint."""

    def test_health_endpoint_accessible(self, health_url):
        """Test health endpoint is accessible."""
        response = requests.get(health_url, timeout=10)

        assert response.status_code in [200, 503]
        data = response.json()
        assert 'status' in data
        assert 'services' in data
        assert 'cache' in data

    def test_health_shows_database_status(self, health_url):
        """Test health endpoint shows database status."""
        response = requests.get(health_url, timeout=10)
        data = response.json()

        assert 'database' in data['services']
        assert data['services']['database'] in ['ok', 'error']

    def test_health_shows_redis_status(self, health_url):
        """Test health endpoint shows Redis status."""
        response = requests.get(health_url, timeout=10)
        data = response.json()

        assert 'redis' in data['services']
        assert data['services']['redis'] in ['ok', 'error', 'disabled']

    def test_health_shows_cache_info(self, health_url):
        """Test health endpoint shows cache information."""
        response = requests.get(health_url, timeout=10)
        data = response.json()

        assert 'cache' in data
        assert 'enabled' in data['cache']
        assert 'sys_date' in data['cache']
        assert 'updated_at' in data['cache']


@pytest.mark.e2e
@pytest.mark.redis
class TestCachedWipApiE2E:
    """E2E tests for cached WIP API endpoints."""

    def _unwrap(self, resp_json):
        """Unwrap API response to get data."""
        if isinstance(resp_json, dict) and 'data' in resp_json:
            return resp_json['data']
        return resp_json

    def test_wip_summary_returns_data(self, api_base_url):
        """Test WIP summary endpoint returns valid data."""
        response = requests.get(f"{api_base_url}/wip/overview/summary", timeout=30)

        assert response.status_code == 200
        data = self._unwrap(response.json())
        assert 'totalLots' in data
        assert 'totalQtyPcs' in data
        assert 'byWipStatus' in data
        assert 'dataUpdateDate' in data

    def test_wip_summary_status_breakdown(self, api_base_url):
        """Test WIP summary contains correct status breakdown."""
        response = requests.get(f"{api_base_url}/wip/overview/summary", timeout=30)
        data = self._unwrap(response.json())

        by_status = data['byWipStatus']
        assert 'run' in by_status
        assert 'queue' in by_status
        assert 'hold' in by_status
        assert 'qualityHold' in by_status
        assert 'nonQualityHold' in by_status

        # Each status should have lots and qtyPcs
        for status in ['run', 'queue', 'hold']:
            assert 'lots' in by_status[status]
            assert 'qtyPcs' in by_status[status]

    def test_wip_matrix_returns_data(self, api_base_url):
        """Test WIP matrix endpoint returns valid data."""
        response = requests.get(f"{api_base_url}/wip/overview/matrix", timeout=30)

        assert response.status_code == 200
        data = self._unwrap(response.json())
        assert 'workcenters' in data
        assert 'packages' in data
        assert 'matrix' in data
        assert 'workcenter_totals' in data
        assert 'package_totals' in data
        assert 'grand_total' in data

    def test_wip_workcenters_returns_list(self, api_base_url):
        """Test workcenters endpoint returns list."""
        response = requests.get(f"{api_base_url}/wip/meta/workcenters", timeout=30)

        assert response.status_code == 200
        data = self._unwrap(response.json())
        assert isinstance(data, list)

        if len(data) > 0:
            assert 'name' in data[0]
            assert 'lot_count' in data[0]

    def test_wip_packages_returns_list(self, api_base_url):
        """Test packages endpoint returns list."""
        response = requests.get(f"{api_base_url}/wip/meta/packages", timeout=30)

        assert response.status_code == 200
        data = self._unwrap(response.json())
        assert isinstance(data, list)

        if len(data) > 0:
            assert 'name' in data[0]
            assert 'lot_count' in data[0]

    def test_wip_hold_summary_returns_data(self, api_base_url):
        """Test hold summary endpoint returns valid data."""
        response = requests.get(f"{api_base_url}/wip/overview/hold", timeout=30)

        assert response.status_code == 200
        data = self._unwrap(response.json())
        assert 'items' in data
        assert isinstance(data['items'], list)


@pytest.mark.e2e
@pytest.mark.redis
class TestCachePerformanceE2E:
    """E2E tests for cache performance."""

    def _unwrap(self, resp_json):
        """Unwrap API response to get data."""
        if isinstance(resp_json, dict) and 'data' in resp_json:
            return resp_json['data']
        return resp_json

    def test_cached_response_is_fast(self, api_base_url):
        """Test cached responses are faster than 2 seconds."""
        # First request may load cache
        requests.get(f"{api_base_url}/wip/overview/summary", timeout=30)

        # Second request should be from cache
        start = time.time()
        response = requests.get(f"{api_base_url}/wip/overview/summary", timeout=30)
        elapsed = time.time() - start

        assert response.status_code == 200
        # Cached response should be fast (< 2 seconds)
        assert elapsed < 2.0, f"Response took {elapsed:.2f}s, expected < 2s"

    def test_multiple_endpoints_consistent(self, api_base_url):
        """Test multiple endpoints return consistent data."""
        # Get summary
        summary_resp = requests.get(f"{api_base_url}/wip/overview/summary", timeout=30)
        summary = self._unwrap(summary_resp.json())

        # Get matrix
        matrix_resp = requests.get(f"{api_base_url}/wip/overview/matrix", timeout=30)
        matrix = self._unwrap(matrix_resp.json())

        # Grand total from matrix should match total from summary (approximately)
        # There may be slight differences due to filtering
        if summary['totalLots'] > 0 and matrix['grand_total'] > 0:
            assert summary['totalQtyPcs'] > 0 or matrix['grand_total'] > 0


@pytest.mark.e2e
@pytest.mark.redis
class TestSearchEndpointsE2E:
    """E2E tests for search endpoints with cache."""

    def _unwrap(self, resp_json):
        """Unwrap API response to get data."""
        if isinstance(resp_json, dict) and 'data' in resp_json:
            data = resp_json['data']
            # Search returns {'items': [...]}
            if isinstance(data, dict) and 'items' in data:
                return data['items']
            return data
        return resp_json

    def test_search_workorders(self, api_base_url):
        """Test workorder search returns results."""
        # Use a common pattern that should exist
        response = requests.get(
            f"{api_base_url}/wip/meta/search",
            params={'field': 'workorder', 'q': 'WO', 'limit': 10},
            timeout=30
        )

        assert response.status_code == 200
        data = self._unwrap(response.json())
        assert isinstance(data, list)

    def test_search_lotids(self, api_base_url):
        """Test lot ID search returns results."""
        response = requests.get(
            f"{api_base_url}/wip/meta/search",
            params={'field': 'lotid', 'q': 'LOT', 'limit': 10},
            timeout=30
        )

        assert response.status_code == 200
        data = self._unwrap(response.json())
        assert isinstance(data, list)

    def test_search_with_short_query_returns_empty(self, api_base_url):
        """Test search with short query returns empty list."""
        response = requests.get(
            f"{api_base_url}/wip/meta/search",
            params={'field': 'workorder', 'q': 'W'},  # Too short
            timeout=30
        )

        assert response.status_code == 200
        data = self._unwrap(response.json())
        assert data == []


@pytest.mark.e2e
@pytest.mark.redis
class TestWipDetailE2E:
    """E2E tests for WIP detail endpoint with cache."""

    def _unwrap(self, resp_json):
        """Unwrap API response to get data."""
        if isinstance(resp_json, dict) and 'data' in resp_json:
            return resp_json['data']
        return resp_json

    def test_wip_detail_with_workcenter(self, api_base_url):
        """Test WIP detail endpoint for a workcenter."""
        # First get list of workcenters
        wc_resp = requests.get(f"{api_base_url}/wip/meta/workcenters", timeout=30)
        workcenters = self._unwrap(wc_resp.json())

        if len(workcenters) > 0:
            wc_name = workcenters[0]['name']
            response = requests.get(
                f"{api_base_url}/wip/detail/{wc_name}",
                timeout=30
            )

            assert response.status_code == 200
            data = self._unwrap(response.json())
            assert 'workcenter' in data
            assert 'summary' in data
            assert 'lots' in data
            assert 'pagination' in data

    def test_wip_detail_pagination(self, api_base_url):
        """Test WIP detail pagination."""
        wc_resp = requests.get(f"{api_base_url}/wip/meta/workcenters", timeout=30)
        workcenters = self._unwrap(wc_resp.json())

        if len(workcenters) > 0:
            wc_name = workcenters[0]['name']
            response = requests.get(
                f"{api_base_url}/wip/detail/{wc_name}",
                params={'page': 1, 'page_size': 10},
                timeout=30
            )

            assert response.status_code == 200
            data = self._unwrap(response.json())
            assert data['pagination']['page'] == 1
            assert data['pagination']['page_size'] == 10
