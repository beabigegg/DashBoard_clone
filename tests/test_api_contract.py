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


class TestEnvelopeRuntimeSweep(unittest.TestCase):
    """Runtime sweep: call every registered API route and assert envelope shape."""

    def setUp(self):
        db._ENGINE = None
        self.app = create_app('testing')
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()

    def _assert_envelope(self, data: dict, url: str):
        """Assert standard { success, data|error, meta } envelope."""
        self.assertIn(
            'success', data,
            f"{url} response missing 'success' field"
        )
        self.assertIn(
            'meta', data,
            f"{url} response missing 'meta' field"
        )
        self.assertIn(
            'timestamp', data.get('meta', {}),
            f"{url} meta missing 'timestamp'"
        )
        if data.get('success'):
            self.assertIn(
                'data', data,
                f"{url} success response missing 'data' field"
            )
        else:
            self.assertIn(
                'error', data,
                f"{url} error response missing 'error' field"
            )
            error = data['error']
            self.assertIn(
                'code', error,
                f"{url} error missing 'code'"
            )
            self.assertIn(
                'message', error,
                f"{url} error missing 'message'"
            )

    def _resolve_url(self, pattern: str, method: str, params: dict | None) -> tuple[str, str | None]:
        """Resolve a URL pattern to a callable URL, substituting path params."""
        import re
        url = pattern
        url = re.sub(r'<[^>]+>', 'TEST_ID', url)
        if method == 'GET' and params:
            from urllib.parse import urlencode
            url = f"{url}?{urlencode(params)}"
        return url

    def test_envelope_runtime_sweep(self):
        """Iterate matrix entries and assert envelope shape for each callable route."""
        from tests.fixtures.route_contract_matrix import (
            ROUTE_CONTRACT_MATRIX,
            SKIP_RUNTIME_SWEEP,
        )

        failures = []

        for pattern, method, params, expected_shape in ROUTE_CONTRACT_MATRIX:
            if pattern in SKIP_RUNTIME_SWEEP:
                continue
            if expected_shape in ('non_json', 'streaming'):
                continue

            url = self._resolve_url(pattern, method, params)

            try:
                if method == 'GET':
                    resp = self.client.get(url)
                elif method == 'POST':
                    resp = self.client.post(
                        url,
                        data=json.dumps(params or {}),
                        content_type='application/json',
                    )
                elif method == 'PATCH':
                    resp = self.client.patch(
                        url,
                        data=json.dumps(params or {}),
                        content_type='application/json',
                    )
                else:
                    continue

                if resp.content_type and 'application/json' in resp.content_type:
                    data = json.loads(resp.data)
                    if 'success' not in data:
                        failures.append(
                            f"{method} {pattern} ({url}): response missing 'success' field"
                        )
                        continue
                    if 'meta' not in data:
                        failures.append(
                            f"{method} {pattern} ({url}): response missing 'meta' field"
                        )
                        continue
                    if 'timestamp' not in data.get('meta', {}):
                        failures.append(
                            f"{method} {pattern} ({url}): meta missing 'timestamp'"
                        )

            except Exception as e:
                failures.append(f"{method} {pattern}: unexpected exception: {e}")

        self.assertEqual(
            failures,
            [],
            "Envelope sweep failures:\n" + "\n".join(failures)
        )


