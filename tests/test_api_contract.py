# -*- coding: utf-8 -*-
"""API contract verification tests.

Enforces:
1. Health endpoints maintain top-level payload (no envelope wrapping)
2. Standard-JSON scope (wip_routes.py) has zero manual jsonify calls
3. Legacy jsonify count in routes/ does not exceed baseline

These tests serve as regression guardrails for the API contract unification
migration (openspec/changes/api-contract-unification).
"""

import ast
import os
import unittest
from pathlib import Path
from unittest.mock import patch
import json

from mes_dashboard.app import create_app
import mes_dashboard.core.database as db

ROUTES_DIR = Path(__file__).parent.parent / "src" / "mes_dashboard" / "routes"

# Baseline jsonify count per file captured at start of Wave A.
# This count MUST NOT increase (it may decrease as migration progresses).
_JSONIFY_BASELINE = {
    "admin_routes.py": 36,
    "dashboard_routes.py": 11,
    "hold_history_routes.py": 12,
    "hold_overview_routes.py": 14,
    "hold_routes.py": 11,
    "job_query_routes.py": 19,
    "material_trace_routes.py": 12,
    "mid_section_defect_routes.py": 13,
    "qc_gate_routes.py": 3,
    "query_tool_routes.py": 55,
    "reject_history_routes.py": 66,
    "resource_history_routes.py": 12,
    "resource_routes.py": 25,
    "trace_routes.py": 14,
    "yield_alert_routes.py": 54,
    # wip_routes.py is intentionally absent: Wave A target is 0 (enforced below)
}


def _count_jsonify_in_file(path: Path) -> int:
    """Count 'jsonify' identifier usages in a Python source file."""
    try:
        source = path.read_text(encoding="utf-8")
    except OSError:
        return 0
    count = 0
    try:
        tree = ast.parse(source)
    except SyntaxError:
        # Fallback to text search
        return source.count("jsonify")
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == "jsonify":
            count += 1
        elif isinstance(node, ast.Attribute) and node.attr == "jsonify":
            count += 1
    return count


class TestWipRoutesContractCompliance(unittest.TestCase):
    """Wave A contract: wip_routes.py must have zero manual jsonify calls."""

    def test_wip_routes_has_no_manual_jsonify(self):
        """wip_routes.py must use helpers exclusively — no manual jsonify."""
        wip_file = ROUTES_DIR / "wip_routes.py"
        count = _count_jsonify_in_file(wip_file)
        self.assertEqual(
            count,
            0,
            f"wip_routes.py still has {count} manual jsonify call(s). "
            "Use success_response/validation_error/not_found_error/internal_error instead."
        )


class TestJsonifyBaselineRegression(unittest.TestCase):
    """Migration trend: jsonify counts in routes/ must not exceed baseline."""

    def test_jsonify_count_does_not_exceed_baseline(self):
        """No route file should gain new manual jsonify calls above its baseline."""
        regressions = []
        for filename, baseline in _JSONIFY_BASELINE.items():
            path = ROUTES_DIR / filename
            if not path.exists():
                continue
            current = _count_jsonify_in_file(path)
            if current > baseline:
                regressions.append(
                    f"{filename}: baseline={baseline}, current={current} (+{current - baseline})"
                )
        self.assertEqual(
            regressions,
            [],
            "jsonify count regression detected (counts increased above baseline):\n"
            + "\n".join(regressions)
        )


