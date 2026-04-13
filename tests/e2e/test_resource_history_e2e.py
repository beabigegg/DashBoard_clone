# -*- coding: utf-8 -*-
"""End-to-end tests for resource history analysis page.

These tests simulate real user workflows through the resource history analysis feature.
Run with: pytest tests/e2e/test_resource_history_e2e.py -v --run-integration
"""

import json
import pytest
from unittest.mock import patch
import pandas as pd
from datetime import datetime

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

import mes_dashboard.core.database as db
import mes_dashboard.core.redis_client as _redis_mod
from mes_dashboard.app import create_app

pytestmark = [pytest.mark.e2e, pytest.mark.local_e2e]


@pytest.fixture
def app():
    """Create application for testing."""
    db._ENGINE = None
    app = create_app('testing')
    app.config['TESTING'] = True
    return app


@pytest.fixture
def client(app):
    """Create test client."""
    return app.test_client()


@pytest.fixture
def redis_enabled(monkeypatch):
    """Enable Redis for tests that require spool storage.

    conftest.py forces REDIS_ENABLED=false to isolate unit tests.
    E2E tests that exercise the spool path need a real Redis connection.
    Redis IS running in the integration environment (confirmed by redis-cli ping).
    """
    import mes_dashboard.core.query_spool_store as _spool_mod
    monkeypatch.setattr(_redis_mod, 'REDIS_ENABLED', True)
    monkeypatch.setattr(_redis_mod, '_REDIS_CLIENT', None)  # force reconnect
    monkeypatch.setattr(_spool_mod, 'QUERY_SPOOL_ENABLED', True)

    # Clear stale spool metadata AND L1 in-process cache so each test gets
    # a clean slate and won't reuse parquet files with the wrong schema.
    from mes_dashboard.services.resource_dataset_cache import _dataset_cache
    from mes_dashboard.core.redis_client import get_key_prefix

    def _clear_spool_state():
        _dataset_cache.clear()
        rc = _redis_mod.get_redis_client()
        if rc:
            prefix = get_key_prefix()
            for ns in ('resource_dataset', 'resource_oee'):
                keys = rc.keys(f"{prefix}:{ns}:spool_meta:*")
                if keys:
                    rc.delete(*keys)

    _clear_spool_state()
    yield
    _clear_spool_state()
    monkeypatch.setattr(_redis_mod, '_REDIS_CLIENT', None)


class TestResourceHistoryPageAccess:
    """E2E tests for page access and navigation."""

    @staticmethod
    def _load_resource_history_entry(client):
        response = client.get('/resource-history', follow_redirects=False)
        if response.status_code == 302 and response.location and 'portal-shell' in response.location:
            shell_response = client.get('/portal-shell/resource-history')
            assert shell_response.status_code == 200
            return shell_response, True
        return response, False

    def test_page_loads_successfully(self, client):
        """Resource history page should load without errors."""
        response, spa_enabled = self._load_resource_history_entry(client)
        assert response.status_code == 200
        content = response.data.decode('utf-8')
        if spa_enabled:
            assert '/static/dist/portal-shell.js' in content
        else:
            assert '設備歷史績效' in content

    def test_page_bootstrap_container_exists(self, client):
        """Resource history page should expose the Vue mount container."""
        response, _spa_enabled = self._load_resource_history_entry(client)
        content = response.data.decode('utf-8')

        assert "id='app'" in content or 'id="app"' in content

    def test_page_references_vite_module(self, client):
        """Resource history page should load the Vite module bundle."""
        response, spa_enabled = self._load_resource_history_entry(client)
        content = response.data.decode('utf-8')

        if spa_enabled:
            assert '/static/dist/portal-shell.js' in content
        else:
            assert '/static/dist/resource-history.js' in content
        assert 'type="module"' in content


