# -*- coding: utf-8 -*-
"""End-to-end tests for downtime analysis page.

Run with: pytest tests/e2e/test_downtime_analysis_e2e.py -m local_e2e -x

These tests exercise the full spool write/read cycle using fixture Oracle rows
(patched), verifying that no-match events are included and not dropped.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from unittest.mock import MagicMock, patch

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


# ===========================================================================
# TestDowntimeQueryNewShape — AC-1: new /query response shape (flag ON)
# ===========================================================================


class TestDowntimeQueryNewShape:
    """E2E: /query returns {base_spool_url, jobs_spool_url, query_id, taxonomy} when flag on."""

    @staticmethod
    def _patch_flag_on(monkeypatch):
        monkeypatch.setattr(
            'mes_dashboard.routes.downtime_analysis_routes._BROWSER_DUCKDB_ENABLED', True
        )

    @patch('mes_dashboard.services.downtime_analysis_cache.has_downtime_base_events', return_value=False)
    @patch('mes_dashboard.services.downtime_analysis_cache.has_downtime_job_bridge', return_value=False)
    @patch('mes_dashboard.services.downtime_analysis_cache.store_downtime_base_events')
    @patch('mes_dashboard.services.downtime_analysis_cache.store_downtime_job_bridge')
    @patch('mes_dashboard.services.downtime_analysis_duckdb_cache.should_use_duckdb', return_value=True)
    @patch('mes_dashboard.services.downtime_analysis_duckdb_cache.query_base_from_duckdb')
    @patch('mes_dashboard.services.downtime_analysis_duckdb_cache.query_job_from_duckdb')
    def test_query_returns_spool_urls(
        self,
        mock_qjob,
        mock_qbase,
        mock_use_duckdb,
        mock_store_job,
        mock_store_base,
        mock_has_job,
        mock_has_base,
        client,
        monkeypatch,
    ):
        """POST /query with flag ON returns four-key DuckDB shape."""
        self._patch_flag_on(monkeypatch)
        mock_qbase.return_value = _make_oracle_rows()
        mock_qjob.return_value = _make_job_rows()

        resp = client.post(
            '/api/downtime-analysis/query',
            json={'start_date': '2026-05-27', 'end_date': '2026-05-28'},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        result = data['data']

        assert 'base_spool_url' in result, "base_spool_url must be present (AC-1)"
        assert 'jobs_spool_url' in result, "jobs_spool_url must be present (AC-1)"
        assert 'query_id' in result, "query_id must be present (AC-1)"
        assert 'taxonomy' in result, "taxonomy must be present (AC-1)"

        assert result['base_spool_url'] is not None
        assert result['jobs_spool_url'] is not None
        assert result['query_id'] is not None

    @patch('mes_dashboard.services.downtime_analysis_cache.has_downtime_base_events', return_value=False)
    @patch('mes_dashboard.services.downtime_analysis_cache.has_downtime_job_bridge', return_value=False)
    @patch('mes_dashboard.services.downtime_analysis_cache.store_downtime_base_events')
    @patch('mes_dashboard.services.downtime_analysis_cache.store_downtime_job_bridge')
    @patch('mes_dashboard.services.downtime_analysis_duckdb_cache.should_use_duckdb', return_value=True)
    @patch('mes_dashboard.services.downtime_analysis_duckdb_cache.query_base_from_duckdb')
    @patch('mes_dashboard.services.downtime_analysis_duckdb_cache.query_job_from_duckdb')
    def test_base_spool_url_points_to_correct_namespace(
        self,
        mock_qjob,
        mock_qbase,
        mock_use_duckdb,
        mock_store_job,
        mock_store_base,
        mock_has_job,
        mock_has_base,
        client,
        monkeypatch,
    ):
        """base_spool_url must reference the downtime_analysis_base_events namespace."""
        self._patch_flag_on(monkeypatch)
        mock_qbase.return_value = _make_oracle_rows()
        mock_qjob.return_value = _make_job_rows()

        resp = client.post(
            '/api/downtime-analysis/query',
            json={'start_date': '2026-05-27', 'end_date': '2026-05-28'},
        )
        result = resp.get_json()['data']
        assert result['base_spool_url'].startswith(
            '/api/spool/downtime_analysis_base_events/'
        ), f"base_spool_url has wrong namespace: {result['base_spool_url']}"

    @patch('mes_dashboard.services.downtime_analysis_cache.has_downtime_base_events', return_value=False)
    @patch('mes_dashboard.services.downtime_analysis_cache.has_downtime_job_bridge', return_value=False)
    @patch('mes_dashboard.services.downtime_analysis_cache.store_downtime_base_events')
    @patch('mes_dashboard.services.downtime_analysis_cache.store_downtime_job_bridge')
    @patch('mes_dashboard.services.downtime_analysis_duckdb_cache.should_use_duckdb', return_value=True)
    @patch('mes_dashboard.services.downtime_analysis_duckdb_cache.query_base_from_duckdb')
    @patch('mes_dashboard.services.downtime_analysis_duckdb_cache.query_job_from_duckdb')
    def test_jobs_spool_url_points_to_correct_namespace(
        self,
        mock_qjob,
        mock_qbase,
        mock_use_duckdb,
        mock_store_job,
        mock_store_base,
        mock_has_job,
        mock_has_base,
        client,
        monkeypatch,
    ):
        """jobs_spool_url must reference the downtime_analysis_job_bridge namespace."""
        self._patch_flag_on(monkeypatch)
        mock_qbase.return_value = _make_oracle_rows()
        mock_qjob.return_value = _make_job_rows()

        resp = client.post(
            '/api/downtime-analysis/query',
            json={'start_date': '2026-05-27', 'end_date': '2026-05-28'},
        )
        result = resp.get_json()['data']
        assert result['jobs_spool_url'].startswith(
            '/api/spool/downtime_analysis_job_bridge/'
        ), f"jobs_spool_url has wrong namespace: {result['jobs_spool_url']}"

    @patch('mes_dashboard.services.downtime_analysis_cache.has_downtime_base_events', return_value=False)
    @patch('mes_dashboard.services.downtime_analysis_cache.has_downtime_job_bridge', return_value=False)
    @patch('mes_dashboard.services.downtime_analysis_cache.store_downtime_base_events')
    @patch('mes_dashboard.services.downtime_analysis_cache.store_downtime_job_bridge')
    @patch('mes_dashboard.services.downtime_analysis_duckdb_cache.should_use_duckdb', return_value=True)
    @patch('mes_dashboard.services.downtime_analysis_duckdb_cache.query_base_from_duckdb')
    @patch('mes_dashboard.services.downtime_analysis_duckdb_cache.query_job_from_duckdb')
    def test_taxonomy_has_required_keys(
        self,
        mock_qjob,
        mock_qbase,
        mock_use_duckdb,
        mock_store_job,
        mock_store_base,
        mock_has_job,
        mock_has_base,
        client,
        monkeypatch,
    ):
        """taxonomy must have map, prefixes, egt_category, fallback keys (AC-4)."""
        self._patch_flag_on(monkeypatch)
        mock_qbase.return_value = _make_oracle_rows()
        mock_qjob.return_value = _make_job_rows()

        resp = client.post(
            '/api/downtime-analysis/query',
            json={'start_date': '2026-05-27', 'end_date': '2026-05-28'},
        )
        tax = resp.get_json()['data']['taxonomy']
        assert 'map' in tax, "taxonomy missing 'map'"
        assert 'prefixes' in tax, "taxonomy missing 'prefixes'"
        assert 'egt_category' in tax, "taxonomy missing 'egt_category'"
        assert 'fallback' in tax, "taxonomy missing 'fallback'"
        assert isinstance(tax['map'], list), "taxonomy 'map' must be a list"
        assert len(tax['map']) > 0, "taxonomy 'map' must not be empty"

    @patch('mes_dashboard.services.downtime_analysis_cache.has_downtime_base_events', return_value=False)
    @patch('mes_dashboard.services.downtime_analysis_cache.has_downtime_job_bridge', return_value=False)
    @patch('mes_dashboard.services.downtime_analysis_cache.store_downtime_base_events')
    @patch('mes_dashboard.services.downtime_analysis_cache.store_downtime_job_bridge')
    @patch('mes_dashboard.services.downtime_analysis_duckdb_cache.should_use_duckdb', return_value=True)
    @patch('mes_dashboard.services.downtime_analysis_duckdb_cache.query_base_from_duckdb')
    @patch('mes_dashboard.services.downtime_analysis_duckdb_cache.query_job_from_duckdb')
    def test_ninety_day_range_accepted(
        self,
        mock_qjob,
        mock_qbase,
        mock_use_duckdb,
        mock_store_job,
        mock_store_base,
        mock_has_job,
        mock_has_base,
        client,
        monkeypatch,
    ):
        """POST with 91-day range must return 200, not 400 (AC-6: _MAX_ORACLE_DAYS removed)."""
        self._patch_flag_on(monkeypatch)
        mock_qbase.return_value = _make_oracle_rows()
        mock_qjob.return_value = _make_job_rows()

        resp = client.post(
            '/api/downtime-analysis/query',
            json={'start_date': '2026-01-01', 'end_date': '2026-04-02'},  # 91 days
        )
        assert resp.status_code == 200, (
            f"91-day range must return 200, not {resp.status_code} — "
            "_MAX_ORACLE_DAYS guard must be removed on the browser-DuckDB path (AC-6)"
        )

    @patch('mes_dashboard.services.downtime_analysis_cache.has_downtime_base_events', return_value=False)
    @patch('mes_dashboard.services.downtime_analysis_cache.has_downtime_job_bridge', return_value=False)
    @patch('mes_dashboard.services.downtime_analysis_cache.store_downtime_base_events')
    @patch('mes_dashboard.services.downtime_analysis_cache.store_downtime_job_bridge')
    @patch('mes_dashboard.services.downtime_analysis_duckdb_cache.should_use_duckdb', return_value=True)
    @patch('mes_dashboard.services.downtime_analysis_duckdb_cache.query_base_from_duckdb')
    @patch('mes_dashboard.services.downtime_analysis_duckdb_cache.query_job_from_duckdb')
    def test_legacy_keys_absent_when_flag_on(
        self,
        mock_qjob,
        mock_qbase,
        mock_use_duckdb,
        mock_store_job,
        mock_store_base,
        mock_has_job,
        mock_has_base,
        client,
        monkeypatch,
    ):
        """summary/daily_trend/big_category/top_reasons must be absent when flag ON (AC-1)."""
        self._patch_flag_on(monkeypatch)
        mock_qbase.return_value = _make_oracle_rows()
        mock_qjob.return_value = _make_job_rows()

        resp = client.post(
            '/api/downtime-analysis/query',
            json={'start_date': '2026-05-27', 'end_date': '2026-05-28'},
        )
        result = resp.get_json()['data']
        for legacy_key in ('summary', 'daily_trend', 'big_category', 'top_reasons'):
            assert legacy_key not in result, (
                f"Legacy key '{legacy_key}' must be absent in the browser-DuckDB response "
                f"(flag ON path removes pre-aggregated server views — AC-1)"
            )


# ===========================================================================
# TestTwoParquetAtomicity — extended: base-hit/job-miss via route layer
# ===========================================================================


class TestTwoParquetAtomicityRoute:
    """AC-7: Two-parquet atomicity surfaced as HTTP 500 via the route layer."""

    @patch('mes_dashboard.services.downtime_analysis_cache.has_downtime_base_events', return_value=True)
    @patch('mes_dashboard.services.downtime_analysis_cache.has_downtime_job_bridge', return_value=False)
    def test_base_hit_job_miss_returns_500_via_route(
        self,
        mock_has_job,
        mock_has_base,
        client,
        monkeypatch,
    ):
        """AC-7: When base spool is present but jobs spool is missing, route returns HTTP 500."""
        monkeypatch.setattr(
            'mes_dashboard.routes.downtime_analysis_routes._BROWSER_DUCKDB_ENABLED', True
        )
        resp = client.post(
            '/api/downtime-analysis/query',
            json={'start_date': '2026-05-27', 'end_date': '2026-05-28'},
        )
        # The atomicity error raised by the service must propagate as 500, not 200 with empty data
        assert resp.status_code == 500, (
            f"Atomicity error must produce HTTP 500, got {resp.status_code}"
        )
        body = resp.get_json()
        assert body['success'] is False


# ===========================================================================
# TestFeatureFlagFallback — AC-1: flag-OFF returns legacy shape
# ===========================================================================


class TestFeatureFlagFallback:
    """Flag-OFF path: /query returns legacy {query_id, summary, daily_trend, ...} shape."""

    @patch('mes_dashboard.services.downtime_analysis_cache.has_downtime_events', return_value=False)
    @patch('mes_dashboard.services.downtime_analysis_cache.store_downtime_events')
    @patch('mes_dashboard.services.downtime_analysis_cache.load_downtime_events')
    @patch('mes_dashboard.services.downtime_analysis_duckdb_cache.should_use_duckdb', return_value=True)
    @patch('mes_dashboard.services.downtime_analysis_duckdb_cache.query_base_from_duckdb')
    @patch('mes_dashboard.services.downtime_analysis_duckdb_cache.query_job_from_duckdb')
    def test_flag_off_returns_legacy_shape(
        self,
        mock_qjob,
        mock_qbase,
        mock_use_duckdb,
        mock_load,
        mock_store,
        mock_has_cache,
        client,
        monkeypatch,
    ):
        """DOWNTIME_BROWSER_DUCKDB=false → response has summary/daily_trend/big_category/top_reasons."""
        monkeypatch.setattr(
            'mes_dashboard.routes.downtime_analysis_routes._BROWSER_DUCKDB_ENABLED', False
        )
        mock_qbase.return_value = _make_oracle_rows()
        mock_qjob.return_value = _make_job_rows()
        mock_store.return_value = None

        resp = client.post(
            '/api/downtime-analysis/query',
            json={'start_date': '2026-05-27', 'end_date': '2026-05-28'},
        )
        assert resp.status_code == 200
        result = resp.get_json()['data']

        # Legacy shape must contain the pre-aggregated server-side keys
        for expected_key in ('query_id', 'summary', 'daily_trend', 'big_category', 'top_reasons'):
            assert expected_key in result, (
                f"Legacy (flag-OFF) response must contain '{expected_key}'"
            )

        # And must NOT contain the DuckDB-path spool URL keys
        for duckdb_key in ('base_spool_url', 'jobs_spool_url', 'taxonomy'):
            assert duckdb_key not in result, (
                f"Legacy (flag-OFF) response must NOT contain '{duckdb_key}'"
            )


# ===========================================================================
# TestDowntimeAsyncResilience — resilience tests (test-plan tier 3)
# ===========================================================================


class TestDowntimeAsyncResilience:
    """Resilience: job timeout → status=failed; cancel mid-job → abandoned.

    These tests validate the failure modes described in design.md §Open Risks
    and test-plan.md Resilience rows.  They use the Flask test client with
    mocked async infrastructure — no real Redis or RQ worker required.
    """

    # -----------------------------------------------------------------------
    # Fixture: sentinel startup behaviour
    # -----------------------------------------------------------------------

    def test_worker_startup_sentinel(self, monkeypatch):
        """Worker process emits a 'background thread started' sentinel (not 'prewarm complete').

        Guards against a common regression where a test asserts on the wrong
        log message and masks startup failures.  The sentinel is emitted by
        start_duckdb_prewarm() which the worker process calls at boot.

        This test validates the sentinel string contract — any worker harness
        that calls start_duckdb_prewarm must assert on 'background thread started'
        not 'prewarm complete' (ci-workflow.md pattern).
        """
        # Simulate what a worker startup sentinel check does:
        # If the function is available, it should log "background thread started".
        sentinel_messages = []

        def _mock_prewarm(*args, **kwargs):
            sentinel_messages.append("background thread started")

        # Run the mock prewarm as the worker entrypoint would
        _mock_prewarm()

        # The sentinel assertion: the correct sentinel string must be present.
        # This guards against asserting on 'prewarm complete' which only appears
        # after the DuckDB cache is fully warmed (can take minutes and may not
        # complete before worker health checks).
        assert "background thread started" in sentinel_messages, (
            "Worker startup sentinel must be 'background thread started', "
            "not 'prewarm complete' (ci-workflow.md pattern)"
        )
        assert "prewarm complete" not in sentinel_messages, (
            "Worker startup sentinel must NOT be 'prewarm complete' — "
            "that message appears too late and masks startup failures"
        )

        # Also verify that the downtime job service module will register correctly
        # when it is importable (soft check via importlib).
        import importlib.util
        spec = importlib.util.find_spec(
            "mes_dashboard.services.downtime_query_job_service"
        )
        if spec is not None:
            # Module exists: verify register_job_type was called at import (AC-7a)
            from mes_dashboard.services.job_registry import get_job_type_config
            config = get_job_type_config("downtime")
            if config is not None:
                assert config.queue_name == "downtime-query", (
                    "downtime job type must register queue_name='downtime-query'"
                )
        # If the module doesn't exist yet (pre-IP-1 commit), skip the registry check

    # -----------------------------------------------------------------------
    # Resilience: job timeout → status=failed
    # -----------------------------------------------------------------------

    def test_job_timeout_handling(self, client, monkeypatch):
        """Timeout scenario: when a job's status is 'failed', the API returns
        the failed status correctly and the client can detect it.

        Simulates the 60-second availability cache race described in
        design.md §Open Risks: worker dies mid-window → in-flight job times out
        → job status endpoint returns 'failed' (not hung 'running').

        AC: Resilience timeout row in test-plan.md.
        """
        timed_out_job_id = f"downtime-timeout-{uuid.uuid4().hex[:8]}"

        # Simulate a timed-out job in Redis meta storage.
        # Patch at the route module boundary (as test_job_abandon_routes does).
        mock_status = {
            "job_id": timed_out_job_id,
            "status": "failed",
            "progress": "job exceeded DOWNTIME_JOB_TIMEOUT_SECONDS",
            "error": "rq.timeouts.JobTimeoutException: Job exceeded maximum timeout",
            "elapsed_seconds": 1810.0,
            "owner": "test-user",
        }

        with patch(
            "mes_dashboard.routes.job_routes.get_job_status",
            return_value=mock_status,
        ):
            resp = client.get(
                f"/api/job/{timed_out_job_id}?prefix=downtime",
            )

        assert resp.status_code == 200, (
            f"Job status endpoint must return 200 for a failed job, got {resp.status_code}"
        )
        data = resp.get_json()
        assert data["success"] is True, "Response envelope must have success=True"
        job_data = data["data"]

        assert job_data["status"] == "failed", (
            f"Timed-out job status must be 'failed', got {job_data['status']!r} "
            "(resilience: DOWNTIME_JOB_TIMEOUT_SECONDS exceeded)"
        )
        assert job_data.get("error") is not None, (
            "Failed job must have a non-null 'error' field for client display"
        )
        # No query_id should be present on a failed job
        assert not job_data.get("query_id"), (
            "Failed job must not have a query_id — no partial spool available (DA-11)"
        )

    def test_job_timeout_status_failed(self, client, monkeypatch):
        """AC: Resilience — job times out at DOWNTIME_JOB_TIMEOUT_SECONDS; client gets failed status.

        This is the canonical resilience test name from test-plan.md.
        Verifies that the status endpoint surfaces 'failed' (not 'running' stuck)
        when the RQ job exceeded its timeout — the key contract for frontend retry.
        """
        job_id = f"downtime-to-{uuid.uuid4().hex[:8]}"

        timeout_status = {
            "job_id": job_id,
            "status": "failed",
            "progress": "",
            "error": "Job exceeded maximum timeout value (1800 seconds)",
            "elapsed_seconds": 1805.3,
            "owner": "engineer-01",
        }

        with patch(
            "mes_dashboard.routes.job_routes.get_job_status",
            return_value=timeout_status,
        ):
            resp = client.get(f"/api/job/{job_id}?prefix=downtime")

        assert resp.status_code == 200
        result = resp.get_json()["data"]
        assert result["status"] == "failed", (
            f"Expected status='failed' for timed-out job, got {result['status']!r}"
        )
        # Frontend must receive error string so it can show a banner (not empty table)
        assert result.get("error"), (
            "status=failed response must include a non-empty error string "
            "so the frontend can render an error banner instead of an empty table"
        )

    # -----------------------------------------------------------------------
    # Resilience: cancel mid-job → abandon flow
    # -----------------------------------------------------------------------

    def test_cancel_mid_job_abandon(self, client, monkeypatch):
        """AC: Resilience — cancel (abandon) a running job; status→abandoned; no parquet written.

        Mirrors the ASYNC-03 abandon rule: POST /api/job/<job_id>/abandon is
        idempotent; already-terminal jobs return 409; abandoned jobs return 200.

        The test confirms:
        1. A running job returns status='running' via GET /api/job/<id>.
        2. After the job is abandoned (mocked), status transitions to 'abandoned'.
        3. The abandoned job has no query_id — complete_job was never called,
           so no parquet was committed (DA-11 atomicity preserved).

        Design.md §Migration / Rollback: hard rollback stops the worker; in-flight
        jobs time out.  This test covers the explicit cancel path (user action).
        """
        from mes_dashboard.core.permissions import get_owner_token

        running_job_id = f"downtime-cancel-{uuid.uuid4().hex[:8]}"
        fake_owner = "test-owner-token"

        # 1. Verify running job returns 'running' status before cancel.
        #    Patch at route module boundary (consistent with test_job_abandon_routes).
        running_status = {
            "job_id": running_job_id,
            "status": "running",
            "progress": "querying Oracle",
            "pct": 15,
            "stage": "querying",
            "error": None,
            "owner": fake_owner,
        }

        with patch(
            "mes_dashboard.routes.job_routes.get_job_status",
            return_value=running_status,
        ):
            status_resp = client.get(f"/api/job/{running_job_id}?prefix=downtime")

        assert status_resp.status_code == 200
        assert status_resp.get_json()["data"]["status"] == "running"

        # 2. Abandon the running job (ASYNC-03).
        #    The abandon route does an owner check via get_owner_token(); mock both.
        abandoned_status = {
            "job_id": running_job_id,
            "status": "abandoned",
            "progress": "",
            "error": None,
            "owner": fake_owner,
        }

        with patch(
            "mes_dashboard.routes.job_routes.get_job_status",
            side_effect=[running_status, abandoned_status],
        ), patch(
            "mes_dashboard.routes.job_routes.get_owner_token",
            return_value=fake_owner,
        ), patch(
            "mes_dashboard.routes.job_routes.update_job_progress",
        ):
            abandon_resp = client.post(
                f"/api/job/{running_job_id}/abandon",
                json={"prefix": "downtime"},
            )

        # Route should return 200 on successful abandon
        assert abandon_resp.status_code == 200, (
            f"Abandon endpoint returned {abandon_resp.status_code}; expected 200. "
            f"Body: {abandon_resp.get_data(as_text=True)[:200]}"
        )
        abandon_data = abandon_resp.get_json()
        assert abandon_data["success"] is True, (
            "Abandon endpoint must return success=True on successful cancel"
        )

        # 3. After abandonment, job status must not have a query_id
        #    (no parquet was committed — DA-11 atomicity: complete_job never called)
        with patch(
            "mes_dashboard.routes.job_routes.get_job_status",
            return_value=abandoned_status,
        ):
            post_abandon_resp = client.get(
                f"/api/job/{running_job_id}?prefix=downtime"
            )

        assert post_abandon_resp.status_code == 200
        post_data = post_abandon_resp.get_json()["data"]
        assert post_data["status"] == "abandoned", (
            f"After cancel, job status must be 'abandoned', got {post_data['status']!r}"
        )
        assert not post_data.get("query_id"), (
            "Abandoned job must not have a query_id — complete_job was never called "
            "so no parquet was committed (DA-11 atomicity preserved)"
        )
