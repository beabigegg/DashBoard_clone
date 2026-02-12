# -*- coding: utf-8 -*-
"""Unit tests for hold_history_service module."""

from __future__ import annotations

import json
import unittest
from datetime import date, datetime, timedelta
from unittest.mock import MagicMock, patch

import pandas as pd

from mes_dashboard.services import hold_history_service


class TestHoldHistoryTrendCache(unittest.TestCase):
    """Test trend cache hit/miss/cross-month behavior."""

    def setUp(self):
        hold_history_service._load_hold_history_sql.cache_clear()

    def _trend_rows_for_days(self, days: list[str]) -> pd.DataFrame:
        rows = []
        for day in days:
            rows.append(
                {
                    'TXN_DATE': day,
                    'HOLD_TYPE': 'quality',
                    'HOLD_QTY': 10,
                    'NEW_HOLD_QTY': 2,
                    'RELEASE_QTY': 3,
                    'FUTURE_HOLD_QTY': 1,
                }
            )
            rows.append(
                {
                    'TXN_DATE': day,
                    'HOLD_TYPE': 'non-quality',
                    'HOLD_QTY': 4,
                    'NEW_HOLD_QTY': 1,
                    'RELEASE_QTY': 1,
                    'FUTURE_HOLD_QTY': 0,
                }
            )
            rows.append(
                {
                    'TXN_DATE': day,
                    'HOLD_TYPE': 'all',
                    'HOLD_QTY': 14,
                    'NEW_HOLD_QTY': 3,
                    'RELEASE_QTY': 4,
                    'FUTURE_HOLD_QTY': 1,
                }
            )
        return pd.DataFrame(rows)

    @patch('mes_dashboard.services.hold_history_service.read_sql_df')
    @patch('mes_dashboard.services.hold_history_service.get_redis_client')
    def test_trend_cache_hit_for_recent_month(self, mock_get_redis_client, mock_read_sql_df):
        today = date.today()
        start = today.replace(day=1)
        end = start + timedelta(days=1)

        cached_days = [
            {
                'date': start.strftime('%Y-%m-%d'),
                'quality': {'holdQty': 11, 'newHoldQty': 2, 'releaseQty': 4, 'futureHoldQty': 1},
                'non_quality': {'holdQty': 5, 'newHoldQty': 1, 'releaseQty': 1, 'futureHoldQty': 0},
                'all': {'holdQty': 16, 'newHoldQty': 3, 'releaseQty': 5, 'futureHoldQty': 1},
            },
            {
                'date': end.strftime('%Y-%m-%d'),
                'quality': {'holdQty': 12, 'newHoldQty': 3, 'releaseQty': 5, 'futureHoldQty': 1},
                'non_quality': {'holdQty': 4, 'newHoldQty': 1, 'releaseQty': 2, 'futureHoldQty': 0},
                'all': {'holdQty': 16, 'newHoldQty': 4, 'releaseQty': 7, 'futureHoldQty': 1},
            },
        ]

        mock_redis = MagicMock()
        mock_redis.get.return_value = json.dumps(cached_days)
        mock_get_redis_client.return_value = mock_redis

        result = hold_history_service.get_hold_history_trend(start.isoformat(), end.isoformat())

        self.assertIsNotNone(result)
        self.assertEqual(len(result['days']), 2)
        self.assertEqual(result['days'][0]['quality']['holdQty'], 11)
        self.assertEqual(result['days'][1]['all']['releaseQty'], 7)
        mock_read_sql_df.assert_not_called()

    @patch('mes_dashboard.services.hold_history_service.read_sql_df')
    @patch('mes_dashboard.services.hold_history_service.get_redis_client')
    def test_trend_cache_miss_populates_cache(self, mock_get_redis_client, mock_read_sql_df):
        today = date.today()
        start = today.replace(day=1)
        end = start + timedelta(days=1)

        mock_redis = MagicMock()
        mock_redis.get.return_value = None
        mock_get_redis_client.return_value = mock_redis

        mock_read_sql_df.return_value = self._trend_rows_for_days([start.isoformat(), end.isoformat()])

        result = hold_history_service.get_hold_history_trend(start.isoformat(), end.isoformat())

        self.assertIsNotNone(result)
        self.assertEqual(len(result['days']), 2)
        self.assertEqual(result['days'][0]['all']['holdQty'], 14)
        self.assertEqual(mock_read_sql_df.call_count, 1)
        mock_redis.setex.assert_called_once()
        cache_key = mock_redis.setex.call_args.args[0]
        self.assertIn('hold_history:daily', cache_key)

    @patch('mes_dashboard.services.hold_history_service.read_sql_df')
    @patch('mes_dashboard.services.hold_history_service.get_redis_client')
    def test_trend_cross_month_assembly_from_cache(self, mock_get_redis_client, mock_read_sql_df):
        today = date.today()
        current_month_start = today.replace(day=1)
        previous_month_end = current_month_start - timedelta(days=1)

        start = previous_month_end - timedelta(days=1)
        end = current_month_start + timedelta(days=1)

        previous_cache = [
            {
                'date': start.strftime('%Y-%m-%d'),
                'quality': {'holdQty': 9, 'newHoldQty': 2, 'releaseQty': 1, 'futureHoldQty': 0},
                'non_quality': {'holdQty': 3, 'newHoldQty': 1, 'releaseQty': 0, 'futureHoldQty': 0},
                'all': {'holdQty': 12, 'newHoldQty': 3, 'releaseQty': 1, 'futureHoldQty': 0},
            },
            {
                'date': (start + timedelta(days=1)).strftime('%Y-%m-%d'),
                'quality': {'holdQty': 8, 'newHoldQty': 1, 'releaseQty': 2, 'futureHoldQty': 0},
                'non_quality': {'holdQty': 2, 'newHoldQty': 1, 'releaseQty': 1, 'futureHoldQty': 0},
                'all': {'holdQty': 10, 'newHoldQty': 2, 'releaseQty': 3, 'futureHoldQty': 0},
            },
        ]

        current_cache = [
            {
                'date': current_month_start.strftime('%Y-%m-%d'),
                'quality': {'holdQty': 7, 'newHoldQty': 2, 'releaseQty': 3, 'futureHoldQty': 1},
                'non_quality': {'holdQty': 2, 'newHoldQty': 1, 'releaseQty': 1, 'futureHoldQty': 0},
                'all': {'holdQty': 9, 'newHoldQty': 3, 'releaseQty': 4, 'futureHoldQty': 1},
            },
            {
                'date': (current_month_start + timedelta(days=1)).strftime('%Y-%m-%d'),
                'quality': {'holdQty': 6, 'newHoldQty': 1, 'releaseQty': 2, 'futureHoldQty': 0},
                'non_quality': {'holdQty': 1, 'newHoldQty': 1, 'releaseQty': 0, 'futureHoldQty': 0},
                'all': {'holdQty': 7, 'newHoldQty': 2, 'releaseQty': 2, 'futureHoldQty': 0},
            },
        ]

        mock_redis = MagicMock()
        mock_redis.get.side_effect = [json.dumps(previous_cache), json.dumps(current_cache)]
        mock_get_redis_client.return_value = mock_redis

        result = hold_history_service.get_hold_history_trend(start.isoformat(), end.isoformat())

        self.assertIsNotNone(result)
        self.assertEqual(len(result['days']), (end - start).days + 1)
        self.assertEqual(result['days'][0]['date'], start.isoformat())
        self.assertEqual(result['days'][-1]['date'], end.isoformat())
        self.assertEqual(result['days'][0]['all']['holdQty'], 12)
        self.assertEqual(result['days'][-1]['quality']['releaseQty'], 2)
        mock_read_sql_df.assert_not_called()

    @patch('mes_dashboard.services.hold_history_service.read_sql_df')
    @patch('mes_dashboard.services.hold_history_service.get_redis_client')
    def test_trend_older_month_queries_oracle_without_cache(self, mock_get_redis_client, mock_read_sql_df):
        today = date.today()
        current_month_start = today.replace(day=1)

        old_month_start = (current_month_start - timedelta(days=100)).replace(day=1)
        start = old_month_start
        end = old_month_start + timedelta(days=1)

        mock_redis = MagicMock()
        mock_get_redis_client.return_value = mock_redis

        mock_read_sql_df.return_value = self._trend_rows_for_days([start.isoformat(), end.isoformat()])

        result = hold_history_service.get_hold_history_trend(start.isoformat(), end.isoformat())

        self.assertIsNotNone(result)
        self.assertEqual(len(result['days']), 2)
        self.assertEqual(mock_read_sql_df.call_count, 1)
        mock_redis.get.assert_not_called()


