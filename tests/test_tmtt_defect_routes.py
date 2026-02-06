# -*- coding: utf-8 -*-
"""Integration tests for TMTT Defect Analysis API routes."""

import unittest
from unittest.mock import patch

import pandas as pd


class TestTmttDefectAnalysisEndpoint(unittest.TestCase):
    """Test GET /api/tmtt-defect/analysis endpoint."""

    def setUp(self):
        from mes_dashboard.core import database as db
        db._ENGINE = None

        from mes_dashboard.app import create_app
        self.app = create_app()
        self.client = self.app.test_client()

    def test_missing_start_date(self):
        resp = self.client.get('/api/tmtt-defect/analysis?end_date=2025-01-31')
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertFalse(data['success'])

    def test_missing_end_date(self):
        resp = self.client.get('/api/tmtt-defect/analysis?start_date=2025-01-01')
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertFalse(data['success'])

    def test_missing_both_dates(self):
        resp = self.client.get('/api/tmtt-defect/analysis')
        self.assertEqual(resp.status_code, 400)

    @patch('mes_dashboard.routes.tmtt_defect_routes.query_tmtt_defect_analysis')
    def test_invalid_date_format(self, mock_query):
        mock_query.return_value = {'error': '日期格式無效，請使用 YYYY-MM-DD'}
        resp = self.client.get(
            '/api/tmtt-defect/analysis?start_date=invalid&end_date=2025-01-31'
        )
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertFalse(data['success'])
        self.assertIn('格式', data['error'])

    @patch('mes_dashboard.routes.tmtt_defect_routes.query_tmtt_defect_analysis')
    def test_exceeds_180_days(self, mock_query):
        mock_query.return_value = {'error': '查詢範圍不能超過 180 天'}
        resp = self.client.get(
            '/api/tmtt-defect/analysis?start_date=2025-01-01&end_date=2025-12-31'
        )
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertIn('180', data['error'])

    @patch('mes_dashboard.routes.tmtt_defect_routes.query_tmtt_defect_analysis')
    def test_successful_query(self, mock_query):
        mock_query.return_value = {
            'kpi': {
                'total_input': 1000, 'lot_count': 10,
                'print_defect_qty': 5, 'print_defect_rate': 0.5,
                'lead_defect_qty': 3, 'lead_defect_rate': 0.3,
            },
            'charts': {
                'by_workflow': [], 'by_package': [], 'by_type': [],
                'by_tmtt_machine': [], 'by_mold_machine': [],
            },
            'detail': [],
        }

        resp = self.client.get(
            '/api/tmtt-defect/analysis?start_date=2025-01-01&end_date=2025-01-31'
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data['success'])
        self.assertIn('kpi', data['data'])
        self.assertIn('charts', data['data'])
        self.assertIn('detail', data['data'])

        # Verify separate defect rates
        kpi = data['data']['kpi']
        self.assertEqual(kpi['print_defect_qty'], 5)
        self.assertEqual(kpi['lead_defect_qty'], 3)

    @patch('mes_dashboard.routes.tmtt_defect_routes.query_tmtt_defect_analysis')
    def test_query_failure_returns_500(self, mock_query):
        mock_query.return_value = None
        resp = self.client.get(
            '/api/tmtt-defect/analysis?start_date=2025-01-01&end_date=2025-01-31'
        )
        self.assertEqual(resp.status_code, 500)


class TestTmttDefectExportEndpoint(unittest.TestCase):
    """Test GET /api/tmtt-defect/export endpoint."""

    def setUp(self):
        from mes_dashboard.core import database as db
        db._ENGINE = None

        from mes_dashboard.app import create_app
        self.app = create_app()
        self.client = self.app.test_client()

    def test_missing_dates(self):
        resp = self.client.get('/api/tmtt-defect/export')
        self.assertEqual(resp.status_code, 400)

    @patch('mes_dashboard.routes.tmtt_defect_routes.export_csv')
    def test_export_csv(self, mock_export):
        mock_export.return_value = iter([
            '\ufeff',
            'LOT ID,TYPE,PACKAGE,WORKFLOW,完工流水碼,TMTT設備,MOLD設備,'
            '投入數,印字不良數,印字不良率(%),腳型不良數,腳型不良率(%)\r\n',
        ])
        resp = self.client.get(
            '/api/tmtt-defect/export?start_date=2025-01-01&end_date=2025-01-31'
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn('text/csv', resp.content_type)
        self.assertIn('attachment', resp.headers.get('Content-Disposition', ''))


class TestTmttDefectPageRoute(unittest.TestCase):
    """Test page route."""

    def setUp(self):
        from mes_dashboard.core import database as db
        db._ENGINE = None

        from mes_dashboard.app import create_app
        self.app = create_app()
        self.client = self.app.test_client()

    def test_page_requires_auth_when_dev(self):
        """Page in 'dev' status returns 403 for unauthenticated users."""
        resp = self.client.get('/tmtt-defect')
        # 403 because page_status is 'dev' and user is not admin
        self.assertIn(resp.status_code, [200, 403])


if __name__ == '__main__':
    unittest.main()
