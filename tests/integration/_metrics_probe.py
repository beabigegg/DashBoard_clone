# -*- coding: utf-8 -*-
"""HTTP probe client for the soak workload's ``/internal/metrics`` endpoint.

Design: stdlib-only (D9).  ``urllib.request`` is used because we only need
snapshot + streaming iterator semantics; pulling in ``httpx`` / ``requests``
would add a dependency purely for convenience.

The endpoint this targets is gated by three layers — see
openspec harden-real-infra-test-coverage spec 3.1.  The probe therefore
assumes the caller has arranged:

  * Layer 1 — app was created with ``REGISTER_INTERNAL_METRICS=True`` (the
    testing / nightly / soak config factory sets this).
  * Layer 2 — ``INTERNAL_METRICS_ENABLED=1`` in the worker environment.
  * Layer 3 — probe calls a loopback address (``127.0.0.1`` / ``::1``).

If any gate is closed the endpoint returns 404 and snapshot() raises
``ProbeGateClosed`` with the layer that likely caused the denial.  Tests
can use that exception to produce a diagnostic message without having to
re-discover which gate was misconfigured.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, Iterator, List, Optional


class ProbeError(RuntimeError):
    """Base class for MetricsProbe failures."""


class ProbeGateClosed(ProbeError):
    """One of the three gates rejected the call (HTTP 404)."""


class ProbeHTTPError(ProbeError):
    """Unexpected HTTP status other than 200 or 404."""


@dataclass
class MetricsProbe:
    """HTTP client for ``GET /internal/metrics`` on a loopback worker.

    Parameters
    ----------
    base_url:
        Fully-qualified worker base URL, e.g. ``http://127.0.0.1:54321``.
        Trailing slash optional.
    timeout_s:
        Per-request HTTP timeout.  Defaults to 10 seconds; soak probes
        should NOT tolerate longer than this because a hung probe is
        itself a leak signal.
    """

    base_url: str
    timeout_s: float = 10.0

    # --------------------------------------------------------------
    # Snapshot
    # --------------------------------------------------------------

    def snapshot(self) -> Dict[str, Any]:
        """Single GET of ``/internal/metrics``; returns the ``data`` dict.

        Raises
        ------
        ProbeGateClosed
            The endpoint returned 404 (gate closed — check env var /
            loopback / registration flag).
        ProbeHTTPError
            Any other non-200 status.
        """
        url = self._metrics_url()
        req = urllib.request.Request(url, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                status = resp.status
                body = resp.read()
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise ProbeGateClosed(
                    f"GET {url} returned 404 — one of the three gates is "
                    "closed (registration flag / INTERNAL_METRICS_ENABLED "
                    "env / loopback remote_addr)"
                ) from exc
            raise ProbeHTTPError(
                f"GET {url} returned HTTP {exc.code}: {exc.read()[:200]!r}"
            ) from exc
        except urllib.error.URLError as exc:
            raise ProbeError(f"GET {url} failed: {exc}") from exc

        if status != 200:
            raise ProbeHTTPError(f"GET {url} returned HTTP {status}")

        try:
            envelope = json.loads(body)
        except json.JSONDecodeError as exc:
            raise ProbeError(
                f"GET {url} returned non-JSON body: {body[:200]!r}"
            ) from exc

        if not isinstance(envelope, dict) or "data" not in envelope:
            raise ProbeError(
                f"GET {url} returned envelope without `data` key: {envelope!r}"
            )

        data = envelope["data"]
        if not isinstance(data, dict):
            raise ProbeError(
                f"GET {url} .data must be dict, got {type(data).__name__}"
            )
        return data

    # --------------------------------------------------------------
    # Streaming iterator
    # --------------------------------------------------------------

    def stream(
        self,
        duration_s: float,
        interval_s: float,
        *,
        clock=time.monotonic,
        sleep=time.sleep,
    ) -> Iterator[Dict[str, Any]]:
        """Yield snapshots every ``interval_s`` for ``duration_s``.

        Each yielded dict includes the seven metric categories plus a
        ``timestamp`` float (epoch seconds) and a ``sample_index`` int
        (0-based), so the caller can serialize without post-processing.

        If ``snapshot()`` raises, the iterator yields a dict carrying
        ``{"timestamp", "sample_index", "error": str}`` and continues —
        the soak test treats a transient probe failure as a sample gap,
        not a fatal error, so the time series survives a single 504 and
        still produces a meaningful regression verdict.
        """
        if duration_s <= 0:
            raise ValueError("duration_s must be positive")
        if interval_s <= 0:
            raise ValueError("interval_s must be positive")

        start = clock()
        deadline = start + duration_s
        index = 0

        while True:
            now = clock()
            sample_wall = time.time()
            try:
                data = self.snapshot()
                record: Dict[str, Any] = {
                    "sample_index": index,
                    "timestamp": sample_wall,
                    "elapsed_s": now - start,
                    **data,
                }
            except ProbeError as exc:
                record = {
                    "sample_index": index,
                    "timestamp": sample_wall,
                    "elapsed_s": now - start,
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                }

            yield record
            index += 1

            now = clock()
            if now >= deadline:
                return

            # Sleep up to the next interval tick, but not past the deadline.
            wake_at = start + index * interval_s
            if wake_at >= deadline:
                wake_at = deadline
            pause = max(0.0, wake_at - now)
            if pause > 0:
                sleep(pause)

    # --------------------------------------------------------------
    # Internal helpers
    # --------------------------------------------------------------

    def _metrics_url(self) -> str:
        base = self.base_url.rstrip("/")
        return f"{base}/internal/metrics"


# Convenience: run a full stream to a list in one call.  Used by the soak
# test's sampler thread to collect the time series for later assertions.
def drain_stream(
    probe: MetricsProbe,
    duration_s: float,
    interval_s: float,
) -> List[Dict[str, Any]]:
    """Consume ``probe.stream(...)`` into a list.  Thin helper."""
    return list(probe.stream(duration_s=duration_s, interval_s=interval_s))


__all__ = [
    "MetricsProbe",
    "ProbeError",
    "ProbeGateClosed",
    "ProbeHTTPError",
    "drain_stream",
]


def _detect_gate_hint(base_url: str, timeout_s: float = 3.0) -> Optional[str]:
    """Best-effort human-readable hint about why the gate might be closed.

    Returns a string describing the most likely misconfiguration, or
    ``None`` if the endpoint appears to be reachable.  Intended for
    pytest failure messages; NOT intended as a security check.
    """
    probe = MetricsProbe(base_url=base_url, timeout_s=timeout_s)
    try:
        probe.snapshot()
        return None
    except ProbeGateClosed:
        return (
            "gate closed (404); check: "
            "(a) worker was booted with FLASK_ENV=testing or another config "
            "with REGISTER_INTERNAL_METRICS=True, "
            "(b) INTERNAL_METRICS_ENABLED=1 in worker env, "
            "(c) probe is calling a loopback address"
        )
    except ProbeError as exc:
        return f"probe failure: {exc}"
