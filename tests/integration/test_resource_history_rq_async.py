# -*- coding: utf-8 -*-
"""Integration tests for Resource History unified-job RQ async dispatch (P3 migration).

pytestmark = pytest.mark.integration_real
(requires real Redis + RQ worker environment and Oracle connectivity to run fully)

Test classes:
  TestUnifiedJobParity — parity between unified-job spool output and legacy single-pass output
    - test_base_job_parity_vs_legacy_spool
    - test_oee_job_parity_vs_legacy_spool

These tests are STUBS — they are skipped pre-merge (nightly integration_real gate).
Full parity assertions require a real Oracle connection and running RQ worker.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration_real


class TestUnifiedJobParity:
    """AC-3 (Tier 1): Parity between unified-job spool and legacy single-pass Oracle output."""

    def test_base_job_parity_vs_legacy_spool(self):
        """ResourceHistoryBaseJob spool parquet matches legacy _query_and_store_canonical_dataset
        base output (columns and row count) for a synthetic date range.

        STUB: Requires real Oracle connection and running RQ worker.
        Full implementation deferred to nightly integration gate.
        """
        pytest.skip(
            "Tier-1 integration stub — requires real Oracle + RQ worker. "
            "Run in nightly-integration gate with RESOURCE_HISTORY_USE_UNIFIED_JOB=on."
        )

    def test_oee_job_parity_vs_legacy_spool(self):
        """ResourceHistoryOeeJob spool parquet matches legacy _query_and_store_canonical_dataset
        OEE output: EQUIPMENTID total TRACKOUT_QTY/NG_QTY within 1e-6 (ratio-of-SUMs parity).

        STUB: Requires real Oracle connection and running RQ worker.
        Full implementation deferred to nightly integration gate.
        """
        pytest.skip(
            "Tier-1 integration stub — requires real Oracle + RQ worker. "
            "Run in nightly-integration gate with RESOURCE_HISTORY_USE_UNIFIED_JOB=on."
        )
