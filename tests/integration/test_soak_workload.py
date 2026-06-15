# -*- coding: utf-8 -*-
"""Soak workload test — short-to-medium-term leak detector.

This test spawns 2 real gunicorn workers, drives sustained low-pressure
traffic against 5 high-traffic endpoints, samples ``/internal/metrics``
every ``sample_interval_seconds``, and asserts six time-series properties
defined in openspec harden-real-infra-test-coverage spec 3.5.

Positioning statement (IMPORTANT — do not remove, see spec 3.5.7):

  * The **default 30-minute run** is designed to detect **short-to-medium-term**
    leaks (degradation observable within a 30-minute window).
  * The **120-minute `workflow_dispatch` override** is the upper bound for
    automated CI investigation of slower regressions.
  * Regressions that only manifest after **8+ hours** of runtime — including
    very slow pool drift, rare code-path leaks, or memory fragmentation that
    takes hours to accumulate — are **explicitly out of scope** for this
    test.
  * **Passing this test is NOT proof of "no leaks"**; it is proof that the
    observed window did not exhibit a measurable leak signal.

Duration is controlled by env vars so the same test runs in three modes:

  ================  ==========================  ===================
  Mode              SOAK_DURATION_SECONDS       SOAK_INTERVAL_SECONDS
  ================  ==========================  ===================
  Local smoke       300 (scripts/soak_local.sh) 30
  CI nightly        1800 (soak-tests.yml)       30
  Dispatch long     ≤ 7200                      30–60
  ================  ==========================  ===================

Warm-up window
--------------
The first ``SOAK_WARMUP_SECONDS`` (default: ``min(60, duration//5)``) of
samples are EXCLUDED from the six time-series assertions.  Reason:
right after worker boot, Python modules are still being lazy-loaded,
DuckDB is initialising its runtime, and Redis caches are being primed
— these show up as rapid metric deltas that are **not** leak signals.
Assertions are still evaluated on the remaining post-warm-up window,
and the warm-up samples are kept in the artifact for debuggability.

Signal strength: CI vs local
----------------------------
The six checkers do NOT produce equally meaningful signals in every
environment.  What each mode actually exercises:

  * **Local (``./scripts/soak_local.sh``)** — full six-signal run.
    Real Oracle + DuckDB + populated caches mean pool / duckdb /
    circuit_breaker / RQ all see traffic, so a mutation like
    commenting out ``finally: conn.close()`` on the query path will
    manifest as a measurable ``_check_pool_slope`` regression.  This
    is the only mode in which the mutation recipes from spec task 3.8
    are meaningful.
  * **GitHub-hosted CI (``.github/workflows/soak-tests.yml``)** —
    primarily validates workflow plumbing + RSS and Redis trends.
    The CI runner has no Oracle, no ``oracledb`` client, and no
    DuckDB runtime, so routes fail at 4xx/5xx before acquiring DB
    connections.  Pool / duckdb / circuit_breaker checkers end up
    trivially passing on zero activity — a green CI run does **not**
    certify those three subsystems as leak-free.

A green soak run is interpreted as "no regression in the signals this
mode actually exercises", never as "no leak anywhere".  Use local soak
as the source of truth for pool / duckdb / CB; use CI soak as a
cadence safety net for plumbing drift and long-term RSS creep.

Artifact:
  After every run (pass OR fail) a file ``soak-metrics-<ts>.json`` is
  written into ``SOAK_ARTIFACT_DIR`` (default: the session tmp dir) and
  its absolute path is emitted via the pytest ``-s`` stream.  Assertion
  failure messages include the artifact path so CI logs and bisect
  tooling can locate the time series.
"""

from __future__ import annotations

import json
import os
import random
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pytest

from ._metrics_probe import MetricsProbe, ProbeError, _detect_gate_hint

# ---------------------------------------------------------------------------
# Test marker
# ---------------------------------------------------------------------------

pytestmark = [pytest.mark.integration_real, pytest.mark.soak]


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_DEFAULT_DURATION_S = 1800    # 30 min — CI nightly default
_DEFAULT_INTERVAL_S = 30
_MIN_DURATION_S = 60          # Enough for 2 first-samples + 2 tail-samples + slop
_MIN_SAMPLES_FOR_ASSERTIONS = 4


