---
change-id: production-achievement-overhaul
schema-version: 0.1.0
last-changed: 2026-07-14
---

# Implementation Plan: production-achievement-overhaul

## Objective

Deliver, as one atomic Tier-0 PR, design.md's 2×2 view-model overhaul of the 生產達成率 report: `DailyView` (當日/前日) and `CumulativeView` (當月/自訂區間) sharing one wire protocol, `PACKAGE_LF` promoted to a first-class spool dimension, 3 admin-configurable MySQL tables (package-LF merge / workcenter merge / daily plans), an hourly warm-cache for today/yesterday, a standalone `/production-achievement-settings` mini-app, and the bundled D6 closing-chunk fetch-completeness fix. All rollup stays client-side (ADR-0016 **extended**, not reversed). Satisfies AC-1..AC-13 (change-classification.md § Inferred Acceptance Criteria). The api/data/business contracts and the ADR-0016 Extension are already final — engineers implement against them.

## Execution Scope

### In Scope
- The full 2×2 model per design.md § Summary + § Affected Components (do NOT build 4 independent code paths). Backend Phases 1-5 and Frontend Phases 6-9 below.
- Backend (backend-engineer): spool grain widening + D6 (AC-1, AC-12); 3 MySQL tables + services with D1/D2 opposite defaults + shift-less plans (AC-2/3/4); verbatim permission reuse (AC-5); 10 route handlers + 5-inline-map `/report` envelope (AC-6); warm-cache module + scheduler wiring (AC-7).
- Frontend (frontend-engineer): 2-stage DuckDB-WASM rollup + D3 aggregate-then-divide (AC-9/AC-10); 4-mode composable state (AC-8); `App.vue` rewrite + chart replacement (AC-9); standalone settings mini-app + 7-location route registration (AC-11).
- Contract coherence (AC-13) for api/data/business/ADR is already landed; the CSS governance rows are a same-PR frontend deliverable (see Contract Updates).

### Out of Scope (non-goals — do not implement)
- **month/range warm-caching** — only 當日/前日 are pre-warmed; 當月/自訂區間 always take the async-spool path. Recorded: design.md § Open Risks (backfilled) + test-plan.md § Out of Scope.
- **Pixel-level / screenshot visual assertions** — owned by visual-reviewer; recorded test-plan.md § Out of Scope.
- **Soak testing** — classification "consider" only; recorded test-plan.md § Out of Scope.
- **OD-9 / OD-10 config-down read-time discriminators** — confirmed no-op; recorded interaction-design.md § Confirmed OD-9/OD-10 + design.md § Open Risks.
- **PA-04 three-shift historical-regime `output_date` assumption** — unaffected; recorded test-plan.md § Out of Scope.
- **Refactoring shared helpers** (a `core/mysql_client.py` query helper, `validate_target_qty`, `MultiSelect.vue`) — keep additive; recorded design.md § Key Decisions + approved plan Phase 3/8. No opportunistic refactors.

## Required Changes

Numbered to the approved plan's phases. **Phase 0** (scaffold + contracts + ADR) and **Phase 10** (contracts consolidation) are DONE. **Phase 11** is the rollout/rollback runbook in ci-gates.md § Rollback Policy (no code). Each row cites the design.md § Affected Components component label — see that table for per-file detail; do not re-derive it here.

