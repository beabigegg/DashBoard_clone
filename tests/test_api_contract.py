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


# ===========================================================================
# Downtime Analysis shape tests (§3.12.1..§3.12.7)
# ===========================================================================


class TestDowntimeSummaryShape(unittest.TestCase):
    """§3.12.1 DowntimeKpiShape — all required fields present and typed."""

    def _build_summary(self, events_df=None):
        from mes_dashboard.services.downtime_analysis_service import _build_summary
        import pandas as pd
        if events_df is None:
            events_df = pd.DataFrame({
                'status': ['UDT', 'SDT', 'EGT'],
                'hours': [2.0, 3.0, 1.0],
            })
        return _build_summary(events_df)

    def test_total_hours_present_and_float(self):
        s = self._build_summary()
        self.assertIn('total_hours', s)
        self.assertIsInstance(s['total_hours'], float)

    def test_udt_sdt_egt_hours_present(self):
        s = self._build_summary()
        for key in ('udt_hours', 'sdt_hours', 'egt_hours'):
            self.assertIn(key, s, f"Missing field '{key}'")
            self.assertIsInstance(s[key], float)

    def test_event_count_is_integer(self):
        s = self._build_summary()
        self.assertIn('event_count', s)
        self.assertIsInstance(s['event_count'], int)

    def test_avg_event_min_is_float(self):
        s = self._build_summary()
        self.assertIn('avg_event_min', s)
        self.assertIsInstance(s['avg_event_min'], float)

    def test_empty_df_returns_zeros(self):
        import pandas as pd
        s = self._build_summary(pd.DataFrame())
        self.assertEqual(s['event_count'], 0)
        self.assertEqual(s['total_hours'], 0.0)
        self.assertEqual(s['avg_event_min'], 0.0)

    def test_nst_excluded_from_totals(self):
        """NST hours must NOT appear in summary (DA-01)."""
        # DA-01 is enforced at SQL layer; service receives only UDT/SDT/EGT events.
        # This test verifies _build_summary does NOT have an NST bucket.
        s = self._build_summary()
        self.assertNotIn('nst_hours', s)


class TestDailyTrendShape(unittest.TestCase):
    """§3.12.2 DailyTrendRow — fields and types."""

    def _build_trend(self):
        import pandas as pd
        from mes_dashboard.services.downtime_analysis_service import _build_daily_trend
        df = pd.DataFrame({
            'status': ['UDT', 'SDT'],
            'hours': [2.0, 1.0],
            'start_ts': ['2026-05-27T08:00:00', '2026-05-27T10:00:00'],
        })
        return _build_daily_trend(df)

    def test_rows_have_required_fields(self):
        rows = self._build_trend()
        self.assertGreater(len(rows), 0)
        row = rows[0]
        for field in ('date', 'udt_hours', 'sdt_hours', 'egt_hours', 'total_hours'):
            self.assertIn(field, row, f"Missing DailyTrendRow field '{field}'")

    def test_date_is_string(self):
        rows = self._build_trend()
        self.assertIsInstance(rows[0]['date'], str)

    def test_hours_are_floats(self):
        rows = self._build_trend()
        for field in ('udt_hours', 'sdt_hours', 'egt_hours', 'total_hours'):
            self.assertIsInstance(rows[0][field], float)


class TestBigCategoryShape(unittest.TestCase):
    """§3.12.3 BigCategoryRow — fields and types."""

    def _build_big_cat(self):
        import pandas as pd
        from mes_dashboard.services.downtime_analysis_service import _build_big_category
        df = pd.DataFrame({
            'category': ['維修', '保養'],
            'hours': [3.0, 1.0],
        })
        return _build_big_category(df)

    def test_rows_have_required_fields(self):
        rows = self._build_big_cat()
        self.assertGreater(len(rows), 0)
        for field in ('category', 'hours', 'event_count', 'pct'):
            self.assertIn(field, rows[0], f"Missing BigCategoryRow field '{field}'")

    def test_category_is_string(self):
        rows = self._build_big_cat()
        self.assertIsInstance(rows[0]['category'], str)

    def test_pct_sums_to_100(self):
        rows = self._build_big_cat()
        total_pct = sum(r['pct'] for r in rows)
        self.assertAlmostEqual(total_pct, 100.0, delta=0.1)

    def test_sorted_by_hours_desc(self):
        rows = self._build_big_cat()
        hours = [r['hours'] for r in rows]
        self.assertEqual(hours, sorted(hours, reverse=True))


