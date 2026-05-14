# Change Request

## Original Request

Redesign the Production History 查詢 page into two explicit query-mode tabs.
- **Tab A 「依產品分類查詢」**: the four cached MultiSelect filters (TYPE/PACKAGE/BOP/FUNCTION) plus a required date range — TYPE required, dates required (current behavior).
- **Tab B 「依識別碼查詢」**: the three wildcard textareas (工單號/LOT ID/Wafer LOT) only — NO date row shown, classification filters NOT required.

Make the backend `start_date`/`end_date` genuinely optional in `production_history_service.validate_query_params`: when identifier wildcard tokens (`mfg_orders`/`lot_ids`/`wafer_lots`) are present and no dates supplied, run a wide/all-time query instead of raising `"必要參數: start_date, end_date"`; classification-mode queries still require dates.

Also add a 「清除篩選」 button next to 查詢 that resets all first-tier selections, the three wildcard textareas, the date range (back to the default 30-day window), and any post-query supplementary/matrix filter, and clears results back to the empty state.

This is a follow-up architecture fix to the already-pushed change `prod-history-first-tier-cache-filters`, motivated by real-world usability feedback.

## Business / User Goal

Engineers use Production History in two distinct ways: (a) browse a product
category over a time window, or (b) look up specific known identifiers. The
current single-panel design forces the date range and a mandatory TYPE
selection onto both, which is wrong for identifier lookups — a pasted LOT ID
already fully scopes the query. Splitting into two tabs matches the real
operational logic and removes friction.

## Non-goals

- No change to the cached cross-filter mechanism (4-tuple DISTINCT set + in-memory filter) introduced by `prod-history-first-tier-cache-filters`.
- No change to the wildcard grammar / parsing (`parse_wildcard_tokens`, `sql/wildcards.py`).
- No change to the second-tier supplementary filters (WorkCenter / Equipment) or the matrix/detail result rendering.
- No new identifier fields.

## Constraints

- Identifier-mode Oracle queries with no date bound must remain performant — `CONTAINERNAME` / `MFGORDERNAME` predicates are indexed; confirm the all-time path does not become an unbounded full-table scan, or apply a sane wide cap.
- Backend change must stay backward compatible: existing callers that always send `start_date`/`end_date` (classification flow, tests) must behave exactly as before.
- Frontend CSS must use existing design tokens (Tailwind) — no new `@layer`.
- i18n: all user-visible text must be synchronized across locales if the project has multiple.

## Known Context

- Current page: `frontend/src/production-history/App.vue` + `composables/useProductionHistory.ts` + `composables/useFirstTierFilters.ts`.
- `useFirstTierFilters` already has an unused `clearAll()` — the 清除篩選 button needs a broader reset spanning both composables + date state.
- Backend hard-requires dates at `src/mes_dashboard/services/production_history_service.py:99`.
- The main query SQL chunks the Oracle scan by `TRACKINTIMESTAMP` window.

## Open Questions

- (resolved with user 2026-05-14) Date handling in identifier mode: **backend date genuinely optional**.
- (resolved with user 2026-05-14) Interaction model: **explicit Tabs**, not auto-detect.

## Requested Delivery Date / Priority

Follow-up to a shipped change; user-reported usability blocker. Normal priority.