class TestHealthEndpointContractException(unittest.TestCase):
    """Health endpoints must maintain top-level payload — never wrapped in envelope."""

    def setUp(self):
        db._ENGINE = None
        self.app = create_app('testing')
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()

    @patch('mes_dashboard.routes.health_routes.check_database', return_value=('ok', None))
    @patch('mes_dashboard.routes.health_routes.check_redis', return_value=('ok', None))
    def test_health_returns_top_level_status_not_envelope(self, _mock_redis, _mock_db):
        """GET /health must return top-level 'status' field, not { success, data, meta }."""
        response = self.client.get('/health')
        data = json.loads(response.data)

        # Must NOT be success/data/meta envelope
        self.assertNotIn(
            'success', data,
            "/health response must NOT use the standard { success, data, meta } envelope"
        )
        self.assertNotIn(
            'data', data,
            "/health response must NOT wrap payload under 'data' key"
        )
        # Must have top-level status
        self.assertIn('status', data)
        self.assertIn(data['status'], ('healthy', 'degraded', 'unhealthy'))

    @patch('mes_dashboard.routes.health_routes.check_database', return_value=('ok', None))
    @patch('mes_dashboard.routes.health_routes.check_redis', return_value=('ok', None))
    def test_health_returns_services_at_top_level(self, _mock_redis, _mock_db):
        """GET /health must include 'services' at top level."""
        response = self.client.get('/health')
        data = json.loads(response.data)
        self.assertIn('services', data)

    def test_health_frontend_shell_returns_top_level_status(self):
        """GET /health/frontend-shell must return top-level 'status', not envelope."""
        response = self.client.get('/health/frontend-shell')
        data = json.loads(response.data)

        self.assertNotIn(
            'success', data,
            "/health/frontend-shell must NOT use the standard envelope"
        )
        self.assertIn('status', data)
        self.assertIn(data['status'], ('healthy', 'unhealthy'))


class TestStandardJsonEnvelopeShape(unittest.TestCase):
    """Verify wip_routes.py responses conform to the standard envelope contract."""

    def setUp(self):
        db._ENGINE = None
        self.app = create_app('testing')
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()

    @patch('mes_dashboard.routes.wip_routes.get_wip_summary')
    def test_success_response_has_standard_envelope(self, mock_fn):
        """Success responses must have { success: true, data: ..., meta: { timestamp } }."""
        mock_fn.return_value = {'totalLots': 0, 'totalQtyPcs': 0, 'byWipStatus': {}, 'dataUpdateDate': None}
        response = self.client.get('/api/wip/overview/summary')
        data = json.loads(response.data)

        self.assertTrue(data['success'])
        self.assertIn('data', data)
        self.assertIn('meta', data)
        self.assertIn('timestamp', data['meta'])

    def test_validation_error_has_standard_error_envelope(self):
        """Validation error responses must have { success: false, error: { code, message }, meta }."""
        response = self.client.get('/api/wip/overview/matrix?status=INVALID')
        data = json.loads(response.data)

        self.assertFalse(data['success'])
        self.assertIsInstance(data['error'], dict)
        self.assertIn('code', data['error'])
        self.assertIn('message', data['error'])
        self.assertIn('meta', data)
        self.assertIn('timestamp', data['meta'])

    @patch('mes_dashboard.routes.wip_routes.get_lot_detail')
    def test_not_found_error_has_standard_error_envelope(self, mock_fn):
        """Not-found responses must have { success: false, error: { code, message }, meta }."""
        mock_fn.return_value = None
        response = self.client.get('/api/wip/lot/NONEXISTENT-LOT')
        data = json.loads(response.data)

        self.assertEqual(response.status_code, 404)
        self.assertFalse(data['success'])
        self.assertEqual(data['error']['code'], 'NOT_FOUND')
        self.assertIn('timestamp', data['meta'])

    @patch('mes_dashboard.routes.wip_routes.get_wip_summary')
    def test_internal_error_has_standard_error_envelope(self, mock_fn):
        """Internal error responses must have { success: false, error: { code, message }, meta }."""
        mock_fn.return_value = None
        response = self.client.get('/api/wip/overview/summary')
        data = json.loads(response.data)

        self.assertEqual(response.status_code, 500)
        self.assertFalse(data['success'])
        self.assertEqual(data['error']['code'], 'INTERNAL_ERROR')
        self.assertIn('timestamp', data['meta'])


if __name__ == "__main__":
    unittest.main()