class TestRouteMatrixComplete(unittest.TestCase):
    """Verify every registered route has a matrix entry or is explicitly skipped."""

    def setUp(self):
        db._ENGINE = None
        self.app = create_app('testing')

    def test_route_matrix_complete(self):
        """Every registered Flask route must appear in ROUTE_CONTRACT_MATRIX or SKIP_RUNTIME_SWEEP."""
        from tests.fixtures.route_contract_matrix import (
            ROUTE_CONTRACT_MATRIX,
            SKIP_RUNTIME_SWEEP,
            NON_ENVELOPED_ENDPOINTS,
        )

        matrix_patterns = {entry[0] for entry in ROUTE_CONTRACT_MATRIX}
        covered = matrix_patterns | set(SKIP_RUNTIME_SWEEP) | set(NON_ENVELOPED_ENDPOINTS)

        # Non-API routes that are intentionally outside the matrix
        EXCLUDED_PREFIXES = ('/', '/static', '/portal-shell', '/admin')
        EXCLUDED_EXACT = {
            '/favicon.ico',
        }

        missing = []
        for rule in self.app.url_map.iter_rules():
            pattern = str(rule)
            # Skip non-API, static, and HTML page routes
            if not pattern.startswith('/api') and not pattern.startswith('/health'):
                continue
            if pattern in EXCLUDED_EXACT:
                continue
            if any(pattern.startswith(p) for p in EXCLUDED_PREFIXES if p != '/api'):
                continue
            if pattern not in covered:
                missing.append(pattern)

        self.assertEqual(
            missing,
            [],
            "Routes missing from contract matrix (add to ROUTE_CONTRACT_MATRIX or SKIP_RUNTIME_SWEEP):\n"
            + "\n".join(sorted(missing))
        )


class TestErrorEnvelopeCodesInAllowlist(unittest.TestCase):
    """Verify error responses use predefined error codes."""

    def setUp(self):
        db._ENGINE = None
        self.app = create_app('testing')
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()

    def test_error_codes_are_defined_constants(self):
        """All error code constants must be non-empty strings."""
        from mes_dashboard.core.response import (
            DB_CONNECTION_FAILED,
            DB_QUERY_TIMEOUT,
            DB_QUERY_ERROR,
            DB_POOL_EXHAUSTED,
            SERVICE_UNAVAILABLE,
            CIRCUIT_BREAKER_OPEN,
            VALIDATION_ERROR,
            UNAUTHORIZED,
            FORBIDDEN,
            NOT_FOUND,
            TOO_MANY_REQUESTS,
            INTERNAL_ERROR,
            CACHE_EXPIRED,
            CACHE_MISS,
            EXTERNAL_SERVICE_TIMEOUT,
            EXTERNAL_SERVICE_ERROR,
            CONTEXT_LIMIT_REACHED,
        )
        ALLOWLIST = {
            DB_CONNECTION_FAILED, DB_QUERY_TIMEOUT, DB_QUERY_ERROR,
            DB_POOL_EXHAUSTED, SERVICE_UNAVAILABLE, CIRCUIT_BREAKER_OPEN,
            VALIDATION_ERROR, UNAUTHORIZED, FORBIDDEN, NOT_FOUND,
            TOO_MANY_REQUESTS, INTERNAL_ERROR, CACHE_EXPIRED, CACHE_MISS,
            EXTERNAL_SERVICE_TIMEOUT, EXTERNAL_SERVICE_ERROR, CONTEXT_LIMIT_REACHED,
        }
        for code in ALLOWLIST:
            self.assertIsInstance(code, str)
            self.assertTrue(len(code) > 0)

    def test_validation_error_code_in_envelope(self):
        """Validation error from wip_routes must return VALIDATION_ERROR code."""
        from mes_dashboard.core.response import VALIDATION_ERROR
        resp = self.client.get('/api/wip/overview/matrix?status=INVALID')
        data = json.loads(resp.data)
        self.assertFalse(data['success'])
        self.assertEqual(data['error']['code'], VALIDATION_ERROR)

    def test_not_found_error_code_in_envelope(self):
        """Not-found error must return NOT_FOUND code."""
        from mes_dashboard.core.response import NOT_FOUND
        from unittest.mock import patch
        with patch('mes_dashboard.routes.wip_routes.get_lot_detail', return_value=None):
            resp = self.client.get('/api/wip/lot/NONEXISTENT-LOT')
        data = json.loads(resp.data)
        self.assertEqual(data['error']['code'], NOT_FOUND)

    def test_internal_error_code_in_envelope(self):
        """Internal error must return INTERNAL_ERROR code."""
        from mes_dashboard.core.response import INTERNAL_ERROR
        from unittest.mock import patch
        with patch('mes_dashboard.routes.wip_routes.get_wip_summary', return_value=None):
            resp = self.client.get('/api/wip/overview/summary')
        data = json.loads(resp.data)
        self.assertEqual(data['error']['code'], INTERNAL_ERROR)