class TestTopReasonsShape(unittest.TestCase):
    """§3.12.4 TopReasonRow — fields, ordering, avg_min."""

    def _build_top(self, top_n=10):
        import pandas as pd
        from mes_dashboard.services.downtime_analysis_service import _build_top_reasons
        df = pd.DataFrame({
            'reason': ['EE Repair', 'EE_PM', 'EE Repair'],
            'status': ['UDT', 'SDT', 'UDT'],
            'hours': [5.0, 2.0, 3.0],
        })
        return _build_top_reasons(df, top_n=top_n)

    def test_rows_have_required_fields(self):
        rows = self._build_top()
        self.assertGreater(len(rows), 0)
        for field in ('reason', 'status', 'hours', 'event_count', 'avg_min'):
            self.assertIn(field, rows[0], f"Missing TopReasonRow field '{field}'")

    def test_sorted_by_hours_desc(self):
        rows = self._build_top()
        hours = [r['hours'] for r in rows]
        self.assertEqual(hours, sorted(hours, reverse=True))

    def test_top_n_respected(self):
        rows = self._build_top(top_n=1)
        self.assertEqual(len(rows), 1)

    def test_avg_min_is_float(self):
        rows = self._build_top()
        for r in rows:
            self.assertIsInstance(r['avg_min'], float)

    def test_null_reason_becomes_unfilled(self):
        import pandas as pd
        from mes_dashboard.services.downtime_analysis_service import _build_top_reasons
        df = pd.DataFrame({'reason': [None, ''], 'status': ['UDT', 'SDT'], 'hours': [1.0, 2.0]})
        rows = _build_top_reasons(df)
        for r in rows:
            self.assertEqual(r['reason'], '(未填寫)')


class TestEquipmentDetailShape(unittest.TestCase):
    """§3.12.5 EquipmentDetailRow — fields and match_source enum."""

    def _build_eq_detail(self):
        import pandas as pd
        from mes_dashboard.services.downtime_analysis_service import _build_equipment_detail
        df = pd.DataFrame({
            'resource_id': ['R-001', 'R-001', 'R-002'],
            'status': ['UDT', 'SDT', 'EGT'],
            'hours': [2.0, 1.5, 0.5],
            'reason': ['EE Repair', 'EE_PM', 'Engineering'],
        })
        return _build_equipment_detail(df, resource_lookup={})

    def test_rows_have_required_fields(self):
        rows = self._build_eq_detail()
        self.assertGreater(len(rows), 0)
        for field in ('resource_id', 'resource_name', 'workcenter', 'family',
                      'udt_hours', 'sdt_hours', 'egt_hours', 'total_hours',
                      'event_count', 'top_reason'):
            self.assertIn(field, rows[0], f"Missing EquipmentDetailRow field '{field}'")

    def test_sorted_by_total_hours_desc(self):
        rows = self._build_eq_detail()
        total_hours = [r['total_hours'] for r in rows]
        self.assertEqual(total_hours, sorted(total_hours, reverse=True))

    def test_resource_name_nullable(self):
        rows = self._build_eq_detail()
        # Without a lookup dict, resource_name should be None (lookup miss)
        self.assertIsNone(rows[0].get('resource_name'))


class TestEventDetailShape(unittest.TestCase):
    """§3.12.6 EventDetailRow — fields, match_source enum, job null when no-match."""

    def _build_events_df(self):
        import pandas as pd
        from mes_dashboard.services.downtime_analysis_service import (
            _enrich_events_df, _bridge_jobid, _merge_cross_shift_events
        )
        from datetime import datetime
        rows = [
            {
                'HISTORYID': 'R-001', 'OLDSTATUSNAME': 'UDT', 'OLDREASONNAME': 'EE Repair',
                'OLDLASTSTATUSCHANGEDATE': datetime(2026, 5, 27, 8, 0),
                'LASTSTATUSCHANGEDATE': datetime(2026, 5, 27, 10, 0),
                'HOURS': 2.0, 'JOBID': None,
            }
        ]
        merged = _merge_cross_shift_events(pd.DataFrame(rows))
        bridged = _bridge_jobid(merged, pd.DataFrame())
        return _enrich_events_df(bridged)

    def test_event_detail_page_has_pagination(self):
        from mes_dashboard.services.downtime_analysis_service import _build_event_detail_page
        df = self._build_events_df()
        result = _build_event_detail_page(df, page=1, page_size=50, resource_lookup={})
        self.assertIn('events', result)
        self.assertIn('pagination', result)
        pagination = result['pagination']
        for key in ('page', 'page_size', 'total_rows', 'total_pages'):
            self.assertIn(key, pagination)

    def test_event_detail_row_has_required_fields(self):
        from mes_dashboard.services.downtime_analysis_service import _build_event_detail_page
        df = self._build_events_df()
        result = _build_event_detail_page(df, page=1, page_size=50, resource_lookup={})
        row = result['events'][0]
        for field in ('event_id', 'resource_id', 'resource_name', 'status', 'reason',
                      'category', 'start_ts', 'end_ts', 'hours', 'match_source', 'job'):
            self.assertIn(field, row, f"Missing EventDetailRow field '{field}'")

    def test_match_source_closed_enum(self):
        from mes_dashboard.services.downtime_analysis_service import _build_event_detail_page
        df = self._build_events_df()
        result = _build_event_detail_page(df, page=1, page_size=50, resource_lookup={})
        for row in result['events']:
            self.assertIn(row['match_source'], ('jobid', 'overlap', 'none'),
                          f"match_source must be closed enum, got {row['match_source']!r}")

    def test_job_is_null_when_no_match(self):
        from mes_dashboard.services.downtime_analysis_service import _build_event_detail_page
        df = self._build_events_df()
        result = _build_event_detail_page(df, page=1, page_size=50, resource_lookup={})
        for row in result['events']:
            if row['match_source'] == 'none':
                self.assertIsNone(row['job'],
                                  "job sub-object must be null when match_source='none'")


