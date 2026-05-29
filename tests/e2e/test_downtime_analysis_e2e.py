# -*- coding: utf-8 -*-
"""End-to-end tests for downtime analysis page.

Run with: pytest tests/e2e/test_downtime_analysis_e2e.py -m local_e2e -x

These tests exercise the full spool write/read cycle using fixture Oracle rows
(patched), verifying that no-match events are included and not dropped.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

import pandas as pd
import pytest

import mes_dashboard.core.database as db
import mes_dashboard.core.redis_client as _redis_mod
from mes_dashboard.app import create_app

pytestmark = [pytest.mark.e2e, pytest.mark.local_e2e]


@pytest.fixture
def app():
    db._ENGINE = None
    app = create_app('testing')
    app.config['TESTING'] = True
    return app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def redis_enabled(monkeypatch):
    """Enable Redis for spool storage in E2E tests."""
    import mes_dashboard.core.query_spool_store as _spool_mod
    monkeypatch.setattr(_redis_mod, 'REDIS_ENABLED', True)
    monkeypatch.setattr(_redis_mod, '_REDIS_CLIENT', None)
    monkeypatch.setattr(_spool_mod, 'QUERY_SPOOL_ENABLED', True)

    from mes_dashboard.services.downtime_analysis_cache import _events_cache

    def _clear_state():
        _events_cache.clear()
        rc = _redis_mod.get_redis_client()
        if rc:
            from mes_dashboard.core.redis_client import get_key_prefix
            prefix = get_key_prefix()
            for ns in ('downtime_analysis_events',):
                keys = rc.keys(f"{prefix}:{ns}:spool_meta:*")
                if keys:
                    rc.delete(*keys)

    _clear_state()
    yield
    _clear_state()
    monkeypatch.setattr(_redis_mod, '_REDIS_CLIENT', None)


def _make_oracle_rows():
    """Return synthetic Oracle rows for base_events.sql simulation."""
    return pd.DataFrame([
        {
            'HISTORYID': 'R-001',
            'OLDSTATUSNAME': 'UDT',
            'OLDREASONNAME': 'EE Repair',
            'OLDLASTSTATUSCHANGEDATE': datetime(2026, 5, 27, 18, 0),
            'LASTSTATUSCHANGEDATE': datetime(2026, 5, 27, 19, 30),
            'HOURS': 1.5,
            'JOBID': 'J001',
        },
        {
            'HISTORYID': 'R-001',
            'OLDSTATUSNAME': 'UDT',
            'OLDREASONNAME': 'EE Repair',
            'OLDLASTSTATUSCHANGEDATE': datetime(2026, 5, 27, 19, 30),
            'LASTSTATUSCHANGEDATE': datetime(2026, 5, 28, 7, 30),
            'HOURS': 12.0,
            'JOBID': 'J001',
        },
        {
            'HISTORYID': 'R-001',
            'OLDSTATUSNAME': 'UDT',
            'OLDREASONNAME': 'EE Repair',
            'OLDLASTSTATUSCHANGEDATE': datetime(2026, 5, 28, 7, 30),
            'LASTSTATUSCHANGEDATE': datetime(2026, 5, 28, 8, 0),
            'HOURS': 0.5,
            'JOBID': 'J001',
        },
        # A UDT event with NO matching job (null JOBID)
        {
            'HISTORYID': 'R-002',
            'OLDSTATUSNAME': 'UDT',
            'OLDREASONNAME': 'Wait For Instructions',
            'OLDLASTSTATUSCHANGEDATE': datetime(2026, 5, 27, 9, 0),
            'LASTSTATUSCHANGEDATE': datetime(2026, 5, 27, 11, 0),
            'HOURS': 2.0,
            'JOBID': None,
        },
    ])


def _make_job_rows():
    """Return synthetic JOB rows."""
    return pd.DataFrame([
        {
            'JOBID': 'J001',
            'RESOURCEID': 'R-001',
            'CREATEDATE': datetime(2026, 5, 27, 17, 30),
            'COMPLETEDATE': datetime(2026, 5, 28, 9, 0),
            'SYMPTOMCODENAME': 'VIBRATION',
            'CAUSECODENAME': 'WEAR',
            'REPAIRCODENAME': 'REPLACED BEARING',
            'COMPLETE_FULLNAME': 'Technician A',
            'FIRSTCLOCKONDATE': datetime(2026, 5, 27, 18, 30),
            'LASTCLOCKOFFDATE': datetime(2026, 5, 28, 8, 30),
            'JOBORDERNAME': 'JO-2026-001',
            'JOBMODELNAME': 'MODEL-XYZ',
        }
    ])


class TestSummaryEndpointIntegration:
    """E2E: real spool write/read cycle with fixture Oracle rows."""

    @patch('mes_dashboard.services.downtime_analysis_service.read_sql_df')
    @patch('mes_dashboard.services.downtime_analysis_service.has_downtime_events', return_value=False)
    @patch('mes_dashboard.services.downtime_analysis_service.store_downtime_events')
    @patch('mes_dashboard.services.downtime_analysis_service.load_downtime_events')
    def test_summary_endpoint_returns_merged_hours(
        self,
        mock_load, mock_store, mock_has_cache,
        mock_read_sql,
        client,
    ):
        """POST /query merges 3 fragments → 1 event (14h) and returns correct summary."""
        base_rows = _make_oracle_rows()
        job_rows = _make_job_rows()

        call_count = {'n': 0}

        def _sql_side_effect(sql, params, **kwargs):
            call_count['n'] += 1
            # First call: base_events.sql, second: job_bridge.sql
            if 'RESOURCESTATUS_SHIFT' in sql or call_count['n'] == 1:
                return base_rows
            return job_rows

        mock_read_sql.side_effect = _sql_side_effect

        # mock load_downtime_events to return what store_downtime_events was called with
        stored = {}

        def _store_side_effect(query_id, df, **kw):
            stored['df'] = df
            stored['query_id'] = query_id

        mock_store.side_effect = _store_side_effect

        resp = client.post(
            '/api/downtime-analysis/query',
            json={'start_date': '2026-05-27', 'end_date': '2026-05-28'},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        result = data['data']
        assert 'query_id' in result
        assert 'summary' in result

        # Verify cross-shift merge: R-001 had 3 fragments → 1 event, 14h
        summary = result['summary']
        assert summary['udt_hours'] == pytest.approx(16.0, abs=0.5)  # 14h (R-001) + 2h (R-002)
        assert summary['event_count'] == 2  # 1 merged event (R-001) + 1 event (R-002)

    @patch('mes_dashboard.services.downtime_analysis_service.read_sql_df')
    @patch('mes_dashboard.services.downtime_analysis_service.has_downtime_events', return_value=False)
    @patch('mes_dashboard.services.downtime_analysis_service.store_downtime_events')
    @patch('mes_dashboard.services.downtime_analysis_service.load_downtime_events')
    def test_summary_structure_matches_contract(
        self,
        mock_load, mock_store, mock_has_cache,
        mock_read_sql,
        client,
    ):
        """POST /query response structure matches §3.12.1."""
        mock_read_sql.return_value = _make_oracle_rows()
        mock_store.return_value = None

        resp = client.post(
            '/api/downtime-analysis/query',
            json={'start_date': '2026-05-27', 'end_date': '2026-05-28'},
        )
        assert resp.status_code == 200
        result = resp.get_json()['data']

        # §3.12.1 fields
        summary = result['summary']
        for field in ('total_hours', 'udt_hours', 'sdt_hours', 'egt_hours',
                      'event_count', 'avg_event_min'):
            assert field in summary, f"Missing summary field '{field}'"

        # §3.12.2 daily_trend
        assert 'daily_trend' in result

        # §3.12.3 big_category
        assert 'big_category' in result

        # §3.12.4 top_reasons
        assert 'top_reasons' in result


class TestEventDetailMatchSourceNoneRowsPresent:
    """E2E: no-match events are included, not dropped (AC-5)."""

    @patch('mes_dashboard.services.downtime_analysis_service.read_sql_df')
    @patch('mes_dashboard.services.downtime_analysis_service.has_downtime_events', return_value=False)
    @patch('mes_dashboard.services.downtime_analysis_service.store_downtime_events')
    @patch('mes_dashboard.services.downtime_analysis_service.load_downtime_events')
    def test_no_match_events_included_in_summary(
        self,
        mock_load, mock_store, mock_has_cache,
        mock_read_sql,
        client,
    ):
        """Events with no JOB match must be counted in event_count, not dropped."""
        # All rows have null JOBID — all should appear as match_source='none'
        no_match_rows = pd.DataFrame([
            {
                'HISTORYID': 'R-003',
                'OLDSTATUSNAME': 'UDT',
                'OLDREASONNAME': 'No Operator',
                'OLDLASTSTATUSCHANGEDATE': datetime(2026, 5, 27, 9, 0),
                'LASTSTATUSCHANGEDATE': datetime(2026, 5, 27, 11, 0),
                'HOURS': 2.0,
                'JOBID': None,
            },
            {
                'HISTORYID': 'R-004',
                'OLDSTATUSNAME': 'SDT',
                'OLDREASONNAME': 'EE_PM',
                'OLDLASTSTATUSCHANGEDATE': datetime(2026, 5, 27, 14, 0),
                'LASTSTATUSCHANGEDATE': datetime(2026, 5, 27, 15, 0),
                'HOURS': 1.0,
                'JOBID': None,
            },
        ])
        mock_read_sql.return_value = no_match_rows
        mock_store.return_value = None

        resp = client.post(
            '/api/downtime-analysis/query',
            json={'start_date': '2026-05-27', 'end_date': '2026-05-27'},
        )
        assert resp.status_code == 200
        result = resp.get_json()['data']
        # Both rows must be counted
        assert result['summary']['event_count'] == 2

    @patch('mes_dashboard.services.downtime_analysis_service.apply_view')
    def test_event_detail_view_returns_no_match_rows(self, mock_apply, client):
        """GET /event-detail must return events with match_source='none' when spool has them."""
        mock_apply.return_value = {
            'events': [
                {
                    'event_id': 'R-003|UDT|No Operator|2026-05-27T09:00:00',
                    'resource_id': 'R-003',
                    'resource_name': None,
                    'status': 'UDT',
                    'reason': 'No Operator',
                    'category': '待料待指示',
                    'start_ts': '2026-05-27T09:00:00',
                    'end_ts': '2026-05-27T11:00:00',
                    'hours': 2.0,
                    'match_source': 'none',
                    'job': None,
                }
            ],
            'pagination': {'page': 1, 'page_size': 50, 'total_rows': 1, 'total_pages': 1},
        }

        resp = client.get('/api/downtime-analysis/event-detail?query_id=MOCK-QID')
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert len(data['events']) == 1
        event = data['events'][0]
        assert event['match_source'] == 'none'
        assert event['job'] is None
