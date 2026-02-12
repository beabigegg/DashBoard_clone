# -*- coding: utf-8 -*-
"""Tests for QC-GATE API and page routes."""

from __future__ import annotations

from unittest.mock import patch

import mes_dashboard.core.database as db

from mes_dashboard.app import create_app


def _client():
    db._ENGINE = None
    app = create_app('testing')
    app.config['TESTING'] = True
    return app.test_client()


@patch('mes_dashboard.routes.qc_gate_routes.get_qc_gate_summary')
def test_qc_gate_summary_route_returns_success(mock_get_summary):
    mock_get_summary.return_value = {
        'cache_time': '2026-02-09T12:00:00',
        'stations': [
            {
                'specname': 'QC-GATE-A',
                'spec_order': 10,
                'buckets': {
                    'lt_6h': 1,
                    '6h_12h': 0,
                    '12h_24h': 0,
                    'gt_24h': 0,
                },
                'total': 1,
                'lots': [],
            }
        ],
    }

    response = _client().get('/api/qc-gate/summary')
    payload = response.get_json()

    assert response.status_code == 200
    assert payload['success'] is True
    assert payload['data']['cache_time'] == '2026-02-09T12:00:00'
    assert payload['data']['stations'][0]['specname'] == 'QC-GATE-A'


@patch('mes_dashboard.routes.qc_gate_routes.get_qc_gate_summary', return_value=None)
def test_qc_gate_summary_route_returns_500_on_failure(_mock_get_summary):
    response = _client().get('/api/qc-gate/summary')
    payload = response.get_json()

    assert response.status_code == 500
    assert payload['success'] is False
    assert 'error' in payload


def test_qc_gate_page_redirects_to_canonical_shell_when_spa_enabled():
    response = _client().get('/qc-gate', follow_redirects=False)
    assert response.status_code == 302
    assert response.location.endswith('/portal-shell/qc-gate')
