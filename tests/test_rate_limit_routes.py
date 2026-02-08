# -*- coding: utf-8 -*-
"""Route-level rate limit behavior tests."""

from __future__ import annotations

from unittest.mock import patch

import mes_dashboard.core.database as db
from mes_dashboard.app import create_app


def _client():
    db._ENGINE = None
    app = create_app('testing')
    app.config['TESTING'] = True
    return app.test_client()


@patch('mes_dashboard.services.resource_service.get_merged_resource_status')
@patch('mes_dashboard.core.rate_limit.check_and_record', return_value=(True, 5))
def test_resource_status_rate_limit_returns_429(_mock_limit, mock_service):
    client = _client()
    response = client.get('/api/resource/status')

    assert response.status_code == 429
    payload = response.get_json()
    assert payload['error']['code'] == 'TOO_MANY_REQUESTS'
    assert response.headers.get('Retry-After') == '5'
    mock_service.assert_not_called()


@patch('mes_dashboard.services.wip_service.get_hold_detail_lots')
@patch('mes_dashboard.core.rate_limit.check_and_record', return_value=(True, 4))
def test_hold_detail_lots_rate_limit_returns_429(_mock_limit, mock_service):
    client = _client()
    response = client.get('/api/wip/hold-detail/lots?reason=YieldLimit')

    assert response.status_code == 429
    payload = response.get_json()
    assert payload['error']['code'] == 'TOO_MANY_REQUESTS'
    assert response.headers.get('Retry-After') == '4'
    mock_service.assert_not_called()