class TestResourceHistoryProgressContract(unittest.TestCase):
    """Contract tests for the resource-history batch query progress endpoint (resource-history-perf)."""

    CONTRACTS_DIR = Path(__file__).parent.parent / "contracts"

    def _read_contract(self, relative_path: str) -> str:
        return (self.CONTRACTS_DIR / relative_path).read_text(encoding="utf-8")

    def test_resource_history_progress_endpoint_in_inventory(self):
        """api-inventory.md and api-contract.md must both register the progress endpoint."""
        inventory = self._read_contract("api/api-inventory.md")
        self.assertIn(
            "resource/history/query/progress",
            inventory,
            "api-inventory.md does not mention resource/history/query/progress — "
            "add the endpoint to resource_history_routes.py scope in the standard-json table.",
        )

        api_contract = self._read_contract("api/api-contract.md")
        self.assertIn(
            "GET /api/resource/history/query/progress",
            api_contract,
            "api-contract.md Section 4 does not contain a row for "
            "GET /api/resource/history/query/progress.",
        )

    def test_resource_history_progress_response_matches_data_shape_contract(self):
        """data-shape-contract.md Section 2.6 must declare all five required fields and closed enum values."""
        data_shape = self._read_contract("data/data-shape-contract.md")

        required_fields = ["query_id", "total_chunks", "completed_chunks", "percent", "status"]
        for field in required_fields:
            self.assertIn(
                field,
                data_shape,
                f"data-shape-contract.md Section 2.6 is missing required field '{field}'.",
            )

        closed_enum_values = ["running", "done", "error"]
        for value in closed_enum_values:
            self.assertIn(
                value,
                data_shape,
                f"data-shape-contract.md Section 2.6 is missing closed enum value '{value}'.",
            )


class TestProductionHistoryQueryModeContract(unittest.TestCase):
    """Contract: POST /api/production-history/query date optionality (api-contract 1.4.0).

    Identifier mode (≥1 wildcard token) → start_date/end_date optional.
    Classification mode (no token) → start_date/end_date still required.
    """

    def setUp(self):
        db._ENGINE = None
        self.app = create_app("testing")
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    @patch("mes_dashboard.routes.production_history_routes.query_production_history")
    def test_query_payload_dates_optional_with_identifier_tokens(self, mock_query):
        """Endpoint accepts a payload with omitted start_date/end_date when identifier token present."""
        mock_query.return_value = {
            "dataset_id": "ph-ctr1",
            "detail": {"rows": [], "pagination": {"page": 1, "per_page": 25, "total_rows": 0, "total_pages": 0}},
            "matrix": {"tree": [], "month_columns": []},
            "filter_options": {"pj_types": []},
            "meta": {"ttl_seconds": 3600, "expires_at": 9999999999, "row_count": 0},
        }
        response = self.client.post(
            "/api/production-history/query",
            json={"lot_ids": ["GA001AB"]},
        )
        self.assertIn(response.status_code, (200, 202))
        data = json.loads(response.data)
        self.assertTrue(data["success"])

    def test_query_payload_classification_mode_still_requires_dates(self):
        """Endpoint still rejects a classification-mode payload that omits dates."""
        response = self.client.post(
            "/api/production-history/query",
            json={"pj_types": ["GA"]},
        )
        self.assertEqual(response.status_code, 400)
        data = json.loads(response.data)
        self.assertFalse(data["success"])
        self.assertEqual(data["error"]["code"], "VALIDATION_ERROR")


