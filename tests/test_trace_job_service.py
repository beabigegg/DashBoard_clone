# -*- coding: utf-8 -*-
"""Unit tests for trace_job_service (async trace job queue)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch


import mes_dashboard.services.async_query_job_service as aqs
import mes_dashboard.services.trace_job_service as tjs


# ---------------------------------------------------------------------------
# is_async_available
# ---------------------------------------------------------------------------
def test_is_async_available_true():
    """Should return True when rq is importable, Redis is up, and workers exist."""
    aqs._RQ_AVAILABLE = None  # reset cached flag (now lives in shared module)
    aqs._rq_health_cache["available"] = None  # reset health cache
    mock_conn = MagicMock()
    with patch.object(aqs, "get_redis_client", return_value=mock_conn), \
         patch("rq.Worker") as mock_worker_cls:
        mock_worker_cls.all.return_value = [MagicMock()]  # simulate one worker
        assert tjs.is_async_available() is True


def test_is_async_available_false_no_redis():
    """Should return False when Redis is unavailable."""
    aqs._RQ_AVAILABLE = True
    aqs._rq_health_cache["available"] = None  # reset health cache (shared module)
    with patch.object(aqs, "get_redis_client", return_value=None):
        assert tjs.is_async_available() is False


# ---------------------------------------------------------------------------
# enqueue_trace_events_job
# ---------------------------------------------------------------------------
@patch.object(tjs, "_get_rq_queue")
@patch.object(tjs, "get_control_redis_client")
def test_enqueue_success(mock_ctrl_redis, mock_queue_fn):
    """Enqueue should return a job_id and store metadata in control-plane Redis."""
    ctrl = MagicMock()
    mock_ctrl_redis.return_value = ctrl

    queue = MagicMock()
    mock_queue_fn.return_value = queue

    job_id, err = tjs.enqueue_trace_events_job(
        "query_tool", ["CID-1", "CID-2"], ["history"], {"params": {}},
    )

    assert job_id is not None
    assert job_id.startswith("trace-evt-")
    assert err is None
    queue.enqueue.assert_called_once()
    ctrl.hset.assert_called_once()
    ctrl.expire.assert_called_once()


@patch.object(tjs, "_get_rq_queue", return_value=None)
def test_enqueue_no_queue(mock_queue_fn):
    """Enqueue should return error when queue is unavailable."""
    job_id, err = tjs.enqueue_trace_events_job(
        "query_tool", ["CID-1"], ["history"], {},
    )

    assert job_id is None
    assert "unavailable" in err


@patch.object(tjs, "_get_rq_queue")
@patch.object(tjs, "get_control_redis_client")
def test_enqueue_queue_error(mock_ctrl_redis, mock_queue_fn):
    """Enqueue should return error when queue.enqueue raises."""
    ctrl = MagicMock()
    mock_ctrl_redis.return_value = ctrl

    queue = MagicMock()
    queue.enqueue.side_effect = RuntimeError("connection refused")
    mock_queue_fn.return_value = queue

    job_id, err = tjs.enqueue_trace_events_job(
        "query_tool", ["CID-1"], ["history"], {},
    )

    assert job_id is None
    assert "connection refused" in err
    # Meta key should be cleaned up on control-plane Redis
    ctrl.delete.assert_called_once()


# ---------------------------------------------------------------------------
# get_job_status
# ---------------------------------------------------------------------------
@patch.object(tjs, "get_control_redis_client")
def test_get_job_status_found(mock_ctrl_redis):
    """Should return status dict from control-plane Redis hash."""
    conn = MagicMock()
    conn.hgetall.return_value = {
        "profile": "query_tool",
        "cid_count": "100",
        "domains": "history,materials",
        "status": "started",
        "progress": "fetching events",
        "created_at": "1740000000.0",
        "completed_at": "",
        "error": "",
    }
    mock_ctrl_redis.return_value = conn

    status = tjs.get_job_status("trace-evt-abc123")

    assert status is not None
    assert status["job_id"] == "trace-evt-abc123"
    assert status["status"] == "started"
    assert status["cid_count"] == 100
    assert status["domains"] == ["history", "materials"]
    assert status["error"] is None


@patch.object(tjs, "get_control_redis_client")
def test_get_job_status_not_found(mock_ctrl_redis):
    """Should return None when job metadata does not exist."""
    conn = MagicMock()
    conn.hgetall.return_value = {}
    mock_ctrl_redis.return_value = conn

    assert tjs.get_job_status("trace-evt-nonexistent") is None


# ---------------------------------------------------------------------------
# get_job_result
# ---------------------------------------------------------------------------
@patch.object(tjs, "get_redis_client")
def test_get_job_result_found_chunked(mock_redis):
    """Should return reconstructed result from chunked Redis keys."""
    result_meta = {
        "profile": "query_tool",
        "domains": {
            "history": {
                "chunks": 1,
                "total": 1,
                "quality_meta": {
                    "status": "complete",
                    "scope": "domain",
                    "domain": "history",
                    "reasons": [],
                },
            }
        },
        "failed_domains": [],
        "quality_meta": {"status": "complete", "scope": "query", "reasons": []},
    }
    chunk_data = [{"CONTAINERID": "CID-1"}]

    conn = MagicMock()

    def _get_side_effect(key):
        if key.endswith(":result:meta"):
            return json.dumps(result_meta)
        if key.endswith(":result:history:0"):
            return json.dumps(chunk_data)
        if key.endswith(":result:aggregation"):
            return None
        return None

    conn.get.side_effect = _get_side_effect
    mock_redis.return_value = conn

    result = tjs.get_job_result("trace-evt-abc123")

    assert result is not None
    assert result["stage"] == "events"
    assert result["results"]["history"]["count"] == 1
    assert result["results"]["history"]["total"] == 1
    assert result["results"]["history"]["quality_meta"]["status"] == "complete"
    assert result["quality_meta"]["status"] == "complete"


@patch.object(tjs, "get_redis_client")
def test_get_job_result_found_legacy(mock_redis):
    """Should fall back to legacy single-key result when no chunked meta exists."""
    result_data = {
        "stage": "events",
        "results": {"history": {"data": [{"CONTAINERID": "CID-1"}], "count": 1}},
        "aggregation": None,
    }
    conn = MagicMock()

    def _get_side_effect(key):
        if key.endswith(":result:meta"):
            return None  # no chunked meta
        if key.endswith(":result"):
            return json.dumps(result_data)
        return None

    conn.get.side_effect = _get_side_effect
    mock_redis.return_value = conn

    result = tjs.get_job_result("trace-evt-abc123")

    assert result is not None
    assert result["stage"] == "events"
    assert result["results"]["history"]["count"] == 1


@patch.object(tjs, "get_redis_client")
def test_get_job_result_not_found(mock_redis):
    """Should return None when result key does not exist."""
    conn = MagicMock()
    conn.get.return_value = None
    mock_redis.return_value = conn

    assert tjs.get_job_result("trace-evt-expired") is None


@patch.object(tjs, "get_redis_client")
def test_get_job_result_with_domain_filter(mock_redis):
    """Should return filtered result with pagination from chunked storage."""
    result_meta = {
        "profile": "query_tool",
        "domains": {
            "history": {"chunks": 1, "total": 3, "quality_meta": {"status": "complete", "scope": "domain", "domain": "history", "reasons": []}},
            "materials": {"chunks": 1, "total": 1, "quality_meta": {"status": "complete", "scope": "domain", "domain": "materials", "reasons": []}},
        },
        "failed_domains": [],
        "quality_meta": {"status": "complete", "scope": "query", "reasons": []},
    }
    history_chunk = [{"id": 1}, {"id": 2}, {"id": 3}]
    materials_chunk = [{"id": 10}]

    conn = MagicMock()

    def _get_side_effect(key):
        if key.endswith(":result:meta"):
            return json.dumps(result_meta)
        if key.endswith(":result:history:0"):
            return json.dumps(history_chunk)
        if key.endswith(":result:materials:0"):
            return json.dumps(materials_chunk)
        if key.endswith(":result:aggregation"):
            return None
        return None

    conn.get.side_effect = _get_side_effect
    mock_redis.return_value = conn

    result = tjs.get_job_result("trace-evt-abc", domain="history", offset=1, limit=1)

    assert "history" in result["results"]
    assert "materials" not in result["results"]
    assert result["results"]["history"]["data"] == [{"id": 2}]
    assert result["results"]["history"]["total"] == 3
    assert result["results"]["history"]["quality_meta"]["status"] == "complete"
    assert result["quality_meta"]["status"] == "complete"


# ---------------------------------------------------------------------------
# execute_trace_events_job (worker entry point)
# ---------------------------------------------------------------------------
@patch.object(tjs, "_write_trace_events_spool")
@patch.object(tjs, "get_redis_client")
@patch.object(tjs, "get_control_redis_client")
@patch("mes_dashboard.services.event_fetcher.EventFetcher.fetch_events")
def test_execute_job_success(mock_fetch, mock_ctrl_redis, mock_redis, mock_spool):
    """Worker should fetch events, store lightweight manifest, and update meta to finished."""
    mock_fetch.return_value = {"CID-1": [{"CONTAINERID": "CID-1"}]}

    conn = MagicMock()
    ctrl = MagicMock()
    mock_redis.return_value = conn
    mock_ctrl_redis.return_value = ctrl
    mock_spool.return_value = None  # spool write is a no-op in tests

    tjs.execute_trace_events_job(
        "test-job-1", "query_tool", ["CID-1"], ["history"], {},
    )

    mock_fetch.assert_called_once_with(["CID-1"], "history")
    mock_spool.assert_called_once()  # spool write was attempted

    # Result manifest stored on cache-plane Redis (1 setex: result:meta)
    setex_calls = [c for c in conn.method_calls if c[0] == "setex"]
    result_meta_call = [c for c in setex_calls if ":result:meta" in str(c)]
    assert len(result_meta_call) == 1
    stored_meta = json.loads(result_meta_call[0][1][2])
    assert "history" in stored_meta["domains"]
    assert stored_meta["domains"]["history"]["total"] == 1
    assert "query_id" in stored_meta  # spool-backed manifest includes query_id

    # No chunk keys (row data is in spool, not Redis)
    chunk_calls = [c for c in setex_calls if ":result:history:" in str(c)]
    assert len(chunk_calls) == 0

    # Job meta (hset) should be on control-plane Redis, status=finished
    hset_calls = [c for c in ctrl.method_calls if c[0] == "hset"]
    last_meta = hset_calls[-1][2]["mapping"]
    assert last_meta["status"] == "finished"


@patch("mes_dashboard.rq_worker_preload.ensure_rq_logging")
@patch.object(tjs, "_store_result_manifest")
@patch.object(tjs, "_write_trace_events_spool")
@patch.object(tjs, "get_redis_client")
@patch.object(tjs, "get_control_redis_client")
@patch.object(tjs, "_build_job_msd_aggregation")
@patch.object(tjs, "_write_msd_events_spool_from_paths")
@patch.object(tjs, "_resolve_msd_lineage_payload")
@patch("mes_dashboard.services.event_fetcher.EventFetcher.fetch_events_to_parquet")
@patch("mes_dashboard.services.mid_section_defect_service._write_msd_detection_stage_spool")
@patch("mes_dashboard.services.mid_section_defect_service._fetch_detection_by_container_ids")
def test_execute_job_msd_container_mode_fetches_detection_for_expanded_container_ids(
    mock_fetch_detection,
    mock_write_detection_stage,
    mock_fetch_events_to_parquet,
    mock_resolve_lineage,
    mock_write_events_stage,
    mock_build_aggregation,
    mock_ctrl_redis,
    mock_redis,
    mock_write_trace_spool,
    mock_store_manifest,
    _mock_ensure_rq_logging,
):
    mock_fetch_events_to_parquet.return_value = (
        1,
        {"status": "complete", "scope": "domain", "domain": "upstream_history", "reasons": []},
    )
    mock_resolve_lineage.return_value = {
        "ancestors": {
            "CID-SEED": ["CID-ANCESTOR-1", "CID-ANCESTOR-2"],
        },
    }
    mock_fetch_detection.return_value = MagicMock(empty=False, __len__=lambda self: 2)
    mock_build_aggregation.return_value = ({"kpi": {"lot_count": 1}}, None)
    mock_ctrl_redis.return_value = MagicMock()
    mock_redis.return_value = MagicMock()
    mock_write_trace_spool.return_value = None
    mock_store_manifest.return_value = None

    tjs.execute_trace_events_job(
        "test-job-msd-1",
        "mid_section_defect",
        ["CID-SEED"],
        ["upstream_history"],
        {
            "seed_container_ids": ["CID-SEED"],
            "params": {
                "mode": "container",
                "station": "測試",
                "direction": "backward",
            },
        },
    )

    mock_fetch_events_to_parquet.assert_called_once()
    fetched_container_ids = mock_fetch_events_to_parquet.call_args.args[0]
    assert fetched_container_ids == ["CID-SEED", "CID-ANCESTOR-1", "CID-ANCESTOR-2"]

    mock_fetch_detection.assert_called_once_with(
        ["CID-SEED", "CID-ANCESTOR-1", "CID-ANCESTOR-2"],
        "測試",
    )
    mock_write_detection_stage.assert_called_once()
    assert mock_write_detection_stage.call_args.args[1] is mock_fetch_detection.return_value
    mock_write_events_stage.assert_called_once()
    mock_build_aggregation.assert_called_once()


@patch.object(tjs, "_write_trace_events_spool")
@patch.object(tjs, "get_redis_client")
@patch.object(tjs, "get_control_redis_client")
@patch("mes_dashboard.services.event_fetcher.EventFetcher.fetch_events")
def test_execute_job_domain_failure_records_partial(mock_fetch, mock_ctrl_redis, mock_redis, mock_spool):
    """Domain fetch failure should result in partial failure, not job crash."""
    mock_fetch.side_effect = RuntimeError("db timeout")

    conn = MagicMock()
    ctrl = MagicMock()
    mock_redis.return_value = conn
    mock_ctrl_redis.return_value = ctrl
    mock_spool.return_value = None

    tjs.execute_trace_events_job(
        "test-job-2", "query_tool", ["CID-1"], ["history"], {},
    )

    # Result manifest stored with failed_domains
    setex_calls = [c for c in conn.method_calls if c[0] == "setex"]
    result_meta_call = [c for c in setex_calls if ":result:meta" in str(c)]
    assert len(result_meta_call) == 1
    stored_meta = json.loads(result_meta_call[0][1][2])
    assert "history" in stored_meta["failed_domains"]

    # Job meta should still be finished on control-plane Redis
    hset_calls = [c for c in ctrl.method_calls if c[0] == "hset"]
    last_meta = hset_calls[-1][2]["mapping"]
    assert last_meta["status"] == "finished"


# ---------------------------------------------------------------------------
# _store_chunked_result
# ---------------------------------------------------------------------------
@patch.object(tjs, "get_redis_client")
def test_store_chunked_result_splits_batches(mock_redis):
    """Large domain data should be split into multiple chunks."""
    conn = MagicMock()
    mock_redis.return_value = conn

    # 12 records, batch size 5 → 3 chunks (5+5+2)
    rows = [{"id": i} for i in range(12)]
    results = {"history": {"data": rows, "count": 12}}

    original_batch_size = tjs.TRACE_STREAM_BATCH_SIZE
    tjs.TRACE_STREAM_BATCH_SIZE = 5
    try:
        tjs._store_chunked_result(conn, "job-1", "query_tool", results, None, [])
    finally:
        tjs.TRACE_STREAM_BATCH_SIZE = original_batch_size

    setex_calls = [c for c in conn.method_calls if c[0] == "setex"]
    # 3 chunk keys + 1 result meta = 4
    assert len(setex_calls) == 4

    # Verify result meta
    meta_call = [c for c in setex_calls if ":result:meta" in str(c)]
    assert len(meta_call) == 1
    meta = json.loads(meta_call[0][1][2])
    assert meta["domains"]["history"]["chunks"] == 3
    assert meta["domains"]["history"]["total"] == 12

    # Verify chunks
    chunk_calls = [c for c in setex_calls if ":result:history:" in str(c)]
    assert len(chunk_calls) == 3
    chunk_0 = json.loads(chunk_calls[0][1][2])
    assert len(chunk_0) == 5


@patch.object(tjs, "get_redis_client")
def test_store_chunked_result_with_aggregation(mock_redis):
    """Aggregation should be stored in a separate key."""
    conn = MagicMock()
    mock_redis.return_value = conn

    results = {"history": {"data": [{"id": 1}], "count": 1}}
    aggregation = {"summary": {"total": 100}}

    tjs._store_chunked_result(conn, "job-1", "mid_section_defect", results, aggregation, [])

    setex_calls = [c for c in conn.method_calls if c[0] == "setex"]
    agg_call = [c for c in setex_calls if ":result:aggregation" in str(c)]
    assert len(agg_call) == 1
    stored_agg = json.loads(agg_call[0][1][2])
    assert stored_agg["summary"]["total"] == 100


# ---------------------------------------------------------------------------
# stream_job_result_ndjson
# ---------------------------------------------------------------------------
@patch.object(tjs, "get_redis_client")
def test_stream_ndjson_chunked(mock_redis):
    """NDJSON stream should yield correct protocol lines for chunked result."""
    result_meta = {
        "profile": "query_tool",
        "domains": {"history": {"chunks": 2, "total": 3}},
        "failed_domains": [],
    }
    chunk_0 = [{"id": 1}, {"id": 2}]
    chunk_1 = [{"id": 3}]

    conn = MagicMock()

    def _get_side_effect(key):
        if key.endswith(":result:meta"):
            return json.dumps(result_meta)
        if key.endswith(":result:history:0"):
            return json.dumps(chunk_0)
        if key.endswith(":result:history:1"):
            return json.dumps(chunk_1)
        if key.endswith(":result:aggregation"):
            return None
        return None

    conn.get.side_effect = _get_side_effect
    mock_redis.return_value = conn

    lines = list(tjs.stream_job_result_ndjson("job-1"))
    parsed = [json.loads(line) for line in lines]

    types = [p["type"] for p in parsed]
    assert types == [
        "meta",
        "domain_start",
        "records",
        "records",
        "domain_end",
        "quality_meta",
        "complete",
    ]

    assert parsed[0]["domains"] == ["history"]
    assert parsed[1]["domain"] == "history"
    assert parsed[1]["total"] == 3
    assert parsed[1]["quality_meta"]["domain"] == "history"
    assert parsed[2]["count"] == 2
    assert parsed[3]["count"] == 1
    assert parsed[4]["count"] == 3
    assert parsed[5]["quality_meta"]["status"] == "complete"
    assert parsed[6]["total_records"] == 3


@patch.object(tjs, "get_redis_client")
def test_stream_ndjson_with_aggregation(mock_redis):
    """NDJSON stream should include aggregation line when present."""
    result_meta = {
        "profile": "mid_section_defect",
        "domains": {"upstream_history": {"chunks": 1, "total": 1}},
        "failed_domains": [],
    }
    conn = MagicMock()

    def _get_side_effect(key):
        if key.endswith(":result:meta"):
            return json.dumps(result_meta)
        if key.endswith(":result:upstream_history:0"):
            return json.dumps([{"id": 1}])
        if key.endswith(":result:aggregation"):
            return json.dumps({"summary": "ok"})
        return None

    conn.get.side_effect = _get_side_effect
    mock_redis.return_value = conn

    lines = list(tjs.stream_job_result_ndjson("job-1"))
    parsed = [json.loads(line) for line in lines]

    types = [p["type"] for p in parsed]
    assert "aggregation" in types

    agg_line = [p for p in parsed if p["type"] == "aggregation"][0]
    assert agg_line["data"]["summary"] == "ok"


@patch.object(tjs, "get_redis_client")
def test_stream_ndjson_legacy_fallback(mock_redis):
    """NDJSON stream should emit full_result for legacy single-key storage."""
    legacy_result = {
        "stage": "events",
        "results": {"history": {"data": [{"id": 1}], "count": 1}},
        "aggregation": None,
    }
    conn = MagicMock()

    def _get_side_effect(key):
        if key.endswith(":result:meta"):
            return None  # no chunked meta
        if key.endswith(":result"):
            return json.dumps(legacy_result)
        return None

    conn.get.side_effect = _get_side_effect
    mock_redis.return_value = conn

    lines = list(tjs.stream_job_result_ndjson("job-1"))
    parsed = [json.loads(line) for line in lines]

    assert len(parsed) == 1
    assert parsed[0]["type"] == "full_result"
    assert parsed[0]["data"]["stage"] == "events"


@patch.object(tjs, "get_redis_client")
def test_stream_ndjson_with_failed_domains(mock_redis):
    """NDJSON stream should include warning line for partial failures."""
    result_meta = {
        "profile": "query_tool",
        "domains": {"materials": {"chunks": 1, "total": 1}},
        "failed_domains": ["history"],
    }
    conn = MagicMock()

    def _get_side_effect(key):
        if key.endswith(":result:meta"):
            return json.dumps(result_meta)
        if key.endswith(":result:materials:0"):
            return json.dumps([{"id": 1}])
        if key.endswith(":result:aggregation"):
            return None
        return None

    conn.get.side_effect = _get_side_effect
    mock_redis.return_value = conn

    lines = list(tjs.stream_job_result_ndjson("job-1"))
    parsed = [json.loads(line) for line in lines]

    types = [p["type"] for p in parsed]
    assert "warning" in types
    assert "quality_meta" in types

    warning = [p for p in parsed if p["type"] == "warning"][0]
    assert warning["code"] == "EVENTS_PARTIAL_FAILURE"
    assert "history" in warning["failed_domains"]


@patch("mes_dashboard.core.query_spool_store.load_spooled_df")
@patch.object(tjs, "get_redis_client")
def test_get_job_result_spool_manifest_exposes_trace_query_id(mock_redis, mock_load_spooled_df):
    """Spool-backed job results should expose canonical trace_query_id for MSD consumers."""
    result_meta = {
        "profile": "mid_section_defect",
        "query_id": "msd-abc123",
        "domains": {"upstream_history": {"total": 1}},
        "failed_domains": [],
    }
    conn = MagicMock()

    def _get_side_effect(key):
        if key.endswith(":result:meta"):
            return json.dumps(result_meta)
        if key.endswith(":result:aggregation"):
            return json.dumps({"kpi": {"lot_count": 1}})
        return None

    conn.get.side_effect = _get_side_effect
    mock_redis.return_value = conn
    mock_load_spooled_df.return_value = None

    result = tjs.get_job_result("job-1")

    assert result is not None
    assert result["query_id"] == "msd-abc123"
    assert result["trace_query_id"] == "msd-abc123"


@patch("mes_dashboard.core.query_spool_store.load_spooled_df")
@patch.object(tjs, "get_redis_client")
def test_stream_ndjson_spool_meta_includes_trace_query_id(mock_redis, mock_load_spooled_df):
    """Spool-backed NDJSON stream should expose canonical trace_query_id in meta."""
    result_meta = {
        "profile": "mid_section_defect",
        "query_id": "msd-abc123",
        "domains": {"upstream_history": {"total": 1}},
        "failed_domains": [],
    }
    conn = MagicMock()

    def _get_side_effect(key):
        if key.endswith(":result:meta"):
            return json.dumps(result_meta)
        if key.endswith(":result:aggregation"):
            return None
        return None

    conn.get.side_effect = _get_side_effect
    mock_redis.return_value = conn
    mock_load_spooled_df.return_value = None

    lines = list(tjs.stream_job_result_ndjson("job-1"))
    parsed = [json.loads(line) for line in lines]

    assert parsed[0]["type"] == "meta"
    assert parsed[0]["query_id"] == "msd-abc123"
    assert parsed[0]["trace_query_id"] == "msd-abc123"


# ---------------------------------------------------------------------------
# _flatten_domain_records
# ---------------------------------------------------------------------------
def test_flatten_domain_records():
    events_by_cid = {
        "CID-1": [{"CONTAINERID": "CID-1", "EVT": "A"}],
        "CID-2": [{"CONTAINERID": "CID-2", "EVT": "B"}, {"CONTAINERID": "CID-2", "EVT": "C"}],
    }
    rows = tjs._flatten_domain_records(events_by_cid)
    assert len(rows) == 3


@patch("mes_dashboard.services.trace_lineage_job_service.load_trace_lineage_result")
def test_resolve_msd_lineage_payload_from_query_id(mock_load):
    mock_load.return_value = {
        "ancestors": {"CID-001": ["CID-A", "CID-B"]},
        "seed_roots": {"CID-001": "ROOT-1"},
    }
    payload = {"lineage_query_id": "trace-lineage-mid-section-defect-123"}

    result = tjs._resolve_msd_lineage_payload(payload)

    assert result["ancestors"]["CID-001"] == ["CID-A", "CID-B"]
    mock_load.assert_called_once_with("trace-lineage-mid-section-defect-123")


def test_expand_msd_container_ids_backward():
    result = tjs._expand_msd_container_ids(
        ["CID-001"],
        {"ancestors": {"CID-001": ["CID-A", "CID-B"]}},
        "backward",
    )

    assert result == ["CID-001", "CID-A", "CID-B"]


def test_detection_hash_matches_make_detection_spool_query_id_multi_station():
    """detection_hash in trace job must use normalized station key, not raw list.

    When the frontend sends station as a list (multi-select), the trace job
    must produce the same detection_hash that _make_detection_spool_query_id
    uses so the D4 path can find the cached detection parquet.
    """
    from mes_dashboard.services.batch_query_engine import compute_query_hash
    from mes_dashboard.services.mid_section_defect_service import (
        _normalize_station,
        _canon_station_key,
        _make_detection_spool_query_id,
    )

    station_list = ['測試', '焊接_WB', '焊接_DW']
    start_date = "2026-05-27"
    end_date = "2026-06-02"

    # Hash as computed by _make_detection_spool_query_id (canonical)
    expected_hash = _make_detection_spool_query_id(start_date, end_date, station_list)

    # Hash as computed by the trace job after the fix (normalize → canon → hash)
    station_key = _canon_station_key(_normalize_station(station_list))
    actual_hash = compute_query_hash({
        "station": station_key,
        "start_date": start_date,
        "end_date": end_date,
    })

    assert actual_hash == expected_hash, (
        f"detection_hash mismatch: trace job would produce {actual_hash!r} "
        f"but spool uses {expected_hash!r}"
    )


def test_build_job_msd_aggregation_passes_station_order_fallback_to_get_summary():
    """_build_job_msd_aggregation must pass station_order_fallback to get_summary.

    Before the fix, get_summary was called without station_order_fallback, so
    upstream_groups defaulted to None and no WORKCENTER_GROUP filter was applied,
    causing downstream machines (e.g. 電鍍) to appear in the attribution chart.
    """
    from unittest.mock import MagicMock, patch

    mock_runtime = MagicMock()
    mock_runtime.is_available.return_value = True
    mock_runtime.get_summary.return_value = {"kpi": {}, "charts": {}}

    payload = {
        "params": {
            "direction": "backward",
            "station": "焊接_WB",
            "loss_reasons": None,
        }
    }

    # MsdDuckdbRuntime is imported inline; patch at definition site
    with patch("mes_dashboard.services.msd_duckdb_runtime.MsdDuckdbRuntime", return_value=mock_runtime):
        tjs._build_job_msd_aggregation(payload, {}, trace_query_id="trace-abc")

    call_kwargs = mock_runtime.get_summary.call_args.kwargs
    # station_order_fallback must be 2 (焊接_WB order)
    assert call_kwargs.get("station_order_fallback") == 2, (
        f"Expected station_order_fallback=2 for 焊接_WB, got {call_kwargs.get('station_order_fallback')}"
    )


def test_build_job_msd_aggregation_passes_upstream_groups_to_get_summary_with_detection():
    """D4 path must pass upstream_station_groups to get_summary_with_detection."""
    from unittest.mock import MagicMock, patch
    from pathlib import Path

    mock_runtime = MagicMock()
    mock_runtime.is_available.return_value = True
    mock_runtime.get_summary.return_value = None  # force D4 path
    mock_runtime.get_summary_with_detection.return_value = {"kpi": {}, "charts": {}}

    payload = {
        "params": {
            "direction": "backward",
            "station": "焊接_WB",
            "loss_reasons": None,
        }
    }

    # Both inline imports must be patched at definition site
    with patch("mes_dashboard.services.msd_duckdb_runtime.MsdDuckdbRuntime", return_value=mock_runtime), \
         patch("mes_dashboard.core.query_spool_store.get_spool_file_path", return_value="/fake/det.parquet"), \
         patch.object(Path, "exists", return_value=True):
        tjs._build_job_msd_aggregation(
            payload, {}, trace_query_id="trace-abc", detection_hash="hash-123"
        )

    call_kwargs = mock_runtime.get_summary_with_detection.call_args.kwargs
    upstream = call_kwargs.get("upstream_station_groups")
    assert upstream is not None, "upstream_station_groups must not be None for backward 焊接_WB"
    assert "電鍍" not in upstream, f"電鍍 must not be in upstream groups: {upstream}"
    assert "切割" in upstream, f"切割 must be in upstream groups for 焊接_WB(order=2): {upstream}"
    assert "焊接_DB" in upstream, f"焊接_DB must be in upstream groups for 焊接_WB(order=2): {upstream}"
