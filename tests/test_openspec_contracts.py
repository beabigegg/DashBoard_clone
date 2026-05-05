# -*- coding: utf-8 -*-
"""OpenSpec contract compliance tests.

Parses five spec directories and asserts that the runtime codebase satisfies
key requirements from each spec.  These are static-analysis tests — they read
source files and verify structure, not live behaviour.

Specs covered:
  1. api-response-contract-unification
  2. anomaly-summary-api
  3. cache-plane-architecture
  4. async-query-job-service
  5. api-safety-hygiene
"""

from __future__ import annotations

import re
from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).parent.parent
SPECS_DIR = PROJECT_ROOT / "openspec" / "specs"
ROUTES_DIR = PROJECT_ROOT / "src" / "mes_dashboard" / "routes"
SERVICES_DIR = PROJECT_ROOT / "src" / "mes_dashboard" / "services"
CORE_DIR = PROJECT_ROOT / "src" / "mes_dashboard" / "core"


def _spec_text(spec_name: str) -> str:
    spec_path = SPECS_DIR / spec_name / "spec.md"
    assert spec_path.exists(), f"spec not found: {spec_path}"
    return spec_path.read_text(encoding="utf-8")


def _src_text(relative_path: str) -> str:
    full = PROJECT_ROOT / relative_path
    assert full.exists(), f"source file not found: {full}"
    return full.read_text(encoding="utf-8")


def _grep(pattern: str, text: str) -> list[str]:
    return re.findall(pattern, text, re.MULTILINE)


# ---------------------------------------------------------------------------
# 1. api-response-contract-unification
# ---------------------------------------------------------------------------

class TestApiResponseContractUnification:
    """Spec: api-response-contract-unification"""

    def test_spec_file_exists(self):
        _spec_text("api-response-contract-unification")

    def test_spec_requires_success_response_helper(self):
        spec = _spec_text("api-response-contract-unification")
        assert "success_response" in spec, "Spec must reference success_response helper"

    def test_spec_requires_error_response_helper(self):
        spec = _spec_text("api-response-contract-unification")
        assert "error_response" in spec or "validation_error" in spec

    def test_response_py_exports_success_response(self):
        src = _src_text("src/mes_dashboard/core/response.py")
        assert "def success_response" in src

    def test_response_py_exports_error_response(self):
        src = _src_text("src/mes_dashboard/core/response.py")
        assert "def error_response" in src

    def test_response_py_exports_validation_error(self):
        src = _src_text("src/mes_dashboard/core/response.py")
        assert "def validation_error" in src

    def test_response_py_exports_not_found_error(self):
        src = _src_text("src/mes_dashboard/core/response.py")
        assert "def not_found_error" in src

    def test_response_py_injects_meta_timestamp(self):
        """success_response must always include meta.timestamp."""
        src = _src_text("src/mes_dashboard/core/response.py")
        assert '"timestamp"' in src or "'timestamp'" in src

    def test_response_py_injects_app_version(self):
        """Envelope meta must include app_version (task 1.6)."""
        src = _src_text("src/mes_dashboard/core/response.py")
        assert "app_version" in src

    def test_routes_do_not_use_raw_jsonify(self):
        """Standard-json routes must not call jsonify() directly.

        health_routes.py and spool_routes.py are approved exceptions
        (health-exception, stream-download-exception).
        """
        approved_exceptions = {
            "health_routes.py",
            "spool_routes.py",
            "auth_routes.py",
        }
        violations = []
        for route_file in ROUTES_DIR.glob("*.py"):
            if route_file.name in approved_exceptions:
                continue
            src = route_file.read_text(encoding="utf-8")
            # Detect direct jsonify( calls by stripping import/comment lines first
            non_import_lines = [
                line for line in src.splitlines()
                if not line.lstrip().startswith("from ")
                and not line.lstrip().startswith("import ")
                and not line.lstrip().startswith("#")
            ]
            non_import_src = "\n".join(non_import_lines)
            if re.search(r'\bjsonify\(', non_import_src):
                violations.append(route_file.name)
        assert not violations, (
            f"These route files call jsonify() directly instead of using response helpers: "
            f"{violations}"
        )

    def test_api_inventory_documents_job_routes(self):
        inventory = _src_text("contracts/api/api-inventory.md")
        assert "job_routes.py" in inventory, (
            "contracts/api/api-inventory.md must document job_routes.py POST /api/job/<id>/abandon"
        )

    def test_api_inventory_documents_app_version(self):
        inventory = _src_text("contracts/api/api-inventory.md")
        assert "app_version" in inventory


