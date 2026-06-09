# Contracts Changelog

All notable contract surface changes belong here.
Format: Keep-a-Changelog (https://keepachangelog.com/).
Versions are semantic per contract type.

While a contract is at 0.x (draft), entries here are optional.
Once a contract reaches 1.0.0, every schema-version bump must have
a corresponding entry below.

## [business 1.14.0] — 2026-06-09
### Added
- resource-status-cross-filter: Added RS-CF-01 cross-filter intersection semantics for the resource-status page. Each chart contributes at most one selection dimension; AND-intersection across all active selections. Exclude-self: the input for each chart's option rendering omits that chart's own predicate. Re-click toggles off. ESC clears and returns focus to trigger. All filtering is client-side; `/api/resource/status` payload unchanged.

## [css 1.7.0] — 2026-06-09
### Added
- resource-status-cross-filter: Cross-filter selection-highlight and clear-control styles (`.cross-filter-clear-btn`, `.cross-filter-clear-btn-wrap`, `td.is-selected`, `.alert-card.is-selected`) added to `frontend/src/resource-status/style.css`, all scoped under `.theme-resource`. Passes `npm run css:check` Rule 6 with zero unscoped top-level rules.

## [ci 1.3.18] — 2026-06-05
### Changed
- gunicorn-preload-workers: Added Gate Compatibility Note for preload/fork-safety integration test coverage. New Tier 3 multi-worker test (`tests/integration/test_preload_fork_safety.py`, markers: `integration_real` + `multi_worker`) asserts: (1) each single-run prewarm (downtime_analysis, material_consumption, resource_history DuckDB, resource_cache init_cache) executes exactly once per gunicorn restart across N workers; (2) each worker holds independent (non-inherited) DB engine pool, Redis pool, and SQLite handles after post_fork reinit; (3) no resource_history duckdb-cache peer-wait timeout; (4) no orphan background thread in master after fork. Covered by existing nightly-integration gate command — no gate tier, command, or status change.

## [data 1.12.3] — 2026-06-03
### Changed
- downtime-analysis-page-redesign: Added wrapper-key confirmation notes to §3.12.5 (`EquipmentDetailRow` → `data.equipment_detail`) and §3.12.6 (`EventDetailRow` → `data.events`). Additive prose clarification; no field added or removed. Ensures frontend composables resolve the correct JSON key and do not produce a silent empty table (AC-8).

## [api 1.14.0] — 2026-06-03
### Added
- downtime-analysis-page-redesign: Additive optional filter params on two existing endpoints. `GET /api/downtime-analysis/equipment-detail` gains `big_category` (string, opt) and `status_types` (string, opt, CSV: `UDT,SDT,EGT`). `GET /api/downtime-analysis/event-detail` gains `big_category`, `status_types`, and `resource_id` (string, opt; Tier 3 lazy-load scoping). All three params apply pandas `.isin()` narrow on the in-memory parquet spool; no Oracle re-query. Omitting all params returns pre-existing unfiltered response (backward-compatible). Response wrapper keys (`equipment_detail`, `events`) and per-row schemas confirmed unchanged. `status_types` serialized as CSV consistent with `_csv_param()` convention. Consumers: `frontend/src/downtime-analysis/` only.

## [business 1.13.1] — 2026-06-01
### Changed
- batch-rowcount-unification (contract accuracy fix): BQE-02 notation corrected from ambiguous tuple `(start_row, end_row)` to explicit dict `{"start_row": int, "end_row": int}` matching implementation. BQE-05 ceiling values corrected from hardcoded "production=3, development=2" to "code default: dev=2, prod=5 per settings.py" — the previous values confused configured ENGINE_PARALLEL with the DB_SLOW_POOL_SIZE default. No behavior change; descriptive accuracy only.

## [business 1.13.0] — 2026-06-01
### Added
- batch-rowcount-unification: Added "Batch Query Engine Rules" group BQE-01..BQE-07. BQE-01: row-count chunking parity (flag=true path produces identical row set to date-range path; spool column schema identical). BQE-02: decompose_by_row_count correctness (inclusive ranges covering 1..total_rows; four edge cases). BQE-03: deterministic ORDER BY key per service (seven authoritative keys guaranteeing tie-breaking pagination). BQE-04: flag-off fallback guarantee (USE_ROW_COUNT_CHUNKING=false preserves existing behavior; spool TTL/cleanup/memory-guard unaffected). BQE-05: DB_SLOW_POOL_SIZE ceiling (HOLD/JOB/MSD ENGINE_PARALLEL must not exceed pool size). BQE-06: count-vs-paged consistency (completeness guarantee applies to non-concurrent reads; concurrent insert/delete mid-query is documented limitation). BQE-07: downtime_analysis_service migration to BatchQueryEngine; spool schema and namespace unchanged. Additive; no existing rules changed.

## [env 1.0.4] — 2026-06-01
### Added
- batch-rowcount-unification: Added missing `BATCH_QUERY_ROWS_PER_CHUNK` (optional, int, default 50000; controls ROW_NUMBER() paged window size when USE_ROW_COUNT_CHUNKING=true; must be ≥ 1; restart required) to the "Batch Query Engine — Row-Count Chunking" table in env-contract.md. The variable was implemented in batch_query_engine.py but omitted from the contract table in 1.0.3. Additive; no existing defaults or semantics changed.

## [env 1.0.3] — 2026-06-01
### Added
- batch-rowcount-unification: New section "Batch Query Engine — Row-Count Chunking": `USE_ROW_COUNT_CHUNKING` (optional, bool, default false; true activates ROW_NUMBER() CTE paging path; restart required). New section "Engine Parallelism — Hold / Job / MSD": `HOLD_ENGINE_PARALLEL`, `JOB_ENGINE_PARALLEL`, `MSD_ENGINE_PARALLEL` (all optional, positive int, default 1; must not exceed DB_SLOW_POOL_SIZE; restart required). All additive with safe defaults; no existing variable defaults or semantics changed.

## [data 1.12.2] — 2026-06-01
### Changed
- batch-rowcount-unification (confirm-only): §3.12.7 spool-schema note clarified — migration of downtime_analysis_service to BatchQueryEngine does not alter the parquet column schema or namespace; no parquet cleanup required for this migration. No column added, removed, or renamed.

## [api 1.13.1] — 2026-05-29
### Changed
- downtime-analysis-page (post-review patch): `GET /api/downtime-analysis/view` now returns 400 for `granularity` values other than `day` (week/month planned). Added `top_n` to endpoint params column. Removed duplicate CHANGELOG entries from individual contract file bodies. Non-breaking.

## [api 1.13.0] — 2026-05-29
### Added
- downtime-analysis-page: Added 5 new endpoints under `/api/downtime-analysis/*` (options, query, view, equipment-detail, event-detail). All require auth; Type A spool pattern (410 → client re-triggers POST /query). Spool namespace `downtime_analysis_*` independent of `resource_dataset_*`; cache key includes `DOWNTIME_BRIDGE_VERSION` constant for IT JOBID backfill invalidation. Response shapes documented in data-shape-contract.md §3.12; domain rules DA-01..DA-06 in business-rules.md. Additive; no existing endpoints changed.

## [api-inventory 1.1.12] — 2026-05-29
### Added
- downtime-analysis-page: Registered `downtime_analysis_routes.py` in standard-json table; documented all 5 endpoint scopes and Type A spool pattern. Added compatibility note. No existing rows changed.

## [data 1.12.1] — 2026-05-29
### Changed
- downtime-analysis-page (post-review patch): Clarified `granularity` note in §3.12.2 DailyTrendRow: currently always daily (day only; week/month planned). Removed duplicate CHANGELOG entries from individual contract file body. Non-breaking.

## [data 1.12.0] — 2026-05-29
### Added
- downtime-analysis-page: Added §3.12 documenting DowntimeKpiShape (§3.12.1), DailyTrendRow (§3.12.2), BigCategoryRow (§3.12.3), TopReasonRow (§3.12.4), EquipmentDetailRow (§3.12.5), EventDetailRow (§3.12.6), JobEnrichment sub-object (§3.12.7, including null-sentinel semantics, match_source closed enum, midnight-UTC DATE note). Additive; no existing schemas changed.

## [business 1.12.1] — 2026-05-29
### Changed
- downtime-analysis-page (post-review patch): Removed duplicate CHANGELOG entries from individual contract file body. No rule changes. Non-breaking.

## [business 1.12.0] — 2026-05-29
### Added
- downtime-analysis-page: Added DA-01..DA-06 (E10 status filter, cross-shift merge key, JOBID bridge algorithm Path A/B with tiebreak, big-category taxonomy reference, wait/repair hours derivation, IT backfill cache invalidation). Eight new decision table rows. Additive; no existing rules changed.

## [css-inventory 1.2.4] — 2026-05-29
### Added
- downtime-analysis-page: Added `frontend/src/downtime-analysis/style.css` (`theme-downtime-analysis`) to Route-Local Feature Layers table. Teleport wrapper rule 4.4 applies.

## [api 1.12.0] — 2026-05-29
### Changed
- ai-pipeline-upgrade: Internal function-mode pipeline collapsed from two LLM calls (R1+R2) to one combined call returning `{"function","params","explanation"}`. `_SESSION_STORE` extended with `chat_history` (cap 8 pairs / 16 messages); injected into combined call and text2sql Stage 1 only. Three new AI functions: `production_history_query`, `resource_history_summary`, `qc_gate_status`. Route surface, response envelope keys, TTL, and error codes unchanged. Backward-compatible.

## [api-inventory 1.1.11] — 2026-05-29
### Changed
- ai-pipeline-upgrade: Updated `ai_routes.py` row — function mode now uses single combined LLM call; `chat_history` added to session store. No route or field changes.

## [data 1.11.0] — 2026-05-29
### Added
- ai-pipeline-upgrade: Added §2.9 (AI Session Store Shape with `chat_history` pairs, 8-pair cap, TTL, pop-preservation). Added param schemas for `production_history_query` (raw_params dispatch), `resource_history_summary` (kwargs), `qc_gate_status` (no params). Added `normalize_chart_data` output for `qc_gate_status` (→ stations list); pass-through for the other two. Additive; no existing schemas changed.

## [business 1.11.0] — 2026-05-29
### Added
- ai-pipeline-upgrade: Added AI-04 (combined-prompt output schema), AI-05 (malformed-JSON fallback), AI-06 (chat_history append policy), AI-07 (cap/eviction), AI-08 (history injection ordering), AI-09 (three new function behavioral contracts + production_history_query latency note). Additive; no existing rules changed.

## [api 1.11.0] — 2026-05-22
### Added
- add-package-detail-tables: Added `package: string | null` to hold-history detail rows; added `PRODUCTLINENAME: string | null` to query-tool lot-history and equipment-lots rows; confirmed equipment-rejects already had PRODUCTLINENAME; added `PRODUCTLINENAME: string | null` to material-consumption detail rows (detail spool schema change — parquet cleanup required on deploy/rollback). All additive; no existing fields removed.

## [api-inventory 1.1.10] — 2026-05-22
### Added
- add-package-detail-tables: Updated `hold_history_routes.py` (detail list `package` field), `query_tool_routes.py` (lot-history + equipment-lots `PRODUCTLINENAME`; equipment-rejects confirmation), `material_consumption_routes.py` (detail/page `PRODUCTLINENAME`; parquet cleanup note). All additive.

## [data 1.10.0] — 2026-05-22
### Added
- add-package-detail-tables: Added §3.11 documenting hold-history detail row schema (new `package: string | null` field). Updated §3.6 (query-tool lot-history / equipment-lots) with `PRODUCTLINENAME: string | null` and `_PARTIAL_NONKEY_COLS_LOT` extension note. Updated §3.9.2 (material-consumption detail spool) with `PRODUCTLINENAME: VARCHAR | null` (breaking-change surface — parquet cleanup required). §3.7 (equipment-rejects) unchanged. All additive; no existing columns removed.

## [api 1.10.0] — 2026-05-21
### Added
- resource-status-package-group: Added optional `package_groups` query param to `/api/resource/status`, `/api/resource/status/summary`, `/api/resource/status/matrix`; added `package_groups: string[]` to `/api/resource/status/options` response; added `PACKAGEGROUPNAME: string | null` to each `/api/resource/status` record (null for ~91% of resources). All additive; no existing endpoints changed.

## [css 1.6.0] — 2026-06-01
### Added
- downtime-analysis-page (close): Added rule 4.5 to §樣式作用域與隔離 — `resource-shared/styles.css` `:is(.theme-X, …)` group maintenance: every new page theme must be added to all `:is()` groups via batch tool; omission silently breaks header/filter/section-card styles; Rule 6 does not detect this. Evidence: commit `1931d26`.

## [css 1.5.0] — 2026-05-21
### Added
- resource-status-package-group (close): Added rule 4.4 to §樣式作用域與隔離 — `<Teleport to="body">` CSS scoping contract: teleported content must be wrapped in a `<div class="theme-<feature>">` ancestor so descendant CSS selectors resolve correctly. Do not combine `theme-<feature>` and component class on the same element. Evidence: FloatingTooltip.vue pre-existing bug surfaced and fixed during this change.

## [css 1.4.0] — 2026-05-21
### Added
- resource-status-package-group: Added "Resource-Status UI Surface Rules" section documenting FilterBar Package Group MultiSelect (label 封裝群組, scoped under `.theme-resource`), EquipmentCard PACKAGEGROUPNAME text row (hide when null, same scope), and MatrixSection Package dimension column (after OU%, same scope). No new CSS source file; css-inventory.md unchanged.

## [data 1.9.0] — 2026-05-21
### Added
- resource-status-package-group: Added §3.10 documenting the merged resource-status record shape (35+ fields). New field PACKAGEGROUPNAME (string | null) resolved via 46-row in-process lookup dict (DW_MES_RESOURCE_PACKAGEGROUP, 7-day TTL, independent of 24h resource_cache cycle). NULL for ~91% of resources. No existing fields removed or renamed.

## [api 1.9.0] — 2026-05-20
### Added
- material-part-consumption: Added 7 endpoints under `/api/material-consumption` (filter-options, query, view, detail, detail/page, detail/job, export). Summary query always synchronous; detail sync ≤ SYNC_ROW_LIMIT, async Type B (RQ queue `material-consumption`) for larger sets. `/view` regroups from DuckDB spool without Oracle re-query. Additive; no existing endpoints changed.

## [css 1.3.0] — 2026-05-20
### Added
- material-part-consumption (close): Added "Known Global Rule Interactions" section documenting that `.ui-card { overflow: hidden }` (global rule in `tailwind.css`) clips `position: absolute` dropdowns nested inside it. Establishes the scoped modifier class + `overflow: visible` override as the authoritative pattern; added corresponding Forbidden Practice entry prohibiting direct modification of the global rule. Evidence: filter panel MultiSelect was silently clipped until `.filter-query-card` override was introduced.

## [css 1.2.1] — 2026-05-20
### Added
- material-part-consumption: Added `.theme-material-consumption` scoping rule for `frontend/src/material-consumption/style.css`. Enforced by `npm run css:check` Rule 6; zero unscoped top-level rules permitted. CI fails on any violation.

## [data 1.8.0] — 2026-05-20
### Added
- material-part-consumption: Added §3.9 with summary spool schema (8 columns: txn_date, material_part, pj_type, primary_category, total_consumed, total_required, lot_count, workorder_count) and detail spool schema (mirrors forward_by_lot.sql columns + pj_type). New spool namespaces only; no existing schemas changed.

## [business 1.10.0] — 2026-05-20
### Added
- material-part-consumption: Added MC-01..MC-05 rules (data source/aggregation grouping, 20-part cap/wildcard/meta-char validation, granularity excluded from summary cache key, async threshold default 30000 rows, no DuckDB prewarm). Additive; no existing rules changed.

## [ci 1.3.17] — 2026-05-20
### Changed
- material-part-consumption: Added worker queue deploy/rollback checklist for the new `material-consumption` RQ queue (systemd unit verification, zero-worker alert, parquet cleanup on schema-breaking rollback). No existing gates changed.

## [css-inventory 1.2.2] — 2026-05-19
### Added
- admin-perf-detail-ui: Added `frontend/src/admin-pages/style.css` (`theme-admin-pages`) to Route-Local Feature Layers table. File pre-existed since `a0aa6a3` but was missing from inventory.

## [business 1.9.0] — 2026-05-19
### Added
- fix-admin-dashboard: `ADMIN-06` — log query path divergence rule: `query_logs_all()`/`count_logs()` must not filter by `synced`; `query_logs()` retains the filter intentionally. `ADMIN-07` — log pagination authoritative total rule: `total` must come from independent `COUNT` queries, not windowed fetch length.

## [data 1.7.0] — 2026-05-19
### Added
- fix-admin-dashboard: New Section 3.8 documenting the full `GET /admin/api/performance-detail` payload shape (baseline keys previously undocumented + new keys). `data.redis` gains `evicted_keys`, `expired_keys`, `mem_fragmentation_ratio`, `slowlog`. New `data.duckdb` sub-object added with `temp_dir_bytes`, `memory_limit_state`. All additions additive.
- Source: change `fix-admin-dashboard`.

## [api 1.8.0] — 2026-05-19
### Added
- fix-admin-dashboard: `/admin/api/performance-detail` `data.redis` gains `evicted_keys` (int), `expired_keys` (int), `mem_fragmentation_ratio` (float), `slowlog` (array of top-5 `{id, duration_us, command}`). New top-level `data.duckdb` sub-object `{temp_dir_bytes, memory_limit_state}`. `/admin/api/logs` query scope widened from `synced=0` rows only to all rows; pagination fixed for merge mode. All changes additive, backward-compatible.
- Source: change `fix-admin-dashboard`.

## [api-inventory 1.1.7] — 2026-05-19
### Changed
- fix-admin-dashboard: `admin_routes.py` compatibility note added for performance-detail new keys and logs filter-scope widening.
- Source: change `fix-admin-dashboard`.

## [ci 1.3.16] — 2026-05-18
### Changed
- admin-pages-vue-spa-and-admin-dashboard-ts-entry: `tsconfig.json` `include` expanded with `"src/admin-dashboard/**/*"` and `"src/admin-pages/**/*"`. Vite `rollupOptions.input` gains `admin-pages` entry. `/admin/pages` `renderMode` flipped `external → native` in `routeContracts.js`. Flask `/admin/pages` switched to Vue SPA HTML serving. `asset_readiness_manifest.json` gains `/admin/pages: ["admin-pages.js"]`. Gate tier unchanged (informational); additive prose only.
- Source: change `admin-pages-vue-spa-and-admin-dashboard-ts-entry`.

## [css-inventory 1.2.1] — 2026-05-18
### Changed
- remove-unused-pages: Added `schema-version: 1.2.0` frontmatter (previously absent), then bumped to 1.2.1. Deleted three removed-app rows: `admin-performance/style.css`, `admin-user-usage-kpi/style.css`, `tables/style.css`.
- Source: change `remove-unused-pages`.

## [ci 1.3.15] — 2026-05-18
### Changed
- remove-unused-pages: frontend-build scope reduced (removed 3 apps: `tables`, `admin-performance`, `admin-user-usage-kpi`; added `production-history`). Additive prose documenting Vite build-input change; gate tier, command, and status unchanged.
- Source: change `remove-unused-pages`.

## [api-inventory 1.1.6] — 2026-05-18
### Changed
- remove-unused-pages: Updated Admin Page Routes row — `/admin/performance` and `/admin/user-usage-kpi` are now documented as redirect-only stubs (HTTP 302 → `/admin/dashboard`), not SPA HTML routes. `/admin/dashboard` is the sole live SPA HTML entry.
- Source: change `remove-unused-pages`.

## [ci 1.3.14] — 2026-05-18
### Changed
- migrate-mid-section-defect-ts (Phase 3): `tsconfig.json` `include` expanded with `"src/mid-section-defect/**/*"`, covering `main.ts` and `App.vue` under `strict: true`. Gate tier unchanged (informational). Additive prose only.
- Source: change `migrate-mid-section-defect-ts`.

## [ci 1.3.13] — 2026-05-18
### Changed
- migrate-material-trace-ts (Phase 3): `tsconfig.json` `include` expanded with `"src/material-trace/**/*"`, covering `main.ts` and `App.vue` under `strict: true`. Gate tier unchanged (informational). Additive prose only.
- Source: change `migrate-material-trace-ts`.

## [api 1.7.0] — 2026-05-18
### Breaking
- equipment-rejects-by-lots: `POST /api/query-tool/equipment-period` (`query_type='rejects'`) and `POST /api/query-tool/export-csv` (`export_type='equipment_rejects'`) response shape changed from aggregate (EQUIPMENTNAME, LOSSREASONNAME, TOTAL_REJECT_QTY, TOTAL_DEFECT_QTY, AFFECTED_LOT_COUNT) to per-reject-event detail rows (see data-shape-contract.md §3.7). Data source changed from LOTREJECTHISTORY filtered by EQUIPMENTNAME to LOTWIPHISTORY→LOTREJECTHISTORY via CONTAINERID (fixes cross-station reject omission). Service parameter renamed `equipment_names → equipment_ids`. Hard cutover — both EquipmentView and LotEquipmentView consumers ship in the same PR. Deprecate-2-minors policy bypassed because all consumers are in the same monorepo and shipped atomically.
- Source: change `equipment-rejects-by-lots`.

## [data 1.6.0] — 2026-05-18
### Breaking
- equipment-rejects-by-lots: Added §3.7 Query-Tool Equipment-Lot-Rejects Row documenting the new per-reject-event detail row shape (23 columns: CONTAINERID, CONTAINERNAME, WORKCENTERNAME, WORKCENTER_GROUP, WORKCENTERSEQUENCE_GROUP, PRODUCTLINENAME, PJ_FUNCTION, PJ_TYPE, PRODUCTNAME, SPECNAME, LOSSREASONNAME, EQUIPMENTNAME, REJECTCOMMENT, REJECT_QTY, STANDBY_QTY, QTYTOPROCESS_QTY, INPROCESS_QTY, PROCESSED_QTY, REJECT_TOTAL_QTY, DEFECT_QTY, TXN_TIME, TXNDATE, TXN_DAY). Old aggregate fields (TOTAL_REJECT_QTY, TOTAL_DEFECT_QTY, AFFECTED_LOT_COUNT) removed. Cross-station semantic documented: EQUIPMENTNAME reflects reject event's equipment (may differ from queried equipment). CSV export column order mirrors §3.7.
- Source: change `equipment-rejects-by-lots`.

## [business 1.8.0] — 2026-05-18
### Added (additive)
- Query Tool Rules: QT-07 (equipment-rejects cross-station semantic — `get_equipment_rejects()` resolves EQUIPMENTIDs via LOTWIPHISTORY to DISTINCT CONTAINERID set, then returns LOTREJECTHISTORY rows for those containers; EQUIPMENTNAME may differ from queried equipment; CONTAINERID is the only correct join key; empty equipment_ids → UserInputError; LOTREJECTHISTORY query short-circuited on empty input).
- Source: change `equipment-rejects-by-lots`.

## [api-inventory 1.1.5] — 2026-05-18
### Changed (breaking)
- equipment-rejects-by-lots: `query_tool_routes.py` `POST /api/query-tool/equipment-period` (`query_type='rejects'`) and `POST /api/query-tool/export-csv` (`export_type='equipment_rejects'`) response shape changed to per-reject-event detail rows (see api-contract.md §10). Breaking cutover — both consumer views (EquipmentView, LotEquipmentView) shipped atomically in same PR. Deprecate-2-minors policy bypassed (monorepo atomic cutover).
- Source: change `equipment-rejects-by-lots`.

## [api 1.6.0] — 2026-05-15
### Added (additive)
- Section 10 Compatibility Note: query-tool `lot_history`, `equipment_lots`, and `adjacent_lots` responses gain `partial_count: integer (≥ 1)`. `TRACKINQTY` now = `MAX(TRACKINQTY)` (original load qty); `TRACKOUTQTY` now = `SUM(TRACKOUTQTY)` (cumulative). Prior `ROW_NUMBER()` deduplication was a silent data-accuracy bug returning only the last partial's values. Additive; no endpoint removed; no error-code change. Strict-guard divergence is transparent to consumers. Export CSV (`lot_history` / `equipment_lots`) gains `partial_count` as a pass-through column.
- Source: change `query-tool-partial-trackout`.

## [data 1.5.0] — 2026-05-15
### Added (additive)
- Section 3.6: Query-Tool Lot-History / Equipment-Lots / Adjacent-Lots Row schema. 17-column table documenting the post-aggregation row shape, grouping keys (4-tuple for lot_history/equipment_lots, 3-tuple for adjacent_lots), `TRACKINQTY = MAX` / `TRACKOUTQTY = SUM` semantics, strict-guard fallback (`partial_count = 1`), and `RELATIVE_POSITION` column (adjacent_lots only). Documents prior wrong behavior (ROW_NUMBER last-partial deduplication). Cross-referenced to QT-05 / QT-06.
- Source: change `query-tool-partial-trackout`.

## [business 1.7.0] — 2026-05-15
### Added (additive)
- Query Tool Rules: `QT-05` (partial-trackout aggregation for `lot_history.sql`, `equipment_lots.sql`, `adjacent_lots.sql`) and `QT-06` (strict guard with per-SQL non-key column lists; INFO log per request; no error to client).
### Changed (additive scope extension)
- PH-06: extended to also enumerate query-tool SQL paths as additional surfaces governed by the same aggregation semantics.
- PH-07: scope note extended to include query-tool paths; query-tool log prefix documented.
- Source: change `query-tool-partial-trackout`.

## [data 1.4.1] — 2026-05-15
### Changed (semantic refinement, same-day patch over 1.4.0)
- Section 3.4: aggregation key reduced from 5-tuple to 4-tuple — TRACKINQTY removed from grouping key. Reason: this MES records TRACKINQTY as qty REMAINING at each partial's start (decreases across partials of one upload), not the original load. Keeping TRACKINQTY in the key prevented real partial-trackout rows from ever merging. Aggregated TRACKINQTY now = `MAX(TRACKINQTY)` = original load qty. TRACKINQTY/TRACKINTIMESTAMP column-note prose updated accordingly.
- Source: change `prod-history-detail-partial-merge` (post-smoke-test correction).

## [business 1.6.1] — 2026-05-15
### Changed (semantic refinement, same-day patch over 1.6.0)
- PH-06 and PH-07 updated from 5-tuple → 4-tuple key (`CONTAINERNAME, SPECNAME, EQUIPMENTID, TRACKINTIMESTAMP`). PH-06 adds `TRACKINQTY = MAX(...)` clause for aggregated rows. PH-07 strict-guard log description corrected to "summary count per request" matching the locked log policy. Decision Table rows updated to 4-tuple.
- Source: change `prod-history-detail-partial-merge` (post-smoke-test correction).

## [api 1.5.1] — 2026-05-15
### Changed (semantic refinement, same-day patch over 1.5.0)
- Section 10 Compatibility Note: aggregation key reduced from 5-tuple to 4-tuple. `partial_count`, CSV `PartialCount`, `total_rows` semantics unchanged. `trackin_qty` for aggregated rows now documented as `MAX(...)` (= original load qty).
- Source: change `prod-history-detail-partial-merge` (post-smoke-test correction).

## [data 1.4.0] — 2026-05-15
### Added (additive)
- Section 3.4: added `partial_count` column (`integer`, not null, view-layer computed) to Production-History Detail Row table. Updated opening sentence to describe aggregated grain (PH-06/PH-07 view-layer) versus raw spool grain. Updated Row-grain rule paragraph to note `detail row count ≤ LOTWIPHISTORY row count` and clarify `partial_count` is synthesized in view layer (not in spool parquet). `TRACKINTIMESTAMP` / `TRACKINQTY` notes updated to mark them as group-shared keys; `TRACKOUTTIMESTAMP` / `TRACKOUTQTY` notes describe both aggregated (MAX/SUM) and raw (strict-guard fallback) modes.
- Source: change `prod-history-detail-partial-merge`.

## [business 1.6.0] — 2026-05-15
### Added (additive)
- Production-History Rules: `PH-06` (partial-trackout aggregation — 5-tuple key `(CONTAINERNAME, SPECNAME, EQUIPMENTID, TRACKINTIMESTAMP, TRACKINQTY)`; `TRACKOUTTIMESTAMP = MAX(...)`, `TRACKOUTQTY = SUM(...)`, `partial_count = COUNT(*)`; A/B-lot interleaving preserved; all three paths DuckDB/pandas/CSV must match; `pagination.total_rows` post-aggregation) and `PH-07` (strict guard — non-key column divergence → raw rows for that group with `partial_count = 1` + INFO log; no error returned). Additive cross-reference clauses appended to `PH-01` (points to PH-06 for view-layer aggregation) and `PH-04` (sort key for aggregated groups uses shared `TRACKINTIMESTAMP`). Two Decision Table rows added for consistent-group and divergent-group branches.
- Source: change `prod-history-detail-partial-merge`.

## [api 1.5.0] — 2026-05-15
### Added (additive)
- Section 10 Compatibility Note: `POST /api/production-history/page` rows gain `partial_count: integer (≥ 1)` (additive). `GET /api/production-history/export` CSV gains trailing column `PartialCount` after `TrackOutQty`. `pagination.total_rows` semantics clarified as post-aggregation count. Aggregation applied consistently across DuckDB SQL, pandas fallback, and CSV stream. Strict-guard divergence behavior is transparent to API consumers (no new error code). See business-rules.md PH-06/PH-07.
- Source: change `prod-history-detail-partial-merge`.

## [css 1.2.0] — 2026-05-15
### Added (additive)
- Detail Table Layout Rule: hold-history `DetailTable.vue`, hold-overview "Hold Lot Details", reject-history `components/DetailTable.vue`, and material-trace "查詢結果" Result Card must all render as single flat tables — one outer card wrapper with `DataTable` directly inside `.card-body`; `.card-body` global padding must not frame the DataTable (apply `padding: 0` scoped override where needed). Reference implementations: `hold-detail/DistributionTable.vue`, `wip-detail/LotTable.vue`. "表中表（table-within-table）" added to Forbidden Practices list.
- Source: changes `hold-history-detail-flat-table`, `reject-material-flat-table`.

## [data 1.3.0] — 2026-05-14
### Added (additive)
- Section 3.5: Production-History Matrix Tree Node — node shape `{label, level, count, month_counts, children}` with per-field table; distinct-count grain rule stating `workcenter`/`spec` `count` and `month_counts` are `COUNT(DISTINCT CONTAINERNAME)` re-evaluated independently at that grain, NOT the sum of child counts (distinct counts are non-additive across hierarchy levels). Leaf `equipment` grain unchanged.
### Changed (descriptive accuracy)
- Section 3.4: trailing matrix sentence tightened — now scopes the `COUNT(DISTINCT CONTAINERNAME)` statement to the leaf cell and cross-references §3.5 for parent-level semantics. No §3.4 column schema change.
- Source: change `fix-matrix-distinct-count`.

## [business 1.5.0] — 2026-05-14
### Added (additive)
- Production-History Rules: `PH-05` (Matrix distinct-count non-additivity — parent-level `workcenter`/`spec` `count` and `month_counts` are `COUNT(DISTINCT CONTAINERNAME)` re-evaluated per grain, not summed from children; both DuckDB SQL and pandas fallback must produce identical trees). Additive cross-reference clause appended to `PH-02` pointing to `PH-05` for parent-level rollup semantics.
- Source: change `fix-matrix-distinct-count`.

## [api 1.4.0] — 2026-05-14
### Added (additive)
- Section 10 Compatibility Note: `POST /api/production-history/query` `start_date`/`end_date` relaxed from unconditionally-required to conditionally-required — required in classification mode (no identifier wildcard tokens), optional in identifier mode (any of `mfg_orders`/`lot_ids`/`wafer_lots` present) where omitting both runs a wide/all-time query. Date-range cap (730d) still applies when dates are supplied. Backward-compatible: callers that always send dates are unaffected. Per-mode validation cross-referenced to business-rules.md PHF-07/PHF-08.
- Source: change `prod-history-query-mode-tabs`.

## [api-inventory 1.1.4] — 2026-05-14
### Changed (descriptive accuracy)
- `production_history_routes.py` scope line updated: `start_date`/`end_date` documented as conditionally-required (classification mode required, identifier mode optional). No endpoint added/removed/renamed. Compatibility Notes entry added for `prod-history-query-mode-tabs`.
- Source: change `prod-history-query-mode-tabs`.

## [business 1.4.0] — 2026-05-14
### Added (additive)
- Production-History Filter Rules: `PHF-07` (identifier-mode date optionality — `start_date`/`end_date` not required when any of `mfg_orders`/`lot_ids`/`wafer_lots` present; runs wide/all-time query; `pj_types` also not required in identifier mode) and `PHF-08` (classification-mode required params — `pj_types`+`start_date`+`end_date` required when no identifier token present; precise post-mode-split restatement of VAL-02). Two Decision Table rows added for the per-mode validation branch.
- Source: change `prod-history-query-mode-tabs`.

## [api 1.3.0] — 2026-05-14
### Added (additive)
- Section 4: new row for `GET /api/production-history/filter-options?selected=<json>` (auth required, response `success_response`, errors 400/404/500).
- Section 10 Compatibility Note: documents new endpoint and six new additive optional body fields on `POST /api/production-history/query` (`pj_packages[]`, `pj_bops[]`, `pj_functions[]`, `mfg_orders[]`, `lot_ids[]`, `wafer_lots[]`); wildcard semantics governed by business-rules.md PHF-01..PHF-06. Type-only flow unchanged; backward-compatible.
- Source: change `prod-history-first-tier-cache-filters`.

## [api-inventory 1.1.3] — 2026-05-14
### Changed (additive)
- `production_history_routes.py` scope extended: new `GET /api/production-history/filter-options` cross-filter cached options endpoint; six new additive optional body fields on `POST /api/production-history/query`. Wildcard rules cross-referenced to PHF-02..PHF-06.
- Compatibility Notes: new entry for `prod-history-first-tier-cache-filters` additive changes.
- Source: change `prod-history-first-tier-cache-filters`.

## [data 1.2.0] — 2026-05-14
### Added (additive)
- Section 2.7: Production-History Filter-Options Response shape (`pj_types`, `packages`, `bops`, `pj_functions` distinct sorted string arrays; `meta.schema_version: 2`, `meta.updated_at`). Cross-filter semantics; constraints on empty/malformed `selected`.
- Section 2.8: Container Filter Cache Payload (internal Redis L2 / in-process L1 schema) — required `schema_version: int`, `tuples[[PJ_TYPE, PRODUCTLINENAME, PJ_BOP, PJ_FUNCTION]]`, denormalised `indices` map, `updated_at`. Documents 4-tuple co-occurrence representation that backs §2.7.
- Source: change `prod-history-first-tier-cache-filters`.

## [business 1.3.0] — 2026-05-14
### Added (additive)
- Production-History Filter Rules group (`PHF-01` cross-filter cardinality via 4-tuple in-memory filter; `PHF-02` wildcard grammar — single `*` any position, non-`*` chars ≥ 2 total, ≤ 100 patterns/field, idempotent parser; `PHF-03` wildcard SQL emit via parameter-bound `LIKE ESCAPE '\'` with `%`/`_` escape; `PHF-04` cache `schema_version` field, mismatch → silent rebuild; `PHF-05` multi-worker rebuild lock at `tmp/container_filter_cache.loading` with 90 s poll fallback; `PHF-06` SQL meta-char rejection — `'`, `;`, `--`, `/*`, `*/`, control chars → 400 before Oracle).
- Source: change `prod-history-first-tier-cache-filters`.

## [ci 1.3.12] — 2026-05-14
### Changed
- Gate Compatibility Note added for `prod-history-first-tier-cache-filters`. Tier 1 fuzz scope expansion: `tests/routes/test_fuzz_routes.py` extended to cover new wildcard fields (`mfg_orders[]`, `lot_ids[]`, `wafer_lots[]`); Tier 1 contract assertion: `/filter-options` response shape; Tier 3 multi-worker concurrency: `container_filter_cache` rebuild lock. New rollback primitive: bump cache `schema_version` 2 → 3 in follow-up deploy to invalidate L2 entries (no `redis-cli DEL` needed, no parquet cleanup). Gate tier, command, and status unchanged.
- Source: change `prod-history-first-tier-cache-filters`.

## [data 1.1.0] — 2026-05-14
### Added (additive)
- Section 3.4: Production-History Detail Row schema (15 columns, raw per-partial-track-out grain, includes `PJ_FUNCTION` pre-staged for filter use by Change 3). Row-grain rule + Matrix `COUNT(DISTINCT CONTAINERNAME)` semantics documented. Aggregated aliases `TRACKIN_TS / TRACKOUT_TS / TRACKIN_QTY / TRACKOUT_QTY` removed; raw column names `TRACKINTIMESTAMP / TRACKOUTTIMESTAMP / TRACKINQTY / TRACKOUTQTY` are now contract-of-record.
- Source: change `prod-history-detail-raw-rows`.

## [business 1.2.0] — 2026-05-14
### Added (additive)
- Production-History Rules group (`PH-01` raw per-partial detail rows; `PH-02` Matrix lot-count via DuckDB `COUNT(DISTINCT CONTAINERNAME)`; `PH-03` `PJ_FUNCTION` spool carriage; `PH-04` detail row ordering by `TRACKINTIMESTAMP` ASC). Drops prior implicit assumption "first partial = original batch quantity".
- Source: change `prod-history-detail-raw-rows`.

## [ci 1.3.11] — 2026-05-13
### Changed
- Gate Compatibility Note added for `migrate-job-query-ts` (Phase 3). `tsconfig.json` `include` expanded with `"src/job-query/**/*"`, covering `main.ts`, `App.vue`, `composables/useJobQueryData.ts`. Gate tier unchanged (informational). Additive prose only.
- Source: change `migrate-job-query-ts`.

## [ci 1.3.10] — 2026-05-13
### Changed
- Gate Compatibility Note added for `resource-history-perf`. New test coverage scope documented under existing gates: `tests/integration/test_resource_history_prewarm.py` (Tier 3 nightly, startup pre-warm + Redis key assertion); `tests/stress/test_resource_history_stress.py` extended with concurrent progress-poll stress (Tier 4); new Playwright resilience + data-boundary specs for progress endpoint (Tier 1). No gate tier, command, or status changes.
- Source: change `resource-history-perf`.

## [api 1.2.2] — 2026-05-13
### Added (additive)
- Section 4: new row for `GET /api/resource/history/query/progress?query_id=<uuid>` (auth required, response `success_response`, errors 400/404).
- Section 10 Compatibility Note: documents progress endpoint as additive new endpoint from `resource-history-perf`.
- Source: change `resource-history-perf`.

## [api-inventory 1.1.2] — 2026-05-13
### Changed (additive)
- `resource_history_routes.py` scope extended with `GET /api/resource/history/query/progress` side-channel endpoint; Redis key pattern documented.
- Compatibility Notes: new entry for `resource-history-perf` additive progress endpoint.
- Source: change `resource-history-perf`.

## [data 1.0.2] — 2026-05-13
### Added (additive)
- Section 2.6: Resource-History Batch Query Progress response shape (`query_id`, `total_chunks`, `completed_chunks`, `percent`, `status`); closed `status` enum `running | done | error`; all five fields required.
- Source: change `resource-history-perf`.

## [env 1.0.2] — 2026-05-13
### Added (additive)
- `RESOURCE_HISTORY_DUCKDB_PATH` (optional, default `tmp/resource_history.duckdb`): path for the persistent DuckDB file that caches last N months of resource-history data. Relative paths resolve against CWD; use absolute path in Docker on a named volume.
- Updated `RESOURCE_HISTORY_PREWARM_MONTHS` description: now controls DuckDB cache window in months (not Redis pre-warm as originally described in 1.0.1).
- Source: change `resource-history-perf` redesign.

## [env 1.0.1] — 2026-05-13
### Added (additive)
- New section "Cache Tuning — Resource History": `RESOURCE_HISTORY_HISTORICAL_TTL` (optional, default 86400s) and `RESOURCE_HISTORY_PREWARM_MONTHS` (optional, default 3). Both optional with safe defaults; restart required.
- Source: change `resource-history-perf`.

## [data 1.0.1] — 2026-05-13
### Added (additive)
- Section 2.5: WIP Filter-Options Response shape documenting `workflows`, `bops`, `pjFunctions` arrays alongside existing arrays. All three are new additive fields from change `wip-hold-drilldown-filters`.
- Section 3.1.1: WIP Detail Lot Row sub-table with explicit column list; adds `pjType` (nullable string, from DB `PJ_TYPE`) as additive new field.
- Source: change `wip-hold-drilldown-filters`.

## [api 1.2.1] — 2026-05-13
### Added (additive)
- Section 10 Compatibility Note: documents three new optional query params (`workflow`, `bop`, `pj_function`) accepted by `/api/wip/overview/summary`, `/api/wip/overview/matrix`, `/api/wip/detail/<workcenter>`, `/api/wip/meta/filter-options`; `pjType` addition to lot rows; `workflows`/`bops`/`pjFunctions` addition to filter-options response.
- Source: change `wip-hold-drilldown-filters`.

## [api-inventory 1.1.1] — 2026-05-13
### Changed (additive)
- `wip_routes.py` scope line extended to document new optional params `workflow`/`bop`/`pj_function`, `pjType` lot field, and `workflows`/`bops`/`pjFunctions` filter-options arrays.
- Compatibility Notes: new entry for wip-hold-drilldown-filters additive changes.
- Source: change `wip-hold-drilldown-filters`.

## [ci 1.3.9] — 2026-05-13
### Changed
- Gate Compatibility Note added for `migrate-resource-history-ts` (Phase 3 item #15). `tsconfig.json` `include` expanded with `"src/resource-history/**/*"`, covering `main.ts`, `useResourceHistoryDuckDB.ts`, `App.vue`, and 7 component SFCs (`FilterBar.vue`, `KpiCards.vue`, `TrendChart.vue`, `StackedChart.vue`, `ComparisonChart.vue`, `HeatmapChart.vue`, `DetailSection.vue`). Gate tier unchanged (informational). Additive prose only.
- Source: change `migrate-resource-history-ts` Phase 3.

## [ci 1.3.8] — 2026-05-13
### Changed
- Gate Compatibility Note added for `migrate-qc-gate-ts` (Phase 3 item #17). `tsconfig.json` `include` expanded with `"src/qc-gate/**/*"`, covering `main.ts`, `App.vue`, `composables/useQcGateData.ts`, `components/LotTable.vue`, `components/QcGateChart.vue`. Gate tier unchanged (informational). Additive prose only.
- Source: change `migrate-qc-gate-ts` Phase 3.

## [ci 1.3.7] — 2026-05-13
### Changed
- Gate Compatibility Note added for `migrate-wip-hold-ts` (Phase 3). `tsconfig.json` `include` expanded with `"src/wip-overview/**/*"`, `"src/wip-detail/**/*"`, `"src/hold-overview/**/*"`, `"src/hold-detail/**/*"`. Gate tier unchanged (informational). Additive prose only.
- Source: change `migrate-wip-hold-ts` Phase 3.

## [ci 1.3.6] — 2026-05-12
### Changed
- Gate Compatibility Note added for `migrate-hold-history-ts` (Phase 3 item #2). `tsconfig.json` `include` expanded with `"src/hold-history/**/*"`. Gate tier unchanged (informational). Additive prose only.
- Source: change `migrate-hold-history-ts` Phase 3.

## [ci 1.3.5] — 2026-05-12
### Changed
- Gate Compatibility Note added for `migrate-reject-history-ts` (Phase 3 item #1). `tsconfig.json` `include` expanded with `"src/reject-history/**/*"`. Gate tier unchanged (informational). Additive prose only.
- Source: change `migrate-reject-history-ts` Phase 3.

## [ci 1.3.4] — 2026-05-12
### Changed
- Gate Compatibility Notes: `frontend-type-check` Phase 1f scope expansion documented — `tsconfig.json include` widened from 5 scopes to also cover `src/wip-shared/**/*`; gate now covers 6 additional modules (3 Vue SFCs + 2 composables + 1 constants module). Also removes `@ts-expect-error` suppressions from `shared-composables/` and `shared-ui/` that were cross-phase placeholders pending this migration. Gate tier, command, and informational status unchanged.
- Source: change `migrate-wip-shared-ts` Phase 1f.

## [ci 1.3.3] — 2026-05-12
### Changed
- Gate Compatibility Notes: `frontend-type-check` Phase 1e scope expansion documented — `tsconfig.json include` widened from `src/core/**/* + src/shared-composables/**/* + src/shared-ui/**/* + src/admin-shared/**/*` to also cover `src/resource-shared/**/*`; gate now covers 3 additional modules (2 Vue SFCs + 1 constants module). Gate tier, command, and informational status unchanged.
- Source: change `migrate-resource-shared-ts` Phase 1e.

## [ci 1.3.2] — 2026-05-12
### Changed
- Gate Compatibility Notes: `frontend-type-check` Phase 1d scope expansion documented — `tsconfig.json include` widened from `src/core/**/* + src/shared-composables/**/* + src/shared-ui/**/*` to also cover `src/admin-shared/**/*`; gate now covers 5 additional modules (4 Vue SFCs + 1 composable). Gate tier, command, and informational status unchanged.
- Source: change `migrate-admin-shared-ts` Phase 2.

## [ci 1.3.1] — 2026-05-05
### Changed
- Gate Compatibility Notes: `frontend-type-check` Phase 1b scope expansion documented — `tsconfig.json include` widened from `src/core/**/*` to also cover `src/shared-composables/**/*`; gate now covers 21 core + 11 shared-composable `.ts` modules under `strict: true`. Gate tier, command, and informational status unchanged.
- Source: change `migrate-shared-composables-ts` Phase 1b.

## [ci 1.3.0] — 2026-05-05
### Added
- Workflow Configuration: updated Node version from 20 → 22 across all jobs; added `unit-and-integration-tests` row (backend-tests.yml) with Node 22 requirement; added Node version constraint note — all pytest-running jobs MUST include `setup-node@v4 node-version: "22"` because parity tests use `--experimental-strip-types`.
- Environment Constraints (conda): new section — `environment.yml` must pin `nodejs>=22.6`; documents conda PATH-shadowing in login-shell pytest runs.
- Source: change `migrate-core-to-typescript` Phase 1a close-out; evidence commits `05e8c99`, `b2fd91b`, `06eaad3`.

## [ci 1.2.1] — 2026-05-05
### Changed
- Gate Compatibility Notes: `frontend-type-check` scope expansion documented — Phase 0 covered only `src/core/index.ts` placeholder (~0 substantive files); Phase 1a widened `tsconfig.json include` to `src/core/**/*`, gate now covers all 21 core `.ts` modules under `strict: true`. No gate tier or command change; informational status unchanged.

## [ci 1.2.0] — 2026-05-05
### Added
- Gate Inventory: 新增 `frontend-type-check` gate（Tier 1，informational，`cd frontend && npm run type-check` / `vue-tsc --noEmit`）；wired in `.github/workflows/frontend-tests.yml`。屬 add-ts-toolchain Phase 0 TypeScript 工具鏈建立，達 promotion criteria 後提升為 required。

## [api 1.2.0] — 2026-05-05
### Added
- 完整 endpoint 表：從 30 個擴展至覆蓋全部 83+ 路徑（新增 WIP、Hold-Overview、Hold-Detail、Hold-History、QC-Gate、Resource、Resource-History、Reject-History、Yield-Alert、Production-History、Material-Trace、Trace、Mid-Section-Defect、Analytics、Query-Tool、Job-Query、Dashboard、Admin 所有端點）。

## [business 1.1.0] — 2026-05-05
### Added
- 新增 9 個 rule 群組：WIP（4 rules）、Hold-Overview（3）、QC-Gate（2）、Resource（3）、Resource-History（4）、Analytics（4）、Query-Tool（4）、Job-Query（4）、Dashboard（4）、Mid-Section-Defect（4）、Admin（5）。

## [ci 1.1.0] — 2026-05-05
### Changed
- Gate inventory: 以真實 pytest marker 命令取代 placeholder；新增 playwright-resilience、playwright-data-boundary、playwright-critical-journeys gate。
- Workflow Configuration: 新增 test directory → tier 對應表。
- nightly-integration gate 分離為獨立 job。

## [data 1.0.0] — 2026-05-05
### Changed (breaking)
- 從空 placeholder 升級為完整規範（0.x 為草稿，無實作依賴，升至 1.0.0 確立為正式版本）。
### Added
- 完整 API envelope shapes（success、error、async job 202、job status）。
- 常用 query result shapes（paginated list、summary+detail、hold-history today snapshot、truncated payload）。
- 逐欄 Required Columns 表（lot row、duration item、pareto row）。
- Invalid Data Behavior 對應表（含 test references）。
- Export/Import Format（CSV、Parquet、NDJSON）。
- Row Limit / Truncation Policy 表。

## [api 0.1.0] — 2026-04-27
Initial draft.

## [css 0.1.0] — 2026-04-27
Initial draft.

## [env 0.1.0] — 2026-04-27
Initial draft.

## [data 0.1.0] — 2026-04-27
Initial draft.

## [business 0.1.0] — 2026-04-27
Initial draft.

## [ci 0.1.0] — 2026-04-27
Initial draft.