| id | area (phase) | required action | owner agent |
|---|---|---|---|
| IP-1 | backend SQL/spool/worker (P1) | Edit `sql/production_achievement.sql` (+`weh.PACKAGE_LF` to SELECT/GROUP BY → 4-dim grain; widen both `:chunk_end_excl` binds to `YYYY-MM-DD HH24:MI:SS`, D6). Edit `workers/production_achievement_worker.py` (`post_aggregate` re-agg + empty-schema fallback carry PACKAGE_LF as nullable 5th col; `pre_query()` appends the D6 closing chunk `[end+1 00:00, end+1 07:30)`; `build_chunk_sql()` full-datetime format). Edit `services/production_achievement_service.py` (bump `_PA_SPOOL_SCHEMA_VERSION` 1→2; add shared `PRODUCTION_ACHIEVEMENT_SPOOL_NAMESPACE`; `build_achievement_rows()` golden-ref +PACKAGE_LF; redefine `get_filter_options().workcenter_groups`→merged D2 list). design.md → Chunk SQL / Worker / PA service. | backend-engineer |
| IP-2 | backend MySQL DDL (P2) | Append 3 idempotent `CREATE TABLE IF NOT EXISTS` to `scripts/sql/production_achievement_tables.sql` (`_package_lf_map`/D1, `_workcenter_merge_map`/D2, `_daily_plans`); seeds per approved plan Phase 2 (~9 pkg rows, exactly 12 wc rows; no `_merged` column suffix). Manually applied before deploy. design.md → MySQL DDL. | backend-engineer |
| IP-3 | backend services + filter_cache + permissions (P3) | Create `services/production_achievement_{package_lf,workcenter_merge,daily_plan}_service.py` (mirror `target_service` `text()`+`get_mysql_connection()` idiom; get/upsert/delete + map dicts; D1 fallback-to-self vs D2 exclude-by-absence vs shift-less plan). Edit `services/filter_cache.py` (+`package_lf_values` key in the 3-loader `_load_cache()`) + create `sql/production_achievement_known_package_lf.sql`. Edit `core/permissions.py` docstring only (widened-scope note, no code change). design.md → New MySQL services / Filter cache / Permissions. | backend-engineer |
| IP-4 | backend routes (P4) | Edit `routes/production_achievement_routes.py`: 10 new handlers (validate → `can_edit_targets` gate → upsert → respond); grow `/report` spool-hit branch 2→5 inline maps (`+package_lf_map, workcenter_merge_map, daily_plan_map`). design.md → Routes. Wire protocol already final (see Contract Updates). | backend-engineer |
| IP-5 | backend warm-cache + scheduler (P5) | Create `services/production_achievement_daily_cache.py` (`_WarmupProductionAchievementJob` subclass with no-op `progress_report()`; `ensure_today/yesterday_loaded()`; **independent** re-read of `PRODUCTION_ACHIEVEMENT_USE_UNIFIED_JOB` before the lazy worker import). Edit `core/spool_warmup_scheduler.py` (+2 `_WARMUP_JOBS` entries; leave the `production_history` exclusion untouched). design.md → Warm-cache module / Scheduler. | backend-engineer |
| IP-6 | frontend DuckDB rollup (P6) | Edit `production-achievement/composables/useProductionAchievementDuckDB.ts`: +3 inline VALUES map tables; 2-stage pipeline `pa_rollup_raw`→`pa_rollup` (D2 INNER JOIN on the resolved raw workcenter_group + D1 LEFT JOIN/COALESCE); replace flat `computeView` with `computeDailyView`/`computeCumulativeView` (D3 aggregate-then-divide in the cumulative trend). design.md → DuckDB-WASM rollup. | frontend-engineer |
| IP-7 | frontend composable state (P7) | Edit `production-achievement/composables/useProductionAchievement.ts`: 4-mode `FilterState`, drop `shift_code`, add `resolveMonthPeriod()`, cap range end at `min(end, today)`, default `焊接_DB`, `runQuery()` branches daily/cumulative over the identical fetch/poll. design.md → Composable state; interaction-design.md § Confirmed OD-3 (auto-run all 4 modes), OD-4 (ignore mid-poll switch). | frontend-engineer |
| IP-8 | frontend App + chart (P8) | Delete `production-achievement/components/AchievementChart.vue`. Create `production-achievement/components/PlanAchievementStackedChart.vue` (real-% stacked series, >100% over-plan segments, `markLine` at y=100 labeled 計畫, colors via `resolveCssVar()`). Rewrite `production-achievement/App.vue` (4-button mode switch defaulting 當日; range-only date inputs; own fake-single-select `:model-value="x?[x]:[]"`; 設定 button; reduced KPI set). design.md → App + chart; interaction-design.md § States / § Controls / § Confirmed OD-1 (no shift filter), OD-7 (preserve mode/station), OD-11 (reduced KPI cards, same formula). | frontend-engineer |
| IP-9 | frontend settings mini-app + registration (P9) | Create `frontend/src/production-achievement-settings/` (`index.html`/`main.ts`/`App.vue`/`style.css`/composable + `components/{PackageLfMappingPanel,WorkcenterMergeMappingPanel,DailyPlanPanel}.vue`; `editForbidden` fail-closed). Register the standalone route in all 7 locations (File-Level Plan). design.md → Settings mini-app / Route registration; interaction-design.md § Confirmed OD-5 (save note), OD-6 (no guard), OD-8 (full raw list via `GET /known-workcenter-groups`), OD-12 (constrained dropdowns). | frontend-engineer |