class TestJobEnrichmentShape(unittest.TestCase):
    """§3.12.7 JobEnrichment — fields and null contract."""

    def _build_enriched_event(self):
        """Build an event with Path A match to get a non-null job sub-object."""
        from datetime import datetime
        import pandas as pd
        from mes_dashboard.services.downtime_analysis_service import (
            _bridge_jobid, _enrich_events_df, _merge_cross_shift_events
        )
        rows = [
            {
                'HISTORYID': 'R-001', 'OLDSTATUSNAME': 'UDT', 'OLDREASONNAME': 'EE Repair',
                'OLDLASTSTATUSCHANGEDATE': datetime(2026, 5, 27, 8, 0),
                'LASTSTATUSCHANGEDATE': datetime(2026, 5, 27, 10, 0),
                'HOURS': 2.0, 'JOBID': 'J-TEST',
            }
        ]
        jobs = [
            {
                'JOBID': 'J-TEST', 'RESOURCEID': 'R-001',
                'CREATEDATE': datetime(2026, 5, 27, 7, 0),
                'COMPLETEDATE': datetime(2026, 5, 27, 11, 0),
                'SYMPTOMCODENAME': 'VIBRATION', 'CAUSECODENAME': 'WEAR',
                'REPAIRCODENAME': 'REPLACE', 'COMPLETE_FULLNAME': 'TechA',
                'FIRSTCLOCKONDATE': datetime(2026, 5, 27, 7, 30),
                'LASTCLOCKOFFDATE': datetime(2026, 5, 27, 9, 30),
                'JOBORDERNAME': 'JO-001', 'JOBMODELNAME': 'MODEL-A',
            }
        ]
        merged = _merge_cross_shift_events(pd.DataFrame(rows))
        bridged = _bridge_jobid(merged, pd.DataFrame(jobs))
        return _enrich_events_df(bridged)

    def test_job_enrichment_fields_present(self):
        from mes_dashboard.services.downtime_analysis_service import _build_event_detail_page
        df = self._build_enriched_event()
        result = _build_event_detail_page(df, page=1, page_size=50, resource_lookup={})
        event_row = result['events'][0]
        self.assertIsNotNone(event_row['job'])
        job = event_row['job']
        for field in ('job_order_name', 'job_model', 'symptom', 'cause', 'repair',
                      'wait_min', 'repair_min', 'handler', 'match_ambiguous'):
            self.assertIn(field, job, f"Missing JobEnrichment field '{field}'")

    def test_wait_min_nullable(self):
        """wait_min may be null per §3.12.7."""
        from mes_dashboard.services.downtime_analysis_service import _build_event_detail_page
        import pandas as pd
        from datetime import datetime
        from mes_dashboard.services.downtime_analysis_service import (
            _bridge_jobid, _enrich_events_df, _merge_cross_shift_events
        )
        rows = [
            {
                'HISTORYID': 'R-001', 'OLDSTATUSNAME': 'UDT', 'OLDREASONNAME': 'EE Repair',
                'OLDLASTSTATUSCHANGEDATE': datetime(2026, 5, 27, 8, 0),
                'LASTSTATUSCHANGEDATE': datetime(2026, 5, 27, 10, 0),
                'HOURS': 2.0, 'JOBID': 'J-NOCLK',
            }
        ]
        jobs = [
            {
                'JOBID': 'J-NOCLK', 'RESOURCEID': 'R-001',
                'CREATEDATE': datetime(2026, 5, 27, 7, 0),
                'COMPLETEDATE': datetime(2026, 5, 27, 11, 0),
                'SYMPTOMCODENAME': None, 'CAUSECODENAME': None,
                'REPAIRCODENAME': None, 'COMPLETE_FULLNAME': None,
                'FIRSTCLOCKONDATE': None,  # null clock
                'LASTCLOCKOFFDATE': None,
                'JOBORDERNAME': None, 'JOBMODELNAME': None,
            }
        ]
        merged = _merge_cross_shift_events(pd.DataFrame(rows))
        bridged = _bridge_jobid(merged, pd.DataFrame(jobs))
        df = _enrich_events_df(bridged)
        result = _build_event_detail_page(df, page=1, page_size=50, resource_lookup={})
        job = result['events'][0]['job']
        self.assertIsNone(job['wait_min'])
        self.assertIsNone(job['repair_min'])

    def test_match_ambiguous_is_boolean(self):
        from mes_dashboard.services.downtime_analysis_service import _build_event_detail_page
        df = self._build_enriched_event()
        result = _build_event_detail_page(df, page=1, page_size=50, resource_lookup={})
        job = result['events'][0]['job']
        self.assertIsInstance(job['match_ambiguous'], bool)


