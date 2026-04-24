# -*- coding: utf-8 -*-
"""Unit tests for hold_today_snapshot_service."""

from __future__ import annotations

import types
import unittest
from unittest.mock import MagicMock, patch

import pandas as pd


def _make_row(
    hold_day, release_day, today_date,
    releasetxndate=None, qty=10, hold_hours=5.0,
    hold_type='quality', is_future_hold=0, futureholdcomments=None,
    containerid='LOT001', holdreasonname='Reason A',
):
    return {
        'HOLD_DAY': hold_day,
        'RELEASE_DAY': release_day,
        'TODAY_DATE': today_date,
        'RELEASETXNDATE': releasetxndate,
        'QTY': qty,
        'HOLD_HOURS': hold_hours,
        'HOLD_TYPE': hold_type,
        'IS_FUTURE_HOLD': is_future_hold,
        'FUTUREHOLDCOMMENTS': futureholdcomments,
        'CONTAINERID': containerid,
        'LOT_ID': containerid,
        'HOLDREASONNAME': holdreasonname,
        'PJ_WORKORDER': 'WO001',
        'PRODUCTNAME': 'PROD001',
        'WORKCENTERNAME': 'WC001',
        'HOLDTXNDATE': pd.Timestamp('2026-04-23 09:00:00'),
        'HOLDEMP': 'user1',
        'HOLDCOMMENTS': None,
        'RELEASEEMP': None,
        'RELEASECOMMENTS': None,
        'NCRID': None,
        'RN_FUTURE_REASON': 1,
        'FUTURE_HOLD_FLAG': 1,
        'HOLDREASONID': 'R001',
    }


TODAY = pd.Timestamp('2026-04-23').date()
YESTERDAY = pd.Timestamp('2026-04-22').date()


def _df(*rows):
    return pd.DataFrame(list(rows))


class TestBuildSummary(unittest.TestCase):

    def setUp(self):
        # Patch read_sql_df_slow to avoid DB calls
        patcher = patch('mes_dashboard.services.hold_today_snapshot_service.read_sql_df')
        self.addCleanup(patcher.stop)
        self.mock_read = patcher.start()
        self.mock_read.return_value = pd.DataFrame()

        from mes_dashboard.services import hold_today_snapshot_service as svc
        self.svc = svc

    def test_summary_on_hold_total_counts_unreleased(self):
        rows = [
            _make_row(YESTERDAY, None, TODAY, releasetxndate=None, containerid='L1', qty=5),
            _make_row(TODAY, TODAY, TODAY, releasetxndate=pd.Timestamp('2026-04-23'), containerid='L2', qty=3),
        ]
        df = _df(*rows)
        summary = self.svc._build_today_summary(df)
        self.assertEqual(summary['onHoldLots'], 1)
        self.assertEqual(summary['onHoldQty'], 5)

    def test_summary_today_new_qty(self):
        rows = [
            _make_row(TODAY, None, TODAY, releasetxndate=None, containerid='L1', qty=7),
            _make_row(YESTERDAY, None, TODAY, releasetxndate=None, containerid='L2', qty=3),
        ]
        df = _df(*rows)
        summary = self.svc._build_today_summary(df)
        self.assertEqual(summary['todayNewQty'], 7)

    def test_summary_today_release_qty(self):
        rows = [
            _make_row(YESTERDAY, TODAY, TODAY, releasetxndate=pd.Timestamp('2026-04-23'), containerid='L1', qty=4),
            _make_row(TODAY, None, TODAY, releasetxndate=None, containerid='L2', qty=2),
        ]
        df = _df(*rows)
        summary = self.svc._build_today_summary(df)
        self.assertEqual(summary['todayReleaseQty'], 4)

    def test_summary_today_future_hold_qty(self):
        rows = [
            _make_row(TODAY, None, TODAY, releasetxndate=None, containerid='L1', qty=5,
                      futureholdcomments='has comment', is_future_hold=1),
            _make_row(TODAY, None, TODAY, releasetxndate=None, containerid='L2', qty=2,
                      futureholdcomments=None, is_future_hold=0),
        ]
        df = _df(*rows)
        summary = self.svc._build_today_summary(df)
        self.assertEqual(summary['todayFutureHoldQty'], 5)

    def test_summary_on_hold_avg_max_hours(self):
        rows = [
            _make_row(YESTERDAY, None, TODAY, releasetxndate=None, containerid='L1', hold_hours=10.0),
            _make_row(YESTERDAY, None, TODAY, releasetxndate=None, containerid='L2', hold_hours=20.0),
        ]
        df = _df(*rows)
        summary = self.svc._build_today_summary(df)
        self.assertAlmostEqual(summary['onHoldAvgHours'], 15.0, places=1)
        self.assertAlmostEqual(summary['onHoldMaxHours'], 20.0, places=1)

    def test_summary_all_zeros_on_empty(self):
        df = pd.DataFrame()
        summary = self.svc._build_today_summary(df) if not df.empty else {
            'onHoldTotalCount': 0, 'onHoldTotalQty': 0, 'todayNewQty': 0,
            'todayReleaseQty': 0, 'todayFutureHoldQty': 0,
            'onHoldAvgHours': 0.0, 'onHoldMaxHours': 0.0,
        }
        self.assertEqual(summary['onHoldTotalCount'], 0)