Companion (P3, frontend surface): edit `admin-dashboard/tabs/PermissionsTab.vue` UI copy so admins know `can_edit_targets` now also gates the 3 new tables — owner frontend-engineer.

## Source Artifact Pointers

| source | relevant pointer | used for |
|---|---|---|
| design.md | § Affected Components table (per-component file paths + nature-of-change) | authoritative what-to-touch map |
| design.md | § Key Decisions D1..D6 | load-bearing implementation constraints (join kinds, warm-cache trap, D3, 2-stage split, D6 locus) |
| design.md | § Migration / Rollback | manual-DDL precondition, parquet v2 self-heal, hard chart cutover |
| design.md | § Open Risks | backfilled non-goals + intentional-delta risks |
| interaction-design.md | § Confirmed (OD-1..OD-12) | frontend interaction constraints (cite by OD id, do not restate derivation) |
| interaction-design.md | § States / § Controls / § Presented Information | per-field provenance, mode discriminators, deleted controls |
| test-plan.md | § Acceptance Criteria → Test Mapping | authoritative AC→test source for `cdd-kit test select` |
| test-plan.md | § Test Files and Names (Backend / Frontend / E2E / Data-boundary / Resilience / Stress) | which files each slice writes/extends |
| test-plan.md | § Test Update Contract | 5 EXISTING tests to update (not only new ones) |
| test-plan.md | § Test Execution Ladder + § Stop Rules | phase floor + evidence discipline |
| ci-gates.md | § Required Gates + § Workflow | gate commands, the +5 `frontend-tests.yml` steps, `tsconfig.json` include gap |
| ci-gates.md | § Rollback Policy | Phase 11 rollout/rollback runbook |
| contracts (api/data/business) + docs/adr/0016 Extension | final wire/data/business rules | implement against; do not free-edit (see Constraints) |

## File-Level Plan

Consolidated manifest, grouped by owner. **Test files are not re-listed here** — see test-plan.md § Test Files and Names for the backend/frontend/e2e/data-boundary/resilience/stress test targets each engineer owns.

### Backend (backend-engineer)
| path | action | notes |
|---|---|---|
| `src/mes_dashboard/sql/production_achievement.sql` | EDIT | +PACKAGE_LF grain; D6 datetime widen (IP-1) |
| `src/mes_dashboard/sql/production_achievement_known_package_lf.sql` | CREATE | ~13-mo rolling `DISTINCT PACKAGE_LF`, hardcoded window (IP-3) |
| `src/mes_dashboard/workers/production_achievement_worker.py` | EDIT | post_aggregate/empty-schema +PACKAGE_LF; D6 closing chunk (IP-1) |
| `src/mes_dashboard/services/production_achievement_service.py` | EDIT | schema-version 1→2; shared namespace const; `workcenter_groups`→merged (IP-1) |
| `scripts/sql/production_achievement_tables.sql` | EDIT (append) | 3 `CREATE TABLE IF NOT EXISTS` + seeds (IP-2) |
| `src/mes_dashboard/services/production_achievement_package_lf_service.py` | CREATE | D1 (IP-3) |
| `src/mes_dashboard/services/production_achievement_workcenter_merge_service.py` | CREATE | D2 (IP-3) |
| `src/mes_dashboard/services/production_achievement_daily_plan_service.py` | CREATE | shift-less plans (IP-3) |
| `src/mes_dashboard/services/filter_cache.py` | EDIT | +`package_lf_values` cache key (IP-3) |
| `src/mes_dashboard/core/permissions.py` | EDIT (docstring only) | widened-scope note; no code/mechanism change (IP-3) |
| `src/mes_dashboard/routes/production_achievement_routes.py` | EDIT | 10 handlers + 5-inline-map `/report` (IP-4) |
| `src/mes_dashboard/services/production_achievement_daily_cache.py` | CREATE | warm-cache subclass + flag re-read (IP-5) |
| `src/mes_dashboard/core/spool_warmup_scheduler.py` | EDIT | +2 `_WARMUP_JOBS`; `production_history` exclusion untouched (IP-5) |

