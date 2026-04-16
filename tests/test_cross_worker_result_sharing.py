# -*- coding: utf-8 -*-
"""Integration tests: cross-worker result sharing via spool store and Redis.

Simulates the multi-process (worker A writes, worker B reads) pattern used
when a background RQ worker produces a result that the API worker then serves.

Gate: @pytest.mark.integration AND --run-integration CLI flag.
Skipped automatically when Redis is not available.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# Redis availability check
# ---------------------------------------------------------------------------

def _redis_available() -> bool:
    """Return True if a real Redis connection is reachable."""
    try:
        from mes_dashboard.core.redis_client import get_redis_client
        client = get_redis_client()
        if client is None:
            return False
        client.ping()
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Fake-Redis factory (shared between tests that don't need real Redis)
# ---------------------------------------------------------------------------

def _make_fake_redis():
    """In-memory dict-backed Redis stub for isolation."""
    store: dict = {}
    lock = threading.Lock()

    client = MagicMock()

    def get(key):
        with lock:
            return store.get(key)

    def setex(key, ttl, value):
        with lock:
            store[key] = value

    def delete(*keys):
        with lock:
            for k in keys:
                store.pop(k, None)

    def hset(key, mapping=None, **kwargs):
        with lock:
            if key not in store:
                store[key] = {}
            if mapping:
                store[key].update(mapping)
            if kwargs:
                store[key].update(kwargs)

    def hgetall(key):
        with lock:
            return dict(store.get(key) or {})

    def expire(key, ttl):
        pass  # not needed for in-memory

    client.get = get
    client.setex = setex
    client.delete = delete
    client.hset = hset
    client.hgetall = hgetall
    client.expire = expire
    client.ping = lambda: True

    return client, store


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_sample_df(rows: int = 50) -> pd.DataFrame:
    return pd.DataFrame({
        "LOT_ID": [f"LOT{i:04d}" for i in range(rows)],
        "QTY": list(range(rows)),
        "STATUS": ["PRD"] * rows,
    })


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestCrossWorkerResultSharing:
    """Verify that spool files and job statuses are readable across simulated workers."""

    # ------------------------------------------------------------------ #
    # 6.10.1 — Spool written by worker A, readable by worker B           #
    # ------------------------------------------------------------------ #

    def test_spool_written_by_worker_readable_by_api(self, tmp_path):
        """Worker-A writes a spool file; a different thread reads it back correctly."""
        from mes_dashboard.core import query_spool_store as spool_mod

        fake_redis, _store = _make_fake_redis()

        df_written = _make_sample_df(rows=30)
        namespace = "test_ns"
        query_id = "crossworker-test-001"

        read_result: list[Optional[pd.DataFrame]] = [None]
        read_error: list[Optional[Exception]] = [None]

        with tempfile.TemporaryDirectory() as spool_dir, \
             patch.object(spool_mod, "QUERY_SPOOL_DIR", Path(spool_dir)), \
             patch.object(spool_mod, "QUERY_SPOOL_ENABLED", True), \
             patch("mes_dashboard.core.query_spool_store.get_redis_client", return_value=fake_redis), \
             patch("mes_dashboard.core.query_spool_store.get_control_redis_client", return_value=fake_redis):

            # --- Worker A: write ---
            ok = spool_mod.store_spooled_df(namespace, query_id, df_written)
            assert ok, "Worker A failed to store spool file"

            # --- Worker B: read from a different thread ---
            def reader_thread():
                try:
                    df = spool_mod.load_spooled_df(namespace, query_id)
                    read_result[0] = df
                except Exception as exc:
                    read_error[0] = exc

            t = threading.Thread(target=reader_thread)
            t.start()
            t.join(timeout=5)

        assert read_error[0] is None, f"Reader thread raised: {read_error[0]}"
        df_read = read_result[0]
        assert df_read is not None, "Worker B got None — spool file not found"
        assert len(df_read) == len(df_written), (
            f"Row count mismatch: written={len(df_written)}, read={len(df_read)}"
        )
        assert list(df_read.columns) == list(df_written.columns), "Column mismatch"

    # ------------------------------------------------------------------ #
    # 6.10.2 — Job status written by worker A visible to worker B        #
    # ------------------------------------------------------------------ #

    def test_job_status_visible_across_workers(self):
        """Status set by 'worker A' thread is readable by 'worker B' thread via Redis."""
        from mes_dashboard.services import async_query_job_service as job_svc

        fake_redis, _store = _make_fake_redis()

        prefix = "test"
        job_id = "xworker-job-abc123def"

        status_seen: list[Optional[dict]] = [None]
        error_in_reader: list[Optional[Exception]] = [None]

        with patch("mes_dashboard.services.async_query_job_service.get_control_redis_client",
                   return_value=fake_redis), \
             patch("mes_dashboard.services.async_query_job_service.get_redis_client",
                   return_value=fake_redis):

            # Worker A: write initial "queued" status.
            meta = {
                "status": "completed",
                "queue_name": "test",
                "created_at": str(time.time()),
                "completed_at": str(time.time()),
                "progress": "",
                "pct": "100",
                "stage": "",
                "completed_stages": "",
                "query_id": "result-q-001",
                "dataset_id": "",
                "error": "",
            }
            key = job_svc._meta_key(prefix, job_id)
            fake_redis.hset(key, mapping=meta)

            # Worker B: read from a different thread.
            def reader():
                try:
                    result = job_svc.get_job_status(prefix, job_id)
                    status_seen[0] = result
                except Exception as exc:
                    error_in_reader[0] = exc

            t = threading.Thread(target=reader)
            t.start()
            t.join(timeout=5)

        assert error_in_reader[0] is None, f"Reader error: {error_in_reader[0]}"
        assert status_seen[0] is not None, "Worker B could not read job status"
        assert status_seen[0]["status"] == "completed"
        assert status_seen[0]["query_id"] == "result-q-001"

    # ------------------------------------------------------------------ #
    # 6.10.3 — Spool not visible before atomic rename completes          #
    # ------------------------------------------------------------------ #

    def test_spool_not_visible_before_atomic_rename(self, tmp_path):
        """Reader must see None (miss) while temp file exists but rename not done yet."""
        from mes_dashboard.core import query_spool_store as spool_mod

        fake_redis, _store = _make_fake_redis()
        namespace = "test_ns"
        query_id = "atomic-rename-test-0x1"

        with tempfile.TemporaryDirectory() as spool_dir, \
             patch.object(spool_mod, "QUERY_SPOOL_DIR", Path(spool_dir)), \
             patch.object(spool_mod, "QUERY_SPOOL_ENABLED", True), \
             patch("mes_dashboard.core.query_spool_store.get_redis_client", return_value=fake_redis), \
             patch("mes_dashboard.core.query_spool_store.get_control_redis_client", return_value=fake_redis):

            # Compute where the canonical spool file would be placed.
            spool_root = Path(spool_dir)
            ns_dir = spool_root / spool_mod._normalize_namespace(namespace)
            ns_dir.mkdir(parents=True, exist_ok=True)
            canonical_path = ns_dir / f"{query_id}.parquet"
            tmp_write_path = canonical_path.with_suffix(".tmp")

            # Writer writes to .tmp but has NOT renamed yet.
            df = _make_sample_df(rows=10)
            df.to_parquet(tmp_write_path, engine="pyarrow", index=False)
            # Do NOT call _move_into_place — canonical_path must not exist yet.
            assert not canonical_path.exists(), "Canonical path must not exist before rename"

            # Reader thread tries to read.  Redis has no metadata yet → expect None.
            read_result: list[Optional[pd.DataFrame]] = [None]

            def reader():
                # No Redis metadata → load_spooled_df returns None (miss).
                result = spool_mod.load_spooled_df(namespace, query_id)
                read_result[0] = result

            t = threading.Thread(target=reader)
            t.start()
            t.join(timeout=5)

            assert read_result[0] is None, (
                "Reader saw data before atomic rename — partial visibility detected"
            )

            # Now complete the rename (writer finishes).
            spool_mod._move_into_place(tmp_write_path, canonical_path)
            assert canonical_path.exists(), "Canonical path must exist after rename"