class TestApplyRecordTypeFilter(unittest.TestCase):

    def setUp(self):
        patcher = patch('mes_dashboard.services.hold_today_snapshot_service.read_sql_df')
        self.addCleanup(patcher.stop)
        patcher.start().return_value = pd.DataFrame()
        from mes_dashboard.services import hold_today_snapshot_service as svc
        self.svc = svc

    def test_on_hold_filters_unreleased(self):
        rows = [
            _make_row(YESTERDAY, None, TODAY, releasetxndate=None, containerid='L1'),
            _make_row(TODAY, TODAY, TODAY, releasetxndate=pd.Timestamp('2026-04-23'), containerid='L2'),
        ]
        df = _df(*rows)
        result = self.svc._apply_record_type_filter_today(df, 'on_hold')
        self.assertEqual(len(result), 1)
        self.assertEqual(result.iloc[0]['CONTAINERID'], 'L1')

    def test_new_filters_today_hold_day(self):
        rows = [
            _make_row(TODAY, None, TODAY, containerid='L1'),
            _make_row(YESTERDAY, None, TODAY, containerid='L2'),
        ]
        df = _df(*rows)
        result = self.svc._apply_record_type_filter_today(df, 'new')
        self.assertEqual(len(result), 1)
        self.assertEqual(result.iloc[0]['CONTAINERID'], 'L1')

    def test_release_filters_today_release_day(self):
        rows = [
            _make_row(YESTERDAY, TODAY, TODAY, releasetxndate=pd.Timestamp('2026-04-23'), containerid='L1'),
            _make_row(YESTERDAY, YESTERDAY, TODAY, releasetxndate=pd.Timestamp('2026-04-22'), containerid='L2'),
        ]
        df = _df(*rows)
        result = self.svc._apply_record_type_filter_today(df, 'release')
        self.assertEqual(len(result), 1)
        self.assertEqual(result.iloc[0]['CONTAINERID'], 'L1')

    def test_combined_or_logic(self):
        rows = [
            _make_row(TODAY, None, TODAY, releasetxndate=None, containerid='L1'),
            _make_row(YESTERDAY, TODAY, TODAY, releasetxndate=pd.Timestamp('2026-04-23'), containerid='L2'),
            _make_row(YESTERDAY, YESTERDAY, TODAY, releasetxndate=pd.Timestamp('2026-04-22'), containerid='L3'),
        ]
        df = _df(*rows)
        result = self.svc._apply_record_type_filter_today(df, 'new,release')
        self.assertEqual(set(result['CONTAINERID']), {'L1', 'L2'})


class TestTruncation(unittest.TestCase):

    def setUp(self):
        patcher_read = patch('mes_dashboard.services.hold_today_snapshot_service.read_sql_df')
        patcher_cache_get = patch('mes_dashboard.services.hold_today_snapshot_service._get_cache', return_value=None)
        patcher_cache_set = patch('mes_dashboard.services.hold_today_snapshot_service._set_cache')
        patcher_wc = patch('mes_dashboard.services.hold_today_snapshot_service._get_wc_group', return_value=None)
        self.mock_read = patcher_read.start()
        patcher_cache_get.start()
        patcher_cache_set.start()
        patcher_wc.start()
        self.addCleanup(patcher_read.stop)
        self.addCleanup(patcher_cache_get.stop)
        self.addCleanup(patcher_cache_set.stop)
        self.addCleanup(patcher_wc.stop)

    def test_truncated_when_over_limit(self):
        import importlib
        import mes_dashboard.services.hold_today_snapshot_service as svc
        # Build 5 rows but set max_rows to 2 via constant patch
        rows = [_make_row(TODAY, None, TODAY, releasetxndate=None, containerid=f'L{i}') for i in range(5)]
        self.mock_read.return_value = _df(*rows)

        with patch.object(svc, 'HOLD_TODAY_MAX_SNAPSHOT_ROWS', 2):
            result = svc.execute_today_snapshot(hold_type='quality')

        self.assertIn('_meta', result)
        self.assertTrue(result['_meta']['truncated'])
        self.assertGreater(result['_meta']['total_before_limit'], 2)
        self.assertEqual(result['_meta']['limit_applied'], 2)


if __name__ == '__main__':
    unittest.main()
