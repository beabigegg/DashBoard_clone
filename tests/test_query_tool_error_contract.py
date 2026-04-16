# -*- coding: utf-8 -*-
"""Error-contract integration tests for all 7 Query Tool route handlers.

For each handler, verify that:
  - UserInputError   → 400 + VALIDATION_ERROR
  - ResourceNotFoundError → 404 + NOT_FOUND
  - QueryTimeoutError → 504 + QUERY_TIMEOUT
  - DataContractError → 500 + INTERNAL_ERROR
  - InternalQueryError → 500 + INTERNAL_ERROR
  - bare RuntimeError → 500 + INTERNAL_ERROR
  - normal payload    → 200 with data intact
"""

import pytest
from unittest.mock import patch

from mes_dashboard.core.cache import NoOpCache
from mes_dashboard.core.rate_limit import reset_rate_limits_for_tests
from mes_dashboard.core.exceptions import (
    UserInputError,
    ResourceNotFoundError,
    QueryTimeoutError,
    DataContractError,
    InternalQueryError,
)
from mes_dashboard.core.response import (
    VALIDATION_ERROR,
    NOT_FOUND,
    QUERY_TIMEOUT,
    INTERNAL_ERROR,
)


@pytest.fixture
def app():
    from mes_dashboard import create_app
    app = create_app()
    app.config['TESTING'] = True
    app.extensions["cache"] = NoOpCache()
    return app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture(autouse=True)
def _reset_rl():
    reset_rate_limits_for_tests()
    yield
    reset_rate_limits_for_tests()


def _assert_error(response, expected_status, expected_code):
    assert response.status_code == expected_status
    body = response.get_json()
    assert body["success"] is False
    assert body["error"]["code"] == expected_code


# ──────────────────────────────────────────────────────────────────────────────
# Helper: exception parametrise matrix
# ──────────────────────────────────────────────────────────────────────────────

_EXC_CASES = [
    (UserInputError("bad input"),                           400, VALIDATION_ERROR),
    (ResourceNotFoundError("not found"),                    404, NOT_FOUND),
    (QueryTimeoutError("timeout"),                          504, QUERY_TIMEOUT),
    (DataContractError("schema drift"),                     500, INTERNAL_ERROR),
    (InternalQueryError("db error", cause=ValueError("x")), 500, INTERNAL_ERROR),
    (RuntimeError("unexpected"),                            500, INTERNAL_ERROR),
]


# ──────────────────────────────────────────────────────────────────────────────
# 1. resolve_lot_input  (/api/query-tool/resolve)
# ──────────────────────────────────────────────────────────────────────────────

class TestResolveErrorContract:

    @pytest.mark.parametrize("exc,status,code", _EXC_CASES)
    @patch('mes_dashboard.routes.query_tool_routes.resolve_lots')
    def test_resolve_exc_contract(self, mock_svc, exc, status, code, client):
        mock_svc.side_effect = exc
        resp = client.post(
            '/api/query-tool/resolve',
            json={'input_type': 'lot_id', 'values': ['LOT-1']},
        )
        _assert_error(resp, status, code)

    @patch('mes_dashboard.routes.query_tool_routes.resolve_lots')
    def test_resolve_success(self, mock_svc, client):
        mock_svc.return_value = {'data': [], 'total': 0, 'input_count': 1, 'not_found': []}
        resp = client.post(
            '/api/query-tool/resolve',
            json={'input_type': 'lot_id', 'values': ['LOT-1']},
        )
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True


# ──────────────────────────────────────────────────────────────────────────────
# 2. query_lot_history  (/api/query-tool/lot-history)
# ──────────────────────────────────────────────────────────────────────────────

class TestLotHistoryErrorContract:

    @pytest.mark.parametrize("exc,status,code", _EXC_CASES)
    @patch('mes_dashboard.routes.query_tool_routes.get_lot_history')
    def test_lot_history_exc_contract(self, mock_svc, exc, status, code, client):
        mock_svc.side_effect = exc
        resp = client.get('/api/query-tool/lot-history?container_id=abc123')
        _assert_error(resp, status, code)

    @patch('mes_dashboard.routes.query_tool_routes.get_lot_history')
    def test_lot_history_success(self, mock_svc, client):
        mock_svc.return_value = {'data': [{'CONTAINERID': 'abc123'}], 'total': 1}
        resp = client.get('/api/query-tool/lot-history?container_id=abc123')
        assert resp.status_code == 200


# ──────────────────────────────────────────────────────────────────────────────
# 3. query_adjacent_lots  (/api/query-tool/adjacent-lots)
# ──────────────────────────────────────────────────────────────────────────────

class TestAdjacentLotsErrorContract:

    @pytest.mark.parametrize("exc,status,code", _EXC_CASES)
    @patch('mes_dashboard.routes.query_tool_routes.get_adjacent_lots')
    def test_adjacent_lots_exc_contract(self, mock_svc, exc, status, code, client):
        mock_svc.side_effect = exc
        resp = client.get(
            '/api/query-tool/adjacent-lots?equipment_id=EQ1&target_time=2024-01-01T00:00:00'
        )
        _assert_error(resp, status, code)

    @patch('mes_dashboard.routes.query_tool_routes.get_adjacent_lots')
    def test_adjacent_lots_success(self, mock_svc, client):
        mock_svc.return_value = {'data': [], 'total': 0}
        resp = client.get(
            '/api/query-tool/adjacent-lots?equipment_id=EQ1&target_time=2024-01-01T00:00:00'
        )
        assert resp.status_code == 200


