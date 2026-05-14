---
change-id: prod-history-first-tier-cache-filters
schema-version: 0.1.0
last-changed: 2026-05-14
risk: high
tier: 1
---

# Proposal — First-tier cache filters for Production History

## Why

Production History today forces users to "query first, narrow later": Type is the only first-tier
filter, so the Oracle main query always scans the full `DW_MES_CONTAINER × DW_MES_LOTWIPHISTORY`
join for the requested date range before any Package / BOP / LOT / 工單 / Wafer-LOT narrowing.
Six in-spool chips appear only after rows come back. For engineers tracking a specific Package
family or a paste of 20 LOT IDs from Excel, this is an order-of-magnitude waste — both in Oracle
load and in wall-clock latency.

This change shifts narrowing **left** (pre-query, server-trusted), in two registers tuned to
cardinality:

- **Low-cardinality (4 fields, full enumerable set)**: `PJ_TYPE`, `PRODUCTLINENAME` (Package),
  `PJ_BOP` (BOP), `PJ_FUNCTION` (Function) — cached as a 4-tuple co-occurrence set so the picker
  can offer cross-filtered options instantly with zero Oracle round-trips per keystroke.
- **High-cardinality (3 fields, unbounded set)**: `MFGORDERNAME` (工單號), `CONTAINERNAME` (LOT ID),
  `FIRSTNAME` (Wafer LOT) — multi-line textarea + `*` wildcard, parsed and validated server-side,
  bound as Oracle `IN ... OR LIKE ... ESCAPE '\'` with `material-trace` precedent.

The second-tier panel keeps `WorkCenter 群組` and `Equipment` (still spool-derived) and drops the
three high-cardinality chips that have been promoted.

## What changes

- `container_filter_cache.py`:
  - SQL switches from UNION-ALL of two flat distinct lists to a single
    `SELECT DISTINCT PJ_TYPE, PRODUCTLINENAME, PJ_BOP, PJ_FUNCTION` over `DW_MES_CONTAINER`.
  - Payload schema bumped to `schema_version: 2`. Loaders that read an older payload drop it and
    rebuild rather than coercing.
  - L1/L2 (Redis JSON) retained; TTL retained (`CACHE_TTL_FILTER_GENERAL`, 24 h).
  - New helper `get_cross_filter_options(selected: dict) -> dict` that filters the in-memory
    4-tuple set in O(N) and returns the four distinct lists narrowed by `selected`.
  - File-lock pattern lifted from `resource_history_duckdb_cache._try_lock`/`_release_lock`
    (`resource_history_duckdb_cache.py:44-65`) to make multi-worker cold-start safe.
- New endpoint `GET /api/production-history/filter-options?selected=<base64-json>` — thin wrapper
  over `get_cross_filter_options`. (The existing spool-driven `POST /api/production-history/options`
  endpoint stays for WorkCenter / Equipment.)
- `production_history_service._build_extra_filters` gains five branches:
  - `pj_functions` (cached MultiSelect, plain `IN`).
  - `mfg_orders` (multi-line + wildcard, `IN + LIKE ESCAPE '\'`).
  - `lot_ids` is upgraded to wildcard-aware (was plain `IN`).
  - `wafer_lots` (multi-line + wildcard, new).
  - Existing `packages` / `bop_codes` stay plain `IN`.
- `core/request_validation.py` gains a `parse_wildcard_tokens(field, raw)` validator that splits
  on newline/comma/whitespace, rejects SQL-meta chars, rejects pure `*`, enforces the min-prefix
  and max-pattern rules from `design.md`. This is the single trust boundary for high-cardinality
  fields.
- Frontend `production-history/App.vue` filter panel grows four MultiSelect rows + three multi-line
  textareas; second-tier panel loses 工單號 / LOT ID / Wafer LOT chips. Cross-filter loader debounces
  selection changes (≥ 200 ms) and re-fetches `/filter-options`.
- Contracts updated: `api`, `data`, `business`, `ci` (always); `css`/`env` only if new tokens or
  env vars are introduced (see `design.md` §Env/CSS).

## Why this layout and not the alternatives

- **Cross-filter cache = in-memory filter over a cached 4-tuple set** (design.md decision D1).
  Per-keystroke Oracle queries (Option A) are unacceptable for a picker. Caching four flat lists
  and running a small filtered subquery on each interaction (Option C) doesn't help because the
  filtered subquery still needs the co-occurrence join — we'd be paying Oracle's cost minus
  caching's benefit. Option B keeps the picker responsive and Oracle quiet.
- **Wildcard grammar = single `*` only, min 2-char anchor, max 100 patterns per field**
  (design.md decision D2). Matches the `material-trace` UX users already know; rejects pure `*`
  (which would expand to `LIKE '%'`) and rejects SQL meta chars before any Oracle bind.
- **Schema versioning + multi-worker file lock** (design.md decisions D3, D4). These are the two
  rollback / safety mechanisms — the version flip lets us release without manually flushing Redis,
  and the lock prevents N gunicorn workers from independently hitting Oracle on cold start.

## Non-goals (explicit)

- No typeahead. The cross-filter picker shows the full cached list filtered by current selection;
  it does not query Oracle per keystroke.
- No DuckDB / spool changes. Change 2 (`prod-history-detail-raw-rows`, archived 2026-05-14) already
  carries `PJ_FUNCTION` through the spool.
- No change to WorkCenter / Equipment behavior. They stay second-tier.
- No matrix-visual changes; this is filter-only.

## Acceptance signals (full list in change-classification.md AC-1..AC-8)

- Empty selection: `/filter-options` returns the full distinct sets without Oracle.
- Cross-filter symmetric across all four cached fields.
- Wildcard `MA2025*` is rejected before Oracle for any SQL meta char; legal patterns bind as
  Oracle `LIKE 'MA2025%' ESCAPE '\'`.
- On simultaneous worker startup, exactly one rebuilds; the rest poll the `.loading` sentinel.
- Schema-version mismatch on Redis L2 → silent rebuild, never deserialize as old shape.