### Frontend (frontend-engineer)
| path | action | notes |
|---|---|---|
| `frontend/src/production-achievement/composables/useProductionAchievementDuckDB.ts` | EDIT | 2-stage rollup + compute*View (IP-6) |
| `frontend/src/production-achievement/composables/useProductionAchievement.ts` | EDIT | 4-mode state, resolveMonthPeriod, defaults (IP-7) |
| `frontend/src/production-achievement/App.vue` | EDIT | 4-mode rewrite, fake-single-select, 設定 button (IP-8) |
| `frontend/src/production-achievement/components/PlanAchievementStackedChart.vue` | CREATE | real-% stacked chart, y=100 markLine (IP-8) |
| `frontend/src/production-achievement/components/AchievementChart.vue` | DELETE | replaced, hard cutover no flag (IP-8) |
| `frontend/src/production-achievement/style.css` | EDIT | new chart classes under existing `.theme-production-achievement`; + css-inventory note (IP-8) |
| `frontend/src/production-achievement-settings/{index.html,main.ts,App.vue,style.css}` + `composables/` | CREATE | settings mini-app shell; new `.theme-production-achievement-settings` scope (IP-9) |
| `frontend/src/production-achievement-settings/components/PackageLfMappingPanel.vue` | CREATE | D1 exception rows + known-unmapped hint (IP-9) |
| `frontend/src/production-achievement-settings/components/WorkcenterMergeMappingPanel.vue` | CREATE | D2, OD-8 full raw list + include/exclude toggle (IP-9) |
| `frontend/src/production-achievement-settings/components/DailyPlanPanel.vue` | CREATE | OD-12 constrained dropdowns (IP-9) |
| `frontend/src/admin-dashboard/tabs/PermissionsTab.vue` | EDIT (copy only) | scope note for whitelist admins (IP-3 companion) |
| `frontend/tsconfig.json` | EDIT | add `src/production-achievement/**/*` + `src/production-achievement-settings/**/*` to `include` (ci-gates.md § Workflow type-check gap) |
| `frontend/vite.config.ts` | EDIT | `INPUT_MAP` entry — registration 1/7 (omission blocks boot) |
| `frontend/src/portal-shell/routeContracts.js` | EDIT | `ROUTE_CONTRACTS` — 2/7 |
| `frontend/src/portal-shell/navigationState.js` | EDIT | `STANDALONE_DRILLDOWN_ROUTES` (NOT `navigationManifest.js`) — 3/7 |
| `frontend/src/portal-shell/nativeModuleRegistry.js` | EDIT | loader/mount gate — 4/7 |
| `data/page_status.json` | EDIT | 5/7 |
| `docs/migration/full-modernization-architecture-blueprint/route_scope_matrix.json` | EDIT | 6/7 |
| `docs/migration/full-modernization-architecture-blueprint/asset_readiness_manifest.json` | EDIT | 7/7 |
| `contracts/css/css-inventory.md` + `contracts/css/css-contract.md` | EDIT | new `.theme-production-achievement-settings` row + changelog entry — same PR as the CSS files (see Contract Updates / Known Risks) |

### Contracts + ADR (ALREADY COMPLETE — do NOT re-derive; see specs/context/contracts-index.md)
| path | status | content |
|---|---|---|
| `contracts/api/api-contract.md`, `contracts/api/openapi.json`, `contracts/openapi.json`, `contracts/api/api-inventory.md` | DONE | 10 endpoint rows + `ProductionAchievementReportResponse` in-place redefinition + Compatibility Notes + both-path export |
| `contracts/data/data-shape-contract.md` | DONE | §3.28.1 / §3.28.4 / §3.30 / §3.31 / §3.32 / §3.33 / §3.34; `_PA_SPOOL_SCHEMA_VERSION` v2 |
| `contracts/business/business-rules.md` | DONE | PA-09 .. PA-15 |
| `docs/adr/0016-production-achievement-async-spool-seam-reduction.md` | DONE | **Extension** addendum (NOT superseded) |

