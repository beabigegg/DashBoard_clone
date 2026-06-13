# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

MES Dashboard 是一個供工廠工程師自助查詢 MES 生產數據的 Web 報表平台（Flask + Vue3/Vite），支援 WIP、Hold、良率、設備、材料追溯等 16 個報表頁面，並整合 AI 自然語言查詢、異常偵測排程與系統管理儀表板。

## Dev commands

```bash
# conda env
conda activate mes-dashboard          # 啟動環境
conda run -n mes-dashboard <cmd>      # 單次執行

# Backend
flask run                             # 開發 server（需先 activate）
gunicorn -c gunicorn.conf.py 'src.mes_dashboard.app:create_app()'  # production

# Frontend
cd frontend && npm run dev            # Vite dev server（含 HMR）
cd frontend && npm run build          # 生產打包（含 HTML 複製腳本）

# Test
pytest                                # 後端測試（在 conda env 內）
cd frontend && npm run test           # Vitest 前端單元測試
cd frontend && npm run css:check      # CSS 治理合規檢查

# Lint / Type
ruff check .                          # Python linter
cd frontend && npm run type-check     # TypeScript 型別檢查（vue-tsc --noEmit）

# CDD
cdd-kit validate                      # 驗證所有 contracts
cdd-kit detect-stack                  # 偵測專案技術棧
```

## Architecture

```
src/mes_dashboard/
  app.py                  # Flask app factory；Blueprint 掛載；runtime-contract 驗證
  routes/                 # 20+ Blueprint 模組（每個功能模組一個檔案）
  services/               # 業務邏輯層（routes 呼叫 services，禁止直接 DB）
  core/
    response.py           # success_response / error_response 統一回應輔助函式
    config.py             # 環境設定（從 .env 載入）
  workers/                # RQ async job workers（reject/yield/trace/material-trace）

frontend/
  src/
    portal-shell/         # 主 SPA shell（路由、導覽、權限守衛）
    <feature>/            # 每個報表功能獨立 Vue 應用（wip/hold/resource 等）
    shared-ui/            # 共用元件（DataTable、SummaryCard、LoadingOverlay 等）
    styles/tailwind.css   # 全域 base/components 層（唯一允許寫 @layer 的地方）
  tailwind.config.js      # Design token 唯一真實來源

外部依賴：
  Oracle DB               # MES 主資料來源（oracledb/cx_Oracle）
  Redis                   # 快取層 + RQ job queue
  DuckDB                  # spool 臨時結果集（DuckDB-WASM 前端視圖）
  LDAP/AD                 # 身分驗證（透過 LDAP API）
  SQLite                  # login session 與 admin log 本地儲存
```

**Entry points:** `src/mes_dashboard/app.py:create_app()` → Flask; `frontend/src/portal-shell/main.js` → SPA root.

---

This repository follows the Contract-Driven Delivery workflow.

- `contracts/` is the single source of truth for what the system should do.
- `tests/` proves the contracts hold.
- `specs/changes/<id>/` records why decisions were made (passive archive — read only when investigating history).
- To start any non-trivial change, use `/cdd-new <description>` in Claude Code.

## CDD Kit Commands

| command | when to use |
|---|---|
| `/cdd-new <description>` | start a new tracked change (scaffolds all artifacts, runs full agent flow) |
| `/cdd-resume <id>` | continue an in-progress change after a session break |
| `/cdd-close <id>` | close a completed change: promote learnings, archive |
| `cdd-kit list` | show all active changes and their status |
| `cdd-kit gate <id>` | verify a change is gate-ready (run before PR) |
| `cdd-kit gate <id> --strict` | full gate with pending-task enforcement (pre-commit default) |
| `cdd-kit archive <id>` | physically move a completed change to `specs/archive/<year>/` |
| `cdd-kit abandon <id> --reason <text>` | mark a change as abandoned; preserves directory for git history |
| `cdd-kit validate` | run all contract validators |
| `cdd-kit detect-stack` | detect the project tech stack |

- **Keep local cdd-kit in sync with CI**: CI workflow runs `npm install -g contract-driven-delivery` without a version pin, so it always installs the latest. New releases may add required artifacts (e.g., `implementation-plan.md` in 2.0.18). After any CI `spec traceability` failure, upgrade locally with `npm install -g contract-driven-delivery` and re-run `cdd-kit validate` to reproduce. Evidence: `hold-history-detail-flat-table` / `reject-material-flat-table` — local 2.0.17 passed; CI 2.0.18 failed on missing `implementation-plan.md`.
- **`ci-gates.md` must contain literal section headers**: `cdd-kit gate` validates `ci-gates.md` by checking for the literal strings "workflow", "promotion policy", and "rollback policy". Always include `## CI/CD Workflow`, `## Promotion Policy`, and `## Rollback Policy` sections or the gate will fail regardless of content completeness. Evidence: `migrate-query-tool-ts` — gate failed on first run; passed after adding these three sections.
- **Resolving section-6 tasks before `cdd-kit gate --strict`**: Tasks 6.2 (PR required gates) and 6.3 (Informational gates) may be marked `done` before CI confirmation when all local Tier 1 gate commands pass and CI runs the identical commands. Task 6.4 (nightly/weekly/manual gates) should be marked `skipped` when no such gates are defined for the change. Leaving any section-6 task in `pending` blocks the pre-commit hook. Evidence: `migrate-material-trace-ts` — pre-commit hook rejected commit with 6.2/6.3/6.4 pending; resolved by updating tasks.yml before commit.
- **`contracts/CHANGELOG.md` is the only location checked by `cdd-kit validate --versions`**: The validator scans `contracts/CHANGELOG.md` for entries matching `## [<type> <version>]` (e.g., `## [api 1.12.0]`). CHANGELOG entries written inside individual contract files (`api-contract.md`, `business-rules.md`, etc.) are never checked and will cause a gate failure. Always write version entries to `contracts/CHANGELOG.md`, never to the individual files. Evidence: `ai-pipeline-upgrade` — backend-engineer embedded entries in individual files; gate failed until entries were moved to `contracts/CHANGELOG.md`.

