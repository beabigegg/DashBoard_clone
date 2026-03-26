## Context

`/mid-section-defect` currently runs a 3-stage backward-only pipeline hardcoded to TMTT (測試) station:
1. `tmtt_detection.sql` — fetch defective lots at TMTT station
2. `LineageEngine.resolve_full_genealogy()` — find ancestor container IDs
3. `upstream_history.sql` — get WIP records at upstream stations → attribute defects to machines

The detection SQL has `LIKE '%TMTT%'` hardcoded on line 38. All internal naming uses `TMTT_` prefix. The page serves one direction (backward) for one station.

This change generalizes to any of the 12 workcenter groups as detection station, adds forward tracing direction, and removes the superseded `/tmtt-defect` page.

## Goals / Non-Goals

**Goals:**
- Parameterize detection station: replace TMTT hardcode with `{{ STATION_FILTER }}` built from `workcenter_groups.py` patterns
- Add forward tracing pipeline: detection rejects → forward lineage → downstream WIP + rejects → forward attribution
- Direction-aware UI: FilterBar station dropdown + direction toggle, KPI/charts/detail switch by direction
- Backward compatibility: `station=測試, direction=backward` produces identical results (renamed columns)
- Remove `/tmtt-defect` page and all associated code

**Non-Goals:**
- No changes to LineageEngine internals (already supports both `resolve_full_genealogy` and `resolve_forward_tree`)
- No changes to `reject-history` or `query-tool` pages
- No new caching strategy (reuse existing L1/L2 cache with station+direction in key)
- No multi-station or multi-direction in a single query

## Decisions

### D1: Parameterized SQL via template substitution (not dynamic SQL builder)

Use `SQLLoader.load_with_params()` with `{{ STATION_FILTER }}` placeholder — the same pattern already used by `upstream_history.sql`'s `{{ ANCESTOR_FILTER }}`. The filter is built in Python from `WORKCENTER_GROUPS[station]['patterns']` as OR-LIKE clauses with bind parameters.

**Alternative considered:** Dynamic SQL builder class. Rejected — adds abstraction for a simple OR-LIKE pattern; template substitution is established in the codebase.

### D2: Separate `station_detection.sql` instead of modifying `tmtt_detection.sql`

Create new `station_detection.sql` as a generalized copy. The old `tmtt_detection.sql` will be deleted when `/tmtt-defect` is removed. Clean separation avoids merge conflicts with any in-flight tmtt-defect work.

**Alternative considered:** Modify in-place. Rejected — the old file is deleted anyway and renaming avoids ambiguity.

### D3: Forward attribution uses TRACKINQTY as denominator

Forward reject rate = `REJECT_TOTAL_QTY / TRACKINQTY × 100` at each downstream station. TRACKINQTY comes from `upstream_history.sql` (needs adding to SELECT). This gives a per-station defect rate for lots that survived the detection station.

**Alternative considered:** Use lot count as denominator. Rejected — TRACKINQTY accounts for partial quantities (split/merge lots) and gives a more accurate rate.

### D4: Direction dispatch at service layer, not route layer

`query_analysis()` gains `station` and `direction` params and dispatches to `_run_backward_pipeline()` or `_run_forward_pipeline()` internally. Routes just pass through. This keeps route handlers thin and testable.

### D5: Forward pipeline reuses upstream_history.sql for WIP records

Both directions need WIP records at various stations. The existing `upstream_history.sql` (with added TRACKINQTY) serves both — just with different container ID sets (ancestors for backward, descendants for forward).

### D6: New `downstream_rejects` event domain in EventFetcher

Forward tracing needs reject records at downstream stations. Add `downstream_rejects` as a new domain in `EventFetcher._build_domain_sql()`, loading `downstream_rejects.sql` with batched IN clause. This follows the established domain pattern.

### D7: Frontend direction toggle — button group, not dropdown

Two discrete states (backward/forward) fit a toggle button group better than a dropdown. Matches the existing btn-primary pattern in the page's CSS.

### D8: Remove `/tmtt-defect` entirely

The generalized traceability center with `station=測試 + lossReasons=[276_腳型不良, 277_印字不良]` reproduces all tmtt-defect functionality. Remove: `frontend/src/tmtt-defect/`, backend routes/services/SQL, test files, and `nativeModuleRegistry.js` registration.

## Risks / Trade-offs

- **Forward pipeline performance for early stations** — Selecting `station=切割 (order=0), direction=forward` could produce a very large descendant tree (all lots flow downstream). → Mitigation: The existing `resolve_forward_tree()` already handles large sets; add a result count warning in UI if > 5000 tracked lots.

- **TRACKINQTY NULL values** — Some WIP records may have NULL TRACKINQTY. → Mitigation: COALESCE to 0 in SQL; skip lots with zero input in attribution to avoid division by zero.

- **TMTT removal breaks bookmarks** — Users with `/tmtt-defect` bookmarks get 404. → Mitigation: Low risk — page was in dev status, not released. No redirect needed.

- **Rename TMTT_ → DETECTION_ in API response keys** — Frontend consumers (CSV export, chart keys) reference these field names. → Mitigation: All consumers are within this page's code; rename consistently in one pass.