class TestResourceHistoryAPIWorkflow:
    """E2E tests for API workflows."""

    @patch('mes_dashboard.services.resource_history_service.get_filter_options')
    def test_filter_options_workflow(self, mock_get_filter_options, client):
        """Filter options should be loadable."""
        mock_get_filter_options.return_value = {
            'workcenter_groups': [
                {'name': '焊接_DB', 'sequence': 1},
                {'name': '焊接_WB', 'sequence': 2},
                {'name': '成型', 'sequence': 4},
            ],
            'families': ['FAM001', 'FAM002'],
        }

        response = client.get('/api/resource/history/options')

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert 'workcenter_groups' in data['data']
        assert 'families' in data['data']

    @patch('mes_dashboard.services.resource_dataset_cache._get_workcenter_mapping')
    @patch('mes_dashboard.services.resource_dataset_cache._get_resource_lookup')
    @patch('mes_dashboard.services.resource_dataset_cache.read_sql_df')
    @patch('mes_dashboard.services.resource_dataset_cache._get_filtered_resources_and_lookup')
    def test_complete_query_workflow(self, mock_res_lookup, mock_read_sql,
                                     mock_get_lookup, mock_get_wc, client, redis_enabled):
        """Complete query workflow via POST /query should return summary + detail."""
        resources = [
            {
                'RESOURCEID': 'RES001',
                'WORKCENTERNAME': '焊接_DB',
                'RESOURCEFAMILYNAME': 'FAM001',
                'RESOURCENAME': 'RES001',
            },
            {
                'RESOURCEID': 'RES002',
                'WORKCENTERNAME': '成型',
                'RESOURCEFAMILYNAME': 'FAM002',
                'RESOURCENAME': 'RES002',
            },
        ]
        resource_lookup = {r['RESOURCEID']: r for r in resources}
        mock_res_lookup.return_value = (
            resources,
            resource_lookup,
            "HISTORYID IN ('RES001', 'RES002')",
        )
        mock_get_lookup.return_value = resource_lookup
        mock_get_wc.return_value = {
            '焊接_DB': {'group': '焊接_DB', 'sequence': 1},
            '成型': {'group': '成型', 'sequence': 4},
        }

        # Base facts DataFrame (per-resource × per-day, single Oracle query)
        base_df = pd.DataFrame([
            {'HISTORYID': 'RES001', 'DATA_DATE': datetime(2024, 1, 1),
             'PRD_HOURS': 4000, 'SBY_HOURS': 500, 'UDT_HOURS': 250,
             'SDT_HOURS': 150, 'EGT_HOURS': 100, 'NST_HOURS': 500, 'TOTAL_HOURS': 5500},
            {'HISTORYID': 'RES002', 'DATA_DATE': datetime(2024, 1, 1),
             'PRD_HOURS': 4000, 'SBY_HOURS': 500, 'UDT_HOURS': 250,
             'SDT_HOURS': 150, 'EGT_HOURS': 100, 'NST_HOURS': 500, 'TOTAL_HOURS': 5500},
        ])
        # OEE facts DataFrame — separate Oracle query for TRACKOUT/NG.
        # DuckDB joins oee_src to resource_dim by EQUIPMENTID = HISTORYID.
        oee_df = pd.DataFrame([
            {'EQUIPMENTID': 'RES001', 'SHIFT_DATE': datetime(2024, 1, 1),
             'TRACKOUT_QTY': 0, 'NG_QTY': 0},
            {'EQUIPMENTID': 'RES002', 'SHIFT_DATE': datetime(2024, 1, 1),
             'TRACKOUT_QTY': 0, 'NG_QTY': 0},
        ])
        # read_sql_df is called twice: first for base SHIFT data, then for OEE facts.
        mock_read_sql.side_effect = [base_df, oee_df]

        response = client.post(
            '/api/resource/history/query',
            json={
                'start_date': '2024-01-01',
                'end_date': '2024-01-07',
                'granularity': 'day',
            },
        )

        assert response.status_code == 200
        resp_json = json.loads(response.data)
        assert resp_json['success'] is True
        # Unwrap nested success_response: actual payload is in resp_json['data']
        data = resp_json.get('data', resp_json)
        if isinstance(data, dict) and 'query_id' not in data and 'data' in resp_json:
            data = resp_json['data']
        assert 'query_id' in data

        # Verify KPI (derived from base_df)
        # Total PRD=8000, SBY=1000, UDT=500, SDT=300, EGT=200
        # OU% = 8000/(8000+1000+500+300+200)*100 = 80.0
        assert data['summary']['kpi']['ou_pct'] == 80.0
        # Availability% = (8000+1000+200)/(8000+1000+200+300+500+1000)*100 = 83.6
        assert data['summary']['kpi']['availability_pct'] == 83.6
        assert data['summary']['kpi']['machine_count'] == 2

        # Verify trend (one period since both rows are same date)
        assert len(data['summary']['trend']) >= 1
        assert 'availability_pct' in data['summary']['trend'][0]

        # Verify heatmap
        assert len(data['summary']['heatmap']) >= 1

        # Verify comparison
        assert len(data['summary']['workcenter_comparison']) == 2

        # Verify detail
        assert data['detail']['total'] == 2
        assert len(data['detail']['data']) == 2

    @patch('mes_dashboard.services.resource_dataset_cache._get_workcenter_mapping')
    @patch('mes_dashboard.services.resource_dataset_cache._get_resource_lookup')
    @patch('mes_dashboard.services.resource_dataset_cache.read_sql_df')
    @patch('mes_dashboard.services.resource_dataset_cache._get_filtered_resources_and_lookup')
    def test_detail_query_workflow(self, mock_res_lookup, mock_read_sql,
                                    mock_get_lookup, mock_get_wc, client, redis_enabled):
        """Detail query via POST /query should return hierarchical data."""
        resources = [
            {
                'RESOURCEID': 'RES001',
                'WORKCENTERNAME': '焊接_DB',
                'RESOURCEFAMILYNAME': 'FAM001',
                'RESOURCENAME': 'RES001',
            },
            {
                'RESOURCEID': 'RES002',
                'WORKCENTERNAME': '焊接_DB',
                'RESOURCEFAMILYNAME': 'FAM001',
                'RESOURCENAME': 'RES002',
            },
        ]
        resource_lookup = {r['RESOURCEID']: r for r in resources}
        mock_res_lookup.return_value = (
            resources,
            resource_lookup,
            "HISTORYID IN ('RES001', 'RES002')",
        )
        mock_get_lookup.return_value = resource_lookup
        mock_get_wc.return_value = {
            '焊接_DB': {'group': '焊接_DB', 'sequence': 1},
        }

        base_df = pd.DataFrame([
            {'HISTORYID': 'RES001', 'DATA_DATE': datetime(2024, 1, 1),
             'PRD_HOURS': 80, 'SBY_HOURS': 10, 'UDT_HOURS': 5, 'SDT_HOURS': 3, 'EGT_HOURS': 2,
             'NST_HOURS': 10, 'TOTAL_HOURS': 110},
            {'HISTORYID': 'RES002', 'DATA_DATE': datetime(2024, 1, 1),
             'PRD_HOURS': 75, 'SBY_HOURS': 15, 'UDT_HOURS': 5, 'SDT_HOURS': 3, 'EGT_HOURS': 2,
             'NST_HOURS': 10, 'TOTAL_HOURS': 110},
        ])
        oee_df = pd.DataFrame([
            {'EQUIPMENTID': 'RES001', 'SHIFT_DATE': datetime(2024, 1, 1),
             'TRACKOUT_QTY': 0, 'NG_QTY': 0},
            {'EQUIPMENTID': 'RES002', 'SHIFT_DATE': datetime(2024, 1, 1),
             'TRACKOUT_QTY': 0, 'NG_QTY': 0},
        ])
        mock_read_sql.side_effect = [base_df, oee_df]

        response = client.post(
            '/api/resource/history/query',
            json={
                'start_date': '2024-01-01',
                'end_date': '2024-01-07',
            },
        )

        assert response.status_code == 200
        resp_json = json.loads(response.data)
        assert resp_json['success'] is True
        data = resp_json.get('data', resp_json)
        assert data['detail']['total'] == 2
        assert len(data['detail']['data']) == 2
        assert data['detail']['truncated'] is False

        # Verify data structure
        first_row = data['detail']['data'][0]
        assert 'workcenter' in first_row
        assert 'family' in first_row
        assert 'resource' in first_row
        assert 'ou_pct' in first_row
        assert 'availability_pct' in first_row
        assert 'prd_hours' in first_row
        assert 'prd_pct' in first_row

    @patch('mes_dashboard.services.resource_history_service._get_filtered_resources')
    @patch('mes_dashboard.services.resource_history_service.read_sql_df')
    def test_export_workflow(self, mock_read_sql, mock_resources, client):
        """Export workflow should return valid CSV."""
        mock_resources.return_value = [
            {
                'RESOURCEID': 'RES001',
                'WORKCENTERNAME': '焊接_DB',
                'RESOURCEFAMILYNAME': 'FAM001',
                'RESOURCENAME': 'RES001',
            }
        ]
        main_df = pd.DataFrame([
            {'HISTORYID': 'RES001',
             'PRD_HOURS': 80, 'SBY_HOURS': 10, 'UDT_HOURS': 5, 'SDT_HOURS': 3, 'EGT_HOURS': 2,
             'NST_HOURS': 10, 'TOTAL_HOURS': 110},
        ])
        # read_sql_df is called twice: first for SHIFT data, then for OEE facts.
        # Return empty DataFrame for the OEE call so EQUIPMENTID groupby is skipped.
        mock_read_sql.side_effect = [main_df, pd.DataFrame()]

        response = client.get(
            '/api/resource/history/export'
            '?start_date=2024-01-01'
            '&end_date=2024-01-07'
        )

        assert response.status_code == 200
        assert 'text/csv' in response.content_type

        content = response.data.decode('utf-8-sig')
        lines = content.strip().split('\n')

        # Should have header + data rows
        assert len(lines) >= 2

        # Verify header
        header = lines[0]
        assert '站點' in header
        assert 'OU%' in header
        assert 'Availability%' in header