## TypeScript Notes

- **TypeScript migration is complete** across all feature apps. All `core/`, `shared-composables/`, `shared-ui/`, shared layers, and feature apps use TypeScript. `portal-shell/` non-entry modules remain JS intentionally (no type coverage needed for the thin shell layer). `workers/duckdb-worker.js` and `main.js` entry points are intentionally JS — `index.html` references `./main.js` and Vite resolves `main.ts` at build time; do not rename these.
- **Node ≥22.6 is required**: `environment.yml` pins `nodejs>=22.6` for `node --experimental-strip-types` support in parity tests. Do not loosen this constraint.
- **SFC-paired tests**: `frontend/vitest.config.js` `include` already lists `src/**/*.test.ts`. Tests placed next to SFCs (e.g., `src/shared-ui/components/__tests__/*.test.ts`) are covered by this glob — no config change needed when adding new SFC-paired tests.
- **echarts callback parameters** (`params` in formatter/tooltip) lack precise types — annotate with `// TODO: type echarts callback` rather than `any`.

## Vue-ECharts Notes

- **`vue-echarts` click events must be bound via `@click` on `<VChart>`, not imperative `echartsInstance.on('click')`**: The `vue-echarts` wrapper forwards all native ECharts events as Vue events carrying `params.name`/`params.data`. `@click` in the template requires no `onMounted`/`onUnmounted` cleanup — the wrapper disposes the instance on unmount, eliminating leak risk. Imperative `chart.on(...)` and ECharts `select` mode are rejected alternatives: the former requires manual lifecycle boilerplate the wrapper already handles; the latter couples visual state to ECharts internals rather than the composable. Evidence: `resource-status-cross-filter` — design.md D4.

## Shared UI Component Notes

- **`frontend/src/shared-ui/components/MultiSelect.vue` is shared by 12 feature apps** (hold-overview, job-query, mid-section-defect, production-history, query-tool, reject-history, resource-history, resource-shared, resource-status, wip-detail, wip-overview, yield-alert-center). Any change to its emit/prop surface must be **additive** (optional events/props that unmounted consumers ignore). Before modifying any `frontend/src/shared-ui/components/` file, grep all consumer apps for usage. Evidence: `fix-prod-history-multiselect-filter` — added `dropdown-close` as optional event so untouched consumers were no-ops.
- **Snapshot-diff filter composables must re-sync after server-driven prune**: any composable that uses a private `_lastCommitted[field]` snapshot to skip no-op refresh must refresh that snapshot from `selection[field]` after every successful `fetchFilterOptions`, because server-side prune mutates `selection` without user action. Skipping this step makes the next dropdown close emit a spurious cross-filter request. Pattern lives in `frontend/src/production-history/composables/useFirstTierFilters.ts`. Evidence: `fix-prod-history-multiselect-filter` — `_pruneSelection` interaction with `commitSelection` diff.

## Frontend Date Formatting Notes

- **Oracle DATE columns serialised as midnight UTC (`T00:00:00`) must not be passed to `new Date()` in a non-UTC locale.** Inspect the raw H/M/S digits via regex before any `Date()` call; if all three are `'00'`, extract year/month/day directly from the string — this avoids a ±8 h TZ shift (e.g., UTC+8 turns midnight into 08:00:00). Only call `new Date()` when the raw time is non-zero. Pattern lives in `frontend/src/material-consumption/components/DetailTable.vue::formatTxnDate`. Applies to every frontend formatter for Oracle DATE columns across all feature apps. Evidence: `material-part-consumption` — txn_date displayed 08:00:00 for all records until the raw-string check was added.

## Accessibility Notes

- **WAI-ARIA combobox close paths must return focus to the trigger**: when adding Escape / outside-click / programmatic close to any popup-style component (MultiSelect, dropdown, dialog), the close handler must `nextTick(() => triggerEl.focus())` or keyboard users lose focus context. Pattern lives in `frontend/src/shared-ui/components/MultiSelect.vue::closeDropdown()`. Evidence: `fix-prod-history-multiselect-filter` — ui-ux-reviewer flagged missing focus return after adding Escape support; fixed inline before merge.