# ---------------------------------------------------------------------------
# 2. anomaly-summary-api
# ---------------------------------------------------------------------------

class TestAnomalySummaryApi:
    """Spec: anomaly-summary-api"""

    def test_spec_file_exists(self):
        _spec_text("anomaly-summary-api")

    def test_spec_requires_anomaly_summary_endpoint(self):
        spec = _spec_text("anomaly-summary-api")
        assert "/api/analytics/anomaly-summary" in spec

    def test_spec_requires_four_detector_breakdown(self):
        spec = _spec_text("anomaly-summary-api")
        for key in ("yield", "reject", "hold", "equipment"):
            assert key in spec, f"Spec must reference {key!r} detector"

    def test_analytics_routes_has_anomaly_summary_endpoint(self):
        src = _src_text("src/mes_dashboard/routes/analytics_routes.py")
        assert "anomaly-summary" in src

    def test_analytics_routes_uses_success_response(self):
        src = _src_text("src/mes_dashboard/routes/analytics_routes.py")
        assert "success_response" in src

    def test_analytics_routes_applies_rate_limit(self):
        src = _src_text("src/mes_dashboard/routes/analytics_routes.py")
        assert "configured_rate_limit" in src or "rate_limit" in src

    def test_anomaly_summary_service_function_exists(self):
        src = _src_text("src/mes_dashboard/services/anomaly_detection_sql_runtime.py")
        assert "get_anomaly_summary" in src or "anomaly_summary" in src

    def test_spec_documents_meta_cache_state(self):
        spec = _spec_text("anomaly-summary-api")
        assert "cache_state" in spec or "cache" in spec

    def test_analytics_routes_injects_cache_state_meta(self):
        src = _src_text("src/mes_dashboard/routes/analytics_routes.py")
        assert "cache_state" in src


# ---------------------------------------------------------------------------
# 3. cache-plane-architecture
# ---------------------------------------------------------------------------

class TestCachePlaneArchitecture:
    """Spec: cache-plane-architecture"""

    def test_spec_file_exists(self):
        _spec_text("cache-plane-architecture")

    def test_spec_defines_four_planes(self):
        spec = _spec_text("cache-plane-architecture")
        for plane in ("snapshot", "heavy-query", "derived-result", "control"):
            assert plane in spec, f"Spec must define {plane!r} plane"

    def test_spec_requires_redis_isolation(self):
        spec = _spec_text("cache-plane-architecture")
        assert "control" in spec and "evict" in spec.lower()

    def test_redis_client_has_control_plane_function(self):
        """get_control_redis_client must exist as a distinct function."""
        src = _src_text("src/mes_dashboard/core/redis_client.py")
        assert "get_control_redis_client" in src

    def test_async_job_service_uses_control_redis(self):
        """async_query_job_service must use control-plane Redis for job metadata."""
        src = _src_text("src/mes_dashboard/services/async_query_job_service.py")
        assert "get_control_redis_client" in src

    def test_spool_files_used_for_heavy_query_plane(self):
        """Parquet spool routes exist for heavy-query plane."""
        src = _src_text("src/mes_dashboard/routes/spool_routes.py")
        assert ".parquet" in src

    def test_spec_requires_duckdb_for_heavy_query_runtime(self):
        spec = _spec_text("cache-plane-architecture")
        assert "DuckDB" in spec or "duckdb" in spec.lower()

    def test_heavy_query_services_use_duckdb_runtime(self):
        """At least one service must import duckdb for heavy-query plane."""
        found_duckdb = any(
            "duckdb" in f.read_text(encoding="utf-8", errors="ignore").lower()
            for f in SERVICES_DIR.glob("*.py")
        )
        assert found_duckdb, "No service module imports duckdb — heavy-query plane missing"


# ---------------------------------------------------------------------------
# 4. async-query-job-service
# ---------------------------------------------------------------------------

