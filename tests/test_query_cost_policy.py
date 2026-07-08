"""Unit tests for query_cost_policy.

AC-4: 4-layer short-circuit returns correct SYNC/ASYNC.
AC-7: no pandas import; no caller outside tests.
Deprecation: DeprecationWarning raised when *_ASYNC_DAY_THRESHOLD env var present.
"""
from __future__ import annotations

import ast
import os
# warnings import removed with TestDeprecationWarning (query-path-c-elimination-cleanup, IP-11)
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _call(
    domain="production",
    date_from=None,
    date_to=None,
    spool_hit=False,
    row_count_fn=None,
    policy=None,
):
    from mes_dashboard.core.query_cost_policy import classify_query_cost

    params: dict = {}
    if date_from is not None:
        params["date_from"] = date_from
    if date_to is not None:
        params["date_to"] = date_to
    return classify_query_cost(
        domain=domain,
        params=params,
        spool_hit=spool_hit,
        row_count_fn=row_count_fn,
        policy=policy,
    )


# ---------------------------------------------------------------------------
# L0 — spool hit
# ---------------------------------------------------------------------------

class TestL0SpoolHit:
    def test_l0_spool_hit_returns_sync(self):
        result = _call(spool_hit=True)
        assert result == "SYNC"

    def test_l0_short_circuits_l1(self):
        """L0 spool_hit=True wins over always-async domain (L1)."""
        result = _call(domain="eap_alarm", spool_hit=True)
        assert result == "SYNC"

    def test_l0_short_circuits_l2(self):
        """L0 spool_hit=True wins even with large date span."""
        result = _call(
            spool_hit=True,
            date_from=date(2023, 1, 1),
            date_to=date(2024, 1, 1),  # 365 days
        )
        assert result == "SYNC"

    def test_l0_short_circuits_l3(self):
        """L0 spool_hit=True wins; row_count_fn should not be called."""
        fn = MagicMock(return_value=999_999)
        result = _call(spool_hit=True, row_count_fn=fn)
        assert result == "SYNC"
        fn.assert_not_called()


# ---------------------------------------------------------------------------
# L1 — always-async domain
# ---------------------------------------------------------------------------

class TestL1AlwaysAsyncDomain:
    @pytest.mark.parametrize("domain", ["eap_alarm", "trace", "msd"])
    def test_l1_always_async_domain_returns_async(self, domain):
        result = _call(domain=domain, spool_hit=False)
        assert result == "ASYNC"

    def test_l1_does_not_short_circuit_when_spool_hit(self):
        """With spool_hit=True, L0 takes precedence over L1."""
        result = _call(domain="trace", spool_hit=True)
        assert result == "SYNC"

    def test_l1_always_async_policy_flag(self):
        """CostPolicy(always_async=True) on a non-listed domain → ASYNC."""
        from mes_dashboard.core.query_cost_policy import CostPolicy

        result = _call(
            domain="custom_domain",
            policy=CostPolicy(always_async=True),
            spool_hit=False,
        )
        assert result == "ASYNC"


# ---------------------------------------------------------------------------
# L2 — date span threshold
# ---------------------------------------------------------------------------

class TestL2DateSpan:
    def test_l2_date_span_over_threshold(self):
        """31-day span >= 30-day threshold → ASYNC."""
        from mes_dashboard.core.query_cost_policy import CostPolicy

        result = _call(
            domain="hold",
            date_from=date(2024, 1, 1),
            date_to=date(2024, 2, 1),  # 31 days
            policy=CostPolicy(day_threshold=30),
        )
        assert result == "ASYNC"

    def test_l2_date_span_at_threshold(self):
        """Exactly 30 days >= 30-day threshold → ASYNC."""
        from mes_dashboard.core.query_cost_policy import CostPolicy

        result = _call(
            domain="hold",
            date_from=date(2024, 1, 1),
            date_to=date(2024, 1, 31),  # 30 days
            policy=CostPolicy(day_threshold=30),
        )
        assert result == "ASYNC"

    def test_l2_date_span_under_threshold(self):
        """29-day span < 30-day threshold → not caught by L2."""
        from mes_dashboard.core.query_cost_policy import CostPolicy

        result = _call(
            domain="hold",
            date_from=date(2024, 1, 1),
            date_to=date(2024, 1, 30),  # 29 days
            # No row_count_fn → L3 not triggered → falls to SYNC
            policy=CostPolicy(day_threshold=30, row_threshold=200_000),
        )
        assert result == "SYNC"

    def test_l2_string_dates_accepted(self):
        """ISO-8601 string dates work in L2 span calculation."""
        from mes_dashboard.core.query_cost_policy import CostPolicy

        result = _call(
            domain="reject",
            date_from="2024-01-01",
            date_to="2024-02-15",  # 45 days
            policy=CostPolicy(day_threshold=30),
        )
        assert result == "ASYNC"

    def test_l2_missing_dates_skips_check(self):
        """If date_from or date_to is missing, L2 is skipped (no KeyError)."""
        from mes_dashboard.core.query_cost_policy import CostPolicy

        result = _call(
            domain="hold",
            date_from=None,
            date_to=None,
            policy=CostPolicy(day_threshold=30, row_threshold=200_000),
        )
        assert result == "SYNC"  # falls through L2 and L3 → SYNC


