# -*- coding: utf-8 -*-
"""Unified spool pipeline helpers for multi-stage RQ jobs.

Encapsulates the pattern of:
  1. Enqueueing an RQ job that produces one or more parquet stage files
  2. Updating job progress per stage via async_query_job_service
  3. Registering final spool metadata once all stages complete

Usage inside an RQ worker function::

    from mes_dashboard.core.spool_pipeline import SpoolPipeline

    def my_rq_job(job_id, query_params):
        pipeline = SpoolPipeline(job_id=job_id, namespace="myreport")
        pipeline.update_progress("running", stage="fetch", pct=10)
        # ... write tmp parquet file ...
        pipeline.register_stage(query_id="myreport-abc123", stage="fetch",
                                 src_path=tmp_path, row_count=n)
        pipeline.update_progress("running", stage="aggregate", pct=60)
        # ... write aggregation parquet ...
        pipeline.register_stage(query_id="myreport-abc123", stage="aggregate",
                                 src_path=agg_path, row_count=m)
        pipeline.complete(query_id="myreport-abc123")
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("mes_dashboard.spool_pipeline")


class SpoolPipeline:
    """Coordinates stage spool registration and job progress for a single RQ job."""

    def __init__(
        self,
        job_id: str,
        namespace: str,
        *,
        prefix: str = "async",
        ttl_seconds: Optional[int] = None,
    ) -> None:
        self.job_id = job_id
        self.namespace = namespace
        self.prefix = prefix
        self.ttl_seconds = ttl_seconds
        self._completed_stages: list[str] = []

    # ------------------------------------------------------------------
    # Progress helpers
    # ------------------------------------------------------------------

    def update_progress(
        self,
        status: str = "running",
        *,
        stage: Optional[str] = None,
        pct: Optional[int] = None,
        message: Optional[str] = None,
    ) -> None:
        """Update job progress metadata in Redis."""
        from mes_dashboard.services.async_query_job_service import update_job_progress

        fields: dict = {"status": status}
        if stage:
            fields["stage"] = stage
        if pct is not None:
            fields["pct"] = str(pct)
        if message:
            fields["progress"] = message
        if self._completed_stages:
            fields["completed_stages"] = ",".join(self._completed_stages)
        update_job_progress(self.prefix, self.job_id, **fields)

    # ------------------------------------------------------------------
    # Stage spool registration
    # ------------------------------------------------------------------

    def register_stage(
        self,
        query_id: str,
        stage: str,
        src_path: Path,
        row_count: int,
    ) -> bool:
        """Move *src_path* to canonical stage location and record metadata."""
        from mes_dashboard.core.query_spool_store import register_stage_spool_file

        ok = register_stage_spool_file(
            self.namespace,
            query_id,
            stage,
            src_path,
            row_count,
            ttl_seconds=self.ttl_seconds,
        )
        if ok:
            self._completed_stages.append(stage)
            logger.debug(
                "SpoolPipeline[%s] stage=%s registered (query_id=%s rows=%d)",
                self.job_id, stage, query_id, row_count,
            )
        else:
            logger.warning(
                "SpoolPipeline[%s] failed to register stage=%s (query_id=%s)",
                self.job_id, stage, query_id,
            )
        return ok

    def register_final(
        self,
        query_id: str,
        src_path: Path,
        row_count: int,
    ) -> bool:
        """Register a single-stage or final consolidated parquet file."""
        from mes_dashboard.core.query_spool_store import register_spool_file

        ok = register_spool_file(
            self.namespace,
            query_id,
            src_path,
            row_count,
            ttl_seconds=self.ttl_seconds,
        )
        if ok:
            logger.debug(
                "SpoolPipeline[%s] final spool registered (query_id=%s rows=%d)",
                self.job_id, query_id, row_count,
            )
        else:
            logger.warning(
                "SpoolPipeline[%s] failed to register final spool (query_id=%s)",
                self.job_id, query_id,
            )
        return ok

    # ------------------------------------------------------------------
    # Completion / failure
    # ------------------------------------------------------------------

    def complete(self, query_id: str) -> None:
        """Mark the job as completed with the given canonical query_id."""
        from mes_dashboard.services.async_query_job_service import complete_job

        complete_job(self.prefix, self.job_id, query_id=query_id)
        logger.info(
            "SpoolPipeline[%s] completed (query_id=%s stages=%s)",
            self.job_id, query_id, self._completed_stages,
        )

    def fail(self, error: str) -> None:
        """Mark the job as failed."""
        from mes_dashboard.services.async_query_job_service import complete_job

        complete_job(self.prefix, self.job_id, error=error)
        logger.warning("SpoolPipeline[%s] failed: %s", self.job_id, error)
