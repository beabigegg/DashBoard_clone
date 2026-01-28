# -*- coding: utf-8 -*-
"""Unit tests for template integration with _base.html.

Verifies that all templates properly extend _base.html and include
the required MesApi and Toast JavaScript modules.
"""

import unittest
from unittest.mock import patch

from mes_dashboard.app import create_app
import mes_dashboard.core.database as db


class TestTemplateIntegration(unittest.TestCase):
    """Test that all templates properly extend _base.html."""

    def setUp(self):
        """Set up test client."""
        db._ENGINE = None
        self.app = create_app('testing')
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()

    def test_portal_includes_base_scripts(self):
        """Portal page should include toast.js and mes-api.js."""
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')

        self.assertIn('toast.js', html)
        self.assertIn('mes-api.js', html)
        self.assertIn('mes-toast-container', html)

    def test_wip_overview_includes_base_scripts(self):
        """WIP Overview page should include toast.js and mes-api.js."""
        response = self.client.get('/wip-overview')
        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')

        self.assertIn('toast.js', html)
        self.assertIn('mes-api.js', html)
        self.assertIn('mes-toast-container', html)

    def test_wip_detail_includes_base_scripts(self):
        """WIP Detail page should include toast.js and mes-api.js."""
        response = self.client.get('/wip-detail')
        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')

        self.assertIn('toast.js', html)
        self.assertIn('mes-api.js', html)
        self.assertIn('mes-toast-container', html)

    def test_tables_page_includes_base_scripts(self):
        """Tables page should include toast.js and mes-api.js."""
        response = self.client.get('/tables')
        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')

        self.assertIn('toast.js', html)
        self.assertIn('mes-api.js', html)
        self.assertIn('mes-toast-container', html)

    def test_resource_page_includes_base_scripts(self):
        """Resource status page should include toast.js and mes-api.js."""
        response = self.client.get('/resource')
        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')

        self.assertIn('toast.js', html)
        self.assertIn('mes-api.js', html)
        self.assertIn('mes-toast-container', html)

    def test_excel_query_page_includes_base_scripts(self):
        """Excel Query page should include toast.js and mes-api.js."""
        response = self.client.get('/excel-query')
        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')

        self.assertIn('toast.js', html)
        self.assertIn('mes-api.js', html)
        self.assertIn('mes-toast-container', html)


class TestToastCSSIntegration(unittest.TestCase):
    """Test that Toast CSS styles are included in all pages."""

    def setUp(self):
        """Set up test client."""
        db._ENGINE = None
        self.app = create_app('testing')
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()

    def test_portal_includes_toast_css(self):
        """Portal page should include Toast CSS styles."""
        response = self.client.get('/')
        html = response.data.decode('utf-8')

        # Check for Toast CSS class definitions
        self.assertIn('.mes-toast-container', html)
        self.assertIn('.mes-toast', html)

    def test_wip_overview_includes_toast_css(self):
        """WIP Overview page should include Toast CSS styles."""
        response = self.client.get('/wip-overview')
        html = response.data.decode('utf-8')

        self.assertIn('.mes-toast-container', html)
        self.assertIn('.mes-toast', html)

    def test_wip_detail_includes_toast_css(self):
        """WIP Detail page should include Toast CSS styles."""
        response = self.client.get('/wip-detail')
        html = response.data.decode('utf-8')

        self.assertIn('.mes-toast-container', html)
        self.assertIn('.mes-toast', html)


class TestMesApiUsageInTemplates(unittest.TestCase):
    """Test that templates use MesApi for API calls."""

    def setUp(self):
        """Set up test client."""
        db._ENGINE = None
        self.app = create_app('testing')
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()

    def test_wip_overview_uses_mesapi(self):
        """WIP Overview should use MesApi.get() for API calls."""
        response = self.client.get('/wip-overview')
        html = response.data.decode('utf-8')

        self.assertIn('MesApi.get', html)
        # Should NOT contain raw fetch() for API calls
        # (checking it doesn't have the old fetchWithTimeout pattern)
        self.assertNotIn('fetchWithTimeout', html)

    def test_wip_detail_uses_mesapi(self):
        """WIP Detail should use MesApi.get() for API calls."""
        response = self.client.get('/wip-detail')
        html = response.data.decode('utf-8')

        self.assertIn('MesApi.get', html)
        self.assertNotIn('fetchWithTimeout', html)

    def test_tables_page_uses_mesapi(self):
        """Tables page should use MesApi.post() for API calls."""
        response = self.client.get('/tables')
        html = response.data.decode('utf-8')

        self.assertIn('MesApi.post', html)

    def test_resource_page_uses_mesapi(self):
        """Resource status page should use MesApi.post() for API calls."""
        response = self.client.get('/resource')
        html = response.data.decode('utf-8')

        self.assertIn('MesApi.post', html)


class TestStaticFilesServing(unittest.TestCase):
    """Test that static JavaScript files are served correctly."""

    def setUp(self):
        """Set up test client."""
        db._ENGINE = None
        self.app = create_app('testing')
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()

    def test_toast_js_is_served(self):
        """toast.js should be served from static directory."""
        response = self.client.get('/static/js/toast.js')
        self.assertEqual(response.status_code, 200)
        content = response.data.decode('utf-8')

        # Verify it's the Toast module
        self.assertIn('Toast', content)
        self.assertIn('info', content)
        self.assertIn('success', content)
        self.assertIn('error', content)
        self.assertIn('loading', content)

    def test_mes_api_js_is_served(self):
        """mes-api.js should be served from static directory."""
        response = self.client.get('/static/js/mes-api.js')
        self.assertEqual(response.status_code, 200)
        content = response.data.decode('utf-8')

        # Verify it's the MesApi module
        self.assertIn('MesApi', content)
        self.assertIn('get', content)
        self.assertIn('post', content)
        self.assertIn('AbortController', content)

    def test_toast_js_contains_retry_button(self):
        """toast.js should support retry button for errors."""
        response = self.client.get('/static/js/toast.js')
        content = response.data.decode('utf-8')

        self.assertIn('retry', content)
        self.assertIn('mes-toast-retry', content)

    def test_mes_api_js_has_exponential_backoff(self):
        """mes-api.js should implement exponential backoff."""
        response = self.client.get('/static/js/mes-api.js')
        content = response.data.decode('utf-8')

        # Check for retry delay calculation (1000, 2000, 4000)
        self.assertIn('1000', content)
        self.assertIn('retry', content.lower())


if __name__ == "__main__":
    unittest.main()
