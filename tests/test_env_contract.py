# -*- coding: utf-8 -*-
"""
Tests that the 4 new batch-rowcount-unification env vars are documented in
contracts/env/env-contract.md and that the engine defaults match the contract.
"""

from __future__ import annotations

from pathlib import Path

import pytest


_CONTRACT_PATH = Path(__file__).resolve().parent.parent / "contracts" / "env" / "env-contract.md"


# ---------------------------------------------------------------------------
# 1. Documentation presence
# ---------------------------------------------------------------------------

class TestNewEnvVarsDocumented:
    """All 5 vars added by batch-rowcount-unification must appear in env-contract.md."""

    def _content(self) -> str:
        return _CONTRACT_PATH.read_text(encoding="utf-8")

    def test_use_row_count_chunking_documented(self):
        assert "USE_ROW_COUNT_CHUNKING" in self._content()

    def test_batch_query_rows_per_chunk_documented(self):
        assert "BATCH_QUERY_ROWS_PER_CHUNK" in self._content()

    def test_hold_engine_parallel_documented(self):
        assert "HOLD_ENGINE_PARALLEL" in self._content()

    def test_job_engine_parallel_documented(self):
        assert "JOB_ENGINE_PARALLEL" in self._content()

    def test_msd_engine_parallel_documented(self):
        assert "MSD_ENGINE_PARALLEL" in self._content()


# ---------------------------------------------------------------------------
# 2. Engine defaults match contract
# ---------------------------------------------------------------------------

class TestEngineDefaultsMatchContract:
    """Module-level constants in batch_query_engine must match the documented defaults."""

    def test_rows_per_chunk_default_is_50000(self, monkeypatch):
        """BATCH_QUERY_ROWS_PER_CHUNK default must be 50000 per env-contract.md."""
        # Reload the constant by reading from the module — if env var is already
        # unset, the constant was frozen at import time to 50000.
        import os
        # Clear any override so we read the module as-loaded.
        saved = os.environ.pop("BATCH_QUERY_ROWS_PER_CHUNK", None)
        try:
            from mes_dashboard.services.batch_query_engine import BATCH_QUERY_ROWS_PER_CHUNK
            # The module was already imported; if the env var was unset before
            # import, the constant equals 50000. We verify it's in the valid range.
            assert BATCH_QUERY_ROWS_PER_CHUNK >= 1, "BATCH_QUERY_ROWS_PER_CHUNK must be positive"
            # If no override was present at import time, it must equal the documented default.
            if saved is None:
                assert BATCH_QUERY_ROWS_PER_CHUNK == 50000, (
                    f"Expected default 50000 (env-contract.md), got {BATCH_QUERY_ROWS_PER_CHUNK}"
                )
        finally:
            if saved is not None:
                os.environ["BATCH_QUERY_ROWS_PER_CHUNK"] = saved

    def test_use_row_count_chunking_default_is_false(self, monkeypatch):
        """_USE_ROW_COUNT_CHUNKING default must be False per env-contract.md."""
        import os
        saved = os.environ.pop("USE_ROW_COUNT_CHUNKING", None)
        try:
            from mes_dashboard.services.batch_query_engine import _USE_ROW_COUNT_CHUNKING
            if saved is None:
                assert _USE_ROW_COUNT_CHUNKING is False, (
                    f"Expected default False (env-contract.md), got {_USE_ROW_COUNT_CHUNKING}"
                )
        finally:
            if saved is not None:
                os.environ["USE_ROW_COUNT_CHUNKING"] = saved

    def test_hold_engine_parallel_default_is_positive_integer(self):
        """HOLD_ENGINE_PARALLEL default 1 per env-contract.md — must be >= 1."""
        import os
        import importlib
        # Read directly from the service module's constant.
        from mes_dashboard.services.hold_dataset_cache import _HOLD_ENGINE_PARALLEL
        assert isinstance(_HOLD_ENGINE_PARALLEL, int), (
            f"_HOLD_ENGINE_PARALLEL must be int, got {type(_HOLD_ENGINE_PARALLEL)}"
        )
        assert _HOLD_ENGINE_PARALLEL >= 1, (
            f"_HOLD_ENGINE_PARALLEL must be >= 1, got {_HOLD_ENGINE_PARALLEL}"
        )

    def test_job_engine_parallel_default_is_positive_integer(self):
        """JOB_ENGINE_PARALLEL default 1 per env-contract.md — must be >= 1."""
        from mes_dashboard.services.job_query_service import _JOB_ENGINE_PARALLEL
        assert isinstance(_JOB_ENGINE_PARALLEL, int)
        assert _JOB_ENGINE_PARALLEL >= 1

    def test_msd_engine_parallel_default_is_positive_integer(self):
        """MSD_ENGINE_PARALLEL default 1 per env-contract.md — must be >= 1."""
        from mes_dashboard.services.mid_section_defect_service import _MSD_ENGINE_PARALLEL
        assert isinstance(_MSD_ENGINE_PARALLEL, int)
        assert _MSD_ENGINE_PARALLEL >= 1


