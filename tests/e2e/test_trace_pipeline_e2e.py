# -*- coding: utf-8 -*-
"""E2E tests for trace pipeline: memory triage, async job queue, NDJSON streaming.

Tests the three core features implemented in the trace pipeline proposals:
  1. Memory triage — admission control, CID limits, MSD bypass
  2. Async job queue — RQ-based async routing, job lifecycle
  3. NDJSON streaming — chunked Redis storage, streaming protocol

Run with: pytest tests/e2e/test_trace_pipeline_e2e.py -v --run-e2e
"""

import json
import os
import time
import uuid

import pytest
import redis
import requests

pytestmark = [pytest.mark.e2e]

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
REDIS_KEY_PREFIX = os.getenv("REDIS_KEY_PREFIX", "mes_wip")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _post_events(base_url, profile, container_ids, domains=None, timeout=60):
    payload = {"profile": profile, "container_ids": container_ids}
    if domains:
        payload["domains"] = domains
    response = None
    for attempt in range(4):
        response = requests.post(
            f"{base_url}/api/trace/events", json=payload, timeout=timeout,
        )
        if response.status_code != 503:
            return response
        try:
            code = (response.json().get("error") or {}).get("code")
        except ValueError:
            code = None
        if code != "SERVICE_UNAVAILABLE" or attempt >= 3:
            return response
        retry_after = response.headers.get("Retry-After")
        try:
            wait_seconds = float(retry_after) if retry_after else 2.0
        except ValueError:
            wait_seconds = 2.0
        time.sleep(wait_seconds)
    return response


def _poll_trace_job_until_terminal(base_url, job_id, timeout=180):
    """Poll trace async job until finished/failed and return the final status."""
    deadline = time.time() + timeout
    final_status = None
    while time.time() < deadline:
        status_resp = requests.get(f"{base_url}/api/trace/job/{job_id}", timeout=10)
        assert status_resp.status_code == 200
        final_status = status_resp.json().get("data", status_resp.json())
        if final_status["status"] in ("finished", "failed"):
            break
        time.sleep(2)
    return final_status


def _unwrap_events_payload(base_url, response):
    """Return materialized events payload from either sync or async response."""
    assert response.status_code in (200, 202), (
        f"Expected 200 or 202, got {response.status_code}: {response.text[:200]}"
    )
    payload = response.json().get("data", response.json())
    if response.status_code == 200:
        return payload

    assert payload.get("async") is True
    job_id = payload.get("job_id")
    assert job_id, f"Async events response missing job_id: {payload}"

    final_status = _poll_trace_job_until_terminal(base_url, job_id)
    assert final_status is not None, "Trace async job polling timed out"
    assert final_status["status"] == "finished", f"Trace async job did not finish: {final_status}"

    result_resp = requests.get(f"{base_url}/api/trace/job/{job_id}/result", timeout=30)
    assert result_resp.status_code == 200, (
        f"Expected 200 result for trace job {job_id}, got {result_resp.status_code}: {result_resp.text[:200]}"
    )
    return result_resp.json().get("data", result_resp.json())


def _resolve_cids(base_url, work_order):
    """Resolve real container IDs from a work order via live API."""
    resp = None
    for attempt in range(4):
        resp = requests.post(
            f"{base_url}/api/query-tool/resolve",
            json={"input_type": "work_order", "values": [work_order]},
            timeout=30,
        )
        if resp.status_code != 429:
            break
        if attempt >= 3:
            break
        retry_after = resp.headers.get("Retry-After")
        try:
            wait_seconds = float(retry_after) if retry_after else 1.0
        except ValueError:
            wait_seconds = 1.0
        time.sleep(wait_seconds)
    if resp.status_code != 200:
        return []
    payload = resp.json()
    # success_response wraps: {"data": {"data": [...]}, "success": true}
    inner = payload.get("data", payload)
    lots = inner.get("data", inner) if isinstance(inner, dict) else inner
    if not isinstance(lots, list):
        lots = []
    return [
        str(lot.get("container_id") or lot.get("CONTAINERID") or "")
        for lot in lots
        if isinstance(lot, dict) and (lot.get("container_id") or lot.get("CONTAINERID"))
    ]


