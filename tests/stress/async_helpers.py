# -*- coding: utf-8 -*-
"""Async job polling helpers for stress tests.

Encapsulates the 202 → polling → result retrieval pattern used by the
production-history and yield-alert async RQ workers.
"""

import os
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import requests

_TIMEOUT = float(os.environ.get("STRESS_TIMEOUT", "60"))


class AsyncJobTimeout(Exception):
    """Raised when an async job does not complete within max_wait seconds."""

    def __init__(self, job_id: str, elapsed: float, max_wait: float):
        self.job_id = job_id
        self.elapsed = elapsed
        self.max_wait = max_wait
        super().__init__(
            f"Async job '{job_id}' timed out after {elapsed:.1f}s (max_wait={max_wait}s)"
        )


@dataclass
class AsyncJobResult:
    """Returned by AsyncJobPoller.submit_and_wait()."""

    job_id: Optional[str]
    status: str  # "sync_hit" | "completed" | "failed" | "timeout"
    elapsed: float
    poll_count: int
    data: Optional[Any] = None  # Parsed response body on success
    error: Optional[str] = None
    http_status: Optional[int] = None


class AsyncJobPoller:
    """Encapsulates the 200/202 → polling → result pattern.

    On HTTP 200 (spool hit): returns immediately with sync result.
    On HTTP 202: extracts job_id + status_url, polls until completed or timeout.
    On job failure: returns error details from polling response.
    On timeout: raises AsyncJobTimeout.

    Usage::

        poller = AsyncJobPoller(base_url, max_wait=300, poll_interval=2.0)
        result = poller.submit_and_wait("POST", "/api/production-history/query", payload)
        # result.job_id, result.status, result.elapsed, result.poll_count, result.data
    """

    def __init__(self, base_url: str, max_wait: float = 300.0, poll_interval: float = 2.0):
        self._base_url = base_url.rstrip("/")
        self._max_wait = max_wait
        self._poll_interval = poll_interval

    def submit_and_wait(
        self,
        method: str,
        path: str,
        payload: Optional[Any] = None,
        params: Optional[dict] = None,
    ) -> AsyncJobResult:
        """Submit a query and wait for the result.

        Args:
            method: HTTP method ("GET" or "POST").
            path: API path relative to base_url.
            payload: JSON body for POST requests.
            params: Query string parameters.

        Returns:
            AsyncJobResult with status and data.

        Raises:
            AsyncJobTimeout: if the job does not complete within max_wait.
        """
        start = time.time()
        url = f"{self._base_url}{path}"

        try:
            if method.upper() == "POST":
                resp = requests.post(url, json=payload, params=params, timeout=_TIMEOUT)
            else:
                resp = requests.get(url, params=params or payload, timeout=_TIMEOUT)
        except Exception as exc:
            return AsyncJobResult(
                job_id=None,
                status="error",
                elapsed=time.time() - start,
                poll_count=0,
                error=str(exc),
            )

        # Sync hit (spool cache or fast response)
        if resp.status_code == 200:
            try:
                body = resp.json()
            except Exception:
                body = None
            return AsyncJobResult(
                job_id=None,
                status="sync_hit",
                elapsed=time.time() - start,
                poll_count=0,
                data=(body.get("data") if isinstance(body, dict) else body),
                http_status=200,
            )

        # Async accepted
        if resp.status_code == 202:
            try:
                body = resp.json()
            except Exception:
                body = {}
            data = body.get("data") or body
            job_id = data.get("job_id") or data.get("task_id")
            status_url = data.get("status_url") or data.get("poll_url")
            # Resolve relative status_url to absolute
            if status_url and status_url.startswith("/"):
                status_url = f"{self._base_url}{status_url}"
            if not status_url and job_id:
                # Derive status URL from path convention
                status_url = f"{self._base_url}{path}/status/{job_id}"

            return self._poll(job_id, status_url, start)

        # Unexpected status
        return AsyncJobResult(
            job_id=None,
            status="error",
            elapsed=time.time() - start,
            poll_count=0,
            error=f"HTTP {resp.status_code}",
            http_status=resp.status_code,
        )

    def _poll(self, job_id: Optional[str], status_url: Optional[str], start: float) -> AsyncJobResult:
        """Poll status_url until done/failed/timeout."""
        if not status_url:
            return AsyncJobResult(
                job_id=job_id,
                status="error",
                elapsed=time.time() - start,
                poll_count=0,
                error="No status_url available for polling",
            )

        poll_count = 0

        while True:
            elapsed = time.time() - start
            if elapsed >= self._max_wait:
                raise AsyncJobTimeout(job_id or "unknown", elapsed, self._max_wait)

            time.sleep(self._poll_interval)
            poll_count += 1

            try:
                poll_resp = requests.get(status_url, timeout=_TIMEOUT)
            except Exception as exc:
                continue  # Transient connectivity issue; keep polling

            if poll_resp.status_code not in (200, 202):
                return AsyncJobResult(
                    job_id=job_id,
                    status="error",
                    elapsed=time.time() - start,
                    poll_count=poll_count,
                    error=f"Poll returned HTTP {poll_resp.status_code}",
                    http_status=poll_resp.status_code,
                )

            try:
                poll_body = poll_resp.json()
            except Exception:
                continue

            poll_data = poll_body.get("data") or poll_body
            status = poll_data.get("status") or poll_data.get("state") or ""

            if status in ("completed", "success", "done"):
                result_data = poll_data.get("result") or poll_data
                return AsyncJobResult(
                    job_id=job_id,
                    status="completed",
                    elapsed=time.time() - start,
                    poll_count=poll_count,
                    data=result_data,
                    http_status=poll_resp.status_code,
                )

            if status in ("failed", "error", "failure"):
                return AsyncJobResult(
                    job_id=job_id,
                    status="failed",
                    elapsed=time.time() - start,
                    poll_count=poll_count,
                    error=poll_data.get("error") or poll_data.get("message") or "Job failed",
                    http_status=poll_resp.status_code,
                    data=poll_data,
                )

            # Still pending/started — continue polling