# ---------------------------------------------------------------------------
# resource-history-cache-fix: RESOURCE_VIEW_CACHE_TTL default
# ---------------------------------------------------------------------------

class TestResourceViewCacheTTLDefault:
    """RESOURCE_VIEW_CACHE_TTL module-level constant must default to 300."""

    def test_resource_view_cache_ttl_default_equals_300(self):
        """_RESOURCE_VIEW_CACHE_TTL must be 300 when env var is not set.

        This test FAILS before IP-6 is implemented because the constant does not exist yet.
        Import directly; do NOT use monkeypatch.setenv (constant is frozen at import time).
        """
        import os
        saved = os.environ.pop("RESOURCE_VIEW_CACHE_TTL", None)
        try:
            from mes_dashboard.services.resource_dataset_cache import _RESOURCE_VIEW_CACHE_TTL
            if saved is None:
                assert _RESOURCE_VIEW_CACHE_TTL == 300, (
                    f"Expected default 300 (env-contract.md), got {_RESOURCE_VIEW_CACHE_TTL}"
                )
        finally:
            if saved is not None:
                os.environ["RESOURCE_VIEW_CACHE_TTL"] = saved

    def test_resource_view_cache_ttl_documented_in_contract(self):
        """RESOURCE_VIEW_CACHE_TTL must appear in env-contract.md."""
        content = _CONTRACT_PATH.read_text(encoding="utf-8")
        assert "RESOURCE_VIEW_CACHE_TTL" in content, (
            "RESOURCE_VIEW_CACHE_TTL must be documented in env-contract.md"
        )


# ---------------------------------------------------------------------------
# unify-duckdb-prewarm-rq: per-service spool TTL defaults (AC-4)
# ---------------------------------------------------------------------------