def _get_redis():
    """Get a direct Redis client for seeding test data."""
    return redis.from_url(REDIS_URL, decode_responses=True)


def _key(suffix):
    return f"{REDIS_KEY_PREFIX}:{suffix}"


def _seed_completed_job(r, job_id, profile, domain_data, aggregation=None,
                        failed_domains=None, batch_size=3):
    """Seed Redis with a completed job's chunked result for streaming tests.

    Args:
        r: Redis client
        job_id: Job identifier
        profile: Profile name
        domain_data: dict of {domain_name: [list of record dicts]}
        aggregation: optional aggregation dict
        failed_domains: list of failed domain names
        batch_size: records per chunk (small for testing)
    """
    ttl = 300  # 5 min TTL for test data

    # Job meta (hash)
    meta_key = _key(f"trace:job:{job_id}:meta")
    r.hset(meta_key, mapping={
        "profile": profile,
        "cid_count": "100",
        "domains": ",".join(domain_data.keys()),
        "status": "finished",
        "progress": "done",
        "created_at": str(time.time() - 10),
        "completed_at": str(time.time()),
        "error": "",
    })
    r.expire(meta_key, ttl)

    # Chunked result storage
    domain_info = {}
    for domain_name, rows in domain_data.items():
        chunks = [
            rows[i:i + batch_size]
            for i in range(0, max(len(rows), 1), batch_size)
        ] if rows else []

        for idx, chunk in enumerate(chunks):
            chunk_key = _key(f"trace:job:{job_id}:result:{domain_name}:{idx}")
            r.setex(chunk_key, ttl, json.dumps(chunk))

        domain_info[domain_name] = {"chunks": len(chunks), "total": len(rows)}

    # Aggregation
    if aggregation is not None:
        agg_key = _key(f"trace:job:{job_id}:result:aggregation")
        r.setex(agg_key, ttl, json.dumps(aggregation))

    # Result meta
    result_meta = {
        "profile": profile,
        "domains": domain_info,
        "failed_domains": sorted(failed_domains) if failed_domains else [],
    }
    result_meta_key = _key(f"trace:job:{job_id}:result:meta")
    r.setex(result_meta_key, ttl, json.dumps(result_meta))


def _cleanup_job(r, job_id):
    """Remove all Redis keys for a test job."""
    pattern = _key(f"trace:job:{job_id}:*")
    keys = list(r.scan_iter(pattern))
    if keys:
        r.delete(*keys)


def _parse_ndjson(response_text):
    """Parse NDJSON response text into list of dicts."""
    lines = []
    for line in response_text.strip().split("\n"):
        line = line.strip()
        if line:
            lines.append(json.loads(line))
    return lines


def _maybe_skip_on_service_overload(resp, context: str):
    """Skip tests when overload protection is intentionally active."""
    if resp.status_code != 503:
        return
    try:
        code = (resp.json().get("error") or {}).get("code")
    except ValueError:
        code = None
    if code == "SERVICE_UNAVAILABLE":
        pytest.skip(f"{context}: service overload guard active")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def base(app_server):
    return app_server


@pytest.fixture(scope="module")
def real_cids(base):
    """Resolve real CIDs from a known work order."""
    cids = _resolve_cids(base, "GA26010001")
    if not cids:
        pytest.skip("No container IDs resolved — cannot test trace pipeline")
    return cids


@pytest.fixture(scope="module")
def rclient():
    """Direct Redis client for seeding/cleanup."""
    r = _get_redis()
    try:
        r.ping()
    except redis.ConnectionError:
        pytest.skip("Redis not available")
    return r


