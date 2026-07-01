# -*- coding: utf-8 -*-
"""4-layer query-cost policy: classify a query as SYNC or ASYNC.

Design decision D5: four layers in short-circuit order:
    L0 — spool hit → always SYNC
    L1 — always-async domain (trace, eap_alarm, msd) → always ASYNC
    L2 — date_span ≥ day_threshold → ASYNC
    L3 — row_count_fn() ≥ row_threshold → ASYNC
    else → SYNC

Replaces the scattered ``*_ASYNC_DAY_THRESHOLD`` env vars with a single
per-domain ``CostPolicy`` record.  The deprecated ``*_ASYNC_DAY_THRESHOLD``
env vars have been removed as of P5 (query-path-c-elimination-cleanup, IP-7).

Per-domain thresholds live in the ``_DOMAIN_POLICIES`` registry (the single
source of truth); ``_default_policy_for`` resolves a domain to its policy and
falls back to ``_DEFAULT_POLICY`` for unregistered domains.

No DB calls at module import.  ``row_count_fn`` is called only when L0–L2
do not short-circuit (prevents unnecessary COUNT(*) queries).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Callable, Literal, Optional


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


# ---------------------------------------------------------------------------
# Per-domain policy registry — SINGLE SOURCE OF TRUTH for async routing.
#
# Every domain that calls classify_query_cost() is declared here so its async
# cutoffs live in one place instead of being re-derived (or hard-coded) at each
# call site. To tune a domain's threshold (e.g. raise resource to a 90-day span
# or lower a row cutoff), edit its entry HERE — no route code changes.
#
# Domains absent from the table fall back to _DEFAULT_POLICY.
# always_async=True short-circuits to ASYNC at L1 (heavy by nature).
#
# NOTE: production_history / yield_alert / material_trace route async on
# spool-miss via their own *_ASYNC_ENABLED + is_async_available() checks and do
# NOT call classify_query_cost — so they are intentionally NOT listed here.
# Adding an entry for them has no effect until they are migrated onto the
# classifier (a separate, behaviour-changing decision).
# ---------------------------------------------------------------------------

_DEFAULT_POLICY = CostPolicy()  # always_async=False, 30 days, 200k rows

_DOMAIN_POLICIES: dict[str, CostPolicy] = {
    # Always-async (L1 short-circuit) — heavy by nature.
    "eap_alarm": CostPolicy(always_async=True),
    "trace": CostPolicy(always_async=True),
    "msd": CostPolicy(always_async=True),
    # Threshold-classified (L2 date-span / L3 row-count). All currently share the
    # 30-day / 200k default — tune per-domain here without touching route code.
    "resource": CostPolicy(day_threshold=30, row_threshold=200_000),
    "hold": CostPolicy(day_threshold=30, row_threshold=200_000),
    "reject": CostPolicy(day_threshold=30, row_threshold=200_000),
    "downtime": CostPolicy(day_threshold=30, row_threshold=200_000),
    "query_tool": CostPolicy(day_threshold=30, row_threshold=200_000),
    "wip": CostPolicy(day_threshold=30, row_threshold=200_000),
}

# Derived from the registry so the L1 always-async set never drifts from the
# table. Equals frozenset({"eap_alarm", "trace", "msd"}).
_ALWAYS_ASYNC_DOMAINS: frozenset[str] = frozenset(
    d for d, p in _DOMAIN_POLICIES.items() if p.always_async
)


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
    """Return the registered CostPolicy for a domain (single source of truth).

    Looks the domain up in ``_DOMAIN_POLICIES``; domains absent from the
    registry fall back to ``_DEFAULT_POLICY`` (30 days / 200k rows, sync-first).
    """
    return _DOMAIN_POLICIES.get(domain, _DEFAULT_POLICY)


def _date_span_days(date_from: "date | str", date_to: "date | str") -> int:
    """Return (date_to - date_from).days; accepts date objects or ISO strings."""
    if isinstance(date_from, str):
        date_from = date.fromisoformat(date_from[:10])
    if isinstance(date_to, str):
        date_to = date.fromisoformat(date_to[:10])
    delta = date_to - date_from  # type: ignore[operator]
    return max(int(delta.days), 0)