class TestResourceHistoryAsyncContract(unittest.TestCase):
    """AC-1: POST /api/resource/history/query with long span → 202 with correct async shape."""

    def setUp(self):
        import mes_dashboard.core.database as db
        db._ENGINE = None
        from mes_dashboard.app import create_app
        self.app = create_app('testing')
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()

    @patch('mes_dashboard.routes.resource_history_routes.is_async_available', return_value=True)
    @patch('mes_dashboard.routes.resource_history_routes.get_owner_token', return_value='contract-test-user')
    @patch('mes_dashboard.routes.resource_history_routes.enqueue_job_dynamic')
    def test_202_response_shape_has_job_id_and_status_url(
        self, mock_enqueue, _mock_owner, _mock_avail
    ):
        """POST /api/resource/history/query long-span → 202 body has async=True, job_id, status_url (AC-1).

        Validates the contract shape: {success: true, data: {async: true, job_id: str, status_url: str}}
        where status_url points to the resource-history prefix.
        """
        import mes_dashboard.routes.resource_history_routes as _rmod
        mock_enqueue.return_value = ("contract-job-001", None)

        with patch.object(_rmod, 'RESOURCE_ASYNC_ENABLED', True), \
             patch.object(_rmod, 'RESOURCE_ASYNC_DAY_THRESHOLD', 90):
            response = self.client.post(
                '/api/resource/history/query',
                json={"start_date": "2024-01-01", "end_date": "2024-07-20"},
            )

        self.assertEqual(response.status_code, 202)
        data = json.loads(response.data)

        # Standard envelope
        self.assertIn('success', data)
        self.assertTrue(data['success'])
        self.assertIn('data', data)

        # Async shape
        payload = data['data']
        self.assertIn('async', payload, "202 body must have 'async' field")
        self.assertTrue(payload['async'], "202 body must have async=True")
        self.assertIn('job_id', payload, "202 body must have 'job_id'")
        self.assertIsInstance(payload['job_id'], str, "job_id must be a string")
        self.assertTrue(len(payload['job_id']) > 0, "job_id must be non-empty")
        self.assertIn('status_url', payload, "202 body must have 'status_url'")
        self.assertIn('resource-history', payload['status_url'],
                      "status_url must reference 'resource-history' prefix")

    def test_resource_history_query_short_span_returns_200_not_202(self):
        """POST /api/resource/history/query short-span → 200 sync (contract backward compat)."""
        import mes_dashboard.routes.resource_history_routes as _rmod

        with patch.object(_rmod, 'RESOURCE_ASYNC_ENABLED', True), \
             patch.object(_rmod, 'RESOURCE_ASYNC_DAY_THRESHOLD', 90), \
             patch('mes_dashboard.services.resource_history_sql_runtime.try_compute_query_from_canonical_spool',
                   return_value=(None, None)), \
             patch('mes_dashboard.routes.resource_history_routes.execute_primary_query',
                   return_value={
                       'query_id': 'short-span-200',
                       'summary': {'kpi': {}, 'trend': [], 'heatmap': [], 'workcenter_comparison': []},
                       'detail': {'data': [], 'total': 0, 'truncated': False, 'max_records': None},
                   }):
            response = self.client.post(
                '/api/resource/history/query',
                json={"start_date": "2024-01-01", "end_date": "2024-01-07"},  # 6 days
            )

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data['success'])
        # Sync response has query_id, not async:true
        self.assertNotIn('async', data.get('data', {}))


if __name__ == "__main__":
    unittest.main()