## Contract Updates

- **API: ALREADY COMPLETE.** api-contract.md has all 10 endpoints (GET/PUT/DELETE `/package-lf-map`, GET/PUT/DELETE `/workcenter-merge-map`, GET/PUT `/daily-plans`, GET `/known-package-lf-values`, GET `/known-workcenter-groups`); `ProductionAchievementReportResponse` redefined in place (breaking, no deprecation window); openapi exported to both paths. **If an implementer must edit api-contract.md again, use `cdd-kit contract endpoint set` / `schema set` (hook-enforced) — never free-form Edit — then re-run `cdd-kit openapi export` for both output paths** (ci-gates.md § Workflow safety net; `openapi-sync-gate` re-fires on push).
- **CSS/UI: NOT a prerequisite — frontend-engineer deliverable in the same PR.** The report app's `.theme-production-achievement` inventory row already exists; the chart-class rewrite (IP-8) and the brand-new `.theme-production-achievement-settings` scope (IP-9) plus their `css-inventory.md` row and `css-contract.md` changelog entry must be authored WITH the CSS files (css-inventory § Synchronization Rule) and are gated by `npm run css:check` rule 6. Not yet present in `contracts/css/` as of this plan (see Known Risks).
- **Env: none.** Reuses `WARMUP_INTERVAL_SECONDS` / `WARMUP_SCHEDULER_ENABLED` / `QUERY_SPOOL_TTL_SECONDS` / `PRODUCTION_ACHIEVEMENT_USE_UNIFIED_JOB` (classification Tasks Not Applicable 2.3/4.3).
- **Data shape: ALREADY COMPLETE.** data-shape-contract.md §3.28.1 (+PACKAGE_LF column, updated grain), §3.28.4 (envelope 5 inline arrays), §3.30/§3.31/§3.32 (3 MySQL tables with D1-vs-D2 defaults), §3.33/§3.34 (inline map shapes).
- **Business logic: ALREADY COMPLETE.** business-rules.md PA-09..PA-15.
- **CI/CD: no `ci-gate-contract.md` change** (classification 2.6/4.4). `.github/workflows/frontend-tests.yml` already carries the +5 Playwright steps (ci-gates.md § Workflow).

## Test Execution Plan

test-plan.md is authoritative — its § Acceptance Criteria → Test Mapping drives `cdd-kit test select`, and § Test Files and Names lists every file/method. **Not duplicated here.** Implementation agents generate evidence with `cdd-kit test run`; the gate validates `test-evidence.yml`.

**Required phase floor** (test-plan.md § Test Execution Ladder): `collect`, `targeted`, `changed-area` (always) + `contract` (affected — 10 endpoints, schema-version pin 1→2, sample regeneration) + `full` (final/CI). Honor § Stop Rules (first-failure-only; no known/waived reclassification).

**By slice:**
- **backend-engineer:** test-plan.md § Test Files and Names → **Backend**, plus § Data-boundary, § Resilience, § Stress. Families unit / contract / integration / data-boundary / resilience.
- **frontend-engineer:** test-plan.md § Test Files and Names → **Frontend** and **E2E / Playwright**, plus the client-side rows of § Data-boundary. Families unit / e2e / monkey.

**Test Update Contract — 5 EXISTING tests must be UPDATED, not merely supplemented** (test-plan.md § Test Update Contract): `TestReportRoute::test_spool_hit_response_shape...` (2→5 inline arrays); `TestSpoolSchema::test_parquet_columns...` (4→5 cols); `TestSpoolSchema::test_schema_version_constant_pinned` (1→2); `test_warmup_jobs_total_count_after_duckdb_additions` (+2); `TestFilterOptionsRoute` `workcenter_groups` (→merged D2 list). Regression: `test_production_history_not_in_warmup_jobs` must STILL pass unchanged.

Trap-critical ACs called out below; all other ACs map via test-plan.md § Acceptance Criteria → Test Mapping (authoritative).