## Cache Architecture Notes

- **Cache namespace must match**: When adding a startup pre-warm for any service, verify the pre-warm writes to the **same** namespace/key pattern that user queries actually read from. Writing to a separate prefix (e.g., `resource_history_prewarm`) while user queries read from `resource_dataset`/`resource_oee` provides zero cache benefit — the mismatch is silent and only discoverable by comparing logs across the two code paths. Always trace the full read path of a live query before implementing a pre-warm. Evidence: `resource-history-perf` — original prewarm used `cache_prefix="resource_history_prewarm"` via `batch_query_engine.execute_plan` while `resource_dataset_cache.py` wrote to `resource_dataset`/`resource_oee` via `register_spool_file()`.
- **Multi-worker startup lock**: Any gunicorn startup background task that loads data from Oracle must use a file-based exclusive lock (`os.O_CREAT | os.O_EXCL` on a `.loading` sentinel file) to prevent all workers from executing the same Oracle query simultaneously. Workers that lose the lock should poll `_try_reuse_existing()` in a loop (5 s intervals, 90 s timeout) until the winner finishes. The pattern is implemented in `resource_history_duckdb_cache.py::_try_lock()` / `_release_lock()`. Evidence: `resource-history-perf` — without the lock, two gunicorn workers each ran the full 30 s Oracle prewarm concurrently.
- **Spool schema breaking changes require post-deploy parquet cleanup**: When any spool-based service rewrites its parquet column schema (rename/add/remove), existing files at `tmp/query_spool/<service>/*.parquet` become incompatible and must be cleared post-deploy or readers will hit schema-mismatch errors at the next `pd.read_parquet` / DuckDB `read_parquet` call. Add `rm tmp/query_spool/<service>/*.parquet` to the deploy runbook for any schema-breaking change, and document it in the change's `ci-gates.md` §Rollback. Evidence: `prod-history-detail-raw-rows` removed aggregated aliases TRACKIN_TS/TRACKOUT_TS/TRACKIN_QTY/TRACKOUT_QTY and added PJ_FUNCTION.
- **Query-tool has no persistent spool — skip parquet cleanup in rollbacks**: The query-tool executes Oracle SQL on-demand per request and does not persist DuckDB parquet files (unlike production-history or resource-history). Do not add `rm tmp/query_spool/query_tool/*.parquet` to any deploy or rollback runbook for query-tool changes. Evidence: `query-tool-partial-trackout` — `ci-gates.md §Rollback Policy` confirmed no parquet cleanup required even after adding `partial_count` to aggregated output.
- **hold-history spool supports live parquets from before a schema change via `DESCRIBE`-based column detection**: `hold_history_sql_runtime._query_list` uses `DESCRIBE hold_src` at runtime to detect whether a new column (e.g., `package`) exists in an existing parquet spool; it falls back to `NULL AS <col>` for old files. This avoids a `BinderException` without requiring a forced purge. Apply this pattern when adding a nullable column to any hold-history SQL backed by a persistent spool, rather than requiring a deploy-time `rm`. Pattern lives at `hold_history_sql_runtime.py:477-598`. Evidence: `add-package-detail-tables`.
- **Backend SQL-to-API rename layer isolates frontend from Oracle column renames**: report-module backends maintain a SQL `AS` alias layer (and pandas fallback rename dict) at the API boundary that maps raw Oracle/spool column names to stable snake_case JSON keys. Example: `production_history_sql_runtime.py:184-205, 242-251` maps `MFGORDERNAME → work_order`, `TRACKINTIMESTAMP → trackin_time`, etc. When renaming Oracle source columns or spool parquet columns, audit THIS layer first — if it already preserves the API JSON key, no frontend audit or contract change is needed. Evidence: `prod-history-detail-raw-rows` renamed 7 Oracle columns; frontend alias audit returned zero hits because the rename layer absorbed the change.
- **SyncWorker destructive migration guard**: Any `SyncWorker` migration that issues `TRUNCATE` or `DELETE FROM` on a table that may contain live data must check `SELECT COUNT(*) ... LIMIT 1` first and skip the destructive statement when `row_count > 0`. The migration-version `REPLACE` must still execute even when the destructive step is skipped, so the guard does not re-trigger on every restart. A startup race (two gunicorn workers both passing the COUNT before either writes the version row) is acceptable because the version-meta `REPLACE` serializes subsequent runs; document this in a code comment. Pattern: `SyncWorker._run_login_session_migration()`. Evidence: `fix-admin-dashboard` — without the guard, a redeploy truncated live dashboard_login_sessions on first startup.
- **`/api/resource/status/options` builds its own inline dict and does NOT call `query_resource_filter_options()`**: These two filter-option surfaces are maintained independently. When adding a new filter field to the resource-status page, add it to BOTH `query_resource_filter_options()` in `resource_service.py` AND the inline dict in the `/status/options` route handler in `resource_routes.py`. Adding only to the service causes a silent omission in the `/status/options` response. Evidence: `resource-status-package-group` — `package_groups` had to be patched into the route's inline dict separately after the service was updated.
- **Oracle CHAR column lookup dicts require `strip()` on both dict-build and per-record lookup**: When building an in-process lookup dict keyed by an Oracle `CHAR` column, apply `str(value).strip()` at dict-build time AND again at each per-record lookup call. Applying strip only at build time leaves lookups silently returning `None` when a live record's `CHAR` value has trailing spaces (CHAR pads to fixed width). Pattern: `resource_cache.py::_load_package_group_lookup` (build) and `get_package_group_name` (lookup). Evidence: `resource-status-package-group` — `test_package_group_lookup_char_trailing_space` confirms both sides required.
- **Type-A spool frontend key mismatch produces a silent empty table, not an error**: when wiring a frontend composable to a `/view`, `/equipment-detail`, or `/event-detail`-style endpoint, verify the exact JSON wrapper key the backend returns (e.g., `{equipment_detail: [...]}` not a bare array; `events` not `rows`) before writing the composable. A wrong key resolves to `undefined`, which the composable silently treats as an empty list. Read the route handler's `success_response(...)` call directly — do not infer the key from the service function name. Evidence: `downtime-analysis-page` — fixed in commit `1931d26`.
- **Canonical spool services use two-phase key resolution in `try_compute_*_from_canonical_spool`**: Phase 1 (superset) — if `[req_start, req_end] ⊆ [today-89d, today]` AND the warmup parquet exists, reuse the warmup key and inject `WHERE "DATA_DATE" >= … AND "DATA_DATE" <= …` into the base temp view and `WHERE "SHIFT_DATE" >= … AND "SHIFT_DATE" <= …` into the OEE temp view (`DATA_DATE` for base spool, `SHIFT_DATE` for OEE — do not apply uniformly). Phase 2 (exact-match fallback) — look up `make_canonical_base_query_id(start_date, end_date)` directly; only this path hits Oracle on a miss. Any service that adds a canonical spool must implement both phases or queries within the warmup window will silently fall through to Oracle on every cache miss. Evidence: `resource-history-cache-fix` — `resource_history_sql_runtime.py:707-750`; `TestWarmupSupersetLookup`.