class TestProductionHistoryPartialMergeContract(unittest.TestCase):
    """Contract assertions for prod-history-detail-partial-merge (2026-05-15).

    AC-4: pagination.total_rows must equal post-aggregation row count.
    AC-6: every detail row must carry partial_count as an integer >= 1.
    """

    def _make_spool(self, tmp_dir, records):
        import os
        import pandas as pd
        df = pd.DataFrame.from_records(records)
        path = os.path.join(tmp_dir, "ph_spool.parquet")
        df.to_parquet(path)
        return path

    def _base_record(self, overrides=None):
        base = {
            "CONTAINERNAME": "LOT-A",
            "SPECNAME": "SPEC-1",
            "EQUIPMENTID": "EQ-01",
            "TRACKINTIMESTAMP": "2026-01-01 08:00:00",
            "TRACKINQTY": 100,
            "TRACKOUTTIMESTAMP": "2026-01-01 10:00:00",
            "TRACKOUTQTY": 50,
            "MFGORDERNAME": "WO-001",
            "FIRSTNAME": "WL-001",
            "PJ_TYPE": "GA",
            "PJ_BOP": "BOP1",
            "PJ_FUNCTION": "FN1",
            "PRODUCTLINENAME": "PKG-A",
            "WORKCENTERNAME": "WC-X",
            "EQUIPMENTNAME": "EQP-NAME-01",
        }
        if overrides:
            base.update(overrides)
        return base

    def test_production_history_detail_pagination_total_rows_post_aggregation(self):
        """AC-4: pagination.total_rows == post-aggregation count, not raw spool row count.

        3 raw spool rows sharing the same 5-tuple must produce total_rows=1.
        """
        import os
        import tempfile
        from mes_dashboard.services.production_history_sql_runtime import compute_detail_page

        with tempfile.TemporaryDirectory() as tmp_dir:
            records = [
                self._base_record({"TRACKOUTTIMESTAMP": "2026-01-01 09:00:00", "TRACKOUTQTY": 20}),
                self._base_record({"TRACKOUTTIMESTAMP": "2026-01-01 10:00:00", "TRACKOUTQTY": 30}),
                self._base_record({"TRACKOUTTIMESTAMP": "2026-01-01 11:00:00", "TRACKOUTQTY": 50}),
            ]
            path = self._make_spool(tmp_dir, records)
            result = compute_detail_page(path, {}, page=1, per_page=25)
            total_rows = result["pagination"]["total_rows"]
            self.assertEqual(
                total_rows,
                1,
                f"AC-4 FAIL: total_rows must be 1 (post-aggregation) when 3 raw rows share "
                f"the same 5-tuple key, but got {total_rows}. "
                "The contract requires total_rows = post-aggregation row count (api-contract.md §10, 2026-05-15).",
            )

    def _make_spool_path(self, records):
        """Helper that returns (path, tmpdir_obj) — caller must keep tmpdir alive."""
        import os
        import tempfile
        import pandas as pd
        tmpdir = tempfile.mkdtemp()
        df = pd.DataFrame.from_records(records)
        path = os.path.join(tmpdir, "ph_spool.parquet")
        df.to_parquet(path)
        return path, tmpdir

    def test_detail_row_schema_has_partial_count_integer(self):
        """AC-6: every row returned by compute_detail_page must contain 'partial_count'
        as an integer >= 1, as declared in contracts/data/data-shape-contract.md §3.4
        and contracts/api/api-contract.md §10 (2026-05-15).
        """
        import shutil
        from mes_dashboard.services.production_history_sql_runtime import compute_detail_page

        records = [
            self._base_record({"TRACKOUTTIMESTAMP": "2026-01-01 10:00:00", "TRACKOUTQTY": 50}),
            self._base_record({"TRACKOUTTIMESTAMP": "2026-01-01 11:00:00", "TRACKOUTQTY": 50}),
        ]
        path, tmpdir = self._make_spool_path(records)
        try:
            result = compute_detail_page(path, {}, page=1, per_page=25)
            rows = result["rows"]
            self.assertTrue(rows, "detail page must return at least one row")
            for i, row in enumerate(rows):
                self.assertIn(
                    "partial_count",
                    row,
                    f"AC-6 FAIL: row[{i}] missing 'partial_count' field. "
                    "Contract requires this field (data-shape-contract.md §3.4).",
                )
                self.assertIsInstance(
                    row["partial_count"],
                    int,
                    f"AC-6 FAIL: row[{i}]['partial_count'] must be int, got {type(row['partial_count'])}.",
                )
                self.assertGreaterEqual(
                    row["partial_count"],
                    1,
                    f"AC-6 FAIL: row[{i}]['partial_count'] must be >= 1, got {row['partial_count']}.",
                )
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