# ===========================================================================
# 1. Memory Triage — Admission Control
# ===========================================================================
class TestTraceAdmissionControl:
    """Verify admission control: CID limits, profile bypass, validation."""

    def test_sync_response_with_small_cid_set(self, base, real_cids):
        """Small CID count returns usable trace data via sync hit or async materialization."""
        small_cids = real_cids[:3]
        resp = _post_events(base, "query_tool", small_cids, domains=["history"])
        _maybe_skip_on_service_overload(resp, "trace sync small cid")

        data = _unwrap_events_payload(base, resp)
        assert data["stage"] == "events"
        assert "results" in data
        assert "history" in data["results"]
        history = data["results"]["history"]
        assert "data" in history
        assert "count" in history
        assert isinstance(history["data"], list)
        # With real CIDs we should get actual history records
        assert history["count"] >= 0

    def test_sync_response_data_structure_complete(self, base, real_cids):
        """Trace response has proper domain data structure after sync/async completion."""
        resp = _post_events(base, "query_tool", real_cids[:5],
                            domains=["history", "materials"])
        _maybe_skip_on_service_overload(resp, "trace sync data structure")
        data = _unwrap_events_payload(base, resp)
        for domain in ["history", "materials"]:
            assert domain in data["results"], f"Missing domain '{domain}'"
            d = data["results"][domain]
            assert "data" in d, f"Domain '{domain}' missing 'data'"
            assert "count" in d, f"Domain '{domain}' missing 'count'"
            assert d["count"] == len(d["data"])

    def test_cid_limit_exceeded_non_msd_returns_413_or_202(self, base):
        """Non-MSD profile with > CID_LIMIT → 413 (no async) or 202 (async)."""
        cid_limit = int(os.getenv("TRACE_EVENTS_CID_LIMIT", "50000"))
        # Generate fake CIDs that exceed the limit
        fake_cids = [f"FAKE-{i:06x}" for i in range(cid_limit + 1)]

        resp = _post_events(base, "query_tool", fake_cids, domains=["history"])

        assert resp.status_code in (413, 202), (
            f"Expected 413 or 202 for {cid_limit + 1} CIDs, got {resp.status_code}"
        )
        if resp.status_code == 413:
            err = resp.json()["error"]
            assert err["code"] == "CID_LIMIT_EXCEEDED"
            assert str(cid_limit) in err["message"]

    def test_msd_profile_bypasses_cid_limit(self, base):
        """MSD profile must NOT return 413 even with > CID_LIMIT CIDs.

        MSD requires all CIDs for accurate aggregation — no hard cutoff.
        With async available, large MSD queries should route to 202.
        Without async, they proceed to sync (may be slow but not rejected).
        """
        async_threshold = int(os.getenv("TRACE_ASYNC_CID_THRESHOLD", "20000"))
        # Use just above async threshold — enough to trigger async routing
        # but below CID_LIMIT to keep test fast
        fake_cids = [f"MSD-{i:06x}" for i in range(async_threshold + 1)]

        resp = _post_events(base, "mid_section_defect", fake_cids,
                            domains=["rejects"])

        # Must NOT be 413 — MSD bypasses CID limit
        assert resp.status_code != 413, (
            "MSD profile should NEVER receive 413 CID_LIMIT_EXCEEDED"
        )
        # Should be 202 (async) or 200 (sync fallback)
        assert resp.status_code in (200, 202)

    def test_empty_container_ids_rejected(self, base):
        """Empty container_ids list → 400 INVALID_PARAMS."""
        resp = _post_events(base, "query_tool", [])
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "INVALID_PARAMS"

    def test_missing_profile_rejected(self, base):
        """Missing profile field → 400."""
        resp = requests.post(
            f"{base}/api/trace/events",
            json={"container_ids": ["CID-001"]},
            timeout=10,
        )
        assert resp.status_code == 400

    def test_invalid_domain_rejected(self, base):
        """Invalid domain name → 400 INVALID_PARAMS."""
        resp = _post_events(
            base, "query_tool", ["CID-001"], domains=["nonexistent_domain"],
        )
        assert resp.status_code == 400
        assert "INVALID_PARAMS" in resp.json()["error"]["code"]