| acceptance criterion | test file / command | expected signal |
|---|---|---|
| AC-1 / AC-12 (D6) | tests/test_production_achievement_unified_job.py | 5-col parquet incl. PACKAGE_LF; closing chunk included exactly once, zero next-day leakage; regression asserts the **corrected total**, not just new-row presence |
| AC-10 (D3) | frontend/src/production-achievement/__tests__/useProductionAchievementDuckDB.test.ts; tests/property/test_production_achievement_aggregate_invariant.py | aggregate-then-divide ≠ mean-of-percentages on unequal-plan fixture |
| AC-6 (10 endpoints) | tests/contract/test_production_achievement_contract.py | 10 endpoint rows present; 5-inline-map envelope; schema-version bump recorded in Compatibility Notes |
| AC-2..AC-5, AC-7..AC-9, AC-11, AC-13 | test-plan.md § Acceptance Criteria → Test Mapping | per that table (authoritative for `cdd-kit test select`) |

## Constraints (load-bearing — do not violate)

- **D1 vs D2 are OPPOSITE join kinds on purpose.** `package_lf_map` = LEFT JOIN + `COALESCE(merged, raw, '(未分類)')` (absence → falls back to self). `workcenter_merge_map` = INNER JOIN (absence → excluded). Never "normalize" them to the same kind — it inverts one table's meaning. Every test touching either must assert "not the other join kind." design.md § Key Decisions D1/D2; test-plan.md § Notes.
- **Redis-orphan-key trap (warm-cache).** Warm-cache MUST invoke the `_WarmupProductionAchievementJob` subclass whose `progress_report()` is a no-op — a bare `ProductionAchievementJob(...).run()` bypasses `enqueue_query_job` and leaks one un-expiring Redis `HSET` key per cycle forever. design.md § Key Decisions (warm-cache) / PA-14.
- **Kill-switch independence.** The warm-cache module must re-read `PRODUCTION_ACHIEVEMENT_USE_UNIFIED_JOB` itself BEFORE the lazy worker import, or a disabled feature still imports the worker and hits Oracle. design.md § Key Decisions; approved plan Phase 5.
- **D3 aggregate-then-divide.** Cumulative trend rate = `SUM(actual)/SUM(plan)` computed BEFORE dividing — never a mean of per-group percentages (silently wrong only when plan magnitudes differ). design.md § Key Decisions D3 / PA-13; test-plan.md § Notes.
- **Two DuckDB stages stay separate.** The merge map keys on the resolved **raw workcenter_group** (produced by Stage 1 `pa_rollup_raw`), not SPECNAME — it cannot be joined against the SPECNAME-grain spool, so the stages cannot be fused. design.md § Key Decisions (two stages).
- **D6 is fetch-completeness only.** Widen the bind + append one closing chunk; do NOT alter the `post_aggregate` GROUP BY locus or the client-vs-server rollup boundary. Regression must assert the corrected total. design.md § Key Decisions D6 / PA-15.
- **Interaction constraints (interaction-design.md § Confirmed):** OD-1 no shift filter (D/N as columns only); OD-3 full auto-run in all 4 modes (no 查詢 button); OD-4 ignore mode/station change while a 202 poll is in flight; OD-7 preserve last mode+station across the settings round-trip (route params / shared store / sessionStorage — impl choice); OD-11 KPI cards reuse the PA-12/13 formula, never a naive re-aggregate; OD-12 DailyPlanPanel keys are constrained dropdowns (no free-text); OD-8 WorkcenterMergeMappingPanel enumerates the full raw universe via `GET /known-workcenter-groups`; OD-5 show a "changes apply on next refresh" note after save; OD-6 no unsaved-edit navigation guard.
- **`MultiSelect.vue` is additive-only** (16 consumers, CLAUDE.md). Reuse `App.vue`'s own fake-single-select idiom `:model-value="x ? [x] : []"`; do not modify the shared component. interaction-design.md § Consistency Commitments.
- **Standalone route, no drawer.** Register `STANDALONE_DRILLDOWN_ROUTES` in `navigationState.js`, NOT `navigationManifest.js`; `INPUT_MAP` omission blocks boot, `ROUTE_CONTRACTS` omission only warns. design.md § Key Decisions D4; CLAUDE.md modernization policy.
- **Chart is a hard cutover, no flag** — delete `AchievementChart.vue`; colors via `resolveCssVar()` CSS custom properties, not inline `rgb()`. design.md § Migration/Rollback; AC-9.
- **api-contract.md edits go through the hook-based CLI** (`cdd-kit contract endpoint set` / `schema set`), never free-form Edit; then `cdd-kit openapi export` both paths.

