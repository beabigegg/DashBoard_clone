# -*- coding: utf-8 -*-
"""Data integrity helpers for stress tests.

Provides row-count baseline collection, pagination walking, and an
IntegrityResult dataclass for verifying data consistency across the
batch-merge → spool → pagination pipeline.
"""

import os
import requests
from dataclasses import dataclass
from typing import Any, Dict, Optional

# Configurable tolerance: default 0.1%
_TOLERANCE_PCT = float(os.environ.get("STRESS_ROW_COUNT_TOLERANCE_PCT", "0.1"))
_TIMEOUT = float(os.environ.get("STRESS_TIMEOUT", "60"))


@dataclass
class IntegrityResult:
    """Holds the outcome of a single data integrity probe."""

    service: str
    baseline_count: Optional[int] = None
    api_total_rows: Optional[int] = None
    pagination_sum: Optional[int] = None
    deficit_pct: Optional[float] = None
    verdict: str = "SKIPPED"  # PASS | FAIL | SKIPPED
    checkpoint_failed: bool = False
    notes: str = ""

    def compute_verdict(self, tolerance_pct: float = _TOLERANCE_PCT) -> None:
        """Set verdict based on comparison of available counts."""
        if self.baseline_count is None or self.api_total_rows is None:
            self.verdict = "SKIPPED"
            return

        # Primary check: baseline vs API total rows
        if self.baseline_count == 0:
            self.deficit_pct = 0.0
            self.verdict = "PASS"
            return

        deficit = self.baseline_count - self.api_total_rows
        self.deficit_pct = (deficit / self.baseline_count) * 100.0

        if self.deficit_pct > tolerance_pct:
            self.verdict = "FAIL"
            self.notes = (
                f"Row count deficit {self.deficit_pct:.2f}% exceeds tolerance {tolerance_pct:.2f}%"
                f" (baseline={self.baseline_count}, api={self.api_total_rows})"
            )
        else:
            # Secondary check: pagination sum if available
            if self.pagination_sum is not None and self.api_total_rows is not None:
                pg_deficit = abs(self.api_total_rows - self.pagination_sum)
                pg_deficit_pct = (pg_deficit / self.api_total_rows * 100.0) if self.api_total_rows else 0.0
                if pg_deficit_pct > tolerance_pct:
                    self.verdict = "FAIL"
                    self.notes = (
                        f"Pagination sum {self.pagination_sum} != api_total_rows {self.api_total_rows} "
                        f"(deficit {pg_deficit_pct:.2f}%)"
                    )
                    return
            self.verdict = "PASS"


class RowCountBaseline:
    """Executes a COUNT(*) query via a lightweight API to establish expected row count.

    Stores expected row counts per service/filter combo so multiple probes
    can share a single baseline query.
    """

    def __init__(self, base_url: str):
        self._base_url = base_url.rstrip("/")
        self._cache: Dict[str, int] = {}

    def get(self, service: str, params: dict) -> Optional[int]:
        """Return the COUNT(*) row count for the given service + params.

        Returns None if the count endpoint is unavailable or the response
        doesn't include a count field.
        """
        cache_key = f"{service}:{sorted(params.items())}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        endpoint_map = {
            "reject_history":      "/api/reject-history/count",
            "production_history":  "/api/production-history/count",
            "yield_alert":         "/api/yield-alert/count",
            "hold_history":        "/api/wip/hold-detail/count",
            "query_tool":          "/api/query-tool/count",
        }
        path = endpoint_map.get(service)
        if not path:
            return None

        # reject_history /count migrated to spool-read: it requires a query_id
        # from a prior POST /query rather than a raw date range.
        probe_params = dict(params)
        if service == "reject_history" and "query_id" not in probe_params:
            qid = self._resolve_reject_query_id(params)
            if qid is None:
                return None
            probe_params = {"query_id": qid}

        try:
            resp = requests.get(
                f"{self._base_url}{path}",
                params=probe_params,
                timeout=_TIMEOUT,
            )
            if resp.status_code != 200:
                return None
            data = resp.json()
            payload = data.get("data") or data
            count = payload.get("total_rows") or payload.get("count") or payload.get("row_count")
            if count is None:
                return None
            result = int(count)
            self._cache[cache_key] = result
            return result
        except Exception:
            return None

    def _resolve_reject_query_id(self, params: dict) -> Optional[str]:
        """POST /api/reject-history/query to obtain a query_id for the spool."""
        body = {"mode": "date_range"}
        for key in ("start_date", "end_date"):
            if params.get(key):
                body[key] = params[key]
        try:
            resp = requests.post(
                f"{self._base_url}/api/reject-history/query",
                json=body,
                timeout=_TIMEOUT,
            )
            if resp.status_code not in (200, 202):
                return None
            payload = resp.json()
            data = payload.get("data") or payload
            return data.get("query_id") or payload.get("query_id")
        except Exception:
            return None


class PaginationWalker:
    """Walks all pages of a spooled result and sums row counts.

    Detects empty/error pages mid-traversal and sets checkpoint_failed.
    Uses page_size=500 by default for efficiency.
    """

    def __init__(self, base_url: str, page_size: int = 500):
        self._base_url = base_url.rstrip("/")
        self._page_size = page_size

    def walk(
        self,
        path: str,
        spool_key: str,
        total_rows: int,
        extra_params: Optional[Dict[str, Any]] = None,
    ) -> tuple[int, bool]:
        """Walk all pages and return (sum_of_rows, checkpoint_failed).

        Args:
            path: API pagination endpoint path.
            spool_key: The spool/job key for paginated results.
            total_rows: Expected total rows (used to calculate page count).
            extra_params: Additional query parameters to include.

        Returns:
            (pagination_sum, checkpoint_failed)
        """
        row_sum = 0
        checkpoint_failed = False
        page = 1
        max_pages = (total_rows // self._page_size) + 2  # +2 safety margin

        while page <= max_pages:
            params: Dict[str, Any] = {
                "spool_key": spool_key,
                "page": page,
                "page_size": self._page_size,
            }
            if extra_params:
                params.update(extra_params)

            try:
                resp = requests.get(
                    f"{self._base_url}{path}",
                    params=params,
                    timeout=_TIMEOUT,
                )
            except Exception:
                checkpoint_failed = True
                break

            if resp.status_code != 200:
                checkpoint_failed = True
                break

            try:
                data = resp.json()
            except Exception:
                checkpoint_failed = True
                break

            payload = data.get("data") or data
            items = payload.get("items") or payload.get("rows") or payload.get("data") or []
            page_row_count = len(items)

            if page_row_count == 0:
                # Check if this is a legitimate last page
                declared_total = payload.get("total_rows") or payload.get("total")
                if declared_total is not None and row_sum >= int(declared_total):
                    break
                # Empty page mid-traversal = checkpoint failure
                checkpoint_failed = True
                break

            row_sum += page_row_count

            # Check if we have collected all rows
            declared_total = payload.get("total_rows") or payload.get("total")
            if declared_total is not None and row_sum >= int(declared_total):
                break

            page += 1

        return row_sum, checkpoint_failed