## BatchQueryEngine Architecture Notes

- **`ROW_NUMBER()` CTE chunking is incompatible with services that require the full assembled dataset for post-query reduction.** Any service whose logic includes cross-row aggregations (group-by across the entire result set, windowed functions, temporal-overlap cross-product joins) cannot use `USE_ROW_COUNT_CHUNKING` — splitting at chunk seams silently corrupts the reduced output with no error and no test failure. Such services must use whole-dataset chunking (`execute_plan` with a single chunk covering the full date range) and apply the reduction as a post-merge stage. `downtime_analysis_service` is the canonical example (permanently excluded per ADR-0003; `_merge_cross_shift_events` and `_bridge_jobid` both require the full dataset). When adding a new service, classify its post-query reductions before deciding on chunking strategy. Evidence: `docs/adr/0003-downtime-rowcount-chunking-exclusion.md`.

## Spool Download Route Notes

- **`spool_routes.py:_ALLOWED_NAMESPACES` is a security whitelist — every new spool-using feature must add its namespace there AND to `tests/test_spool_routes.py`**: `GET /api/spool/<namespace>/…` returns HTTP 400 for any namespace not in `_ALLOWED_NAMESPACES` (path-traversal guard). Omitting a new namespace causes all parquet downloads for that feature to fail with 400 after deploy, even though data was written successfully. Add the namespace to the `frozenset` in `spool_routes.py` AND to the `@pytest.mark.parametrize("ns", […])` list in `tests/test_spool_routes.py` in the same PR as the spool write. Evidence: `downtime-browser-duckdb` — `downtime_analysis_base_events` and `downtime_analysis_job_bridge` omitted from whitelist; browser received HTTP 400 on every parquet download post-deploy despite valid spool files on disk.

## Portal-Shell CSS Architecture Notes

