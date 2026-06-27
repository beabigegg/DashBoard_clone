# -*- coding: utf-8 -*-
"""Unit tests for GET /api/db-scheduling/queue route.

Tests:
- 401 when unauthenticated (api_public=False, no session)
- 200 + success envelope when authenticated
- matchSource closed enum (workflow / bop-fallback / none)
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

import mes_dashboard.core.database as db
from mes_dashboard.app import create_app


@pytest.fixture()
def app():
    db._ENGINE = None
    app = create_app('testing')
    app.config['TESTING'] = True
    return app


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def auth_client(app):
    """Client with a user session set (simulates logged-in user)."""
    c = app.test_client()
    with c.session_transaction() as sess:
        sess['user'] = {'username': 'testuser', 'mail': 'test@test.com'}
    return c


# ---------------------------------------------------------------------------
# 401 test
# ---------------------------------------------------------------------------

class TestQueueAuth:
    def test_queue_unauthenticated(self, client):
        """GET /api/db-scheduling/queue without auth → 401 when api_public=False."""
        with (
            patch('mes_dashboard.app.is_api_public', return_value=False),
            patch('mes_dashboard.app.is_user_logged_in', return_value=False),
        ):
            resp = client.get('/api/db-scheduling/queue')
        assert resp.status_code == 401
        data = resp.get_json()
        assert data['success'] is False
        assert data['error']['code'] == 'UNAUTHORIZED'


# ---------------------------------------------------------------------------
# 200 + envelope tests
# ---------------------------------------------------------------------------

class TestQueueShape:

    @patch('mes_dashboard.routes.db_scheduling_routes.get_db_scheduling_queue')
    def test_queue_authenticated_shape(self, mock_service, auth_client):
        """Authenticated request returns success=True, data is list, each item has 15 fields."""
        mock_service.return_value = [
            {
                'lotId': 'LOT-001',
                'workflowName': 'WF-A',
                'packageLef': 'SOT-23',
                'pjType': 'TypeA',
                'waferLot': 'WL-001',
                'uts': '2026/01/15',
                'qty': 100,
                'bop': 'U-Eutectic',
                'eqpPackageLef': 'SOT-23',
                'eqpPjType': 'TypeB',
                'eqpWaferLot': 'WL-RUN-001',
                'eqpUts': '2026/06/01',
                'targetSpec': '1DB',
                'equipment': 'EQ-001',
                'matchSource': 'workflow',
            }
        ]
        resp = auth_client.get('/api/db-scheduling/queue')
        data = resp.get_json()

        assert resp.status_code == 200
        assert data['success'] is True
        assert isinstance(data['data'], list)
        assert len(data['data']) == 1

        row = data['data'][0]
        required = {
            'lotId', 'workflowName', 'packageLef', 'pjType', 'waferLot',
            'uts', 'qty', 'bop',
            'eqpPackageLef', 'eqpPjType', 'eqpWaferLot', 'eqpUts',
            'targetSpec', 'equipment', 'matchSource',
        }
        assert required <= set(row.keys())

    @patch('mes_dashboard.routes.db_scheduling_routes.get_db_scheduling_queue')
    def test_queue_empty_list_is_valid(self, mock_service, auth_client):
        """An empty list is a valid response (no D/B-START lots or all unmatched)."""
        mock_service.return_value = []
        resp = auth_client.get('/api/db-scheduling/queue')
        data = resp.get_json()

        assert resp.status_code == 200
        assert data['success'] is True
        assert data['data'] == []

    @patch('mes_dashboard.routes.db_scheduling_routes.get_db_scheduling_queue')
    def test_queue_500_on_service_exception(self, mock_service, auth_client):
        """Service-layer exception returns 500 with error envelope."""
        mock_service.side_effect = RuntimeError('unexpected error')
        resp = auth_client.get('/api/db-scheduling/queue')
        data = resp.get_json()

        assert resp.status_code == 500
        assert data['success'] is False


# ---------------------------------------------------------------------------
# matchSource closed-enum contract (AC-6)
# ---------------------------------------------------------------------------

class TestMatchSourceEnum:

    VALID_MATCH_SOURCES = {'workflow', 'bop-fallback', 'none'}

    @patch('mes_dashboard.routes.db_scheduling_routes.get_db_scheduling_queue')
    def test_queue_match_source_values(self, mock_service, auth_client):
        """matchSource only takes values 'workflow' / 'bop-fallback' / 'none'."""
        mock_service.return_value = [
            {
                'lotId': 'LOT-001', 'workflowName': 'WF-A',
                'packageLef': None, 'pjType': None, 'waferLot': None,
                'uts': None, 'qty': 10, 'bop': 'U-test',
                'eqpPackageLef': 'SOT-23', 'eqpPjType': None,
                'eqpWaferLot': None, 'eqpUts': None,
                'targetSpec': '1DB', 'equipment': 'EQ-001',
                'matchSource': 'workflow',
            },
            {
                'lotId': 'LOT-002', 'workflowName': 'WF-B',
                'packageLef': None, 'pjType': None, 'waferLot': None,
                'uts': None, 'qty': 20, 'bop': 'E-epoxy',
                'eqpPackageLef': 'DFN-8', 'eqpPjType': None,
                'eqpWaferLot': None, 'eqpUts': None,
                'targetSpec': 'Epoxy D/B', 'equipment': 'EQ-002',
                'matchSource': 'bop-fallback',
            },
        ]
        resp = auth_client.get('/api/db-scheduling/queue')
        data = resp.get_json()

        for row in data['data']:
            assert row['matchSource'] in self.VALID_MATCH_SOURCES, (
                f"Invalid matchSource '{row['matchSource']}' — must be one of "
                f"{self.VALID_MATCH_SOURCES}"
            )
