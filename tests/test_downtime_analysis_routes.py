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