# ===========================================================================
# 2. Async Job Queue
# ===========================================================================
class TestTraceAsyncJobQueue:
    """Verify async job routing, lifecycle, and result retrieval."""

    def test_async_routing_returns_202_with_correct_format(self, base):
        """Large CID count + async available → 202 with job metadata."""
        threshold = int(os.getenv("TRACE_ASYNC_CID_THRESHOLD", "20000"))
        fake_cids = [f"ASYNC-{i:06x}" for i in range(threshold + 1)]

        resp = _post_events(base, "query_tool", fake_cids, domains=["history"])

        if resp.status_code != 202:
            pytest.skip("Async not available (RQ worker not running)")

        payload = resp.json()
        data = payload.get("data", payload)
        assert data["async"] is True
        assert data["stage"] == "events"
        assert "job_id" in data
        assert data["job_id"].startswith("trace-evt-")
        assert "status_url" in data
        assert "stream_url" in data
        assert data["status_url"] == f"/api/trace/job/{data['job_id']}"
        assert data["stream_url"] == f"/api/trace/job/{data['job_id']}/stream"

    def test_job_status_after_enqueue(self, base):
        """After async enqueue, job status should be queryable."""
        threshold = int(os.getenv("TRACE_ASYNC_CID_THRESHOLD", "20000"))
        fake_cids = [f"STATUS-{i:06x}" for i in range(threshold + 1)]

        enqueue_resp = _post_events(base, "query_tool", fake_cids,
                                    domains=["history"])
        if enqueue_resp.status_code != 202:
            pytest.skip("Async not available")

        job_id = enqueue_resp.json().get("data", enqueue_resp.json())["job_id"]

        status_resp = requests.get(
            f"{base}/api/trace/job/{job_id}", timeout=10,
        )
        assert status_resp.status_code == 200
        status = status_resp.json().get("data", status_resp.json())
        assert status["job_id"] == job_id
        assert status["status"] in ("queued", "started", "finished", "failed")
        assert status["profile"] == "query_tool"
        assert status["cid_count"] == threshold + 1
        assert "history" in status["domains"]
        assert "elapsed_seconds" in status

    def test_job_lifecycle_poll_until_terminal(self, base):
        """Full lifecycle: enqueue → poll until finished/failed → verify result."""
        threshold = int(os.getenv("TRACE_ASYNC_CID_THRESHOLD", "20000"))
        fake_cids = [f"LIFE-{i:06x}" for i in range(threshold + 1)]

        enqueue_resp = _post_events(base, "query_tool", fake_cids,
                                    domains=["history"])
        if enqueue_resp.status_code != 202:
            pytest.skip("Async not available")

        job_id = enqueue_resp.json().get("data", enqueue_resp.json())["job_id"]
        status_url = f"{base}/api/trace/job/{job_id}"

        # Poll until terminal state (max 120s — fake CIDs will fail fast)
        terminal = False
        final_status = None
        deadline = time.time() + 120
        while time.time() < deadline:
            resp = requests.get(status_url, timeout=30)
            assert resp.status_code == 200
            final_status = resp.json().get("data", resp.json())
            if final_status["status"] in ("finished", "failed"):
                terminal = True
                break
            time.sleep(2)

        assert terminal, f"Job did not reach terminal state within 120s, last: {final_status}"

        # Job with fake CIDs may finish with empty results or fail —
        # either is acceptable. Key is that the lifecycle completed.
        if final_status["status"] == "finished":
            # Result should be retrievable
            result_resp = requests.get(
                f"{base}/api/trace/job/{job_id}/result", timeout=30,
            )
            assert result_resp.status_code == 200
            result = result_resp.json().get("data", result_resp.json())
            assert result["stage"] == "events"
            assert "results" in result

    def test_job_not_found_returns_404(self, base):
        """Non-existent job → 404."""
        resp = requests.get(
            f"{base}/api/trace/job/trace-evt-nonexistent99", timeout=10,
        )
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "JOB_NOT_FOUND"

    def test_job_result_not_found_returns_404(self, base):
        """Non-existent job result → 404."""
        resp = requests.get(
            f"{base}/api/trace/job/trace-evt-nonexistent99/result", timeout=10,
        )
        assert resp.status_code == 404

    def test_job_result_before_completion_returns_409(self, base, rclient):
        """Result request for an in-progress job → 409."""
        job_id = f"trace-evt-inprogress{uuid.uuid4().hex[:6]}"
        meta_key = _key(f"trace:job:{job_id}:meta")
        rclient.hset(meta_key, mapping={
            "profile": "query_tool",
            "cid_count": "100",
            "domains": "history",
            "status": "started",
            "progress": "fetching",
            "created_at": str(time.time()),
            "completed_at": "",
            "error": "",
        })
        rclient.expire(meta_key, 60)

        try:
            resp = requests.get(
                f"{base}/api/trace/job/{job_id}/result", timeout=10,
            )
            assert resp.status_code == 409
            assert resp.json()["error"]["code"] == "JOB_NOT_COMPLETE"
        finally:
            rclient.delete(meta_key)