class TestAsyncQueryJobService:
    """Spec: async-query-job-service"""

    def test_spec_file_exists(self):
        _spec_text("async-query-job-service")

    def test_spec_requires_enqueue_job(self):
        spec = _spec_text("async-query-job-service")
        assert "enqueue_job" in spec

    def test_spec_requires_get_job_status(self):
        spec = _spec_text("async-query-job-service")
        assert "get_job_status" in spec

    def test_spec_requires_update_job_progress(self):
        spec = _spec_text("async-query-job-service")
        assert "update_job_progress" in spec

    def test_spec_requires_complete_job(self):
        spec = _spec_text("async-query-job-service")
        assert "complete_job" in spec

    def test_spec_requires_is_async_available(self):
        spec = _spec_text("async-query-job-service")
        assert "is_async_available" in spec

    def test_service_exports_enqueue_job(self):
        src = _src_text("src/mes_dashboard/services/async_query_job_service.py")
        assert "def enqueue_job" in src

    def test_service_exports_get_job_status(self):
        src = _src_text("src/mes_dashboard/services/async_query_job_service.py")
        assert "def get_job_status" in src

    def test_service_exports_update_job_progress(self):
        src = _src_text("src/mes_dashboard/services/async_query_job_service.py")
        assert "def update_job_progress" in src

    def test_service_exports_complete_job(self):
        src = _src_text("src/mes_dashboard/services/async_query_job_service.py")
        assert "def complete_job" in src

    def test_service_exports_is_async_available(self):
        src = _src_text("src/mes_dashboard/services/async_query_job_service.py")
        assert "def is_async_available" in src

    def test_job_metadata_key_schema(self):
        """Job metadata must follow {prefix}:job:{job_id}:meta key schema."""
        src = _src_text("src/mes_dashboard/services/async_query_job_service.py")
        assert ":job:" in src and ":meta" in src

    def test_rq_health_ttl_is_60_seconds(self):
        src = _src_text("src/mes_dashboard/services/async_query_job_service.py")
        assert "_RQ_HEALTH_TTL_SECONDS = 60" in src


# ---------------------------------------------------------------------------
# 5. api-safety-hygiene
# ---------------------------------------------------------------------------

class TestApiSafetyHygiene:
    """Spec: api-safety-hygiene"""

    def test_spec_file_exists(self):
        _spec_text("api-safety-hygiene")

    def test_spec_requires_rate_limiting_on_high_cost_apis(self):
        spec = _spec_text("api-safety-hygiene")
        assert "TOO_MANY_REQUESTS" in spec or "rate" in spec.lower()

    def test_spec_requires_429_with_retry_after(self):
        spec = _spec_text("api-safety-hygiene")
        assert "429" in spec or "TOO_MANY_REQUESTS" in spec

    def test_response_py_exports_too_many_requests_error(self):
        src = _src_text("src/mes_dashboard/core/response.py")
        assert "def too_many_requests_error" in src

    def test_response_py_exports_too_many_requests_code(self):
        src = _src_text("src/mes_dashboard/core/response.py")
        assert "TOO_MANY_REQUESTS" in src

    def test_rate_limit_module_exists(self):
        rate_limit = CORE_DIR / "rate_limit.py"
        assert rate_limit.exists(), "core/rate_limit.py must exist"

    def test_rate_limit_module_has_configured_rate_limit(self):
        src = _src_text("src/mes_dashboard/core/rate_limit.py")
        assert "def configured_rate_limit" in src

    def test_high_cost_routes_apply_rate_limit(self):
        """Routes known to be high-cost and explicitly in api-safety-hygiene scope
        must apply rate limiting.  production_history_routes.py is not yet listed
        in the spec scope so it is excluded here.
        """
        high_cost_routes = [
            "analytics_routes.py",
            "reject_history_routes.py",
            "yield_alert_routes.py",
            "material_trace_routes.py",
        ]
        missing = []
        for filename in high_cost_routes:
            src = (ROUTES_DIR / filename).read_text(encoding="utf-8")
            if "rate_limit" not in src.lower() and "configured_rate_limit" not in src:
                missing.append(filename)
        assert not missing, f"These high-cost route files lack rate limiting: {missing}"

    def test_spec_requires_depth_safe_nan_cleaning(self):
        spec = _spec_text("api-safety-hygiene")
        assert "depth" in spec.lower() or "recursive" in spec.lower()

    def test_job_abandon_route_is_rate_limited(self):
        """The new POST /api/job/<id>/abandon endpoint must apply rate limiting."""
        src = _src_text("src/mes_dashboard/routes/job_routes.py")
        assert "configured_rate_limit" in src or "_JOB_ABANDON_RATE_LIMIT" in src