class TestResourceHistoryValidation:
    """E2E tests for input validation."""

    def test_date_range_validation(self, client):
        """Inverted date range (end_date < start_date) should be rejected."""
        response = client.post(
            '/api/resource/history/query',
            json={
                'start_date': '2026-01-02',
                'end_date': '2024-01-01',
            },
        )

        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['success'] is False

    def test_missing_required_params(self, client):
        """Missing required parameters should return error."""
        response = client.post(
            '/api/resource/history/query',
            json={},
        )

        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['success'] is False

    @patch('mes_dashboard.services.resource_dataset_cache._get_workcenter_mapping')
    @patch('mes_dashboard.services.resource_dataset_cache._get_resource_lookup')
    @patch('mes_dashboard.services.resource_dataset_cache.read_sql_df')
    @patch('mes_dashboard.services.resource_dataset_cache._get_filtered_resources_and_lookup')
    def test_granularity_options(self, mock_res_lookup, mock_read_sql,
                                  mock_get_lookup, mock_get_wc, client):
        """Different granularity options should work via POST /query."""
        resources = [{
            'RESOURCEID': 'RES001',
            'WORKCENTERNAME': '焊接_DB',
            'RESOURCEFAMILYNAME': 'FAM001',
            'RESOURCENAME': 'RES001',
        }]
        resource_lookup = {r['RESOURCEID']: r for r in resources}
        mock_res_lookup.return_value = (
            resources,
            resource_lookup,
            "HISTORYID IN ('RES001')",
        )
        mock_get_lookup.return_value = resource_lookup
        mock_get_wc.return_value = {
            '焊接_DB': {'group': '焊接_DB', 'sequence': 1},
        }

        base_df = pd.DataFrame([{
            'HISTORYID': 'RES001',
            'DATA_DATE': datetime(2024, 1, 1),
            'PRD_HOURS': 100, 'SBY_HOURS': 10, 'UDT_HOURS': 5,
            'SDT_HOURS': 3, 'EGT_HOURS': 2, 'NST_HOURS': 10,
            'TOTAL_HOURS': 130,
        }])
        mock_read_sql.return_value = base_df

        for granularity in ['day', 'week', 'month', 'year']:
            response = client.post(
                '/api/resource/history/query',
                json={
                    'start_date': '2024-01-01',
                    'end_date': '2024-01-31',
                    'granularity': granularity,
                },
            )

            assert response.status_code == 200, f"Failed for granularity={granularity}"