- **All feature CSS must be scoped under `.theme-<name>`**: Portal-shell (`nativeModuleRegistry.js`) loads each feature's CSS bundle once via dynamic `import()` and caches it permanently in `<head>`. Unscoped rules (e.g., `.card`, `.pareto-chart-wrap`) from any bundle bleed into every subsequent page because no bundle is ever unloaded. Always prefix every rule with the feature's root class (e.g., `.theme-hold-history .card`). Specificity 0-2-0 beats unscoped 0-1-0 regardless of injection order. **Enforced by `npm run css:check` Rule 6** (`frontend/scripts/css-governance-check.js`); CI fails the build on any unscoped top-level rule in a feature `style.css`. Evidence: `hold-history-detail-flat-table` — unscoped `.pareto-chart-wrap { height: 360px }` in hold-history CSS overrode hold-overview's chart height on page switch; the lint rule was added after a follow-up audit found 290+ unscoped rules across 7 features (`resource-status`, `qc-gate`, `resource-history`, `query-tool`, `mid-section-defect`, `job-query`, `yield-alert-center`).
- **CSS source fixes require `npm run build` to take effect**: The app serves from `src/mes_dashboard/static/dist/` (Flask static), not the Vite dev server. After editing any `frontend/src/*/style.css`, run `cd frontend && npm run build`. New builds generate hashed filenames (e.g., `style5.css`) rather than named files (e.g., `hold-history.css`) — stale named files in `dist/` are orphaned and not referenced by the new bundles.
- **`<Teleport to="body">` moves the DOM node outside the feature root, breaking all `.theme-<feature> .component` descendant CSS selectors**: Wrap the teleported content in a thin `<div class="theme-<feature>">` — this element carries no styling, but provides the required ancestor scope. Do NOT put both `theme-<feature>` and the component class on the same element (`.theme-x.component` combined selector does not match the authored `.theme-x .component` rules). Contract: `contracts/css/css-contract.md` rule 4.4. Evidence: `resource-status-package-group` — `FloatingTooltip.vue` lot tooltip rendered unstyled until wrapper was added.
- **`resource-shared/styles.css` `:is()` groups must include every portal-shell page theme**: the stylesheet uses `:is(.theme-X, …)` selectors (95 occurrences) to batch-apply header, filter, and section-card styles. Adding a new page without inserting its theme class into every group causes those styles to silently not apply — `npm run css:check` Rule 6 does not catch this. Use `sed` batch replacement on the new theme name when adding any page. Contract: `contracts/css/css-contract.md` rule 4.5. Evidence: `downtime-analysis-page` — batch-patched via sed in commit `1931d26`.

## Modernization Policy Artifact Notes

- **Page additions/removals require updating two JSON files in `docs/migration/full-modernization-architecture-blueprint/`**: `asset_readiness_manifest.json` (maps route → required dist asset; read by `app.py:_validate_in_scope_asset_readiness()` at startup via `lru_cache` — stale entries crash gunicorn with `RuntimeError`) and `route_scope_matrix.json` (drives in-scope route classification). Neither file is reached by grepping Flask routes or Vite config alone. Add both to `## Allowed Paths` whenever a change adds or removes a page. Evidence: `remove-unused-pages` — `/tables` removal not reflected here caused gunicorn startup crash post-deploy.
- **`data/page_status.json` is a runtime-persisted registry that is never modified by code deletion**: `page_registry.py:_load()` reads it at runtime to build navigation drawers; a removed page's entry will continue rendering in the sidebar and emit "缺少 route contract: <route>" until the entry is manually removed from the `pages` array. Explicitly include `data/page_status.json` in `## Allowed Paths` and delete the page's object from the array as part of any page removal change. Evidence: `remove-unused-pages` — `/tables` entry persisted in sidebar after all code was deleted.
- **When changing a page's `drawer_id` in `data/page_status.json`, also update its corresponding assertion in `tests/test_modernization_policy_hardening.py`.** Each page registration test hardcodes the expected `drawer_id`; the mismatch will not surface at dev time but will fail CI. The test method is named by convention `test_page_status_contains_<page>_in_<drawer>` — if the drawer changes, rename the method and update the assert. Evidence: `material-part-consumption` — CI failed after page moved from `drawer-2` to `drawer` without updating the test.

## Downtime Analysis Service Architecture Notes

- **`downtime_analysis_service` uses function-body imports for `load_downtime_events` at all four call sites** (`apply_view`, `_build_equipment_detail_page`, and two others at `lines 1164, 1210`) — the name never exists in the service module's namespace. Patching `mes_dashboard.services.downtime_analysis_service.load_downtime_events` silently has no effect. Always patch at the definition site: `mes_dashboard.services.downtime_analysis_cache.load_downtime_events`. Evidence: `downtime-analysis-page-redesign` — backend-engineer corrected this during TDD; verified at four call sites.

## WIP Service Architecture Notes

- `_get_wip_search_index` (in `wip_service.py`) builds the in-process filter-options search index. It has two paths: (a) incremental sync from `previous` cache, (b) full-rebuild fallback (`if index_payload is None:` block) that calls `_materialize_search_payload`. **Any new field added to the filter-options response** (e.g., a new dropdown category) must be appended to the `index_payload` dict in BOTH paths: after the `_materialize_search_payload` call in the full-rebuild branch, AND carried forward via `previous.get(...)` in the incremental branch. Adding only to a helper function that is never called from `_get_wip_search_index` will silently omit the field on every service restart. Evidence: `wip-hold-drilldown-filters` (workflows/bops/pjFunctions).

## Admin Service Test Isolation Notes

- **`rq_monitor_service` imports `get_redis_client` at module level (`from x import y`)**: patching `mes_dashboard.core.redis_client.get_redis_client` at function level does NOT intercept calls made through `rq_monitor_service`. Any performance-detail test that runs after a test with `REDIS_ENABLED=True` must additionally stub `mes_dashboard.services.rq_monitor_service.get_rq_monitor_summary` (patch at the service boundary). Real `rq.Worker` objects from a live Redis context contain non-serializable values that corrupt test output. Evidence: `fix-admin-dashboard` — `TestPerfDetailRedisAdditiveKeys` required this stub after `TestApiLogsSqliteIncludesSynced` left Redis enabled.

