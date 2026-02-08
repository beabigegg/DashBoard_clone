# -*- coding: utf-8 -*-
"""End-to-end tests for realtime equipment status cache.

Tests the full flow from cache sync to API response.
Requires a running server with --run-e2e flag.
"""

import pytest
import requests


@pytest.mark.e2e
class TestEquipmentStatusCacheSync:
    """Test equipment status cache synchronization."""

    def test_health_check_includes_equipment_status_cache(self, health_url):
        """Test health check includes equipment_status_cache status."""
        response = requests.get(health_url)

        assert response.status_code == 200
        data = response.json()

        # Should have equipment_status_cache in response
        assert 'equipment_status_cache' in data
        cache_status = data['equipment_status_cache']

        # Should have expected fields
        assert 'enabled' in cache_status
        assert 'loaded' in cache_status
        assert 'count' in cache_status
        assert 'updated_at' in cache_status

    def test_health_check_includes_workcenter_mapping(self, health_url):
        """Test health check includes workcenter_mapping status."""
        response = requests.get(health_url)

        assert response.status_code == 200
        data = response.json()

        # Should have workcenter_mapping in response
        assert 'workcenter_mapping' in data
        wc_status = data['workcenter_mapping']

        # Should have expected fields
        assert 'loaded' in wc_status
        assert 'workcenter_count' in wc_status
        assert 'group_count' in wc_status


@pytest.mark.e2e
class TestMergedQueryApi:
    """Test merged resource status API endpoints."""

    def test_resource_status_endpoint(self, api_base_url):
        """Test /api/resource/status endpoint."""
        url = f"{api_base_url}/resource/status"
        response = requests.get(url)

        assert response.status_code == 200
        data = response.json()

        assert data['success'] is True
        assert 'data' in data
        assert 'count' in data

        # If data exists, verify structure
        if data['data']:
            record = data['data'][0]
            # Should have merged fields
            assert 'RESOURCEID' in record
            assert 'RESOURCENAME' in record
            # Should have workcenter mapping fields
            assert 'WORKCENTER_GROUP' in record
            assert 'WORKCENTER_SHORT' in record
            # Should have realtime status fields
            assert 'STATUS_CATEGORY' in record

    def test_resource_status_with_workcenter_filter(self, api_base_url):
        """Test /api/resource/status with workcenter_groups filter."""
        url = f"{api_base_url}/resource/status"
        response = requests.get(url, params={'workcenter_groups': '焊接'})

        assert response.status_code == 200
        data = response.json()

        assert data['success'] is True

        # All results should be in the specified group
        for record in data['data']:
            # May be None if mapping not found
            if record.get('WORKCENTER_GROUP'):
                assert record['WORKCENTER_GROUP'] == '焊接'

    def test_resource_status_with_production_filter(self, api_base_url):
        """Test /api/resource/status with is_production filter."""
        url = f"{api_base_url}/resource/status"
        response = requests.get(url, params={'is_production': 'true'})

        assert response.status_code == 200
        data = response.json()

        assert data['success'] is True

    def test_resource_status_with_status_category_filter(self, api_base_url):
        """Test /api/resource/status with status_categories filter."""
        url = f"{api_base_url}/resource/status"
        response = requests.get(url, params={'status_categories': 'PRODUCTIVE,DOWN'})

        assert response.status_code == 200
        data = response.json()

        assert data['success'] is True

        # All results should be in specified categories
        for record in data['data']:
            if record.get('STATUS_CATEGORY'):
                assert record['STATUS_CATEGORY'] in ['PRODUCTIVE', 'DOWN']

    def test_resource_status_summary_endpoint(self, api_base_url):
        """Test /api/resource/status/summary endpoint."""
        url = f"{api_base_url}/resource/status/summary"
        response = requests.get(url)

        assert response.status_code == 200
        data = response.json()

        assert data['success'] is True
        assert 'data' in data

        summary = data['data']
        assert 'total_count' in summary
        assert 'by_status_category' in summary
        assert 'by_workcenter_group' in summary
        assert 'with_active_job' in summary
        assert 'with_wip' in summary

    def test_resource_status_matrix_endpoint(self, api_base_url):
        """Test /api/resource/status/matrix endpoint."""
        url = f"{api_base_url}/resource/status/matrix"
        response = requests.get(url)

        assert response.status_code == 200
        data = response.json()

        assert data['success'] is True
        assert 'data' in data

        # If data exists, verify structure
        if data['data']:
            row = data['data'][0]
            assert 'workcenter_group' in row
            assert 'workcenter_sequence' in row
            assert 'total' in row
            # Should have standard status columns
            assert 'PRD' in row
            assert 'SBY' in row
            assert 'UDT' in row
            assert 'SDT' in row
            assert 'EGT' in row
            assert 'NST' in row
            assert 'OTHER' in row


@pytest.mark.e2e
class TestFilterOptionsIncludeNewFields:
    """Test filter options API includes new fields."""

    def test_status_options_endpoint(self, api_base_url):
        """Test /api/resource/status/options endpoint."""
        url = f"{api_base_url}/resource/status/options"
        response = requests.get(url)

        assert response.status_code == 200
        data = response.json()

        assert data['success'] is True
        assert 'data' in data

        options = data['data']
        # Should have workcenter_groups
        assert 'workcenter_groups' in options
        assert isinstance(options['workcenter_groups'], list)

        # Should have status_categories
        assert 'status_categories' in options
        assert isinstance(options['status_categories'], list)


@pytest.mark.e2e
@pytest.mark.redis
class TestCacheIntegration:
    """Test cache integration (requires Redis)."""

    def test_cache_data_consistency(self, api_base_url, health_url):
        """Test cache data is consistent between health and API."""
        # Get health status
        health_resp = requests.get(health_url)
        health_data = health_resp.json()

        cache_status = health_data.get('equipment_status_cache', {})

        if not cache_status.get('enabled') or not cache_status.get('loaded'):
            pytest.skip("Equipment status cache not enabled or loaded")

        cache_count = cache_status.get('count', 0)

        # Get all equipment status via API
        api_resp = requests.get(f"{api_base_url}/resource/status")
        api_data = api_resp.json()

        # Count should be consistent (within reasonable margin for filtering)
        api_count = api_data.get('count', 0)

        # API may have filters applied from resource-cache, so it could be less
        # but should never exceed cache count
        assert api_count <= cache_count or cache_count == 0