class TestResourceHistoryNavigation:
    """E2E tests for navigation integration."""

    def test_portal_includes_history_tab(self, client):
        """Portal should include resource history tab."""
        if bool(client.application.config.get("PORTAL_SPA_ENABLED", False)):
            response = client.get('/api/portal/navigation')
            assert response.status_code == 200
            payload = response.get_json()
            pages = [
                page
                for drawer in payload.get("drawers", [])
                for page in drawer.get("pages", [])
            ]
            history_pages = [page for page in pages if page.get("route") == "/resource-history"]
            assert history_pages, "resource-history route missing from portal navigation contract"
            assert history_pages[0].get("name") == "設備歷史績效"
        else:
            response = client.get('/')
            content = response.data.decode('utf-8')
            assert '設備歷史績效' in content
            assert 'resourceHistoryFrame' in content


if __name__ == '__main__':
    pytest.main([__file__, '-v'])


class TestResourceHistorySpoolReuse:
    """E2E tests for resource-history spool caching and reuse."""

    @staticmethod
    def _fake_oracle_df():
        import pandas as pd
        return pd.DataFrame({
            "HISTORYID": [1, 2],
            "STATECODE": ["PRD", "SBY"],
            "DURATION_HOURS": [8.0, 4.0],
            "TRACKOUT_QTY": [100, 0],
            "NG_QTY": [5, 0],
        })

    def test_two_identical_queries_oracle_called_once(self, client, monkeypatch):
        """Two identical POST /query calls → Oracle mock called only once (second uses spool)."""
        oracle_calls = {"count": 0}

        def fake_execute_primary_query(**kwargs):
            oracle_calls["count"] += 1
            return {
                "query_id": "spool-reuse-qid",
                "summary": {"kpi": {}, "trend": [], "heatmap": [], "workcenter_comparison": []},
                "detail": {"data": [], "total": 0, "truncated": False, "max_records": None},
                "_meta": {},
            }

        def fake_canonical_spool(*args, **kwargs):
            """First call returns None (miss), second returns result (hit)."""
            if oracle_calls["count"] >= 1:
                return (
                    {
                        "query_id": "spool-reuse-qid",
                        "summary": {"kpi": {}, "trend": [], "heatmap": [], "workcenter_comparison": []},
                        "detail": {"data": [], "total": 0, "truncated": False, "max_records": None},
                    },
                    {},
                )
            return (None, {})

        with patch(
            "mes_dashboard.routes.resource_history_routes.execute_primary_query",
            side_effect=fake_execute_primary_query,
        ), patch(
            "mes_dashboard.services.resource_history_sql_runtime.try_compute_query_from_canonical_spool",
            side_effect=fake_canonical_spool,
        ):
            payload = {"start_date": "2025-01-01", "end_date": "2025-01-31"}

            # First call (cache miss → Oracle)
            r1 = client.post(
                "/api/resource/history/query",
                json=payload,
                content_type="application/json",
            )
            # Second call (cache hit → spool)
            r2 = client.post(
                "/api/resource/history/query",
                json=payload,
                content_type="application/json",
            )

        assert r1.status_code == 200
        assert r2.status_code == 200
        assert oracle_calls["count"] == 1  # Oracle called only once

        d1 = r1.get_json()["data"]
        d2 = r2.get_json()["data"]
        assert d1.get("query_id") == d2.get("query_id")

    def test_canonical_spool_hit_skips_oracle(self, client, monkeypatch):
        """try_compute_query_from_canonical_spool returning result → Oracle not called."""
        oracle_calls = {"count": 0}

        def fake_execute_primary_query(**kwargs):
            oracle_calls["count"] += 1
            return {}

        canonical_result = {
            "query_id": "canonical-qid-test",
            "summary": {"kpi": {}, "trend": [], "heatmap": [], "workcenter_comparison": []},
            "detail": {"data": [], "total": 0, "truncated": False, "max_records": None},
        }

        with patch(
            "mes_dashboard.routes.resource_history_routes.execute_primary_query",
            side_effect=fake_execute_primary_query,
        ), patch(
            "mes_dashboard.services.resource_history_sql_runtime.try_compute_query_from_canonical_spool",
            return_value=(canonical_result, {}),
        ):
            payload = {"start_date": "2025-06-01", "end_date": "2025-06-30"}
            response = client.post(
                "/api/resource/history/query",
                json=payload,
                content_type="application/json",
            )

        assert response.status_code == 200
        assert oracle_calls["count"] == 0  # Oracle NOT called
        data = response.get_json()["data"]
        assert data.get("query_id") == "canonical-qid-test"