## QueryBuilder Architecture Notes

- **Two independent IN-list conditions require counter-forwarding**: When a single service function needs two separate `QueryBuilder` instances (e.g., `EQUIPMENTID IN (...)` and `WORKCENTER_GROUP IN (...)`), forward `wg_builder._param_counter = builder._param_counter` before calling `add_in_condition`, then `builder._param_counter = wg_builder._param_counter` and `builder.params.update(wg_builder.params)` after. Without this, both builders start at `p0` and Oracle raises `ORA-01006: bind variable does not exist` at runtime. Evidence: `src/mes_dashboard/services/query_tool_service.py:2558-2567` (`equipment-rejects-by-lots`).
- **`_PARTIAL_NONKEY_COLS_LOT` must include every non-key column returned by lot-history/equipment-lots SQL**: `query_tool_sql_runtime.py` uses this frozenset in the QT-06 strict guard. Any new column added to `lot_history.sql` or `equipment_lots.sql` must also be added to `_PARTIAL_NONKEY_COLS_LOT`; omitting it causes the guard to silently collapse rows with divergent values for that column (data corruption, not an error). Add the column to `_PARTIAL_NONKEY_COLS_LOT` atomically with the SQL change. Pin this with a membership test (pattern: `tests/test_query_tool_sql_runtime.py::TestPartialNonkeyColsLotContainsProductlinename`). Evidence: `add-package-detail-tables` — omitting `PRODUCTLINENAME` would have silently merged rows with different package values.

## SQL Architecture Notes

- **CTE SQL changes require updates in both the CTE SELECT and the outer SELECT**: When a SQL file uses a named CTE (e.g., `ranked`) that feeds an outer final SELECT, any new column must appear in BOTH the CTE's SELECT list AND the outer SELECT. Adding only to the outer SELECT causes a "column not found" error; adding only to the CTE silently drops the column before the outer SELECT reads it. Evidence: `add-package-detail-tables` — `hold_history/list.sql`, `lot_history.sql`, and `equipment_lots.sql` all required two-location edits (CTE + outer SELECT).
- **SQL-to-frontend column gap: SQL returning a column the frontend never renders is invisible to backend-only audits**: When auditing which columns a table surface is missing, cross-check SQL `SELECT` output against frontend template rendering — not just the backend route response. A column already present in SQL but absent from the Vue template produces no error and passes all backend tests. Audits that stop at the route response layer will miss this class of gap. Evidence: `add-package-detail-tables` — `equipment_lot_rejects.sql:52` already returned `PRODUCTLINENAME`; only the frontend template was missing the column.

## MES Domain Semantics Notes

- **`LOTWIPHISTORY.TRACKINQTY` is remaining-qty-per-partial, not original load.** Same upload session shares one `TRACKINTIMESTAMP` but has decrementing `TRACKINQTY` across partials (partial N+1 = partial N TRACKINQTY − partial N TRACKOUTQTY). To identify one session use only `TRACKINTIMESTAMP` as the group key; original load = `MAX(TRACKINQTY)` over the group; trackout = `SUM(TRACKOUTQTY)`; loss = `MAX(TRACKINQTY) − SUM(TRACKOUTQTY)`. Contract: `contracts/business/business-rules.md` PH-06. Evidence: lot `GA26041607-A00-005` (TRACKINQTY 99424 → 26624 = 99424 − 72800) — `prod-history-detail-partial-merge` initially used a 5-tuple key including TRACKINQTY and silently failed to merge any real partial-trackout on production data.
- **Fixture discipline for partial-trackout tests**: always include at least one fixture where partials of the same `TRACKINTIMESTAMP` have *different* `TRACKINQTY` values (use real arithmetic: TRACKINQTY[N+1] = TRACKINQTY[N] − TRACKOUTQTY[N]). A fixture with uniform `TRACKINQTY` across partials cannot distinguish a 4-key from a 5-key aggregation design — both pass. Evidence: `tests/test_production_history_sql_runtime.py::test_partial_merge_same_trackin_time_different_trackin_qty`.

## Test Coverage Discipline

