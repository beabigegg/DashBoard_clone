# -*- coding: utf-8 -*-
"""Unit tests for template integration with _base.html.

Verifies that all templates properly extend _base.html and include
required core JavaScript resources.
"""

import unittest
import os
from unittest.mock import patch

from mes_dashboard.app import create_app
import mes_dashboard.core.database as db


def _login_as_admin(client):
    with client.session_transaction() as sess:
        sess['admin'] = {'displayName': 'Test Admin', 'employeeNo': 'A001'}


class TestTemplateIntegration(unittest.TestCase):
    """Test that all templates properly extend _base.html."""

    def setUp(self):
        self._old_portal_spa = os.environ.get("PORTAL_SPA_ENABLED")
        os.environ["PORTAL_SPA_ENABLED"] = "false"
        db._ENGINE = None
        self.app = create_app('testing')
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()
        _login_as_admin(self.client)

    def tearDown(self):
        if self._old_portal_spa is None:
            os.environ.pop("PORTAL_SPA_ENABLED", None)
        else:
            os.environ["PORTAL_SPA_ENABLED"] = self._old_portal_spa

    def test_portal_includes_base_scripts(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')

        self.assertIn('toast.js', html)
        self.assertIn('mes-api.js', html)
        self.assertIn('mes-toast-container', html)

    def test_wip_overview_serves_pure_vite_module(self):
        response = self.client.get('/wip-overview')
        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')

        self.assertIn('/static/dist/wip-overview.js', html)
        self.assertIn('type="module"', html)
        self.assertNotIn('mes-toast-container', html)

    def test_wip_detail_serves_pure_vite_module(self):
        response = self.client.get('/wip-detail')
        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')

        self.assertIn('/static/dist/wip-detail.js', html)
        self.assertIn('type="module"', html)
        self.assertNotIn('mes-toast-container', html)

    def test_hold_overview_serves_pure_vite_module(self):
        response = self.client.get('/hold-overview')
        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')

        self.assertIn('/static/dist/hold-overview.js', html)
        self.assertIn('type="module"', html)
        self.assertNotIn('mes-toast-container', html)

    def test_tables_page_serves_pure_vite_module(self):
        response = self.client.get('/tables')
        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')

        self.assertIn('/static/dist/tables.js', html)
        self.assertIn('type="module"', html)
        self.assertNotIn('mes-toast-container', html)

    def test_resource_page_serves_pure_vite_module(self):
        response = self.client.get('/resource')
        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')

        self.assertIn('/static/dist/resource-status.js', html)
        self.assertIn('type="module"', html)
        self.assertNotIn('mes-toast-container', html)

    def test_excel_query_page_includes_base_scripts(self):
        response = self.client.get('/excel-query')
        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')

        self.assertIn('toast.js', html)
        self.assertIn('mes-api.js', html)
        self.assertIn('mes-toast-container', html)

    def test_query_tool_page_includes_base_scripts(self):
        response = self.client.get('/query-tool')
        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')

        self.assertIn('toast.js', html)
        self.assertIn('mes-api.js', html)
        self.assertIn('mes-toast-container', html)

    def test_tmtt_defect_page_includes_base_scripts(self):
        response = self.client.get('/tmtt-defect')
        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')

        self.assertIn('toast.js', html)
        self.assertIn('mes-api.js', html)
        self.assertIn('mes-toast-container', html)


class TestPortalDynamicDrawerRendering(unittest.TestCase):
    """Test dynamic portal drawer rendering."""

    def setUp(self):
        self._old_portal_spa = os.environ.get("PORTAL_SPA_ENABLED")
        os.environ["PORTAL_SPA_ENABLED"] = "false"
        db._ENGINE = None
        self.app = create_app('testing')
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()
        _login_as_admin(self.client)

    def tearDown(self):
        if self._old_portal_spa is None:
            os.environ.pop("PORTAL_SPA_ENABLED", None)
        else:
            os.environ["PORTAL_SPA_ENABLED"] = self._old_portal_spa

    def test_portal_uses_navigation_config_for_sidebar_links_without_iframe(self):
        drawers = [
            {
                "id": "custom",
                "name": "自訂分類",
                "order": 1,
                "admin_only": False,
                "pages": [
                    {
                        "route": "/wip-overview",
                        "name": "自訂首頁",
                        "status": "released",
                        "order": 1,
                    }
                ],
            },
            {
                "id": "dev-tools",
                "name": "開發工具",
                "order": 2,
                "admin_only": True,
                "pages": [
                    {
                        "route": "/admin/pages",
                        "name": "頁面管理",
                        "status": "dev",
                        "order": 1,
                    }
                ],
            },
        ]
        with patch("mes_dashboard.app.get_navigation_config", return_value=drawers):
            response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        html = response.data.decode("utf-8")
        self.assertIn("自訂分類", html)
        self.assertIn('href="/wip-overview"', html)
        self.assertIn('data-route="/wip-overview"', html)
        self.assertIn('href="/admin/pages"', html)
        self.assertIn('data-route="/admin/pages"', html)
        self.assertNotIn("<iframe", html)

    def test_portal_hides_admin_only_drawer_for_non_admin(self):
        client = self.app.test_client()
        drawers = [
            {
                "id": "custom",
                "name": "自訂分類",
                "order": 1,
                "admin_only": False,
                "pages": [
                    {
                        "route": "/wip-overview",
                        "name": "自訂首頁",
                        "status": "released",
                        "order": 1,
                    }
                ],
            },
            {
                "id": "dev-tools",
                "name": "開發工具",
                "order": 2,
                "admin_only": True,
                "pages": [
                    {
                        "route": "/admin/pages",
                        "name": "頁面管理",
                        "status": "dev",
                        "order": 1,
                    }
                ],
            },
        ]
        with patch("mes_dashboard.app.get_navigation_config", return_value=drawers):
            response = client.get("/")

        self.assertEqual(response.status_code, 200)
        html = response.data.decode("utf-8")
        self.assertIn("自訂分類", html)
        self.assertNotIn("開發工具", html)
        self.assertNotIn('href="/admin/pages"', html)
        self.assertNotIn("<iframe", html)


class TestToastCSSIntegration(unittest.TestCase):
    """Test that Toast CSS styles are included in pages."""

    def setUp(self):
        self._old_portal_spa = os.environ.get("PORTAL_SPA_ENABLED")
        os.environ["PORTAL_SPA_ENABLED"] = "false"
        db._ENGINE = None
        self.app = create_app('testing')
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()
        _login_as_admin(self.client)

    def tearDown(self):
        if self._old_portal_spa is None:
            os.environ.pop("PORTAL_SPA_ENABLED", None)
        else:
            os.environ["PORTAL_SPA_ENABLED"] = self._old_portal_spa

    def test_portal_includes_toast_css(self):
        response = self.client.get('/')
        html = response.data.decode('utf-8')

        self.assertIn('.mes-toast-container', html)
        self.assertIn('.mes-toast', html)

    def test_wip_overview_excludes_toast_css(self):
        response = self.client.get('/wip-overview')
        html = response.data.decode('utf-8')

        self.assertNotIn('.mes-toast-container', html)
        self.assertNotIn('.mes-toast', html)

    def test_wip_detail_excludes_toast_css(self):
        response = self.client.get('/wip-detail')
        html = response.data.decode('utf-8')

        self.assertNotIn('.mes-toast-container', html)
        self.assertNotIn('.mes-toast', html)


class TestMesApiUsageInTemplates(unittest.TestCase):
    """Test that templates either inline MesApi usage or load Vite modules."""

    def setUp(self):
        db._ENGINE = None
        self.app = create_app('testing')
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()
        _login_as_admin(self.client)

    def test_wip_overview_uses_mesapi(self):
        response = self.client.get('/wip-overview')
        html = response.data.decode('utf-8')

        self.assertTrue('MesApi.get' in html or '/static/dist/wip-overview.js' in html)
        self.assertNotIn('fetchWithTimeout', html)

    def test_wip_detail_uses_mesapi(self):
        response = self.client.get('/wip-detail')
        html = response.data.decode('utf-8')

        self.assertTrue('MesApi.get' in html or '/static/dist/wip-detail.js' in html)
        self.assertNotIn('fetchWithTimeout', html)

    def test_tables_page_uses_mesapi_or_vite_module(self):
        response = self.client.get('/tables')
        html = response.data.decode('utf-8')

        self.assertTrue('MesApi.post' in html or '/static/dist/tables.js' in html)

    def test_resource_page_uses_mesapi_or_vite_module(self):
        response = self.client.get('/resource')
        html = response.data.decode('utf-8')

        self.assertTrue(
            'MesApi.post' in html or
            'MesApi.get' in html or
            '/static/dist/resource-status.js' in html
        )

    def test_query_tool_page_uses_vite_module(self):
        response = self.client.get('/query-tool')
        html = response.data.decode('utf-8')

        self.assertIn('/static/dist/query-tool.js', html)
        self.assertIn('type="module"', html)

    def test_tmtt_defect_page_uses_vite_module(self):
        response = self.client.get('/tmtt-defect')
        html = response.data.decode('utf-8')

        self.assertIn('/static/dist/tmtt-defect.js', html)
        self.assertIn('type="module"', html)


class TestViteModuleIntegration(unittest.TestCase):
    """Ensure page templates render Vite module assets."""

    def setUp(self):
        db._ENGINE = None
        self.app = create_app('testing')
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()
        _login_as_admin(self.client)

    def test_pages_render_vite_module_reference(self):
        endpoints_and_assets = [
            ('/wip-overview', 'wip-overview.js'),
            ('/wip-detail', 'wip-detail.js'),
            ('/hold-overview', 'hold-overview.js'),
            ('/hold-detail?reason=test-reason', 'hold-detail.js'),
            ('/tables', 'tables.js'),
            ('/resource', 'resource-status.js'),
            ('/resource-history', 'resource-history.js'),
            ('/job-query', 'job-query.js'),
            ('/excel-query', 'excel-query.js'),
            ('/query-tool', 'query-tool.js'),
            ('/tmtt-defect', 'tmtt-defect.js'),
        ]
        for endpoint, asset in endpoints_and_assets:
            with patch('mes_dashboard.app.os.path.exists', return_value=False):
                response = self.client.get(endpoint)
            self.assertEqual(response.status_code, 200)
            html = response.data.decode('utf-8')
            self.assertIn(f'/static/dist/{asset}', html)
            self.assertIn('type="module"', html)


class TestStaticFilesServing(unittest.TestCase):
    """Test that static JavaScript files are served correctly."""

    def setUp(self):
        db._ENGINE = None
        self.app = create_app('testing')
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()
        _login_as_admin(self.client)

    def test_toast_js_is_served(self):
        response = self.client.get('/static/js/toast.js')
        self.assertEqual(response.status_code, 200)
        content = response.data.decode('utf-8')

        self.assertIn('Toast', content)
        self.assertIn('info', content)
        self.assertIn('success', content)
        self.assertIn('error', content)
        self.assertIn('loading', content)

    def test_mes_api_js_is_served(self):
        response = self.client.get('/static/js/mes-api.js')
        self.assertEqual(response.status_code, 200)
        content = response.data.decode('utf-8')

        self.assertIn('MesApi', content)
        self.assertIn('get', content)
        self.assertIn('post', content)
        self.assertIn('AbortController', content)

    def test_toast_js_contains_retry_button(self):
        response = self.client.get('/static/js/toast.js')
        content = response.data.decode('utf-8')

        self.assertIn('retry', content)
        self.assertIn('mes-toast-retry', content)

    def test_mes_api_js_has_exponential_backoff(self):
        response = self.client.get('/static/js/mes-api.js')
        content = response.data.decode('utf-8')

        self.assertIn('1000', content)
        self.assertIn('retry', content.lower())


if __name__ == "__main__":
    unittest.main()