## Sequencing & Dependencies

- **Backend before end-to-end frontend.** Backend IP-1..IP-5 (specifically the widened v2 spool grain from IP-1 and the 5-inline-map `/report` from IP-4) must land before frontend IP-6..IP-9 can be exercised end-to-end (DuckDB rollup + Playwright + dual-tier parity consume the widened parquet + inline maps).
- **Parallelization IS allowed** since the api/data/business contracts are already final: frontend IP-6..IP-9 scaffolding + vitest/unit layers can proceed in parallel against the fixed contracts (data-shape §3.28.1/§3.28.4/§3.33/§3.34 + api rows) using mocked fixtures — no live backend needed for unit tests. backend-engineer and frontend-engineer may run as **separate agent invocations**; only cross-stack E2E/Playwright and the dual-tier parity tests require both stacks landed.
- **Within backend:** IP-1 (namespace const + schema-version) is referenced by IP-5 (warm-cache imports the namespace/worker); IP-2 (DDL) precedes IP-3 (services read the tables); keep IP-1..IP-5 in one PR so the `get_filter_options().workcenter_groups`→merged redefinition (IP-1) and the merge service (IP-3) ship atomically.
- **Within frontend:** IP-6 (rollup) → IP-7 (composable calls `compute*View`) → IP-8 (App renders); IP-9 (settings) needs IP-4's endpoints for live data but its UI/unit layer is independent.
- **Concurrent-agent evidence race** (CLAUDE.md): if backend + frontend both run `cdd-kit test run`, they race on `test-evidence.yml` — the last agent re-runs combining both stacks.
- **Rollout order** (Phase 11, ci-gates.md § Rollback Policy): apply the 3 MySQL tables BEFORE the backend deploy; parquet v2 self-heals by key mismatch (optional `rm` fast-forward); on rollback revert the `vite.config.ts` `INPUT_MAP` entry first or atomically (a dangling entry blocks boot).

## Handoff Constraints

- Implementation agents must not infer missing requirements from chat history.
- Do not re-copy full design, test strategy, CI policy, or contract prose into this plan; follow the source pointers above.
- If this plan omits a required file, behavior, contract, or test, stop and report `blocked`.
- Keep implementation within the file-level plan unless a Context Expansion Request is approved (context-manifest.md § Allowed Paths is the read/write boundary per agent).

## Known Risks

- **CSS governance rows not yet landed.** No `.theme-production-achievement-settings` row exists in `contracts/css/css-inventory.md` and there is no production-achievement-overhaul entry in `contracts/css/css-contract.md` (verified against the working tree as of this plan). This is expected — new-CSS-file governance rows land with the frontend PR per the css-inventory § Synchronization Rule — but frontend-engineer MUST add them alongside IP-8/IP-9 or `npm run css:check` rule 6 and the css-governance gate fail.
- **`frontend/tsconfig.json` `include` gap** (ci-gates.md § Workflow): the type-check gate currently has ZERO coverage of `production-achievement`'s `.ts` composables; frontend-engineer must add both new app globs. Informational gate, but a real coverage hole for IP-6/IP-7.
- **`tests/acceptance/acceptance.yml` is a human-authored placeholder** (test-plan.md § Notes) — the acceptance-driver is non-authoritative until filled; flag to qa-reviewer if unfilled at gate time.
- **`.cdd/code-map.yml` is stale** (generated 2026-07-13, shows modified in git, predates the not-yet-created `production-achievement-settings/` directory). design.md grounded all affected-component ranges by direct source reads instead; engineers should do the same for new files. Ask the user to run `cdd-kit code-map` after implementation. Not blocking.
- **D6 intentionally changes historical N-shift numbers** at the closing seam only — the regression fixture must assert the corrected total so the intended-only delta is durable (design.md § Open Risks).
- **Config-store outage reads as an empty report** (OD-9 accepted, no read-time discriminator) — operational, not a code defect; confirm acceptable at QA sign-off (design.md § Open Risks).