class TestHoldHistoryServiceFunctions(unittest.TestCase):
    """Test non-trend service function formatting and behavior."""

    def setUp(self):
        hold_history_service._load_hold_history_sql.cache_clear()

    @patch('mes_dashboard.services.hold_history_service.read_sql_df')
    def test_reason_pareto_formats_response(self, mock_read_sql_df):
        mock_read_sql_df.return_value = pd.DataFrame(
            [
                {'REASON': '品質確認', 'ITEM_COUNT': 10, 'QTY': 2000, 'PCT': 40.0, 'CUM_PCT': 40.0},
                {'REASON': '工程驗證', 'ITEM_COUNT': 8, 'QTY': 1800, 'PCT': 32.0, 'CUM_PCT': 72.0},
            ]
        )

        result = hold_history_service.get_hold_history_reason_pareto('2026-02-01', '2026-02-07', 'quality')

        self.assertIsNotNone(result)
        self.assertEqual(len(result['items']), 2)
        self.assertEqual(result['items'][0]['reason'], '品質確認')
        self.assertEqual(result['items'][0]['count'], 10)
        self.assertEqual(result['items'][1]['cumPct'], 72.0)

    @patch('mes_dashboard.services.hold_history_service.read_sql_df')
    def test_reason_pareto_passes_record_type_flags(self, mock_read_sql_df):
        mock_read_sql_df.return_value = pd.DataFrame([])

        hold_history_service.get_hold_history_reason_pareto(
            '2026-02-01', '2026-02-07', 'quality', record_type='on_hold'
        )

        params = mock_read_sql_df.call_args.args[1]
        self.assertEqual(params['include_new'], 0)
        self.assertEqual(params['include_on_hold'], 1)
        self.assertEqual(params['include_released'], 0)

    @patch('mes_dashboard.services.hold_history_service.read_sql_df')
    def test_reason_pareto_multi_record_type_flags(self, mock_read_sql_df):
        mock_read_sql_df.return_value = pd.DataFrame([])

        hold_history_service.get_hold_history_reason_pareto(
            '2026-02-01', '2026-02-07', 'quality', record_type='on_hold,released'
        )

        params = mock_read_sql_df.call_args.args[1]
        self.assertEqual(params['include_new'], 0)
        self.assertEqual(params['include_on_hold'], 1)
        self.assertEqual(params['include_released'], 1)

    @patch('mes_dashboard.services.hold_history_service.read_sql_df')
    def test_reason_pareto_normalizes_invalid_hold_type(self, mock_read_sql_df):
        mock_read_sql_df.return_value = pd.DataFrame([])

        hold_history_service.get_hold_history_reason_pareto('2026-02-01', '2026-02-07', 'invalid')

        params = mock_read_sql_df.call_args.args[1]
        self.assertEqual(params['hold_type'], 'quality')

    @patch('mes_dashboard.services.hold_history_service.read_sql_df')
    def test_duration_formats_response(self, mock_read_sql_df):
        mock_read_sql_df.return_value = pd.DataFrame(
            [
                {'RANGE_LABEL': '<4h', 'ITEM_COUNT': 5, 'QTY': 500, 'PCT': 25.0},
                {'RANGE_LABEL': '4-24h', 'ITEM_COUNT': 7, 'QTY': 700, 'PCT': 35.0},
                {'RANGE_LABEL': '1-3d', 'ITEM_COUNT': 4, 'QTY': 400, 'PCT': 20.0},
                {'RANGE_LABEL': '>3d', 'ITEM_COUNT': 4, 'QTY': 400, 'PCT': 20.0},
            ]
        )

        result = hold_history_service.get_hold_history_duration('2026-02-01', '2026-02-07', 'quality')

        self.assertIsNotNone(result)
        self.assertEqual(len(result['items']), 4)
        self.assertEqual(result['items'][0]['range'], '<4h')
        self.assertEqual(result['items'][0]['qty'], 500)
        self.assertEqual(result['items'][1]['count'], 7)

    @patch('mes_dashboard.services.hold_history_service.read_sql_df')
    def test_duration_passes_record_type_flags(self, mock_read_sql_df):
        mock_read_sql_df.return_value = pd.DataFrame([])

        hold_history_service.get_hold_history_duration(
            '2026-02-01', '2026-02-07', 'quality', record_type='released'
        )

        params = mock_read_sql_df.call_args.args[1]
        self.assertEqual(params['include_new'], 0)
        self.assertEqual(params['include_on_hold'], 0)
        self.assertEqual(params['include_released'], 1)

    @patch('mes_dashboard.services.hold_history_service._get_wc_group')
    @patch('mes_dashboard.services.hold_history_service.read_sql_df')
    def test_list_formats_response_and_pagination(self, mock_read_sql_df, mock_wc_group):
        mock_wc_group.side_effect = lambda wc: {'WB': '焊接_WB', 'DB': '焊接_DB'}.get(wc)
        mock_read_sql_df.return_value = pd.DataFrame(
            [
                {
                    'LOT_ID': 'LOT001',
                    'WORKORDER': 'GA26010001',
                    'WORKCENTER': 'WB',
                    'HOLD_REASON': '品質確認',
                    'QTY': 250,
                    'HOLD_DATE': datetime(2026, 2, 1, 8, 30, 0),
                    'HOLD_EMP': '王小明',
                    'HOLD_COMMENT': '確認中',
                    'RELEASE_DATE': None,
                    'RELEASE_EMP': None,
                    'RELEASE_COMMENT': None,
                    'HOLD_HOURS': 12.345,
                    'NCR_ID': 'NCR-001',
                    'TOTAL_COUNT': 3,
                },
                {
                    'LOT_ID': 'LOT002',
                    'WORKORDER': 'GA26010002',
                    'WORKCENTER': 'DB',
                    'HOLD_REASON': '工程驗證',
                    'QTY': 100,
                    'HOLD_DATE': datetime(2026, 2, 1, 9, 10, 0),
                    'HOLD_EMP': '陳小華',
                    'HOLD_COMMENT': '待確認',
                    'RELEASE_DATE': datetime(2026, 2, 1, 12, 0, 0),
                    'RELEASE_EMP': '李主管',
                    'RELEASE_COMMENT': '已解除',
                    'HOLD_HOURS': 2.5,
                    'NCR_ID': None,
                    'TOTAL_COUNT': 3,
                },
            ]
        )

        result = hold_history_service.get_hold_history_list(
            start_date='2026-02-01',
            end_date='2026-02-07',
            hold_type='quality',
            reason=None,
            page=1,
            per_page=2,
        )

        self.assertIsNotNone(result)
        self.assertEqual(len(result['items']), 2)
        self.assertEqual(result['items'][0]['workcenter'], '焊接_WB')
        self.assertEqual(result['items'][1]['workcenter'], '焊接_DB')
        self.assertEqual(result['items'][0]['qty'], 250)
        self.assertEqual(result['items'][1]['qty'], 100)
        self.assertEqual(result['items'][0]['releaseDate'], None)
        self.assertEqual(result['items'][0]['holdHours'], 12.35)
        self.assertEqual(result['pagination']['total'], 3)
        self.assertEqual(result['pagination']['totalPages'], 2)

    def test_trend_sql_contains_shift_boundary_logic(self):
        sql = hold_history_service._load_hold_history_sql('trend')

        self.assertIn('0730', sql)
        self.assertIn('ROW_NUMBER', sql)
        self.assertIn('FUTUREHOLDCOMMENTS', sql)


if __name__ == '__main__':  # pragma: no cover
    unittest.main()