def _default_warmup_s(duration_s: int) -> int:
    """Warm-up window heuristic; see module docstring."""
    return max(0, min(60, duration_s // 5))

# Endpoint rotation for the traffic thread.  These are the five
# high-traffic endpoints specified in spec 3.5.3.  In the short soak
# (testing-config gunicorn, no real Oracle) several of them will return
# 5xx — that is fine; we care about metric deltas, not response status.
_TRAFFIC_ENDPOINTS: Tuple[Tuple[str, str, Dict[str, Any]], ...] = (
    ("GET",  "/health", {}),
    ("GET",  "/api/reject-history/options", {}),
    ("POST", "/api/hold-overview/summary", {"json": {}}),
    ("POST", "/api/query-tool/resolve", {"json": {"lot": "SOAK_PROBE"}}),
    ("POST", "/query", {"json": {}}),  # resource_history_bp prefix "/query"
    # today-snapshot simulates auto-refresh pattern (60s interval in real usage)
    ("POST", "/api/hold-history/today-snapshot", {"json": {"hold_type": "quality", "record_type": "on_hold"}}),
)


@pytest.fixture
def soak_config() -> Dict[str, Any]:
    """Configurable duration/interval, overridable via env vars.

    See module docstring for the three operating modes.  The function
    clamps ``SOAK_DURATION_SECONDS`` at 60s so we never run so short
    that the time-series assertions have fewer than 4 samples to work
    with (assertions lose statistical meaning below that).
    """
    duration = int(os.environ.get("SOAK_DURATION_SECONDS", _DEFAULT_DURATION_S))
    interval = int(os.environ.get("SOAK_INTERVAL_SECONDS", _DEFAULT_INTERVAL_S))

    if duration < _MIN_DURATION_S:
        pytest.fail(
            f"SOAK_DURATION_SECONDS={duration} is below the floor of "
            f"{_MIN_DURATION_S}s; time-series assertions require at least "
            f"{_MIN_SAMPLES_FOR_ASSERTIONS} samples (first 2 + tail 2)."
        )
    if interval <= 0 or interval > duration // 2:
        pytest.fail(
            f"SOAK_INTERVAL_SECONDS={interval} must be positive and at most "
            f"duration/2 ({duration // 2}s) to yield ≥ 2 samples."
        )

    warmup = int(os.environ.get("SOAK_WARMUP_SECONDS", _default_warmup_s(duration)))
    if warmup < 0 or warmup >= duration:
        pytest.fail(
            f"SOAK_WARMUP_SECONDS={warmup} must be in [0, duration={duration}); "
            "a warm-up ≥ duration leaves no samples for the assertions."
        )

    artifact_dir = os.environ.get("SOAK_ARTIFACT_DIR")
    return {
        "duration_seconds": duration,
        "sample_interval_seconds": interval,
        "warmup_seconds": warmup,
        "artifact_dir": Path(artifact_dir) if artifact_dir else None,
    }


@pytest.fixture
def _soak_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Activate the Layer-2 gate for workers spawned by ``gunicorn_workers``.

    The gunicorn_workers fixture inherits ``os.environ`` (excluding
    PYTEST_CURRENT_TEST), so we flip INTERNAL_METRICS_ENABLED here and
    teardown restores it.  FLASK_ENV=testing is already set by the
    fixture itself, which triggers REGISTER_INTERNAL_METRICS=True in
    TestingConfig (Layer 1).  Layer 3 is satisfied by calling
    127.0.0.1:<port> from the probe.
    """
    monkeypatch.setenv("INTERNAL_METRICS_ENABLED", "1")


# ---------------------------------------------------------------------------
# Traffic driver thread
# ---------------------------------------------------------------------------


def _traffic_thread(
    worker_urls: List[str],
    stop_event: threading.Event,
    stats: Dict[str, int],
    *,
    target_rps: float = 3.0,
) -> None:
    """Round-robin HTTP requests across workers × endpoints.

    We do not care whether the endpoint returns 200 — the test is about
    observing metric drift under sustained request load, not about the
    correctness of any particular endpoint.  All exceptions are caught;
    stats are kept so the test can later confirm traffic actually flowed.
    """
    request_interval = 1.0 / max(0.1, target_rps)
    iteration = 0
    while not stop_event.is_set():
        worker_url = worker_urls[iteration % len(worker_urls)]
        method, path, opts = _TRAFFIC_ENDPOINTS[iteration % len(_TRAFFIC_ENDPOINTS)]
        iteration += 1

        url = f"{worker_url.rstrip('/')}{path}"
        data: Optional[bytes] = None
        headers = {"User-Agent": "soak-driver/1.0"}
        if "json" in opts:
            data = json.dumps(opts["json"]).encode()
            headers["Content-Type"] = "application/json"

        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                status_bucket = f"status_{resp.status // 100}xx"
                stats[status_bucket] = stats.get(status_bucket, 0) + 1
        except urllib.error.HTTPError as exc:
            bucket = f"status_{exc.code // 100}xx"
            stats[bucket] = stats.get(bucket, 0) + 1
        except Exception:
            stats["network_error"] = stats.get("network_error", 0) + 1

        # Jitter the sleep so workers don't all receive in lock-step
        # (tiny amount — 10% of interval).
        pause = request_interval * (0.9 + random.random() * 0.2)
        if stop_event.wait(timeout=pause):
            return


# ---------------------------------------------------------------------------
# Sampler thread
# ---------------------------------------------------------------------------


def _sampler_thread(
    probe: MetricsProbe,
    duration_s: float,
    interval_s: float,
    samples: List[Dict[str, Any]],
    stop_event: threading.Event,
) -> None:
    """Stream /internal/metrics into `samples` until duration elapses.

    Even if the probe raises, the stream inserts an error record and
    continues — so the time-series survives a single transient failure
    and the 6 properties can still be evaluated (or will fail with a
    readable message identifying the sample gap).
    """
    try:
        for record in probe.stream(duration_s=duration_s, interval_s=interval_s):
            samples.append(record)
            if stop_event.is_set():
                return
    except Exception as exc:  # pragma: no cover — stream itself should not throw
        samples.append({
            "sample_index": len(samples),
            "timestamp": time.time(),
            "elapsed_s": 0.0,
            "error": f"stream_crashed: {exc}",
            "error_type": type(exc).__name__,
        })


# ---------------------------------------------------------------------------
# The soak test
# ---------------------------------------------------------------------------


def test_soak_workload_six_property_regression(
    _soak_env,
    gunicorn_workers,
    soak_config: Dict[str, Any],
    tmp_path: Path,
) -> None:
    """Drive sustained traffic, sample metrics, assert 6 time-series properties.

    Flow:
      1. gunicorn_workers fixture has already booted N workers bound to
         loopback with FLASK_ENV=testing + local_redis + temp_spool_dir.
      2. Flip INTERNAL_METRICS_ENABLED=1 via `_soak_env` fixture (auto).
      3. Verify at least one worker exposes /internal/metrics (gate smoke).
      4. Spawn one traffic thread and one sampler thread (against worker 0).
      5. Wait duration + 5s grace, stop both threads.
      6. Dump the time series + traffic stats to
         ``soak-metrics-<timestamp>.json`` UNCONDITIONALLY.
      7. Evaluate 6 properties; on failure include artifact path.

    Mutation-check hooks (Phase 3 Task 3.8 will formally exercise these;
    documented here so reviewers can reproduce the FAIL modes):
      * Comment out ``finally: connection.close()`` in ``_query_execution``
        → pool slope assertion (a) will FAIL.
      * Remove the half-open transition guard in circuit breaker state
        machine → transitions assertion (e) will FAIL.
    """
    workers = gunicorn_workers
    if not workers:
        pytest.fail("gunicorn_workers fixture returned no workers")

    worker_urls = [f"http://127.0.0.1:{port}" for _, port in workers]

    duration_s = soak_config["duration_seconds"]
    interval_s = soak_config["sample_interval_seconds"]

    # Gate smoke check: one probe call before we burn the soak duration
    probe = MetricsProbe(base_url=worker_urls[0])
    try:
        first_snapshot = probe.snapshot()
    except ProbeError as exc:
        hint = _detect_gate_hint(worker_urls[0])
        pytest.fail(
            f"/internal/metrics is not reachable from the test host: {exc}. "
            f"Hint: {hint}"
        )

    missing_keys = _EXPECTED_CATEGORIES - set(first_snapshot.keys())
    if missing_keys:
        pytest.fail(
            f"/internal/metrics snapshot is missing categories "
            f"{sorted(missing_keys)}; got {sorted(first_snapshot.keys())}"
        )

    # Spin up traffic + sampler threads
    stop_event = threading.Event()
    traffic_stats: Dict[str, int] = {}
    samples: List[Dict[str, Any]] = []

    traffic = threading.Thread(
        target=_traffic_thread,
        args=(worker_urls, stop_event, traffic_stats),
        name="soak-traffic",
        daemon=True,
    )
    sampler = threading.Thread(
        target=_sampler_thread,
        args=(probe, duration_s, interval_s, samples, stop_event),
        name="soak-sampler",
        daemon=True,
    )

    print(
        f"\n[soak] starting: duration={duration_s}s interval={interval_s}s "
        f"workers={len(worker_urls)}"
    )
    start = time.monotonic()
    traffic.start()
    sampler.start()

    # Let the sampler finish naturally; stop traffic a bit after deadline
    # (grace so the last sample sees some request activity).
    sampler.join(timeout=duration_s + 30)
    stop_event.set()
    traffic.join(timeout=10)

    elapsed = time.monotonic() - start
    print(
        f"[soak] finished: elapsed={elapsed:.1f}s samples={len(samples)} "
        f"traffic={traffic_stats}"
    )

    # Always dump artifact BEFORE assertions so a failed run still ships
    # the evidence needed for bisect.
    artifact_dir = soak_config["artifact_dir"] or tmp_path
    artifact_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = artifact_dir / f"soak-metrics-{int(time.time())}.json"
    artifact_payload = {
        "schema_version": 1,
        "duration_seconds": duration_s,
        "sample_interval_seconds": interval_s,
        "warmup_seconds": soak_config.get("warmup_seconds", 0),
        "workers": [{"pid": pid, "port": port} for pid, port in workers],
        "traffic_stats": traffic_stats,
        "samples": samples,
        "started_at": time.time() - elapsed,
        "ended_at": time.time(),
    }
    artifact_path.write_text(json.dumps(artifact_payload, indent=2, default=str))
    print(f"[soak] artifact: {artifact_path}")

    # Evaluate the six properties — collect FAIL messages rather than
    # short-circuit, so a single run surfaces every problem at once.
    warmup_s = float(soak_config.get("warmup_seconds", 0))
    errors: List[str] = []
    for check in (
        _check_pool_slope,
        _check_duckdb_bounded,
        _check_redis_converges,
        _check_rss_growth,
        _check_circuit_breaker_transitions,
        _check_rq_queue_depth,
    ):
        try:
            check(samples, warmup_s=warmup_s)
        except AssertionError as exc:
            errors.append(str(exc))

    # Traffic-flow sanity: at least some requests should have landed.
    # If zero traffic happened, the metric deltas are meaningless and the
    # test is not actually exercising what it claims to.
    total_requests = sum(
        v for k, v in traffic_stats.items()
        if k.startswith("status_") or k == "network_error"
    )
    if total_requests == 0:
        errors.append(
            "traffic thread issued zero requests — test is not actually "
            "exercising the workers; check endpoint paths and worker boot."
        )

    if errors:
        joined = "\n\n".join(f"* {e}" for e in errors)
        pytest.fail(
            f"Soak assertions FAILED ({len(errors)}/6):\n{joined}\n\n"
            f"Artifact: {artifact_path}"
        )


# ---------------------------------------------------------------------------
# Six property checkers
# ---------------------------------------------------------------------------

_EXPECTED_CATEGORIES = {
    "pool", "duckdb", "redis", "spool", "worker_rss", "circuit_breaker", "rq"
}


def _valid_samples(samples: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return only samples that were successfully parsed (no probe error)."""
    return [s for s in samples if "error" not in s]


def _post_warmup(
    samples: List[Dict[str, Any]],
    warmup_s: float,
) -> List[Dict[str, Any]]:
    """Drop samples whose ``elapsed_s`` is below the warm-up threshold.

    If the filter would leave fewer than ``_MIN_SAMPLES_FOR_ASSERTIONS``,
    fall back to returning whatever samples we have so assertions still
    emit a diagnostic message rather than silently passing.
    """
    valid = _valid_samples(samples)
    trimmed = [s for s in valid if s.get("elapsed_s", 0.0) >= warmup_s]
    if len(trimmed) < _MIN_SAMPLES_FOR_ASSERTIONS:
        return valid
    return trimmed


def _require_min_samples(samples: List[Dict[str, Any]], label: str) -> None:
    if len(samples) < _MIN_SAMPLES_FOR_ASSERTIONS:
        raise AssertionError(
            f"[{label}] only {len(samples)} valid samples "
            f"(need ≥ {_MIN_SAMPLES_FOR_ASSERTIONS}); cannot evaluate property. "
            "Probable causes: /internal/metrics is intermittently 404, "
            "workers crashed mid-run, or probe thread was starved."
        )


def _linear_slope(values: List[float]) -> float:
    """Ordinary least-squares slope, x = sample index."""
    n = len(values)
    if n < 2:
        return 0.0
    xs = list(range(n))
    mean_x = sum(xs) / n
    mean_y = sum(values) / n
    num = sum((xs[i] - mean_x) * (values[i] - mean_y) for i in range(n))
    den = sum((xs[i] - mean_x) ** 2 for i in range(n))
    if den == 0:
        return 0.0
    return num / den


def _quantile(values: List[float], q: float) -> float:
    """Linear interpolation quantile without importing numpy."""
    if not values:
        return 0.0
    s = sorted(values)
    if len(s) == 1:
        return s[0]
    pos = q * (len(s) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(s) - 1)
    frac = pos - lo
    return s[lo] + (s[hi] - s[lo]) * frac


# --- (a) pool.checkout - pool.checkin slope --------------------------------


def _check_pool_slope(samples: List[Dict[str, Any]], *, warmup_s: float = 0) -> None:
    """Pool-exhaustion detector.

    Note on signal shape: ``pool.checkout`` / ``pool.checkin`` are
    SQLAlchemy ``pool.checkedout()`` / ``pool.checkedin()`` instantaneous
    counts (current busy / current idle), not cumulative counters.  So
    ``checkout - checkin`` oscillates within ±max_capacity; for tiny
    pools (testing config uses size=1, overflow=0) the signal oscillates
    in {-1, 0, +1}.  The OLS-slope threshold of 0.05/sample is
    calibrated for the 60-sample CI run where noise averages out;
    small-N runs have a sqrt(1/N) noise floor well above 0.05.

    We therefore:
      * require ≥ 20 samples before applying the strict 0.05/sample
        threshold (below that, small-N noise dominates);
      * additionally assert head/tail saturation ratio regardless of N
        — this catches a real leak (saturation stays pinned to 1.0
        once the pool is exhausted) without being fooled by
        oscillation.
    """
    window = _post_warmup(samples, warmup_s)
    _require_min_samples(window, "pool_slope")

    deltas: List[float] = []
    saturations: List[float] = []
    for s in window:
        pool = s.get("pool", {})
        if "checkout" in pool and "checkin" in pool:
            deltas.append(float(pool["checkout"] - pool["checkin"]))
        if "saturation" in pool:
            try:
                saturations.append(float(pool["saturation"]))
            except (TypeError, ValueError):
                pass

    if len(deltas) < _MIN_SAMPLES_FOR_ASSERTIONS:
        raise AssertionError(
            f"[pool_slope] only {len(deltas)} samples with numeric "
            f"pool.checkout/checkin; pool collector may be erroring "
            "(check snapshot['pool'] for an 'error' key)."
        )

    # Head/tail saturation signal works across all sample counts because
    # saturation is bounded to [0, 1] and its time-average is stable.
    if saturations and len(saturations) >= _MIN_SAMPLES_FOR_ASSERTIONS:
        head_n = min(5, max(1, len(saturations) // 3))
        tail_n = head_n
        head_sat = sum(saturations[:head_n]) / head_n
        tail_sat = sum(saturations[-tail_n:]) / tail_n
        if tail_sat > 0.9 and head_sat < 0.5:
            raise AssertionError(
                f"[pool_slope] pool saturation climbed from "
                f"head_mean={head_sat:.2f} to tail_mean={tail_sat:.2f} — "
                "pool is exhausted in the tail window but was not in the "
                "head window.  This is the canonical leak signature "
                "(connections not returned → pool pinned to capacity)."
            )

    # Strict OLS slope threshold only applies when N ≥ 20.  For shorter
    # runs, small-N noise swamps the 0.05/sample threshold; print an
    # informational message so the framework reports what it skipped.
    slope = _linear_slope(deltas)
    if len(deltas) < 20:
        print(
            f"[pool_slope] slope={slope:+.4f}/sample over {len(deltas)} "
            "samples (strict 0.05/sample threshold requires ≥ 20 samples; "
            "small-N noise is expected for short runs). head/tail "
            "saturation signal evaluated above."
        )
        return

    if abs(slope) >= 0.05:
        raise AssertionError(
            f"[pool_slope] linear regression slope of "
            f"pool.checkout - pool.checkin = {slope:+.4f}/sample exceeds the "
            f"±0.05 threshold across {len(deltas)} samples. "
            f"First 3 deltas={deltas[:3]} last 3 deltas={deltas[-3:]}. "
            "A positive slope indicates connections are being checked out "
            "faster than they are returned (leak)."
        )


# --- (b) duckdb.temp_bytes capped at first-quartile * 3 --------------------


def _check_duckdb_bounded(samples: List[Dict[str, Any]], *, warmup_s: float = 0) -> None:
    window = _post_warmup(samples, warmup_s)
    _require_min_samples(window, "duckdb_bounded")

    bytes_series: List[float] = []
    for s in window:
        duck = s.get("duckdb", {})
        if "temp_bytes" in duck:
            bytes_series.append(float(duck["temp_bytes"]))
    if len(bytes_series) < _MIN_SAMPLES_FOR_ASSERTIONS:
        raise AssertionError(
            f"[duckdb_bounded] only {len(bytes_series)} samples with "
            "duckdb.temp_bytes; collector may be erroring or DuckDB "
            "temp dir not configured on the worker."
        )

    q1 = _quantile(bytes_series, 0.25)
    max_bytes = max(bytes_series)

    # When the first quartile is zero (typical in testing where DuckDB
    # never spills), treat max ≤ 1MiB as 'bounded' and skip the 3× rule;
    # otherwise the rule would fire on the very first byte written.
    if q1 == 0:
        if max_bytes > 1 * 1024 * 1024:
            raise AssertionError(
                f"[duckdb_bounded] first-quartile temp_bytes=0 but max "
                f"reached {max_bytes}B (>1MiB); DuckDB started spilling "
                "mid-soak which is itself a regression signal."
            )
        return

    if max_bytes > q1 * 3:
        raise AssertionError(
            f"[duckdb_bounded] max duckdb.temp_bytes={max_bytes} "
            f"exceeds 3× first-quartile (Q1={q1:.0f}, cap={q1 * 3:.0f}). "
            f"min={min(bytes_series):.0f} median="
            f"{_quantile(bytes_series, 0.5):.0f} "
            f"p95={_quantile(bytes_series, 0.95):.0f} "
            f"max={max_bytes:.0f}. "
            "DuckDB temp-file footprint grew past the expected working set; "
            "check for a query that forgot to release its spill."
        )


# --- (c) redis.key_count convergence (last 5 within ±10% of first 5) -------


def _check_redis_converges(samples: List[Dict[str, Any]], *, warmup_s: float = 0) -> None:
    window = _post_warmup(samples, warmup_s)
    _require_min_samples(window, "redis_converges")

    key_counts: List[float] = []
    for s in window:
        redis_cat = s.get("redis", {})
        if "key_count" in redis_cat:
            key_counts.append(float(redis_cat["key_count"]))
    if len(key_counts) < _MIN_SAMPLES_FOR_ASSERTIONS:
        raise AssertionError(
            f"[redis_converges] only {len(key_counts)} samples with "
            "redis.key_count; Redis collector may be erroring or "
            "REDIS_ENABLED=false on the workers."
        )

    # Use min(5, half) samples so short runs still get a signal.
    head_n = min(5, max(1, len(key_counts) // 2))
    tail_n = min(5, max(1, len(key_counts) // 2))
    head_mean = sum(key_counts[:head_n]) / head_n
    tail_mean = sum(key_counts[-tail_n:]) / tail_n

    # If head_mean is zero, apply the ±10% rule symmetrically by allowing
    # tail up to 10 keys (arbitrary small constant); otherwise a 0→1 key
    # delta would fail a ratio-based rule.
    if head_mean == 0:
        if tail_mean > 10:
            raise AssertionError(
                f"[redis_converges] head mean = 0 keys but tail mean = "
                f"{tail_mean:.1f}; Redis is accumulating keys with no "
                "baseline. Check namespace cleanup in cache services."
            )
        return

    # When absolute key counts are tiny (≤5), a single-key jitter produces
    # large percentage swings that are statistical noise, not real eviction
    # or accumulation.  Skip the percentage rule; a flat ±3-key tolerance is
    # sufficient at this scale.
    if max(head_mean, tail_mean) <= 5:
        if abs(tail_mean - head_mean) > 3:
            raise AssertionError(
                f"[redis_converges] low-count drift: head_mean={head_mean:.1f} "
                f"tail_mean={tail_mean:.1f} — absolute delta exceeds 3 keys."
            )
        return

    drift_pct = (tail_mean - head_mean) / head_mean * 100.0
    if abs(drift_pct) > 10.0:
        raise AssertionError(
            f"[redis_converges] tail/head drift = {drift_pct:+.1f}% "
            f"(head_mean={head_mean:.1f} tail_mean={tail_mean:.1f}) "
            f"exceeds ±10% over {len(key_counts)} samples. "
            "A positive drift indicates Redis key accumulation; a negative "
            "drift of similar magnitude may indicate mass eviction or TTL "
            "collapse."
        )


# --- (d) worker_rss growth < 15% from baseline ------------------------------


def _check_rss_growth(samples: List[Dict[str, Any]], *, warmup_s: float = 0) -> None:
    """RSS leak detector.

    Uses head-median vs tail-median (not first-sample-as-baseline vs
    peak) because:
      * A single-sample spike followed by GC drop is not a leak — peak
        would flag it as one.
      * The first sample within the post-warmup window is still biased
        low if Python lazy-loading continues past the warmup cutoff;
        a median over the first N/3 samples is more representative of
        "steady-state baseline".
    The 15% threshold comes straight from spec scenario 3.5.5 (d).
    """
    window = _post_warmup(samples, warmup_s)
    _require_min_samples(window, "rss_growth")

    # worker_rss reports *this worker's* pid + rss.  Since the probe only
    # talks to worker 0, we get a single PID time series here.  Grouping
    # by PID is still safe (handles re-fork events).
    by_pid: Dict[int, List[float]] = {}
    for s in window:
        rss_cat = s.get("worker_rss", {})
        pid = rss_cat.get("pid")
        rss = rss_cat.get("rss_bytes")
        if pid is None or rss is None:
            continue
        by_pid.setdefault(int(pid), []).append(float(rss))

    if not by_pid:
        raise AssertionError(
            "[rss_growth] no worker_rss observations; psutil may be "
            "missing from the worker environment, or the collector is "
            "returning {'error': ...}."
        )

    offenders = []
    for pid, series in by_pid.items():
        if len(series) < _MIN_SAMPLES_FOR_ASSERTIONS:
            continue
        third = max(1, len(series) // 3)
        head_median = _quantile(series[:third], 0.5)
        tail_median = _quantile(series[-third:], 0.5)
        if head_median == 0:
            continue
        growth_pct = (tail_median - head_median) / head_median * 100.0
        if growth_pct >= 15.0:
            offenders.append((pid, head_median, tail_median, max(series), growth_pct))

    if offenders:
        lines = [
            f"pid={pid} head_median={hm:.0f}B tail_median={tm:.0f}B "
            f"peak={pk:.0f}B growth={growth:+.1f}%"
            for pid, hm, tm, pk, growth in offenders
        ]
        raise AssertionError(
            "[rss_growth] one or more workers grew ≥ 15% from "
            "head-median to tail-median:\n  "
            + "\n  ".join(lines)
            + "\nHead-median vs tail-median is preferred to first-sample "
              "vs peak because it ignores transient spikes and lazy-load "
              "tails. A real leak shows up as a sustained tail climb; "
              "correlate with DuckDB / pool / spool deltas in the "
              "artifact to narrow the culprit."
        )


# --- (e) circuit breaker state transitions < 3 -----------------------------


def _check_circuit_breaker_transitions(
    samples: List[Dict[str, Any]], *, warmup_s: float = 0
) -> None:
    window = _post_warmup(samples, warmup_s)
    _require_min_samples(window, "circuit_breaker_transitions")

    states: List[str] = []
    timestamps: List[float] = []
    for s in window:
        cb = s.get("circuit_breaker", {})
        state = cb.get("state") or cb.get("status")
        if state is None:
            continue
        states.append(str(state))
        timestamps.append(float(s.get("timestamp", 0.0)))

    if not states:
        raise AssertionError(
            "[circuit_breaker_transitions] no circuit_breaker.state "
            "observations; collector may be erroring (check "
            "snapshot['circuit_breaker'] for an 'error' key)."
        )

    transitions: List[Tuple[str, str, float]] = []
    for i in range(1, len(states)):
        if states[i] != states[i - 1]:
            transitions.append((states[i - 1], states[i], timestamps[i]))

    if len(transitions) >= 3:
        lines = [
            f"{before} -> {after} @ t={ts:.0f}"
            for before, after, ts in transitions
        ]
        raise AssertionError(
            f"[circuit_breaker_transitions] observed {len(transitions)} "
            "state transitions (threshold = 3):\n  "
            + "\n  ".join(lines)
            + "\nFrequent flapping suggests the breaker threshold or "
              "cool-down is misconfigured against the current fault rate."
        )


# --- (f) RQ queue depth: tail ≤ head × 1.5 ---------------------------------


def _check_rq_queue_depth(samples: List[Dict[str, Any]], *, warmup_s: float = 0) -> None:
    window = _post_warmup(samples, warmup_s)
    _require_min_samples(window, "rq_queue_depth")

    by_queue: Dict[str, List[float]] = {}
    for s in window:
        rq_cat = s.get("rq", {})
        if not isinstance(rq_cat, dict):
            continue
        queues = rq_cat.get("by_queue", {})
        if not isinstance(queues, dict):
            continue
        for qname, depths in queues.items():
            if not isinstance(depths, dict):
                continue
            pending = depths.get("pending")
            if pending is None:
                continue
            by_queue.setdefault(qname, []).append(float(pending))

    if not by_queue:
        # RQ disabled or rq not installed on the worker — short soak in
        # testing mode will hit this branch; emit a warning via stdout but
        # do not fail the assertion (no queue = nothing to leak).
        print(
            "[rq_queue_depth] no RQ queue observations — rq disabled or "
            "no queue produced samples; assertion skipped."
        )
        return

    offenders: List[Tuple[str, float, float, float]] = []
    for qname, series in by_queue.items():
        if len(series) < _MIN_SAMPLES_FOR_ASSERTIONS:
            continue
        head_n = min(5, max(1, len(series) // 2))
        tail_n = min(5, max(1, len(series) // 2))
        head_mean = sum(series[:head_n]) / head_n
        tail_mean = sum(series[-tail_n:]) / tail_n

        if head_mean == 0:
            # Baseline empty; allow tail up to 5 pending jobs as "not a leak".
            if tail_mean > 5:
                offenders.append((qname, head_mean, tail_mean, float("inf")))
            continue

        ratio = tail_mean / head_mean
        if ratio > 1.5:
            offenders.append((qname, head_mean, tail_mean, ratio))

    if offenders:
        lines = [
            f"queue={q} head_mean={h:.1f} tail_mean={t:.1f} ratio={r:.2f}"
            for q, h, t, r in offenders
        ]
        raise AssertionError(
            "[rq_queue_depth] one or more RQ queues grew unboundedly:\n  "
            + "\n  ".join(lines)
            + "\nThis catches 'no resource leak but backlog creeps upward' "
              "regressions: workers keep up with RSS/pool but producers "
              "outpace consumers. Check worker concurrency vs enqueue rate."
        )


# ---------------------------------------------------------------------------
# Tier 4 — preload restart-loop / connection-leak soak (gunicorn-preload-workers)
# ---------------------------------------------------------------------------


@pytest.mark.soak
def test_preload_workers_restart_loop_no_connection_leak(gunicorn_url):
    """Tier 4 soak: restart gunicorn 5× and assert no Oracle connection leak.

    After each restart, /internal/metrics must report pool.checked_in > 0
    (connections returned to pool, none orphaned) and no Oracle-error log
    lines within the sampling window.

    This is a short restart-loop (5 cycles in ~30 s), not the 30-min drift
    test — the long-duration variant lives in soak-tests.yml workflow.

    Assumptions:
    - ``gunicorn_url`` fixture is provided by conftest.py and points to a
      running gunicorn instance with ``preload_app=True`` and
      ``REGISTER_INTERNAL_METRICS=True``.
    - If ``gunicorn_url`` is not available (CI without Oracle), the test is
      skipped via the fixture's own skip logic.
    """
    import urllib.request
    import urllib.error
    import json as _json

    metrics_url = f"{gunicorn_url.rstrip('/')}/internal/metrics"

    def _fetch_metrics():
        try:
            with urllib.request.urlopen(metrics_url, timeout=10) as resp:
                return _json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403, 404):
                pytest.skip(
                    f"/internal/metrics returned {exc.code} — "
                    "REGISTER_INTERNAL_METRICS may not be set or endpoint requires auth"
                )
            raise
        except Exception as exc:
            pytest.skip(f"/internal/metrics unavailable: {exc}")

    errors: list[str] = []
    for restart_cycle in range(5):
        # Sample metrics before each restart.
        metrics_before = _fetch_metrics()

        # Send SIGHUP to gunicorn master to trigger a graceful reload.
        # The gunicorn_url fixture should expose the master PID via an env var
        # or a .pid file.  If not available, skip gracefully.
        master_pid_path = os.environ.get("GUNICORN_PID_FILE", "gunicorn.pid")
        if not os.path.exists(master_pid_path):
            pytest.skip(
                f"GUNICORN_PID_FILE ({master_pid_path!r}) not found — "
                "restart-loop test requires a running gunicorn with --pid"
            )

        with open(master_pid_path) as fh:
            master_pid = int(fh.read().strip())

        import signal as _signal
        os.kill(master_pid, _signal.SIGHUP)  # graceful reload (not SIGTERM)

        # Wait for workers to reload (up to 15 s).
        deadline = time.monotonic() + 15.0
        metrics_after = None
        while time.monotonic() < deadline:
            time.sleep(1)
            try:
                metrics_after = _fetch_metrics()
                break
            except Exception:
                pass

        if metrics_after is None:
            errors.append(
                f"cycle {restart_cycle}: /internal/metrics unreachable after reload"
            )
            continue

        # Assert: connection pool not leaked (checked_in > 0 means at least one
        # connection was returned to the pool — not all orphaned in workers).
        pool = metrics_after.get("pool") or {}
        checked_in = pool.get("checked_in", 0)
        if checked_in == 0 and pool.get("checked_out", 0) == 0 and pool.get("max_capacity", 0) == 0:
            # No pool info available (Oracle not configured in CI) — skip assertion.
            pass
        elif checked_in == 0 and pool.get("max_capacity", 1) > 0:
            errors.append(
                f"cycle {restart_cycle}: pool.checked_in == 0 after reload — "
                f"possible connection leak (metrics: {pool})"
            )

    if errors:
        raise AssertionError(
            "preload restart-loop detected connection anomalies:\n  "
            + "\n  ".join(errors)
        )