These rules exist because we shipped a class of "silent drop" bugs (route ignored a filter param; snapshot path bypassed a filter; cross-filter dropdown didn't narrow) where the bug shipped through CI green because the tests asserted *what the code did*, not *what the code should do*. See `e002c4c` for the systemic remediation.

- **Do NOT use `mock.assert_called_once_with(...)` as a whitelist of expected kwargs.** Python's mock requires *exact* kwargs equality, so adding a new param to the production call breaks the assert; the standard "fix" is to add the new param to the whitelist — which silently re-allows the same param to be dropped later. Prefer `mock.assert_called_once()` followed by `mock.call_args.kwargs[key] == value` for each kwarg you actually care about. Evidence: hold-overview route silently dropped `workflow/bop/pj_function` because three independent `assert_called_once_with(...)` blocks omitted them; the leak was invisible until manual user testing.
- **Route forwarding must be asserted per-kwarg, with non-default values.** For every request parameter a Flask route reads, write a test that supplies a non-default value (`?bop=EAC17`) and asserts `mock_service.call_args.kwargs['bop'] == 'EAC17'`. A test that only checks happy-path empty defaults cannot detect a missing `args.get(...)` at the route layer.
- **Services with a snapshot/cache path AND an Oracle fallback must have tests on BOTH paths for every filter kwarg.** Tests that only stub `read_sql_df` (Oracle path) leave the snapshot path — which dominates production traffic when Redis is warm — completely unverified. The snapshot path lives behind `_get_wip_dataframe()` / `get_cached_wip_data()` / `_get_*_snapshot()`; mock at that layer with a DataFrame fixture that includes the filter column being tested. Evidence: `get_hold_detail_summary` / `get_hold_detail_lots` / `get_wip_hold_summary` all accepted `bop`/`workflow`/`pj_function` in their signature, applied them in the Oracle fallback, and silently dropped them in the snapshot path for production users.
- **Filter fixtures must include EVERY filter column the function honors.** If `_apply_non_indexed_filters` reads `BOP`/`WORKFLOWNAME`/`PJ_FUNCTION` but the fixture DataFrame only has indexed columns, the function silently no-ops on those filters and the test passes regardless. When extending a filter, add the column to existing fixtures or write a new fixture-builder helper. Evidence: `_sample_hold_df()` in `tests/test_wip_service.py` was missing all three non-indexed columns for months before the regression was caught manually.
- **Cross-filter narrowing has its own test surface — assert "selecting A narrows B".** For every page with multi-dropdown filters, write tests that set filter_A and assert filter_B's option list excludes rows where A doesn't match. Cover at minimum: single-value narrowing, CSV multi-value union, pairwise intersection (A AND B), and the exclude-self property (selecting `bop=X` should still show all available BOP values in the bops dropdown, not just X). The canonical pattern lives in `tests/test_wip_service.py::TestFilterOptionsCrossFilterNarrowing` and `tests/test_container_filter_cache.py::test_cross_filter_*`. Pages that intentionally do NOT cross-filter (e.g., reject-history) should pin that contract with an explicit "does_not_narrow" test (`tests/test_reject_history_service.py::test_get_filter_options_does_not_narrow_packages_by_selection`) so future cross-filter additions are deliberate.
- **Module-level constants frozen at import time cannot be overridden via `monkeypatch.setenv()`.** When a service reads `os.getenv(...)` into a module-level constant (e.g., `_USE_ROW_COUNT_CHUNKING = os.getenv("USE_ROW_COUNT_CHUNKING", "").lower() == "true"`), the value is frozen at the first import. Patching the env var after import has no effect. Tests must patch the attribute directly: `monkeypatch.setattr("mes_dashboard.services.<service>._USE_ROW_COUNT_CHUNKING", True)`. The same rule applies to any module-level `requests.Session`, integer constants, or feature-flag booleans. Evidence: `tests/integration/test_rowcount_flag_parity.py` — all flag-toggle tests use `setattr`, not `setenv`.
- **Env-var contract tests must pin default values, not just assert the var name appears in the contract file.** A test that only checks `"VAR_NAME" in contract_text` passes even when the documented default is wrong. For every env var with a code default, add a companion test that imports the module-level constant and asserts it equals the value stated in `env-contract.md`. This catches the class of error where the contract and code drift silently. Pattern: `tests/test_env_contract.py::TestEngineDefaultsMatchContract` — caught BQE-05 (contract said `prod=3`, code default was `5`). Evidence: `batch-rowcount-unification`.
- **Check for module-level `pytestmark` before adding mock-based tests to any file in `tests/integration/`.** Files like `tests/integration/test_oracle_error_path.py` carry `pytestmark = pytest.mark.integration_real` at the top, which silently skips all tests in that module unless `pytest --run-integration-real` is passed. A mock-based test placed there will appear to pass in CI because it is simply skipped, not executed. Keep mock-based tests in an unmarked file (e.g., `tests/integration/test_rowcount_flag_parity.py`). Evidence: `batch-rowcount-unification` — `TestPartialChunkFailure` would have been silently skipped if placed in `test_oracle_error_path.py`.

## Context Governance

For context-governed changes, read `specs/changes/<change-id>/context-manifest.md` before using file-reading or broad search tools.

- Read only paths allowed by the manifest or approved expansions.
- If more context is needed, stop and write a Context Expansion Request in the manifest (`cdd-kit context request`).
- The full agent-log format (including `files-read:` schema) is defined in
  `~/.claude/skills/contract-driven-delivery/references/agent-log-protocol.md`.
  Read that once; do not paraphrase it elsewhere.
- In `context-manifest.md` `## Allowed Paths`, use directory-level paths (e.g., `frontend/src/core/`), not glob patterns (e.g., `frontend/src/core/**/*.ts`). `cdd-kit context check` rejects glob patterns and causes a preflight failure. Evidence: migrate-shared-ui-ts initial manifest.

## AI Pipeline Architecture Notes

- **`raw_params`-style callables require the `dispatch: raw_params` YAML flag in `ai_functions.yaml`**: `query_production_history(raw_params: Dict)` takes a single positional dict, not keyword args. The AI pipeline's default `service_fn(**params)` dispatch silently fails for such callables — no error at import time, only fails at runtime when the LLM invokes the function. Any AI function whose target callable uses a `raw_params: Dict` positional signature must set `dispatch: raw_params` in its `ai_functions.yaml` entry, which routes the call to `service_fn(params)` instead of `service_fn(**params)`. Pin with a dispatch adapter test (pattern: `TestProductionHistoryQueryDispatchAdapter`). Evidence: `ai-pipeline-upgrade` — `production_history_service.query_production_history` dispatch failure discovered during design.
- **`advance_query_state` pops the full `_SESSION_STORE` entry on `ready_to_search`**: When slot-filling completes, `advance_query_state` pops the entire session dict for the `conversation_id`. Any cross-turn state added to `_SESSION_STORE[conversation_id]` (e.g., `chat_history`) is silently lost on the first completed slot-filling query. To preserve it: extract `saved = state.get("<key>", [])` before the pop; restore after: `_SESSION_STORE[conversation_id] = {"<key>": saved}`. Pin with a two-turn integration test (pattern: `TestHistorySurvivesAdvanceQueryStatePop`). Evidence: `ai-pipeline-upgrade` — chat_history evicted silently until R3 fix was applied at `ai_query_understanding.py:258-264`.
- **`_AI_SESSION` in `ai_query_service.py` is a `requests.Session` object bound at module import time**: tests that need to intercept HTTP calls from this service must patch `mes_dashboard.services.ai_query_service._AI_SESSION`, not `requests.post`. Patching `requests.post` at function level does not intercept calls routed through the pre-bound Session object. Apply the same boundary-patch discipline to any other service that holds a module-level Session. Evidence: `downtime-analysis-page` — `TestCallLlmText` required this correction in commit `ccb9347`.

## CI Workflow Notes

- **New Playwright specs require a browser install step in the CI workflow**: GitHub Actions runners have no pre-installed Chromium. When a PR first introduces a Playwright spec for a page, add `npx playwright install --with-deps chromium` as a step in `frontend-tests.yml` before the `npx playwright test …` step. Without this, the runner exits with "Executable doesn't exist" and all tests fail with no output. The local hard rule (global `CLAUDE.md §Hard rules #2`) about not running `playwright install` applies only to the shared-browser host machine — it does not apply to CI runners. Evidence: `downtime-analysis-page` — fixed in commit `6fac60c`.

## GunicornHarness Integration Test Notes

- **GunicornHarness subprocess must use `mes_dashboard:create_app()` (not `src.mes_dashboard.app:create_app()`) and prepend `src/` to `PYTHONPATH`**: without both, the subprocess gets `ModuleNotFoundError: No module named 'mes_dashboard'`. Use the same pattern as the existing `gunicorn_workers` fixture in `tests/integration/conftest.py`. Evidence: `gunicorn-preload-workers` — `tests/integration/_multi_worker_harness.py::GunicornHarness.start()`.
- **`is_testing_runtime` in `app.py:799` is True when any of `app.config["TESTING"]`, `app.testing`, or `os.getenv("PYTEST_CURRENT_TEST")` is set**: all three are set by `tests/conftest.py` (`FLASK_ENV=testing` selects `TestingConfig.TESTING=True`; `PYTEST_CURRENT_TEST` is set by pytest itself). This guard silently skips all single-run prewarms. A `GunicornHarness` subprocess must pop `FLASK_ENV`, `FLASK_TESTING`, and `PYTEST_CURRENT_TEST`, and set `REDIS_ENABLED=true` before `Popen`, or prewarms never start and integration assertions on log sentinels will always fail. Evidence: `gunicorn-preload-workers` — `src/mes_dashboard/app.py:798-818`; `tests/integration/_multi_worker_harness.py:424-435`; `tests/conftest.py:18-19`.
- **`start_duckdb_prewarm()` logs "background thread started" on every call but logs "prewarm complete" only after a full Oracle load**: if `_try_reuse_existing()` finds a valid `tmp/resource_history.duckdb`, the thread exits silently. Integration tests asserting exactly-one prewarm execution must check `"resource_history DuckDB prewarm background thread started"`, not `"prewarm complete"`, or they will fail spuriously in warm-cache environments (e.g., a running production service has already written the file today). Evidence: `gunicorn-preload-workers` — `tests/integration/test_preload_fork_safety.py:113-117, 368-378`.
- **GunicornHarness must set both `REGISTER_INTERNAL_METRICS=true` and `INTERNAL_METRICS_ENABLED=1` to reach `/internal/metrics`**: `REGISTER_INTERNAL_METRICS` is env-var-overrideable via `_bool_env()` in `Config` (default `False`), so clearing `FLASK_ENV` (required to allow prewarms — see `is_testing_runtime` note above) removes the `TestingConfig.REGISTER_INTERNAL_METRICS=True` override. Both env vars must be set explicitly. Evidence: `gunicorn-preload-workers` — `src/mes_dashboard/config/settings.py:53, 179`; `tests/integration/_multi_worker_harness.py:434-436`.
