# -*- coding: utf-8 -*-
"""Integration tests for Production Achievement unified-job RQ async dispatch
(production-achievement-async-spool, ADR-0016).

pytestmark = pytest.mark.integration_real
(requires real Redis + RQ worker environment and Oracle connectivity to run
fully -- nightly integration_real gate, not the Tier-1 pre-merge ladder;
CI-blocking 202/200/503 branch coverage lives in
tests/test_production_achievement_routes.py instead, which mocks
is_async_available()/enqueue_query_job -- no Redis required there.)

Test classes:
  TestProductionAchievementSpoolDownload — authorized client streams the
    SPECNAME-grain parquet via GET /api/spool/production_achievement/<id>.parquet
  TestUnifiedJobParity — worker spool parquet business-key diff vs
    build_achievement_rows() (test-only golden reference, PA-06/PA-07)

These tests are STUBS -- they are skipped pre-merge (nightly integration_real
gate), mirroring tests/integration/test_resource_history_rq_async.py.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration_real


class TestProductionAchievementSpoolDownload:
    """AC-3: authorized client can download the async spool parquet."""

    def test_authorized_client_streams_parquet(self):
        """GET /api/spool/production_achievement/<query_id>.parquet streams
        the SPECNAME-grain parquet written by ProductionAchievementJob.

        STUB: Requires real Redis + running RQ worker + Oracle connection to
        produce a real spool file end-to-end. Full implementation deferred to
        the nightly integration_real gate.
        """
        pytest.skip(
            "Tier-1 integration stub — requires real Redis + RQ worker + Oracle. "
            "Run in nightly-integration gate with PRODUCTION_ACHIEVEMENT_USE_UNIFIED_JOB=on."
        )


class TestUnifiedJobParity:
    """AC-7: dual-tier parity between the unified-job spool and the
    synchronous golden reference (build_achievement_rows()) for an identical
    date range -- enqueue -> job -> spool round-trip."""

    def test_worker_parquet_business_key_diff_vs_build_achievement_rows_golden(self):
        """ProductionAchievementJob's SPECNAME-grain parquet, rolled up
        client-side-equivalent (SPECNAME -> workcenter_group via
        filter_cache.get_spec_workcenter_mapping()) and joined against
        targets, must business-key-diff to zero against
        build_achievement_rows() (the retained test-only golden) for the
        same date range and target snapshot.

        STUB: Requires real Oracle connection and a running RQ worker to
        produce a real spool + execute the real Oracle read for the golden
        comparison. Full implementation deferred to the nightly
        integration_real gate.
        """
        pytest.skip(
            "Tier-1 integration stub — requires real Oracle + RQ worker. "
            "Run in nightly-integration gate with PRODUCTION_ACHIEVEMENT_USE_UNIFIED_JOB=on."
        )
