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
