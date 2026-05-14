# -*- coding: utf-8 -*-
"""Shared SQL emitter for wildcard token lists.

Lifted from the inline ``_add_exact_or_pattern_condition`` pattern in
``services/material_trace_service.py`` (lines 85-117) so that any service
needing the same "user-typed list of tokens with ``*`` wildcards → safe
Oracle SQL fragment" translation can reuse a single audited
implementation.

The parser side lives in :mod:`mes_dashboard.core.request_validation`
(``parse_wildcard_tokens`` + :class:`WildcardToken`). This module only
emits SQL from already-validated tokens — it does NOT re-validate, escape,
or normalise user input. Callers MUST pass tokens through
``parse_wildcard_tokens`` first.

U2 decision (change ``prod-history-first-tier-cache-filters`` —
backend-engineer agent): lifted to shared module rather than duplicating
inside ``production_history_service.py`` because (a) the wildcard grammar
is now contractually defined (PHF-02/PHF-03) and applies identically to
any service emitting LIKE filters from textarea input, (b) future audits
benefit from a single chokepoint, (c) ``material_trace_service`` can be
migrated to this emitter in a follow-up without behaviour change.
"""

from __future__ import annotations

from typing import Any, Dict, List, Sequence, Tuple

from mes_dashboard.core.request_validation import WildcardToken


def build_wildcard_clause(
    column: str,
    tokens: Sequence[WildcardToken],
    param_prefix: str,
) -> Tuple[str, Dict[str, Any]]:
    """Emit a SQL fragment for a column matching any of the given tokens.

    Combines exact tokens into a single ``IN (...)`` clause and emits one
    ``LIKE :bind ESCAPE '\\'`` term per pattern token, all joined by ``OR``
    inside an outer parenthesis pair so the fragment can be safely
    AND-ed into a larger WHERE.

    Example output (1 exact + 2 patterns on ``c.MFGORDERNAME`` with
    ``param_prefix='mfg'``)::

        ((c.MFGORDERNAME IN (:mfg_in_0))
         OR (c.MFGORDERNAME LIKE :mfg_p_1 ESCAPE '\\')
         OR (c.MFGORDERNAME LIKE :mfg_p_2 ESCAPE '\\'))

    Args:
        column: Fully-qualified column reference (e.g. ``c.MFGORDERNAME``).
            Inserted verbatim — caller is responsible for ensuring it is a
            trusted literal (NOT user input).
        tokens: Pre-validated tokens from
            :func:`mes_dashboard.core.request_validation.parse_wildcard_tokens`.
        param_prefix: Stable, collision-free prefix for the bind parameter
            names this call emits. The caller is responsible for ensuring
            different fields use distinct prefixes within the same query.

    Returns:
        ``(sql_fragment, bind_params)``. ``sql_fragment`` is empty string
        when ``tokens`` is empty (caller should skip the AND in that
        case). ``bind_params`` is always a fresh dict.
    """
    if not tokens:
        return "", {}

    exact_values: List[str] = [t.bound_value for t in tokens if t.kind == "exact"]
    pattern_values: List[str] = [t.bound_value for t in tokens if t.kind == "pattern"]

    parts: List[str] = []
    params: Dict[str, Any] = {}

    if exact_values:
        placeholders: List[str] = []
        for i, val in enumerate(exact_values):
            name = f"{param_prefix}_in_{i}"
            placeholders.append(f":{name}")
            params[name] = val
        parts.append(f"({column} IN ({', '.join(placeholders)}))")

    for i, val in enumerate(pattern_values):
        name = f"{param_prefix}_p_{i}"
        params[name] = val
        parts.append(f"({column} LIKE :{name} ESCAPE '\\')")

    if len(parts) == 1:
        return parts[0], params
    return "(" + " OR ".join(parts) + ")", params