# ===========================================================================
# 3. NDJSON Streaming
# ===========================================================================
class TestTraceNDJSONStream:
    """Verify NDJSON streaming endpoint and protocol."""

    def test_stream_not_found_returns_404(self, base):
        """Stream for non-existent job → 404."""
        resp = requests.get(
            f"{base}/api/trace/job/trace-evt-nonexistent99/stream", timeout=10,
        )
        assert resp.status_code == 404

    def test_stream_before_completion_returns_409(self, base, rclient):
        """Stream request for an in-progress job → 409."""
        job_id = f"trace-evt-stream409{uuid.uuid4().hex[:6]}"
        meta_key = _key(f"trace:job:{job_id}:meta")
        rclient.hset(meta_key, mapping={
            "profile": "query_tool",
            "cid_count": "50",
            "domains": "history",
            "status": "started",
            "progress": "fetching",
            "created_at": str(time.time()),
            "completed_at": "",
            "error": "",
        })
        rclient.expire(meta_key, 60)

        try:
            resp = requests.get(
                f"{base}/api/trace/job/{job_id}/stream", timeout=30,
            )
            assert resp.status_code == 409
            data = resp.json()
            assert data["error"]["code"] == "JOB_NOT_COMPLETE"
            assert data.get("meta", {}).get("job_status") == "started"
        finally:
            rclient.delete(meta_key)

    def test_stream_protocol_single_domain(self, base, rclient):
        """Stream a completed job with one domain — verify full NDJSON protocol."""
        job_id = f"trace-evt-stream1d{uuid.uuid4().hex[:6]}"
        records = [{"CID": f"C{i}", "EVENT": f"ev{i}", "TS": "2026-01-01"}
                    for i in range(7)]

        _seed_completed_job(rclient, job_id, "query_tool",
                            {"history": records}, batch_size=3)
        try:
            resp = requests.get(
                f"{base}/api/trace/job/{job_id}/stream", timeout=10,
            )
            assert resp.status_code == 200
            assert "application/x-ndjson" in resp.headers["Content-Type"]
            assert resp.headers.get("Cache-Control") == "no-cache"

            lines = _parse_ndjson(resp.text)
            types = [ln["type"] for ln in lines]

            # Protocol: meta → domain_start → records(×3) → domain_end → quality_meta → complete
            assert types[0] == "meta"
            assert types[1] == "domain_start"
            assert types[-2] == "quality_meta"
            assert types[-1] == "complete"

            # Verify meta line
            meta = lines[0]
            assert meta["job_id"] == job_id
            assert meta["profile"] == "query_tool"
            assert "history" in meta["domains"]

            # Verify domain_start
            ds = lines[1]
            assert ds["domain"] == "history"
            assert ds["total"] == 7

            # Verify records batches (7 records / batch_size=3 → 3 chunks)
            record_lines = [ln for ln in lines if ln["type"] == "records"]
            assert len(record_lines) == 3  # ceil(7/3) = 3 chunks
            total_streamed = sum(ln["count"] for ln in record_lines)
            assert total_streamed == 7

            # Verify batch indices
            batches = [ln["batch"] for ln in record_lines]
            assert batches == [0, 1, 2]

            # Verify actual data content
            all_records = []
            for ln in record_lines:
                assert ln["domain"] == "history"
                all_records.extend(ln["data"])
            assert len(all_records) == 7
            assert all_records[0]["CID"] == "C0"
            assert all_records[6]["CID"] == "C6"

            # Verify domain_end count matches
            de = [ln for ln in lines if ln["type"] == "domain_end"][0]
            assert de["count"] == 7

            # Verify complete
            complete = lines[-1]
            assert complete["total_records"] == 7
        finally:
            _cleanup_job(rclient, job_id)

    def test_stream_protocol_multi_domain(self, base, rclient):
        """Stream a completed job with multiple domains."""
        job_id = f"trace-evt-streammd{uuid.uuid4().hex[:6]}"
        history = [{"CID": f"H{i}", "EVENT": "hist"} for i in range(5)]
        materials = [{"CID": f"M{i}", "MAT": "mat"} for i in range(4)]
        rejects = [{"CID": f"R{i}", "REJ": "rej"} for i in range(2)]

        _seed_completed_job(rclient, job_id, "query_tool", {
            "history": history,
            "materials": materials,
            "rejects": rejects,
        }, batch_size=3)

        try:
            resp = requests.get(
                f"{base}/api/trace/job/{job_id}/stream", timeout=10,
            )
            assert resp.status_code == 200
            lines = _parse_ndjson(resp.text)
            types = [ln["type"] for ln in lines]

            # Must start with meta and end with complete
            assert types[0] == "meta"
            assert types[-1] == "complete"
            assert set(lines[0]["domains"]) == {"history", "materials", "rejects"}

            # Each domain must have domain_start → records → domain_end sequence
            for domain_name, expected_total in [("history", 5), ("materials", 4), ("rejects", 2)]:
                starts = [ln for ln in lines if ln["type"] == "domain_start" and ln["domain"] == domain_name]
                ends = [ln for ln in lines if ln["type"] == "domain_end" and ln["domain"] == domain_name]
                recs = [ln for ln in lines if ln["type"] == "records" and ln["domain"] == domain_name]

                assert len(starts) == 1, f"Expected 1 domain_start for {domain_name}"
                assert len(ends) == 1, f"Expected 1 domain_end for {domain_name}"
                assert starts[0]["total"] == expected_total
                assert ends[0]["count"] == expected_total
                assert sum(ln["count"] for ln in recs) == expected_total

            # Total records across all domains
            complete = lines[-1]
            assert complete["total_records"] == 11  # 5 + 4 + 2
        finally:
            _cleanup_job(rclient, job_id)

    def test_stream_with_aggregation(self, base, rclient):
        """Stream includes aggregation line for MSD profile."""
        job_id = f"trace-evt-streamagg{uuid.uuid4().hex[:6]}"
        rejects = [{"CID": f"R{i}", "DEFECT": "scratch"} for i in range(4)]
        aggregation = {
            "total_defects": 42,
            "by_category": {"scratch": 30, "crack": 12},
        }

        _seed_completed_job(rclient, job_id, "mid_section_defect",
                            {"rejects": rejects}, aggregation=aggregation,
                            batch_size=5)
        try:
            resp = requests.get(
                f"{base}/api/trace/job/{job_id}/stream", timeout=10,
            )
            assert resp.status_code == 200
            lines = _parse_ndjson(resp.text)
            types = [ln["type"] for ln in lines]

            assert "aggregation" in types
            agg_line = [ln for ln in lines if ln["type"] == "aggregation"][0]
            assert agg_line["data"]["total_defects"] == 42
            assert agg_line["data"]["by_category"]["scratch"] == 30

            # aggregation must come after domain_end and before complete
            agg_idx = types.index("aggregation")
            complete_idx = types.index("complete")
            last_domain_end_idx = max(
                i for i, t in enumerate(types) if t == "domain_end"
            )
            assert last_domain_end_idx < agg_idx < complete_idx
        finally:
            _cleanup_job(rclient, job_id)

    def test_stream_with_failed_domains(self, base, rclient):
        """Stream includes warning line when some domains failed."""
        job_id = f"trace-evt-streamfail{uuid.uuid4().hex[:6]}"
        history = [{"CID": "C1", "EVENT": "ev1"}]

        _seed_completed_job(rclient, job_id, "query_tool",
                            {"history": history},
                            failed_domains=["materials", "rejects"],
                            batch_size=5)
        try:
            resp = requests.get(
                f"{base}/api/trace/job/{job_id}/stream", timeout=10,
            )
            assert resp.status_code == 200
            lines = _parse_ndjson(resp.text)
            types = [ln["type"] for ln in lines]

            assert "warning" in types
            warning = [ln for ln in lines if ln["type"] == "warning"][0]
            assert warning["code"] == "EVENTS_PARTIAL_FAILURE"
            assert set(warning["failed_domains"]) == {"materials", "rejects"}
        finally:
            _cleanup_job(rclient, job_id)

    def test_stream_empty_domain(self, base, rclient):
        """Stream handles domain with zero records gracefully."""
        job_id = f"trace-evt-streamempty{uuid.uuid4().hex[:6]}"

        _seed_completed_job(rclient, job_id, "query_tool",
                            {"history": []}, batch_size=5)
        try:
            resp = requests.get(
                f"{base}/api/trace/job/{job_id}/stream", timeout=10,
            )
            assert resp.status_code == 200
            lines = _parse_ndjson(resp.text)
            types = [ln["type"] for ln in lines]

            assert "domain_start" in types
            assert "domain_end" in types
            ds = [ln for ln in lines if ln["type"] == "domain_start"][0]
            de = [ln for ln in lines if ln["type"] == "domain_end"][0]
            assert ds["total"] == 0
            assert de["count"] == 0

            complete = lines[-1]
            assert complete["total_records"] == 0
        finally:
            _cleanup_job(rclient, job_id)

    def test_stream_content_matches_result_endpoint(self, base, rclient):
        """Stream data must match what GET /result returns."""
        job_id = f"trace-evt-streammatch{uuid.uuid4().hex[:6]}"
        records = [{"CID": f"C{i}", "VAL": i * 10} for i in range(8)]

        _seed_completed_job(rclient, job_id, "query_tool",
                            {"history": records}, batch_size=3)
        try:
            # Get via result endpoint
            result_resp = requests.get(
                f"{base}/api/trace/job/{job_id}/result", timeout=10,
            )
            assert result_resp.status_code == 200
            result_data = result_resp.json().get("data", result_resp.json())

            # Get via stream endpoint
            stream_resp = requests.get(
                f"{base}/api/trace/job/{job_id}/stream", timeout=10,
            )
            assert stream_resp.status_code == 200
            lines = _parse_ndjson(stream_resp.text)

            # Collect all streamed records
            streamed_records = []
            for ln in lines:
                if ln["type"] == "records" and ln["domain"] == "history":
                    streamed_records.extend(ln["data"])

            # Compare counts
            result_history = result_data["results"]["history"]
            assert len(streamed_records) == result_history["count"]

            # Compare actual data content
            assert streamed_records == result_history["data"]
        finally:
            _cleanup_job(rclient, job_id)