# ---------------------------------------------------------------------------
# L3 — row count threshold
# ---------------------------------------------------------------------------

class TestL3RowCount:
    def test_l3_rowcount_over_threshold(self):
        """row_count_fn returns 200_001 >= 200_000 → ASYNC."""
        from mes_dashboard.core.query_cost_policy import CostPolicy

        fn = MagicMock(return_value=200_001)
        result = _call(
            domain="reject",
            policy=CostPolicy(row_threshold=200_000),
            row_count_fn=fn,
        )
        assert result == "ASYNC"
        fn.assert_called_once()

    def test_l3_rowcount_at_threshold(self):
        """row_count_fn returns exactly 200_000 >= 200_000 → ASYNC."""
        from mes_dashboard.core.query_cost_policy import CostPolicy

        fn = MagicMock(return_value=200_000)
        result = _call(
            domain="reject",
            policy=CostPolicy(row_threshold=200_000),
            row_count_fn=fn,
        )
        assert result == "ASYNC"

    def test_l3_rowcount_under_threshold(self):
        """row_count_fn returns 199_999 < 200_000 → SYNC."""
        from mes_dashboard.core.query_cost_policy import CostPolicy

        fn = MagicMock(return_value=199_999)
        result = _call(
            domain="reject",
            policy=CostPolicy(row_threshold=200_000),
            row_count_fn=fn,
        )
        assert result == "SYNC"

    def test_l3_row_count_fn_error_does_not_raise(self):
        """If row_count_fn raises, classify_query_cost stays SYNC (conservative)."""
        from mes_dashboard.core.query_cost_policy import CostPolicy

        def bad_fn():
            raise ConnectionError("DB unreachable")

        result = _call(
            domain="reject",
            policy=CostPolicy(row_threshold=200_000),
            row_count_fn=bad_fn,
        )
        assert result == "SYNC"

    def test_l2_short_circuits_l3(self):
        """When L2 triggers ASYNC, row_count_fn is NOT called."""
        from mes_dashboard.core.query_cost_policy import CostPolicy

        fn = MagicMock(return_value=0)
        result = _call(
            domain="hold",
            date_from=date(2024, 1, 1),
            date_to=date(2024, 3, 1),  # ~60 days > 30
            row_count_fn=fn,
            policy=CostPolicy(day_threshold=30, row_threshold=200_000),
        )
        assert result == "ASYNC"
        fn.assert_not_called()

    def test_all_under_threshold_returns_sync(self):
        """All layers pass → SYNC."""
        from mes_dashboard.core.query_cost_policy import CostPolicy

        fn = MagicMock(return_value=1000)
        result = _call(
            domain="production",
            date_from=date(2024, 1, 1),
            date_to=date(2024, 1, 5),  # 4 days
            row_count_fn=fn,
            policy=CostPolicy(day_threshold=30, row_threshold=200_000),
        )
        assert result == "SYNC"


# ---------------------------------------------------------------------------
# Per-domain policy registry (_DOMAIN_POLICIES) — single source of truth
# ---------------------------------------------------------------------------

class TestDomainPolicyRegistry:
    """The registry centralises per-domain thresholds; these pin its contract.

    All entries are behaviour-preserving (30 days / 200k rows) at introduction —
    these tests fail loudly if a future edit silently changes a domain's routing.
    """

    # Every domain that calls classify_query_cost() must be registered so the
    # table stays the source of truth. Update this list when a domain is added.
    _CLASSIFIER_DOMAINS = ["resource", "hold", "reject", "downtime", "query_tool", "wip"]
    _ALWAYS_ASYNC = ["eap_alarm", "trace", "msd"]

    def test_always_async_set_is_exactly_the_three_heavy_domains(self):
        """_ALWAYS_ASYNC_DOMAINS is derived from the registry and must not drift."""
        from mes_dashboard.core.query_cost_policy import _ALWAYS_ASYNC_DOMAINS

        assert _ALWAYS_ASYNC_DOMAINS == frozenset({"eap_alarm", "trace", "msd"})

    @pytest.mark.parametrize("domain", _ALWAYS_ASYNC)
    def test_always_async_domains_resolve_to_always_async_policy(self, domain):
        from mes_dashboard.core.query_cost_policy import _default_policy_for

        assert _default_policy_for(domain).always_async is True

    @pytest.mark.parametrize("domain", _CLASSIFIER_DOMAINS)
    def test_classifier_domains_are_registered(self, domain):
        """Each threshold domain is present in the registry (not falling back)."""
        from mes_dashboard.core.query_cost_policy import _DOMAIN_POLICIES

        assert domain in _DOMAIN_POLICIES

    @pytest.mark.parametrize("domain", _CLASSIFIER_DOMAINS)
    def test_classifier_domains_preserve_default_thresholds(self, domain):
        """Behaviour-preservation pin: all threshold domains stay 30d / 200k."""
        from mes_dashboard.core.query_cost_policy import _default_policy_for

        policy = _default_policy_for(domain)
        assert policy.always_async is False
        assert policy.day_threshold == 30
        assert policy.row_threshold == 200_000

    def test_unregistered_domain_falls_back_to_default(self):
        from mes_dashboard.core.query_cost_policy import _DEFAULT_POLICY, _default_policy_for

        assert _default_policy_for("totally_unknown_domain") is _DEFAULT_POLICY

    def test_registry_resolution_matches_classify_result(self):
        """A 40-day span on a registered 30-day domain routes ASYNC via the registry."""
        # resource is registered at day_threshold=30 → 40-day span → ASYNC
        assert _call(domain="resource", date_from="2025-01-01", date_to="2025-02-10") == "ASYNC"
        # ...and a 10-day span stays SYNC.
        assert _call(domain="resource", date_from="2025-01-01", date_to="2025-01-11") == "SYNC"