# ──────────────────────────────────────────────────────────────────────────────
# 4. query_lot_associations  (/api/query-tool/lot-associations)
# ──────────────────────────────────────────────────────────────────────────────

class TestLotAssociationsErrorContract:

    @pytest.mark.parametrize("exc,status,code", _EXC_CASES)
    @patch('mes_dashboard.routes.query_tool_routes.get_lot_materials')
    def test_lot_associations_exc_contract(self, mock_svc, exc, status, code, client):
        mock_svc.side_effect = exc
        resp = client.get('/api/query-tool/lot-associations?container_id=abc123&type=materials')
        _assert_error(resp, status, code)

    @patch('mes_dashboard.routes.query_tool_routes.get_lot_materials')
    def test_lot_associations_success(self, mock_svc, client):
        mock_svc.return_value = {'data': [], 'total': 0}
        resp = client.get('/api/query-tool/lot-associations?container_id=abc123&type=materials')
        assert resp.status_code == 200


# ──────────────────────────────────────────────────────────────────────────────
# 5. query_equipment_period  (/api/query-tool/equipment-period)
# ──────────────────────────────────────────────────────────────────────────────

class TestEquipmentPeriodErrorContract:

    @pytest.mark.parametrize("exc,status,code", _EXC_CASES)
    @patch('mes_dashboard.routes.query_tool_routes.get_equipment_status_hours')
    def test_equipment_period_exc_contract(self, mock_svc, exc, status, code, client):
        mock_svc.side_effect = exc
        resp = client.post(
            '/api/query-tool/equipment-period',
            json={
                'equipment_ids': ['EQ1'],
                'start_date': '2024-01-01',
                'end_date': '2024-01-31',
                'query_type': 'status_hours',
            },
        )
        _assert_error(resp, status, code)

    @patch('mes_dashboard.routes.query_tool_routes.get_equipment_status_hours')
    def test_equipment_period_success(self, mock_svc, client):
        mock_svc.return_value = {'data': [], 'total': 0}
        resp = client.post(
            '/api/query-tool/equipment-period',
            json={
                'equipment_ids': ['EQ1'],
                'start_date': '2024-01-01',
                'end_date': '2024-01-31',
                'query_type': 'status_hours',
            },
        )
        assert resp.status_code == 200


# ──────────────────────────────────────────────────────────────────────────────
# 6. lookup_lot_equipment  (/api/query-tool/lot-equipment-lookup)
# ──────────────────────────────────────────────────────────────────────────────

class TestLotEquipmentLookupErrorContract:

    @pytest.mark.parametrize("exc,status,code", _EXC_CASES)
    @patch('mes_dashboard.routes.query_tool_routes.resolve_lot_equipment')
    def test_lot_equipment_lookup_exc_contract(self, mock_svc, exc, status, code, client):
        mock_svc.side_effect = exc
        resp = client.post(
            '/api/query-tool/lot-equipment-lookup',
            json={
                'input_type': 'lot_id',
                'values': ['LOT-1'],
                'workcenter_groups': ['WC1'],
            },
        )
        _assert_error(resp, status, code)

    @patch('mes_dashboard.routes.query_tool_routes.resolve_lot_equipment')
    def test_lot_equipment_lookup_success(self, mock_svc, client):
        mock_svc.return_value = {'data': [], 'total': 0}
        resp = client.post(
            '/api/query-tool/lot-equipment-lookup',
            json={
                'input_type': 'lot_id',
                'values': ['LOT-1'],
                'workcenter_groups': ['WC1'],
            },
        )
        assert resp.status_code == 200


# ──────────────────────────────────────────────────────────────────────────────
# 7. export_csv  (/api/query-tool/export-csv)
# ──────────────────────────────────────────────────────────────────────────────

class TestExportCsvErrorContract:

    @pytest.mark.parametrize("exc,status,code", _EXC_CASES)
    @patch('mes_dashboard.routes.query_tool_routes.get_lot_history')
    def test_export_csv_exc_contract(self, mock_svc, exc, status, code, client):
        mock_svc.side_effect = exc
        resp = client.post(
            '/api/query-tool/export-csv',
            json={
                'export_type': 'lot_history',
                'params': {'container_id': 'abc123'},
            },
        )
        _assert_error(resp, status, code)

    @patch('mes_dashboard.routes.query_tool_routes.generate_csv_stream')
    @patch('mes_dashboard.routes.query_tool_routes.get_lot_history')
    def test_export_csv_success(self, mock_svc, mock_stream, client):
        mock_svc.return_value = {
            'data': [{'col': 'val'}],
            'total': 1,
        }
        mock_stream.return_value = iter([b'col\r\nval\r\n'])
        resp = client.post(
            '/api/query-tool/export-csv',
            json={
                'export_type': 'lot_history',
                'params': {'container_id': 'abc123'},
            },
        )
        assert resp.status_code == 200
        assert 'text/csv' in resp.content_type