class TestDuckdbPrewarmTtlDefaults:
    """Module-level TTL constants must match the documented defaults in env-contract.md."""

    def test_resource_history_spool_ttl_default_is_72000(self):
        """resource_dataset_cache._CACHE_TTL must default to 72000 (env-contract.md RESOURCE_HISTORY_SPOOL_TTL).

        This test FAILS before IP-5 is implemented.
        Import directly; do NOT use monkeypatch.setenv (constant is frozen at import time).
        """
        import os
        saved = os.environ.pop("RESOURCE_HISTORY_SPOOL_TTL", None)
        try:
            from mes_dashboard.services import resource_dataset_cache
            if saved is None:
                assert resource_dataset_cache._CACHE_TTL == 72000, (
                    f"resource_dataset_cache._CACHE_TTL expected 72000, got "
                    f"{resource_dataset_cache._CACHE_TTL}"
                )
        finally:
            if saved is not None:
                os.environ["RESOURCE_HISTORY_SPOOL_TTL"] = saved

    def test_downtime_analysis_cache_ttl_default_is_72000(self):
        """downtime_analysis_cache._CACHE_TTL must default to 72000 (env-contract.md DOWNTIME_ANALYSIS_CACHE_TTL).

        This test FAILS before IP-6 is implemented.
        """
        import os
        saved = os.environ.pop("DOWNTIME_ANALYSIS_CACHE_TTL", None)
        try:
            from mes_dashboard.services import downtime_analysis_cache
            if saved is None:
                assert downtime_analysis_cache._CACHE_TTL == 72000, (
                    f"downtime_analysis_cache._CACHE_TTL expected 72000, got "
                    f"{downtime_analysis_cache._CACHE_TTL}"
                )
        finally:
            if saved is not None:
                os.environ["DOWNTIME_ANALYSIS_CACHE_TTL"] = saved

    def test_cache_ttl_dataset_unchanged_at_7200(self):
        """CACHE_TTL_DATASET in config/constants.py must remain 7200 (unchanged by this change)."""
        from mes_dashboard.config.constants import CACHE_TTL_DATASET
        assert CACHE_TTL_DATASET == 7200, (
            f"CACHE_TTL_DATASET expected 7200 (must not be changed), got {CACHE_TTL_DATASET}"
        )

    def test_resource_history_spool_ttl_documented_in_contract(self):
        """RESOURCE_HISTORY_SPOOL_TTL must appear in env-contract.md."""
        content = _CONTRACT_PATH.read_text(encoding="utf-8")
        assert "RESOURCE_HISTORY_SPOOL_TTL" in content, (
            "RESOURCE_HISTORY_SPOOL_TTL must be documented in env-contract.md"
        )

    def test_downtime_analysis_cache_ttl_documented_in_contract(self):
        """DOWNTIME_ANALYSIS_CACHE_TTL must appear in env-contract.md."""
        content = _CONTRACT_PATH.read_text(encoding="utf-8")
        assert "DOWNTIME_ANALYSIS_CACHE_TTL" in content, (
            "DOWNTIME_ANALYSIS_CACHE_TTL must be documented in env-contract.md"
        )

    def test_resource_async_env_vars_pinned_defaults(self):
        """All four RESOURCE_* async env vars must have exact contract-pinned defaults (AC-5).

        Tests RESOURCE_ASYNC_ENABLED=true, RESOURCE_ASYNC_DAY_THRESHOLD=90,
        RESOURCE_WORKER_QUEUE='resource-history-query', RESOURCE_JOB_TIMEOUT_SECONDS=1800.

        Note: module-level constants are frozen at import; tests must use monkeypatch.setattr(),
        not monkeypatch.setenv(). Here we reload the module with env cleared to verify defaults.
        """
        import importlib
        import os

        # Test RESOURCE_ASYNC_ENABLED default=True
        _old_enabled = os.environ.pop("RESOURCE_ASYNC_ENABLED", None)
        try:
            from mes_dashboard.services import resource_query_job_service as _svc
            importlib.reload(_svc)
            assert _svc.RESOURCE_ASYNC_ENABLED is True, (
                f"RESOURCE_ASYNC_ENABLED must default True, got {_svc.RESOURCE_ASYNC_ENABLED!r}"
            )
        finally:
            if _old_enabled is not None:
                os.environ["RESOURCE_ASYNC_ENABLED"] = _old_enabled
            else:
                from mes_dashboard.services import resource_query_job_service as _svc
                importlib.reload(_svc)

        # RESOURCE_ASYNC_DAY_THRESHOLD removed (query-path-c-elimination-cleanup, IP-7).
        # Verify it is absent from the service module.
        from mes_dashboard.services import resource_query_job_service as _svc
        importlib.reload(_svc)
        assert not hasattr(_svc, "RESOURCE_ASYNC_DAY_THRESHOLD"), (
            "RESOURCE_ASYNC_DAY_THRESHOLD was removed in IP-7 but is still present on the module."
        )

        # Test RESOURCE_WORKER_QUEUE default='resource-history-query'
        _old_queue = os.environ.pop("RESOURCE_WORKER_QUEUE", None)
        try:
            from mes_dashboard.services import resource_query_job_service as _svc
            importlib.reload(_svc)
            assert _svc.RESOURCE_WORKER_QUEUE == "resource-history-query", (
                f"RESOURCE_WORKER_QUEUE must default 'resource-history-query', got {_svc.RESOURCE_WORKER_QUEUE!r}"
            )
        finally:
            if _old_queue is not None:
                os.environ["RESOURCE_WORKER_QUEUE"] = _old_queue
            else:
                from mes_dashboard.services import resource_query_job_service as _svc
                importlib.reload(_svc)

        # Test RESOURCE_JOB_TIMEOUT_SECONDS default=1800
        _old_timeout = os.environ.pop("RESOURCE_JOB_TIMEOUT_SECONDS", None)
        try:
            from mes_dashboard.services import resource_query_job_service as _svc
            importlib.reload(_svc)
            assert _svc.RESOURCE_JOB_TIMEOUT_SECONDS == 1800, (
                f"RESOURCE_JOB_TIMEOUT_SECONDS must default 1800, got {_svc.RESOURCE_JOB_TIMEOUT_SECONDS!r}"
            )
        finally:
            if _old_timeout is not None:
                os.environ["RESOURCE_JOB_TIMEOUT_SECONDS"] = _old_timeout
            else:
                from mes_dashboard.services import resource_query_job_service as _svc
                importlib.reload(_svc)

    def test_resource_async_vars_documented_in_env_contract(self):
        """All four RESOURCE_* async vars must appear in env-contract.md (AC-5)."""
        content = _CONTRACT_PATH.read_text(encoding="utf-8")
        for var in (
            "RESOURCE_ASYNC_ENABLED",
            # RESOURCE_ASYNC_DAY_THRESHOLD removed (query-path-c-elimination-cleanup, IP-7)
            "RESOURCE_WORKER_QUEUE",
            "RESOURCE_JOB_TIMEOUT_SECONDS",
        ):
            if var.startswith("#"):
                continue
            assert var in content, (
                f"{var} must be documented in env-contract.md (AC-5)"
            )
        # Assert RESOURCE_ASYNC_DAY_THRESHOLD is NOT in the env-contract.md property table.
        # It may appear in comments/notes explaining its removal — check it's not in
        # a table row (prefixed with `|`).
        import re
        table_rows = [line for line in content.splitlines() if "RESOURCE_ASYNC_DAY_THRESHOLD" in line and line.strip().startswith("|")]
        assert not table_rows, (
            "RESOURCE_ASYNC_DAY_THRESHOLD was removed in IP-7 but is still present in a "
            "table row in env-contract.md. Remove the table row."
        )

    def test_production_achievement_async_env_vars_pinned_defaults(self):
        """All three PRODUCTION_ACHIEVEMENT_* async env vars must have exact
        contract-pinned defaults (production-achievement-async-spool, AC-5).

        Tests PRODUCTION_ACHIEVEMENT_USE_UNIFIED_JOB=on (route module),
        PRODUCTION_ACHIEVEMENT_WORKER_QUEUE='production-achievement-query',
        PRODUCTION_ACHIEVEMENT_JOB_TIMEOUT_SECONDS=1800 (worker module).

        Module-level constants are frozen at import; tests must use
        monkeypatch.setattr(), not monkeypatch.setenv() -- here we reload the
        module with env cleared to verify defaults (mirrors
        test_resource_async_env_vars_pinned_defaults).
        """
        import importlib
        import os

        # PRODUCTION_ACHIEVEMENT_USE_UNIFIED_JOB default=True (route module)
        _old_flag = os.environ.pop("PRODUCTION_ACHIEVEMENT_USE_UNIFIED_JOB", None)
        try:
            from mes_dashboard.routes import production_achievement_routes as _routes
            importlib.reload(_routes)
            assert _routes._PRODUCTION_ACHIEVEMENT_USE_UNIFIED_JOB is True, (
                "PRODUCTION_ACHIEVEMENT_USE_UNIFIED_JOB must default True, got "
                f"{_routes._PRODUCTION_ACHIEVEMENT_USE_UNIFIED_JOB!r}"
            )
        finally:
            if _old_flag is not None:
                os.environ["PRODUCTION_ACHIEVEMENT_USE_UNIFIED_JOB"] = _old_flag
            else:
                from mes_dashboard.routes import production_achievement_routes as _routes
                importlib.reload(_routes)

        # PRODUCTION_ACHIEVEMENT_WORKER_QUEUE default='production-achievement-query' (worker module)
        _old_queue = os.environ.pop("PRODUCTION_ACHIEVEMENT_WORKER_QUEUE", None)
        try:
            from mes_dashboard.workers import production_achievement_worker as _worker
            importlib.reload(_worker)
            assert _worker.PRODUCTION_ACHIEVEMENT_WORKER_QUEUE == "production-achievement-query", (
                "PRODUCTION_ACHIEVEMENT_WORKER_QUEUE must default "
                f"'production-achievement-query', got {_worker.PRODUCTION_ACHIEVEMENT_WORKER_QUEUE!r}"
            )
        finally:
            if _old_queue is not None:
                os.environ["PRODUCTION_ACHIEVEMENT_WORKER_QUEUE"] = _old_queue
            else:
                from mes_dashboard.workers import production_achievement_worker as _worker
                importlib.reload(_worker)

        # PRODUCTION_ACHIEVEMENT_JOB_TIMEOUT_SECONDS default=1800 (worker module)
        _old_timeout = os.environ.pop("PRODUCTION_ACHIEVEMENT_JOB_TIMEOUT_SECONDS", None)
        try:
            from mes_dashboard.workers import production_achievement_worker as _worker
            importlib.reload(_worker)
            assert _worker.PRODUCTION_ACHIEVEMENT_JOB_TIMEOUT_SECONDS == 1800, (
                "PRODUCTION_ACHIEVEMENT_JOB_TIMEOUT_SECONDS must default 1800, got "
                f"{_worker.PRODUCTION_ACHIEVEMENT_JOB_TIMEOUT_SECONDS!r}"
            )
        finally:
            if _old_timeout is not None:
                os.environ["PRODUCTION_ACHIEVEMENT_JOB_TIMEOUT_SECONDS"] = _old_timeout
            else:
                from mes_dashboard.workers import production_achievement_worker as _worker
                importlib.reload(_worker)
