# -*- coding: utf-8 -*-
"""4-layer query-cost policy: classify a query as SYNC or ASYNC.

Design decision D5: four layers in short-circuit order:
    L0 — spool hit → always SYNC
    L1 — always-async domain (trace, eap_alarm, msd) → always ASYNC
    L2 — date_span ≥ day_threshold → ASYNC
    L3 — row_count_fn() ≥ row_threshold → ASYNC
    else → SYNC

Replaces the scattered ``*_ASYNC_DAY_THRESHOLD`` env vars with a single
per-domain ``CostPolicy`` record.  The old env vars are **deprecated**
(runtime ``DeprecationWarning`` emitted when present in os.environ); they
are NOT removed until P5 per the deprecate-2-minors breaking-change policy.

No DB calls at module import.  ``row_count_fn`` is called only when L0–L2
do not short-circuit (prevents unnecessary COUNT(*) queries).
"""
from __future__ import annotations

import os
import warnings
from dataclasses import dataclass
from datetime import date
from typing import Callable, Literal, Optional

# ---------------------------------------------------------------------------
# Deprecated env vars: list of (env_name, replacement_guidance).
# Only vars that actually exist in the deployed codebase are listed (grepped
# from src/ — RESOURCE_, HOLD_, REJECT_, DOWNTIME_).  Do NOT invent vars
# to reach an arbitrary count (known risk from implementation-plan.md §Known
# Risks).
# ---------------------------------------------------------------------------
_DEPRECATED_THRESHOLD_VARS: tuple[tuple[str, str], ...] = (
    (
        "DOWNTIME_ASYNC_DAY_THRESHOLD",
        "Use CostPolicy.day_threshold via classify_query_cost() instead.",
    ),
    (
        "HOLD_ASYNC_DAY_THRESHOLD",
        "Use CostPolicy.day_threshold via classify_query_cost() instead.",
    ),
    (
        "RESOURCE_ASYNC_DAY_THRESHOLD",
        "Use CostPolicy.day_threshold via classify_query_cost() instead.",
    ),
    (
        "REJECT_ASYNC_DAY_THRESHOLD",
        "Use CostPolicy.day_threshold via classify_query_cost() instead.",
    ),
)

# Domains that are always async regardless of date span or row count.
_ALWAYS_ASYNC_DOMAINS: frozenset[str] = frozenset({"eap_alarm", "trace", "msd"})


def _check_deprecated_threshold_env() -> None:
    """Emit DeprecationWarning for any *_ASYNC_DAY_THRESHOLD env var present."""
    for var_name, guidance in _DEPRECATED_THRESHOLD_VARS:
        if var_name in os.environ:
            warnings.warn(
                f"{var_name} is deprecated and will be removed in a future minor "
                f"release (deprecate-2-minors policy). {guidance}",
                DeprecationWarning,
                stacklevel=3,
            )


@dataclass(frozen=True)
class CostPolicy:
    """Per-domain routing policy for classify_query_cost().

    Attributes:
        always_async:   If True, domain is always routed ASYNC (L1).
        day_threshold:  Calendar-day span at/above which L2 → ASYNC.
        row_threshold:  Estimated row count at/above which L3 → ASYNC.
    """

    always_async: bool = False
    day_threshold: int = 30       # L2 threshold (calendar days)
    row_threshold: int = 200_000  # L3 threshold (estimated rows from COUNT(*))


def classify_query_cost(
    domain: str,
    params: dict,
    spool_hit: bool = False,
    row_count_fn: Optional[Callable[[], int]] = None,
    policy: Optional[CostPolicy] = None,
) -> Literal["SYNC", "ASYNC"]:
    """Classify a query as SYNC or ASYNC using 4-layer short-circuit logic.

    Also emits DeprecationWarning for any ``*_ASYNC_DAY_THRESHOLD`` env vars
    present in os.environ.

    Args:
        domain:       Domain identifier (e.g. "eap_alarm", "hold", "reject").
        params:       Query parameter dict; must contain "date_from"/"date_to"
                      as ``datetime.date`` or ISO-8601 string for L2 check.
        spool_hit:    True if a valid cached spool already exists (L0 → SYNC).
        row_count_fn: Optional callable that returns an int row count from
                      a lightweight COUNT(*) query.  Called only when L0–L2
                      do not short-circuit.
        policy:       CostPolicy override.  If None, a default policy is
                      derived from the domain.

    Returns:
        "SYNC" or "ASYNC".
    """
    _check_deprecated_threshold_env()

    # Resolve effective policy
    if policy is None:
        policy = _default_policy_for(domain)

    # L0 — spool hit → always SYNC (overrides everything)
    if spool_hit:
        return "SYNC"

    # L1 — always-async domain → ASYNC
    if domain in _ALWAYS_ASYNC_DOMAINS or policy.always_async:
        return "ASYNC"

    # L2 — date span >= day_threshold → ASYNC
    date_from = params.get("date_from")
    date_to = params.get("date_to")
    if date_from is not None and date_to is not None:
        span_days = _date_span_days(date_from, date_to)
        if span_days >= policy.day_threshold:
            return "ASYNC"

    # L3 — row count >= row_threshold → ASYNC
    if row_count_fn is not None:
        try:
            count = row_count_fn()
            if count >= policy.row_threshold:
                return "ASYNC"
        except Exception:
            # If the COUNT(*) fails, be conservative and stay SYNC.
            pass

    return "SYNC"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _default_policy_for(domain: str) -> CostPolicy:
    """Return a reasonable default CostPolicy for the given domain."""
    if domain in _ALWAYS_ASYNC_DOMAINS:
        return CostPolicy(always_async=True, day_threshold=30, row_threshold=200_000)
    return CostPolicy(always_async=False, day_threshold=30, row_threshold=200_000)


def _date_span_days(date_from: "date | str", date_to: "date | str") -> int:
    """Return (date_to - date_from).days; accepts date objects or ISO strings."""
    if isinstance(date_from, str):
        date_from = date.fromisoformat(date_from[:10])
    if isinstance(date_to, str):
        date_to = date.fromisoformat(date_to[:10])
    delta = date_to - date_from  # type: ignore[operator]
    return max(int(delta.days), 0)