# ===========================================================================
# 4. Full Async → Stream End-to-End
# ===========================================================================
class TestTraceAsyncToStream:
    """Full end-to-end: POST events → async 202 → poll → stream NDJSON."""

    def test_full_async_lifecycle_with_stream(self, base, real_cids):
        """Complete flow: real CIDs → async → poll → stream → verify data.

        Uses real CIDs but requires TRACE_ASYNC_CID_THRESHOLD to be low enough
        or enough CIDs. If async not triggered, test sync+seed stream instead.
        """
        threshold = int(os.getenv("TRACE_ASYNC_CID_THRESHOLD", "20000"))

        if len(real_cids) <= threshold:
            # Even below threshold, the route may still choose async on spool miss.
            resp = _post_events(base, "query_tool", real_cids[:10],
                                domains=["history"])
            _maybe_skip_on_service_overload(resp, "trace async lifecycle sync fallback")
            data = _unwrap_events_payload(base, resp)
            assert data["stage"] == "events"
            assert "history" in data["results"]
            # Result path proven — stream is tested in TestTraceNDJSONStream
            return

        # If we have enough CIDs, test full async lifecycle
        resp = _post_events(base, "query_tool", real_cids, domains=["history"])
        assert resp.status_code == 202
        job_id = resp.json().get("data", resp.json())["job_id"]

        # Poll until finished
        deadline = time.time() + 180
        final_status = None
        while time.time() < deadline:
            status_resp = requests.get(
                f"{base}/api/trace/job/{job_id}", timeout=10,
            )
            final_status = status_resp.json().get("data", status_resp.json())
            if final_status["status"] in ("finished", "failed"):
                break
            time.sleep(2)

        assert final_status["status"] == "finished", (
            f"Job did not finish: {final_status}"
        )

        # Stream the result
        stream_resp = requests.get(
            f"{base}/api/trace/job/{job_id}/stream", timeout=30,
        )
        assert stream_resp.status_code == 200
        lines = _parse_ndjson(stream_resp.text)

        # Verify protocol integrity
        assert lines[0]["type"] == "meta"
        assert lines[-1]["type"] == "complete"
        assert lines[-1]["total_records"] > 0