# ---------------------------------------------------------------------------
# Deprecation warning
# ---------------------------------------------------------------------------

# TestDeprecationWarning removed (query-path-c-elimination-cleanup, IP-7/IP-11):
# _check_deprecated_threshold_env() and _DEPRECATED_THRESHOLD_VARS have been deleted
# from query_cost_policy.py. The 4 *_ASYNC_DAY_THRESHOLD vars are no longer read
# anywhere in the codebase. Contract tests for their absence are in
# tests/contract/test_env_async_threshold_removal.py.


# ---------------------------------------------------------------------------
# AC-7: no pandas import; no caller outside tests
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).parent.parent
_NEW_MODULES = [
    _REPO_ROOT / "src/mes_dashboard/core/oracle_arrow_reader.py",
    _REPO_ROOT / "src/mes_dashboard/core/query_cost_policy.py",
    _REPO_ROOT / "src/mes_dashboard/core/base_chunked_duckdb_job.py",
]


class TestNoPandasAndNoCallers:
    @pytest.mark.parametrize("module_path", _NEW_MODULES)
    def test_no_pandas_import_in_new_modules(self, module_path):
        """AC-7: None of the 3 new core modules may import pandas."""
        source = module_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(module_path))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                else:
                    names = [node.module or ""]
                for name in names:
                    assert not (name == "pandas" or name.startswith("pandas.")), (
                        f"{module_path.name} must not import pandas (AC-7)"
                    )

    def test_no_caller_outside_tests(self):
        """AC-7: grep src/ for the 3 new module names — expect zero matches (with P1 allowlist).

        P1 (eap-alarm-unified-job-poc) wires the first real caller of base_chunked_duckdb_job:
          eap_alarm_worker.py — approved caller since EapAlarmJob inherits BaseChunkedDuckDBJob.
        oracle_arrow_reader and query_cost_policy remain zero-caller outside their own file.
        """
        # P1+ approved callers per module stem.  Extend as each Px migration lands.
        _APPROVED_CALLERS: dict = {
            "base_chunked_duckdb_job": {
                "eap_alarm_worker",
                "production_history_worker",
                "reject_history_worker",
                "resource_history_base_worker",
                "resource_history_oee_worker",
                "material_trace_duckdb_runtime",
                "downtime_worker",
                "production_achievement_worker",
            },
            "oracle_arrow_reader": {
                "material_trace_duckdb_runtime",
                "downtime_worker",
            },
            # query-path-c-elimination-cleanup (IP-7, P5): all callers that replaced
            # per-domain *_ASYNC_DAY_THRESHOLD with classify_query_cost() calls.
            # wip-rq-worker-chunks-cleanup: wip_query_job_service added as approved caller.
            "query_cost_policy": {
                "resource_query_job_service",
                "reject_query_job_service",
                "query_tool_routes",
                "downtime_analysis_routes",
                "hold_query_job_service",
                "wip_routes",
                "resource_history_routes",
                "hold_history_routes",
                "wip_query_job_service",
            },
        }

        src_dir = _REPO_ROOT / "src/mes_dashboard"
        new_module_stems = {
            "oracle_arrow_reader",
            "query_cost_policy",
            "base_chunked_duckdb_job",
        }
        for py_file in src_dir.rglob("*.py"):
            # Skip the modules themselves.
            if py_file.stem in new_module_stems:
                continue
            text = py_file.read_text(encoding="utf-8", errors="ignore")
            for stem in new_module_stems:
                if py_file.stem in _APPROVED_CALLERS.get(stem, set()):
                    continue  # P1+ approved caller — intentional usage
                assert stem not in text, (
                    f"Found caller of {stem} in {py_file.relative_to(_REPO_ROOT)} "
                    f"— new modules must ship with zero callers until their Px migration (AC-7). "
                    f"If this is intentional, add {py_file.stem!r} to _APPROVED_CALLERS[{stem!r}]."
                )
