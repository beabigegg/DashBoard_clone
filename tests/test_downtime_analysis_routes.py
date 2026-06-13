# -*- coding: utf-8 -*-
"""Route tests for downtime_analysis_routes.py.

Per-kwarg forwarding style: assert mock_service.call_args.kwargs['key'] == value.
NEVER uses assert_called_once_with(...) whitelists (CLAUDE.md Test Coverage Discipline).
Both snapshot path (spool hit via apply_view) and Oracle fallback path (query_downtime_dataset)
are exercised for every kwarg.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

import mes_dashboard.core.database as db
from mes_dashboard.app import create_app


@pytest.fixture
def app():
    db._ENGINE = None
    app = create_app('testing')
    app.config['TESTING'] = True
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def _mock_query_result(query_id='test-qid'):
    return {
        'query_id': query_id,
        'summary': {
            'total_hours': 0.0, 'udt_hours': 0.0, 'sdt_hours': 0.0,
            'egt_hours': 0.0, 'event_count': 0, 'avg_event_min': 0.0,
        },
        'daily_trend': [],
        'big_category': [],
        'top_reasons': [],
    }


def _mock_view_result():
    return {
        'summary': {
            'total_hours': 5.0, 'udt_hours': 5.0, 'sdt_hours': 0.0,
            'egt_hours': 0.0, 'event_count': 2, 'avg_event_min': 150.0,
        },
        'daily_trend': [],
        'big_category': [],
        'top_reasons': [],
    }


# ===========================================================================
# TestSummaryRoute — POST /query
# ===========================================================================


class TestSummaryRoute:
    """POST /api/downtime-analysis/query kwarg forwarding tests."""

    @patch('mes_dashboard.routes.downtime_analysis_routes.query_downtime_dataset')
    def test_start_date_forwarded(self, mock_svc, client):
        mock_svc.return_value = _mock_query_result()
        client.post('/api/downtime-analysis/query',
                    json={'start_date': '2026-04-01', 'end_date': '2026-04-30'})
        assert mock_svc.call_args.kwargs['start_date'] == '2026-04-01'

    @patch('mes_dashboard.routes.downtime_analysis_routes.query_downtime_dataset')
    def test_end_date_forwarded(self, mock_svc, client):
        mock_svc.return_value = _mock_query_result()
        client.post('/api/downtime-analysis/query',
                    json={'start_date': '2026-04-01', 'end_date': '2026-04-30'})
        assert mock_svc.call_args.kwargs['end_date'] == '2026-04-30'

    @patch('mes_dashboard.routes.downtime_analysis_routes.query_downtime_dataset')
    def test_workcenter_groups_forwarded(self, mock_svc, client):
        mock_svc.return_value = _mock_query_result()
        client.post('/api/downtime-analysis/query',
                    json={'start_date': '2026-04-01', 'end_date': '2026-04-30',
                          'workcenter_groups': ['WC_ASSY']})
        assert mock_svc.call_args.kwargs['workcenter_groups'] == ['WC_ASSY']

    @patch('mes_dashboard.routes.downtime_analysis_routes.query_downtime_dataset')
    def test_families_forwarded(self, mock_svc, client):
        mock_svc.return_value = _mock_query_result()
        client.post('/api/downtime-analysis/query',
                    json={'start_date': '2026-04-01', 'end_date': '2026-04-30',
                          'families': ['FAM-A']})
        assert mock_svc.call_args.kwargs['families'] == ['FAM-A']

    @patch('mes_dashboard.routes.downtime_analysis_routes.query_downtime_dataset')
    def test_resource_ids_forwarded(self, mock_svc, client):
        mock_svc.return_value = _mock_query_result()
        client.post('/api/downtime-analysis/query',
                    json={'start_date': '2026-04-01', 'end_date': '2026-04-30',
                          'resource_ids': ['R-42']})
        assert mock_svc.call_args.kwargs['resource_ids'] == ['R-42']

    @patch('mes_dashboard.routes.downtime_analysis_routes.query_downtime_dataset')
    def test_package_groups_forwarded(self, mock_svc, client):
        mock_svc.return_value = _mock_query_result()
        client.post('/api/downtime-analysis/query',
                    json={'start_date': '2026-04-01', 'end_date': '2026-04-30',
                          'package_groups': ['PKG-X']})
        assert mock_svc.call_args.kwargs['package_groups'] == ['PKG-X']

    @patch('mes_dashboard.routes.downtime_analysis_routes.query_downtime_dataset')
    def test_big_categories_forwarded(self, mock_svc, client):
        mock_svc.return_value = _mock_query_result()
        client.post('/api/downtime-analysis/query',
                    json={'start_date': '2026-04-01', 'end_date': '2026-04-30',
                          'big_categories': ['維修']})
        assert mock_svc.call_args.kwargs['big_categories'] == ['維修']

    @patch('mes_dashboard.routes.downtime_analysis_routes.query_downtime_dataset')
    def test_status_types_forwarded(self, mock_svc, client):
        mock_svc.return_value = _mock_query_result()
        client.post('/api/downtime-analysis/query',
                    json={'start_date': '2026-04-01', 'end_date': '2026-04-30',
                          'status_types': ['SDT']})
        assert mock_svc.call_args.kwargs['status_types'] == ['SDT']

    def test_missing_dates_returns_400(self, client):
        resp = client.post('/api/downtime-analysis/query', json={'start_date': '2026-04-01'})
        assert resp.status_code == 400

    def test_invalid_date_format_returns_400(self, client):
        resp = client.post('/api/downtime-analysis/query',
                           json={'start_date': 'not-a-date', 'end_date': '2026-04-30'})
        assert resp.status_code == 400

    def test_reversed_dates_returns_400(self, client):
        resp = client.post('/api/downtime-analysis/query',
                           json={'start_date': '2026-04-30', 'end_date': '2026-04-01'})
        assert resp.status_code == 400


# ===========================================================================
# TestBigCategoryRoute — GET /view
# ===========================================================================


class TestBigCategoryRoute:
    """GET /api/downtime-analysis/view kwarg forwarding tests."""

    @patch('mes_dashboard.routes.downtime_analysis_routes.apply_view')
    def test_query_id_forwarded(self, mock_apply, client):
        mock_apply.return_value = _mock_view_result()
        client.get('/api/downtime-analysis/view?query_id=ABC123&granularity=day')
        assert mock_apply.call_args.kwargs['query_id'] == 'ABC123'

    @patch('mes_dashboard.routes.downtime_analysis_routes.apply_view')
    def test_granularity_day_forwarded(self, mock_apply, client):
        mock_apply.return_value = _mock_view_result()
        client.get('/api/downtime-analysis/view?query_id=ABC123&granularity=day')
        assert mock_apply.call_args.kwargs['granularity'] == 'day'

    def test_granularity_week_returns_400(self, client):
        resp = client.get('/api/downtime-analysis/view?query_id=ABC123&granularity=week')
        assert resp.status_code == 400

    def test_granularity_month_returns_400(self, client):
        resp = client.get('/api/downtime-analysis/view?query_id=ABC123&granularity=month')
        assert resp.status_code == 400

    @patch('mes_dashboard.routes.downtime_analysis_routes.apply_view')
    def test_top_n_forwarded(self, mock_apply, client):
        mock_apply.return_value = _mock_view_result()
        client.get('/api/downtime-analysis/view?query_id=ABC123&top_n=5')
        assert mock_apply.call_args.kwargs['top_n'] == 5

    @patch('mes_dashboard.routes.downtime_analysis_routes.apply_view')
    def test_expired_spool_returns_410(self, mock_apply, client):
        mock_apply.return_value = None
        resp = client.get('/api/downtime-analysis/view?query_id=STALE')
        assert resp.status_code == 410

    def test_missing_query_id_returns_400(self, client):
        resp = client.get('/api/downtime-analysis/view')
        assert resp.status_code == 400


# ===========================================================================
# TestTopReasonsRoute — GET /view (top_n)
# ===========================================================================


class TestTopReasonsRoute:
    """top_n param is forwarded to apply_view."""

    @patch('mes_dashboard.routes.downtime_analysis_routes.apply_view')
    def test_top_n_default_is_10(self, mock_apply, client):
        mock_apply.return_value = _mock_view_result()
        client.get('/api/downtime-analysis/view?query_id=XYZ')
        assert mock_apply.call_args.kwargs['top_n'] == 10

    @patch('mes_dashboard.routes.downtime_analysis_routes.apply_view')
    def test_top_n_custom_forwarded(self, mock_apply, client):
        mock_apply.return_value = _mock_view_result()
        client.get('/api/downtime-analysis/view?query_id=XYZ&top_n=20')
        assert mock_apply.call_args.kwargs['top_n'] == 20


# ===========================================================================
# TestEquipmentDetailRoute — GET /equipment-detail
# ===========================================================================


class TestEquipmentDetailRoute:
    """GET /api/downtime-analysis/equipment-detail kwarg forwarding."""

    @patch('mes_dashboard.routes.downtime_analysis_routes.apply_view')
    @patch('mes_dashboard.routes.downtime_analysis_routes._get_resource_lookup_safe', return_value={})
    def test_query_id_forwarded(self, _mock_rl, mock_apply, client):
        mock_apply.return_value = {'equipment_detail': []}
        client.get('/api/downtime-analysis/equipment-detail?query_id=EQ-001')
        assert mock_apply.call_args.kwargs['query_id'] == 'EQ-001'

    @patch('mes_dashboard.routes.downtime_analysis_routes.apply_view')
    @patch('mes_dashboard.routes.downtime_analysis_routes._get_resource_lookup_safe', return_value={})
    def test_view_name_is_equipment_detail(self, _mock_rl, mock_apply, client):
        mock_apply.return_value = {'equipment_detail': []}
        client.get('/api/downtime-analysis/equipment-detail?query_id=EQ-001')
        assert mock_apply.call_args.kwargs['view_name'] == 'equipment_detail'

    @patch('mes_dashboard.routes.downtime_analysis_routes.apply_view')
    @patch('mes_dashboard.routes.downtime_analysis_routes._get_resource_lookup_safe', return_value={})
    def test_expired_returns_410(self, _mock_rl, mock_apply, client):
        mock_apply.return_value = None
        resp = client.get('/api/downtime-analysis/equipment-detail?query_id=STALE')
        assert resp.status_code == 410

    def test_missing_query_id_returns_400(self, client):
        resp = client.get('/api/downtime-analysis/equipment-detail')
        assert resp.status_code == 400


# ===========================================================================
# TestEventDetailRoute — GET /event-detail
# ===========================================================================


class TestEventDetailRoute:
    """GET /api/downtime-analysis/event-detail kwarg forwarding."""

    @patch('mes_dashboard.routes.downtime_analysis_routes.apply_view')
    @patch('mes_dashboard.routes.downtime_analysis_routes._get_resource_lookup_safe', return_value={})
    def test_query_id_forwarded(self, _mock_rl, mock_apply, client):
        mock_apply.return_value = {'events': [], 'pagination': {'page': 1, 'page_size': 50, 'total_rows': 0, 'total_pages': 0}}
        client.get('/api/downtime-analysis/event-detail?query_id=EV-001')
        assert mock_apply.call_args.kwargs['query_id'] == 'EV-001'

    @patch('mes_dashboard.routes.downtime_analysis_routes.apply_view')
    @patch('mes_dashboard.routes.downtime_analysis_routes._get_resource_lookup_safe', return_value={})
    def test_page_forwarded(self, _mock_rl, mock_apply, client):
        mock_apply.return_value = {'events': [], 'pagination': {'page': 2, 'page_size': 50, 'total_rows': 0, 'total_pages': 0}}
        client.get('/api/downtime-analysis/event-detail?query_id=EV-001&page=2')
        assert mock_apply.call_args.kwargs['page'] == 2

    @patch('mes_dashboard.routes.downtime_analysis_routes.apply_view')
    @patch('mes_dashboard.routes.downtime_analysis_routes._get_resource_lookup_safe', return_value={})
    def test_page_size_forwarded(self, _mock_rl, mock_apply, client):
        mock_apply.return_value = {'events': [], 'pagination': {'page': 1, 'page_size': 100, 'total_rows': 0, 'total_pages': 0}}
        client.get('/api/downtime-analysis/event-detail?query_id=EV-001&page_size=100')
        assert mock_apply.call_args.kwargs['page_size'] == 100

    @patch('mes_dashboard.routes.downtime_analysis_routes.apply_view')
    @patch('mes_dashboard.routes.downtime_analysis_routes._get_resource_lookup_safe', return_value={})
    def test_view_name_is_event_detail(self, _mock_rl, mock_apply, client):
        mock_apply.return_value = {'events': [], 'pagination': {'page': 1, 'page_size': 50, 'total_rows': 0, 'total_pages': 0}}
        client.get('/api/downtime-analysis/event-detail?query_id=EV-001')
        assert mock_apply.call_args.kwargs['view_name'] == 'event_detail'

    @patch('mes_dashboard.routes.downtime_analysis_routes.apply_view')
    @patch('mes_dashboard.routes.downtime_analysis_routes._get_resource_lookup_safe', return_value={})
    def test_expired_returns_410(self, _mock_rl, mock_apply, client):
        mock_apply.return_value = None
        resp = client.get('/api/downtime-analysis/event-detail?query_id=STALE')
        assert resp.status_code == 410

    def test_missing_query_id_returns_400(self, client):
        resp = client.get('/api/downtime-analysis/event-detail')
        assert resp.status_code == 400

    @patch('mes_dashboard.routes.downtime_analysis_routes.apply_view')
    @patch('mes_dashboard.routes.downtime_analysis_routes._get_resource_lookup_safe', return_value={})
    def test_page_size_capped_at_200(self, _mock_rl, mock_apply, client):
        """page_size > 200 is silently capped at 200."""
        mock_apply.return_value = {'events': [], 'pagination': {}}
        client.get('/api/downtime-analysis/event-detail?query_id=EV-001&page_size=999')
        assert mock_apply.call_args.kwargs['page_size'] == 200


# ===========================================================================
# TestEquipmentDetailRoute extensions — new filter params (IP-3)
# ===========================================================================

# NOTE: These are additional methods for the existing TestEquipmentDetailRoute.
# They are placed in a separate class below because the existing class is
# fully read-only (the tests above cover query_id, view_name, expired, missing).
# We extend via a new parallel class TestEquipmentDetailFilterRoute.


class TestEquipmentDetailFilterRoute:
    """Per-kwarg forwarding for the three new filter params on equipment-detail."""

    @patch('mes_dashboard.routes.downtime_analysis_routes.apply_view')
    @patch('mes_dashboard.routes.downtime_analysis_routes._get_resource_lookup_safe', return_value={})
    def test_big_category_forwarded(self, _mock_rl, mock_apply, client):
        """?big_category=維修 must be forwarded to apply_view."""
        mock_apply.return_value = {'equipment_detail': [], 'pagination': {'page': 1, 'page_size': 20, 'total_rows': 0, 'total_pages': 0}}
        client.get('/api/downtime-analysis/equipment-detail?query_id=EQ-001&big_category=維修')
        mock_apply.assert_called_once()
        assert mock_apply.call_args.kwargs['big_category'] == '維修'

    @patch('mes_dashboard.routes.downtime_analysis_routes.apply_view')
    @patch('mes_dashboard.routes.downtime_analysis_routes._get_resource_lookup_safe', return_value={})
    def test_status_types_csv_forwarded(self, _mock_rl, mock_apply, client):
        """?status_types=UDT,SDT must be parsed by _csv_param and forwarded as list."""
        mock_apply.return_value = {'equipment_detail': [], 'pagination': {'page': 1, 'page_size': 20, 'total_rows': 0, 'total_pages': 0}}
        client.get('/api/downtime-analysis/equipment-detail?query_id=EQ-001&status_types=UDT,SDT')
        mock_apply.assert_called_once()
        assert mock_apply.call_args.kwargs['status_types'] == ['UDT', 'SDT']

    @patch('mes_dashboard.routes.downtime_analysis_routes.apply_view')
    @patch('mes_dashboard.routes.downtime_analysis_routes._get_resource_lookup_safe', return_value={})
    def test_resource_id_forwarded(self, _mock_rl, mock_apply, client):
        """?resource_id=HIST-007 must be forwarded to apply_view."""
        mock_apply.return_value = {'equipment_detail': [], 'pagination': {'page': 1, 'page_size': 20, 'total_rows': 0, 'total_pages': 0}}
        client.get('/api/downtime-analysis/equipment-detail?query_id=EQ-001&resource_id=HIST-007')
        mock_apply.assert_called_once()
        assert mock_apply.call_args.kwargs['resource_id'] == 'HIST-007'

    @patch('mes_dashboard.routes.downtime_analysis_routes.apply_view')
    @patch('mes_dashboard.routes.downtime_analysis_routes._get_resource_lookup_safe', return_value={})
    def test_omit_filter_params_calls_service_without_filter_kwargs(self, _mock_rl, mock_apply, client):
        """Omitting all filter params must forward None for each filter kwarg."""
        mock_apply.return_value = {'equipment_detail': [], 'pagination': {'page': 1, 'page_size': 20, 'total_rows': 0, 'total_pages': 0}}
        client.get('/api/downtime-analysis/equipment-detail?query_id=EQ-001')
        mock_apply.assert_called_once()
        assert mock_apply.call_args.kwargs.get('big_category') is None
        assert mock_apply.call_args.kwargs.get('status_types') is None
        assert mock_apply.call_args.kwargs.get('resource_id') is None

    @patch('mes_dashboard.routes.downtime_analysis_routes.apply_view')
    @patch('mes_dashboard.routes.downtime_analysis_routes._get_resource_lookup_safe', return_value={})
    def test_page_size_cap_raised_to_1000(self, _mock_rl, mock_apply, client):
        """page_size=1000 must be accepted (cap raised from 200 to 1000 per DQ-2)."""
        mock_apply.return_value = {'equipment_detail': [], 'pagination': {'page': 1, 'page_size': 1000, 'total_rows': 0, 'total_pages': 0}}
        client.get('/api/downtime-analysis/equipment-detail?query_id=EQ-001&page_size=1000')
        mock_apply.assert_called_once()
        assert mock_apply.call_args.kwargs['page_size'] == 1000


# ===========================================================================
# TestEventDetailFilterRoute — new filter params on event-detail (IP-3)
# ===========================================================================


class TestEventDetailFilterRoute:
    """Per-kwarg forwarding for the three new filter params on event-detail."""

    @patch('mes_dashboard.routes.downtime_analysis_routes.apply_view')
    @patch('mes_dashboard.routes.downtime_analysis_routes._get_resource_lookup_safe', return_value={})
    def test_big_category_forwarded(self, _mock_rl, mock_apply, client):
        """?big_category=維修 must be forwarded to apply_view."""
        mock_apply.return_value = {'events': [], 'pagination': {'page': 1, 'page_size': 20, 'total_rows': 0, 'total_pages': 0}}
        client.get('/api/downtime-analysis/event-detail?query_id=EV-001&big_category=維修')
        mock_apply.assert_called_once()
        assert mock_apply.call_args.kwargs['big_category'] == '維修'

    @patch('mes_dashboard.routes.downtime_analysis_routes.apply_view')
    @patch('mes_dashboard.routes.downtime_analysis_routes._get_resource_lookup_safe', return_value={})
    def test_status_types_csv_forwarded(self, _mock_rl, mock_apply, client):
        """?status_types=UDT,SDT must be parsed by _csv_param and forwarded as list."""
        mock_apply.return_value = {'events': [], 'pagination': {'page': 1, 'page_size': 20, 'total_rows': 0, 'total_pages': 0}}
        client.get('/api/downtime-analysis/event-detail?query_id=EV-001&status_types=UDT,SDT')
        mock_apply.assert_called_once()
        assert mock_apply.call_args.kwargs['status_types'] == ['UDT', 'SDT']

    @patch('mes_dashboard.routes.downtime_analysis_routes.apply_view')
    @patch('mes_dashboard.routes.downtime_analysis_routes._get_resource_lookup_safe', return_value={})
    def test_resource_id_forwarded(self, _mock_rl, mock_apply, client):
        """?resource_id=HIST-001 must be forwarded to apply_view."""
        mock_apply.return_value = {'events': [], 'pagination': {'page': 1, 'page_size': 20, 'total_rows': 0, 'total_pages': 0}}
        client.get('/api/downtime-analysis/event-detail?query_id=EV-001&resource_id=HIST-001')
        mock_apply.assert_called_once()
        assert mock_apply.call_args.kwargs['resource_id'] == 'HIST-001'


# ===========================================================================
# TestFilterDataBoundary — boundary/edge cases for filter params (IP-3)
# ===========================================================================


class TestFilterDataBoundary:
    """Boundary tests: empty/missing/invalid filter params must return 200 (not 500)."""

    @patch('mes_dashboard.routes.downtime_analysis_routes.apply_view')
    @patch('mes_dashboard.routes.downtime_analysis_routes._get_resource_lookup_safe', return_value={})
    def test_equipment_detail_empty_big_category_returns_200(self, _mock_rl, mock_apply, client):
        """?big_category= (empty string) must return 200 with no filter applied."""
        mock_apply.return_value = {'equipment_detail': [], 'pagination': {'page': 1, 'page_size': 20, 'total_rows': 0, 'total_pages': 0}}
        resp = client.get('/api/downtime-analysis/equipment-detail?query_id=EQ-001&big_category=')
        assert resp.status_code == 200
        mock_apply.assert_called_once()
        # Empty string must forward as None (no filter)
        assert mock_apply.call_args.kwargs.get('big_category') is None

    @patch('mes_dashboard.routes.downtime_analysis_routes.apply_view')
    @patch('mes_dashboard.routes.downtime_analysis_routes._get_resource_lookup_safe', return_value={})
    def test_equipment_detail_invalid_status_types_returns_200(self, _mock_rl, mock_apply, client):
        """?status_types=INVALID must return 200; unknown status yields empty-but-valid result."""
        mock_apply.return_value = {'equipment_detail': [], 'pagination': {'page': 1, 'page_size': 20, 'total_rows': 0, 'total_pages': 0}}
        resp = client.get('/api/downtime-analysis/equipment-detail?query_id=EQ-001&status_types=INVALID')
        assert resp.status_code == 200
        mock_apply.assert_called_once()
        # Forwarded as-is; service handles unknown status gracefully
        assert mock_apply.call_args.kwargs['status_types'] == ['INVALID']

    @patch('mes_dashboard.routes.downtime_analysis_routes.apply_view')
    @patch('mes_dashboard.routes.downtime_analysis_routes._get_resource_lookup_safe', return_value={})
    def test_event_detail_missing_resource_id_returns_200(self, _mock_rl, mock_apply, client):
        """Omitting resource_id entirely must return 200 with no filter applied."""
        mock_apply.return_value = {'events': [], 'pagination': {'page': 1, 'page_size': 20, 'total_rows': 0, 'total_pages': 0}}
        resp = client.get('/api/downtime-analysis/event-detail?query_id=EV-001')
        assert resp.status_code == 200
        mock_apply.assert_called_once()
        assert mock_apply.call_args.kwargs.get('resource_id') is None

    @patch('mes_dashboard.routes.downtime_analysis_routes.apply_view')
    @patch('mes_dashboard.routes.downtime_analysis_routes._get_resource_lookup_safe', return_value={})
    def test_equipment_detail_response_has_equipment_detail_key(self, _mock_rl, mock_apply, client):
        """equipment-detail response wrapper key must be 'equipment_detail' (AC-5)."""
        mock_apply.return_value = {
            'equipment_detail': [{'resource_id': 'R1'}],
            'pagination': {'page': 1, 'page_size': 20, 'total_rows': 1, 'total_pages': 1},
        }
        resp = client.get('/api/downtime-analysis/equipment-detail?query_id=EQ-001')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'equipment_detail' in data['data']

    @patch('mes_dashboard.routes.downtime_analysis_routes.apply_view')
    @patch('mes_dashboard.routes.downtime_analysis_routes._get_resource_lookup_safe', return_value={})
    def test_event_detail_response_has_events_key(self, _mock_rl, mock_apply, client):
        """event-detail response wrapper key must be 'events' (AC-8)."""
        mock_apply.return_value = {
            'events': [{'event_id': 'E1'}],
            'pagination': {'page': 1, 'page_size': 20, 'total_rows': 1, 'total_pages': 1},
        }
        resp = client.get('/api/downtime-analysis/event-detail?query_id=EV-001')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'events' in data['data']


# ===========================================================================
# TestQueryRoute — POST /query — new browser-DuckDB response shape (AC-1, AC-6)
# ===========================================================================


def _mock_raw_result(query_id='raw-qid'):
    """Mock return value for query_downtime_dataset_raw (flag-on path)."""
    return {
        'base_spool_url': f'/api/spool/downtime_analysis_base_events/{query_id}.parquet',
        'jobs_spool_url': f'/api/spool/downtime_analysis_job_bridge/{query_id}.parquet',
        'query_id': query_id,
        'taxonomy': {
            'map': [['EE Repair', '維修']],
            'prefixes': [['TMTT_', '檢查']],
            'egt_category': '工程',
            'fallback': '其他/未分類',
        },
    }


class TestQueryRoute:
    """POST /api/downtime-analysis/query — new response shape (flag ON).

    AC-1: four keys present and non-null.
    AC-6: 90-day limit removed; >90d range accepted.
    """

    @patch('mes_dashboard.services.downtime_analysis_service.query_downtime_dataset_raw')
    def test_response_shape_has_all_four_keys(self, mock_raw, client, monkeypatch):
        """Flag-on: response must have base_spool_url, jobs_spool_url, query_id, taxonomy."""
        monkeypatch.setattr(
            'mes_dashboard.routes.downtime_analysis_routes._BROWSER_DUCKDB_ENABLED', True
        )
        mock_raw.return_value = _mock_raw_result()
        # Patch at route-module level (the name imported into the route module)
        with patch('mes_dashboard.routes.downtime_analysis_routes.query_downtime_dataset_raw',
                   return_value=_mock_raw_result()):
            resp = client.post('/api/downtime-analysis/query',
                               json={'start_date': '2026-04-01', 'end_date': '2026-04-30'})
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert 'base_spool_url' in data
        assert 'jobs_spool_url' in data
        assert 'query_id' in data
        assert 'taxonomy' in data

    @patch('mes_dashboard.routes.downtime_analysis_routes.query_downtime_dataset_raw')
    def test_base_spool_url_non_null(self, mock_raw, client, monkeypatch):
        monkeypatch.setattr(
            'mes_dashboard.routes.downtime_analysis_routes._BROWSER_DUCKDB_ENABLED', True
        )
        mock_raw.return_value = _mock_raw_result()
        resp = client.post('/api/downtime-analysis/query',
                           json={'start_date': '2026-04-01', 'end_date': '2026-04-30'})
        assert resp.status_code == 200
        assert resp.get_json()['data']['base_spool_url'] is not None

    @patch('mes_dashboard.routes.downtime_analysis_routes.query_downtime_dataset_raw')
    def test_jobs_spool_url_non_null(self, mock_raw, client, monkeypatch):
        monkeypatch.setattr(
            'mes_dashboard.routes.downtime_analysis_routes._BROWSER_DUCKDB_ENABLED', True
        )
        mock_raw.return_value = _mock_raw_result()
        resp = client.post('/api/downtime-analysis/query',
                           json={'start_date': '2026-04-01', 'end_date': '2026-04-30'})
        assert resp.status_code == 200
        assert resp.get_json()['data']['jobs_spool_url'] is not None

    @patch('mes_dashboard.routes.downtime_analysis_routes.query_downtime_dataset_raw')
    def test_query_id_non_null(self, mock_raw, client, monkeypatch):
        monkeypatch.setattr(
            'mes_dashboard.routes.downtime_analysis_routes._BROWSER_DUCKDB_ENABLED', True
        )
        mock_raw.return_value = _mock_raw_result()
        resp = client.post('/api/downtime-analysis/query',
                           json={'start_date': '2026-04-01', 'end_date': '2026-04-30'})
        assert resp.status_code == 200
        assert resp.get_json()['data']['query_id'] is not None

    @patch('mes_dashboard.routes.downtime_analysis_routes.query_downtime_dataset_raw')
    def test_taxonomy_non_null(self, mock_raw, client, monkeypatch):
        monkeypatch.setattr(
            'mes_dashboard.routes.downtime_analysis_routes._BROWSER_DUCKDB_ENABLED', True
        )
        mock_raw.return_value = _mock_raw_result()
        resp = client.post('/api/downtime-analysis/query',
                           json={'start_date': '2026-04-01', 'end_date': '2026-04-30'})
        assert resp.status_code == 200
        assert resp.get_json()['data']['taxonomy'] is not None

    @patch('mes_dashboard.routes.downtime_analysis_routes.query_downtime_dataset_raw')
    def test_legacy_keys_absent_when_flag_on(self, mock_raw, client, monkeypatch):
        """Flag-on: summary/daily_trend/big_category/top_reasons must NOT be in data."""
        monkeypatch.setattr(
            'mes_dashboard.routes.downtime_analysis_routes._BROWSER_DUCKDB_ENABLED', True
        )
        mock_raw.return_value = _mock_raw_result()
        resp = client.post('/api/downtime-analysis/query',
                           json={'start_date': '2026-04-01', 'end_date': '2026-04-30'})
        assert resp.status_code == 200
        data = resp.get_json()['data']
        for legacy_key in ('summary', 'daily_trend', 'big_category', 'top_reasons'):
            assert legacy_key not in data, f"Legacy key '{legacy_key}' must not appear in flag-on response"

    @patch('mes_dashboard.routes.downtime_analysis_routes.query_downtime_dataset')
    def test_feature_flag_off_returns_legacy_shape(self, mock_svc, client, monkeypatch):
        """Flag-off: legacy {query_id, summary, daily_trend, big_category, top_reasons} returned."""
        monkeypatch.setattr(
            'mes_dashboard.routes.downtime_analysis_routes._BROWSER_DUCKDB_ENABLED', False
        )
        mock_svc.return_value = _mock_query_result()
        resp = client.post('/api/downtime-analysis/query',
                           json={'start_date': '2026-04-01', 'end_date': '2026-04-30'})
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert 'query_id' in data
        assert 'summary' in data

    def test_range_over_90_days_returns_200_not_400(self, client, monkeypatch):
        """AC-6: date range > 90 days must be accepted (no _MAX_ORACLE_DAYS guard)."""
        monkeypatch.setattr(
            'mes_dashboard.routes.downtime_analysis_routes._BROWSER_DUCKDB_ENABLED', True
        )
        with patch('mes_dashboard.routes.downtime_analysis_routes.query_downtime_dataset_raw',
                   return_value=_mock_raw_result()):
            resp = client.post('/api/downtime-analysis/query',
                               json={'start_date': '2025-12-15', 'end_date': '2026-06-12'})
        # 179 days — should pass (only 730d cap remains)
        assert resp.status_code == 200

    def test_range_over_730_days_still_returns_400(self, client):
        """SYS-04 730-day hard cap must remain in place."""
        resp = client.post('/api/downtime-analysis/query',
                           json={'start_date': '2024-01-01', 'end_date': '2026-06-12'})
        assert resp.status_code == 400

    # --- per-kwarg forwarding tests for flag-on path ---

    @patch('mes_dashboard.routes.downtime_analysis_routes.query_downtime_dataset_raw')
    def test_start_date_forwarded_flag_on(self, mock_raw, client, monkeypatch):
        monkeypatch.setattr(
            'mes_dashboard.routes.downtime_analysis_routes._BROWSER_DUCKDB_ENABLED', True
        )
        mock_raw.return_value = _mock_raw_result()
        client.post('/api/downtime-analysis/query',
                    json={'start_date': '2026-01-01', 'end_date': '2026-04-30'})
        mock_raw.assert_called_once()
        assert mock_raw.call_args.kwargs['start_date'] == '2026-01-01'

    @patch('mes_dashboard.routes.downtime_analysis_routes.query_downtime_dataset_raw')
    def test_workcenter_groups_forwarded_flag_on(self, mock_raw, client, monkeypatch):
        monkeypatch.setattr(
            'mes_dashboard.routes.downtime_analysis_routes._BROWSER_DUCKDB_ENABLED', True
        )
        mock_raw.return_value = _mock_raw_result()
        client.post('/api/downtime-analysis/query',
                    json={'start_date': '2026-04-01', 'end_date': '2026-04-30',
                          'workcenter_groups': ['WC_TEST']})
        mock_raw.assert_called_once()
        assert mock_raw.call_args.kwargs['workcenter_groups'] == ['WC_TEST']

    @patch('mes_dashboard.routes.downtime_analysis_routes.query_downtime_dataset_raw')
    def test_resource_ids_forwarded_flag_on(self, mock_raw, client, monkeypatch):
        monkeypatch.setattr(
            'mes_dashboard.routes.downtime_analysis_routes._BROWSER_DUCKDB_ENABLED', True
        )
        mock_raw.return_value = _mock_raw_result()
        client.post('/api/downtime-analysis/query',
                    json={'start_date': '2026-04-01', 'end_date': '2026-04-30',
                          'resource_ids': ['R-42']})
        mock_raw.assert_called_once()
        assert mock_raw.call_args.kwargs['resource_ids'] == ['R-42']


class TestQueryRouteContract:
    """Contract-level assertions: response shape conforms to api-contract v1.15.0 (AC-1)."""

    @patch('mes_dashboard.routes.downtime_analysis_routes.query_downtime_dataset_raw')
    def test_response_shape_conforms_to_api_contract_v1_15(self, mock_raw, client, monkeypatch):
        """All four top-level keys present; taxonomy has map/prefixes/egt_category/fallback."""
        monkeypatch.setattr(
            'mes_dashboard.routes.downtime_analysis_routes._BROWSER_DUCKDB_ENABLED', True
        )
        mock_raw.return_value = _mock_raw_result()
        resp = client.post('/api/downtime-analysis/query',
                           json={'start_date': '2026-04-01', 'end_date': '2026-04-30'})
        assert resp.status_code == 200
        data = resp.get_json()['data']
        # Four required top-level keys
        for key in ('base_spool_url', 'jobs_spool_url', 'query_id', 'taxonomy'):
            assert key in data, f"Missing required key: {key}"
        # Taxonomy shape
        taxonomy = data['taxonomy']
        for tkey in ('map', 'prefixes', 'egt_category', 'fallback'):
            assert tkey in taxonomy, f"taxonomy missing key: {tkey}"
        assert taxonomy['egt_category'] == '工程'
        assert taxonomy['fallback'] == '其他/未分類'


# ===========================================================================
# TestMaxOracleDaysRemoved — AC-6: _MAX_ORACLE_DAYS constant must be absent
# ===========================================================================


class TestMaxOracleDaysRemoved:
    """AC-6: _MAX_ORACLE_DAYS and its guard in _validate_dates must be gone."""

    def test_max_oracle_days_constant_absent(self):
        """_MAX_ORACLE_DAYS must NOT exist on the routes module (AC-6)."""
        import mes_dashboard.routes.downtime_analysis_routes as routes_mod
        assert not hasattr(routes_mod, '_MAX_ORACLE_DAYS'), (
            "_MAX_ORACLE_DAYS must be removed from downtime_analysis_routes (AC-6)"
        )

    def test_validate_dates_accepts_180_days(self):
        """_validate_dates must accept 180-day range without raising ValueError."""
        from mes_dashboard.routes.downtime_analysis_routes import _validate_dates
        # Should not raise — only the 730-day cap remains
        _validate_dates('2025-12-15', '2026-06-12')  # 179 days

    def test_validate_dates_accepts_91_days_oracle_path(self):
        """Dates older than 3 months and >90 days must no longer be rejected."""
        from mes_dashboard.routes.downtime_analysis_routes import _validate_dates
        # Historical range that previously triggered _MAX_ORACLE_DAYS guard
        _validate_dates('2025-01-01', '2025-06-30')  # 179 days, historical = Oracle path

    def test_duckdb_window_days_constant_absent(self):
        """_DUCKDB_WINDOW_DAYS must also be removed (only needed for _MAX_ORACLE_DAYS check)."""
        import mes_dashboard.routes.downtime_analysis_routes as routes_mod
        assert not hasattr(routes_mod, '_DUCKDB_WINDOW_DAYS'), (
            "_DUCKDB_WINDOW_DAYS must be removed from downtime_analysis_routes"
        )


# ===========================================================================
# TestDowntimeAsyncQuery — AC-1/2a/2b/2c/AC-7 async gate tests
# ===========================================================================


class TestDowntimeAsyncQuery:
    """Tests for the async RQ branch in POST /api/downtime-analysis/query.

    Uses monkeypatch.setattr on module-level constants (frozen at import).
    """

    def test_long_range_returns_202(self, client, monkeypatch):
        """AC-1: long range + flag=true + worker available → 202 with async/job_id/status_url."""
        import mes_dashboard.routes.downtime_analysis_routes as routes_mod
        monkeypatch.setattr(routes_mod, '_BROWSER_DUCKDB_ENABLED', True)
        monkeypatch.setattr(routes_mod, '_ASYNC_ENABLED', True)
        monkeypatch.setattr(routes_mod, '_ASYNC_DAY_THRESHOLD', 30)

        with patch('mes_dashboard.routes.downtime_analysis_routes.is_async_available',
                   return_value=True), \
             patch('mes_dashboard.routes.downtime_analysis_routes.enqueue_job_dynamic',
                   return_value=('downtime-abc123', None)), \
             patch('mes_dashboard.routes.downtime_analysis_routes.get_owner_token',
                   return_value='test-owner'):
            resp = client.post('/api/downtime-analysis/query',
                               json={'start_date': '2026-01-01', 'end_date': '2026-04-30'})

        assert resp.status_code == 202
        data = resp.get_json()['data']
        assert data['async'] is True
        assert data['job_id'] == 'downtime-abc123'
        assert 'status_url' in data

    def test_short_range_returns_200(self, client, monkeypatch):
        """AC-2a: date range < threshold → 200 sync path unchanged."""
        import mes_dashboard.routes.downtime_analysis_routes as routes_mod
        monkeypatch.setattr(routes_mod, '_BROWSER_DUCKDB_ENABLED', True)
        monkeypatch.setattr(routes_mod, '_ASYNC_ENABLED', True)
        monkeypatch.setattr(routes_mod, '_ASYNC_DAY_THRESHOLD', 30)

        with patch('mes_dashboard.routes.downtime_analysis_routes.query_downtime_dataset_raw',
                   return_value=_mock_raw_result()):
            # 28 days — below threshold
            resp = client.post('/api/downtime-analysis/query',
                               json={'start_date': '2026-04-01', 'end_date': '2026-04-29'})

        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert 'query_id' in data
        assert data.get('async') is not True

    def test_flag_disabled_returns_200(self, client, monkeypatch):
        """AC-2b: DOWNTIME_ASYNC_ENABLED=false → 200 sync regardless of range."""
        import mes_dashboard.routes.downtime_analysis_routes as routes_mod
        monkeypatch.setattr(routes_mod, '_BROWSER_DUCKDB_ENABLED', True)
        monkeypatch.setattr(routes_mod, '_ASYNC_ENABLED', False)
        monkeypatch.setattr(routes_mod, '_ASYNC_DAY_THRESHOLD', 30)

        with patch('mes_dashboard.routes.downtime_analysis_routes.query_downtime_dataset_raw',
                   return_value=_mock_raw_result()):
            # 119 days — above threshold, but flag disabled
            resp = client.post('/api/downtime-analysis/query',
                               json={'start_date': '2026-01-01', 'end_date': '2026-04-30'})

        assert resp.status_code == 200
        assert resp.get_json()['data'].get('async') is not True

    def test_worker_unavailable_falls_back_to_200(self, client, monkeypatch):
        """AC-2c: is_async_available()=False → 200 sync fallback."""
        import mes_dashboard.routes.downtime_analysis_routes as routes_mod
        monkeypatch.setattr(routes_mod, '_BROWSER_DUCKDB_ENABLED', True)
        monkeypatch.setattr(routes_mod, '_ASYNC_ENABLED', True)
        monkeypatch.setattr(routes_mod, '_ASYNC_DAY_THRESHOLD', 30)

        with patch('mes_dashboard.routes.downtime_analysis_routes.is_async_available',
                   return_value=False), \
             patch('mes_dashboard.routes.downtime_analysis_routes.query_downtime_dataset_raw',
                   return_value=_mock_raw_result()):
            resp = client.post('/api/downtime-analysis/query',
                               json={'start_date': '2026-01-01', 'end_date': '2026-04-30'})

        assert resp.status_code == 200
        assert resp.get_json()['data'].get('async') is not True

    def test_status_url_contains_prefix_downtime(self, client, monkeypatch):
        """AC-7: status_url must be /api/job/<job_id>?prefix=downtime."""
        import mes_dashboard.routes.downtime_analysis_routes as routes_mod
        monkeypatch.setattr(routes_mod, '_BROWSER_DUCKDB_ENABLED', True)
        monkeypatch.setattr(routes_mod, '_ASYNC_ENABLED', True)
        monkeypatch.setattr(routes_mod, '_ASYNC_DAY_THRESHOLD', 30)

        with patch('mes_dashboard.routes.downtime_analysis_routes.is_async_available',
                   return_value=True), \
             patch('mes_dashboard.routes.downtime_analysis_routes.enqueue_job_dynamic',
                   return_value=('downtime-xyz789', None)), \
             patch('mes_dashboard.routes.downtime_analysis_routes.get_owner_token',
                   return_value='test-owner'):
            resp = client.post('/api/downtime-analysis/query',
                               json={'start_date': '2026-01-01', 'end_date': '2026-04-30'})

        assert resp.status_code == 202
        status_url = resp.get_json()['data']['status_url']
        assert 'prefix=downtime' in status_url
        assert 'downtime-xyz789' in status_url


# ===========================================================================
# TestDowntimeJobDispatch — AC-7a job-type registration test
# ===========================================================================


class TestDowntimeJobDispatch:
    """AC-7a: register_job_type('downtime', ...) must fire on import."""

    def test_job_type_registered(self, monkeypatch):
        """importing downtime_query_job_service must register 'downtime' in the registry.

        Uses importlib.reload() after clearing the registry dict so that the
        module-level register_job_type() side effect re-runs (setattr alone
        does not re-execute the call).
        """
        import importlib

        from mes_dashboard.services.job_registry import _REGISTRY
        # Clear the registry to ensure a clean state
        _REGISTRY.clear()

        # Reload the job service module — this re-executes the module-level
        # register_job_type() call at the bottom of the file.
        import mes_dashboard.services.downtime_query_job_service as job_svc
        importlib.reload(job_svc)

        from mes_dashboard.services.job_registry import list_registered_job_types
        assert "downtime" in list_registered_job_types(), (
            "register_job_type('downtime', ...) must run when downtime_query_job_service is imported"
        )
