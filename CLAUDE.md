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
mypy src/                             # Python type check
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

## TypeScript Notes

- **TypeScript migration is complete** across all feature apps. All `core/`, `shared-composables/`, `shared-ui/`, shared layers, and feature apps use TypeScript. `portal-shell/` non-entry modules remain JS intentionally (no type coverage needed for the thin shell layer). `workers/duckdb-worker.js` and `main.js` entry points are intentionally JS — `index.html` references `./main.js` and Vite resolves `main.ts` at build time; do not rename these.
- **Node ≥22.6 is required**: `environment.yml` pins `nodejs>=22.6` for `node --experimental-strip-types` support in parity tests. Do not loosen this constraint.
- **SFC-paired tests**: `frontend/vitest.config.js` `include` already lists `src/**/*.test.ts`. Tests placed next to SFCs (e.g., `src/shared-ui/components/__tests__/*.test.ts`) are covered by this glob — no config change needed when adding new SFC-paired tests.
- **echarts callback parameters** (`params` in formatter/tooltip) lack precise types — annotate with `// TODO: type echarts callback` rather than `any`.

## Shared UI Component Notes

- **`frontend/src/shared-ui/components/MultiSelect.vue` is shared by 9 feature apps** (production-history, wip-detail, wip-overview, hold-overview, reject-history, resource-history, resource-status, query-tool, mid-section-defect, yield-alert-center). Any change to its emit/prop surface must be **additive** (optional events/props that unmounted consumers ignore). Before modifying any `frontend/src/shared-ui/components/` file, grep all 9+ apps for usage. Evidence: `fix-prod-history-multiselect-filter` — added `dropdown-close` as optional event so 8 untouched consumers were no-ops.
- **Snapshot-diff filter composables must re-sync after server-driven prune**: any composable that uses a private `_lastCommitted[field]` snapshot to skip no-op refresh must refresh that snapshot from `selection[field]` after every successful `fetchFilterOptions`, because server-side prune mutates `selection` without user action. Skipping this step makes the next dropdown close emit a spurious cross-filter request. Pattern lives in `frontend/src/production-history/composables/useFirstTierFilters.ts`. Evidence: `fix-prod-history-multiselect-filter` — `_pruneSelection` interaction with `commitSelection` diff.
- **`frontend/src/admin-user-usage-kpi/components/` (7 files) is a build-time dependency of `admin-dashboard`**: `admin-dashboard/tabs/UsageTab.vue` imports all 7 components (`DauTrendChart`, `DeptBreakdownTable`, `DurationDistChart`, `HourlyLoginChart`, `KpiCard`, `RecentSessionsTable`, `TopUsersTable`) via relative `../../admin-user-usage-kpi/components/` paths. Deleting or migrating `admin-user-usage-kpi/` without auditing `admin-dashboard` first will break the Vite build. Always grep `admin-dashboard/` before any change to `admin-user-usage-kpi/`. Evidence: `remove-unused-pages` — `rm -rf admin-user-usage-kpi/` broke the build; `components/` was restored while SPA entry files remained deleted.

## Accessibility Notes

- **WAI-ARIA combobox close paths must return focus to the trigger**: when adding Escape / outside-click / programmatic close to any popup-style component (MultiSelect, dropdown, dialog), the close handler must `nextTick(() => triggerEl.focus())` or keyboard users lose focus context. Pattern lives in `frontend/src/shared-ui/components/MultiSelect.vue::closeDropdown()`. Evidence: `fix-prod-history-multiselect-filter` — ui-ux-reviewer flagged missing focus return after adding Escape support; fixed inline before merge.

## Cache Architecture Notes

- **Cache namespace must match**: When adding a startup pre-warm for any service, verify the pre-warm writes to the **same** namespace/key pattern that user queries actually read from. Writing to a separate prefix (e.g., `resource_history_prewarm`) while user queries read from `resource_dataset`/`resource_oee` provides zero cache benefit — the mismatch is silent and only discoverable by comparing logs across the two code paths. Always trace the full read path of a live query before implementing a pre-warm. Evidence: `resource-history-perf` — original prewarm used `cache_prefix="resource_history_prewarm"` via `batch_query_engine.execute_plan` while `resource_dataset_cache.py` wrote to `resource_dataset`/`resource_oee` via `register_spool_file()`.
- **Multi-worker startup lock**: Any gunicorn startup background task that loads data from Oracle must use a file-based exclusive lock (`os.O_CREAT | os.O_EXCL` on a `.loading` sentinel file) to prevent all workers from executing the same Oracle query simultaneously. Workers that lose the lock should poll `_try_reuse_existing()` in a loop (5 s intervals, 90 s timeout) until the winner finishes. The pattern is implemented in `resource_history_duckdb_cache.py::_try_lock()` / `_release_lock()`. Evidence: `resource-history-perf` — without the lock, two gunicorn workers each ran the full 30 s Oracle prewarm concurrently.
- **Spool schema breaking changes require post-deploy parquet cleanup**: When any spool-based service rewrites its parquet column schema (rename/add/remove), existing files at `tmp/query_spool/<service>/*.parquet` become incompatible and must be cleared post-deploy or readers will hit schema-mismatch errors at the next `pd.read_parquet` / DuckDB `read_parquet` call. Add `rm tmp/query_spool/<service>/*.parquet` to the deploy runbook for any schema-breaking change, and document it in the change's `ci-gates.md` §Rollback. Evidence: `prod-history-detail-raw-rows` removed aggregated aliases TRACKIN_TS/TRACKOUT_TS/TRACKIN_QTY/TRACKOUT_QTY and added PJ_FUNCTION.
- **Query-tool has no persistent spool — skip parquet cleanup in rollbacks**: The query-tool executes Oracle SQL on-demand per request and does not persist DuckDB parquet files (unlike production-history or resource-history). Do not add `rm tmp/query_spool/query_tool/*.parquet` to any deploy or rollback runbook for query-tool changes. Evidence: `query-tool-partial-trackout` — `ci-gates.md §Rollback Policy` confirmed no parquet cleanup required even after adding `partial_count` to aggregated output.
- **Backend SQL-to-API rename layer isolates frontend from Oracle column renames**: report-module backends maintain a SQL `AS` alias layer (and pandas fallback rename dict) at the API boundary that maps raw Oracle/spool column names to stable snake_case JSON keys. Example: `production_history_sql_runtime.py:184-205, 242-251` maps `MFGORDERNAME → work_order`, `TRACKINTIMESTAMP → trackin_time`, etc. When renaming Oracle source columns or spool parquet columns, audit THIS layer first — if it already preserves the API JSON key, no frontend audit or contract change is needed. Evidence: `prod-history-detail-raw-rows` renamed 7 Oracle columns; frontend alias audit returned zero hits because the rename layer absorbed the change.

## Portal-Shell CSS Architecture Notes

- **All feature CSS must be scoped under `.theme-<name>`**: Portal-shell (`nativeModuleRegistry.js`) loads each feature's CSS bundle once via dynamic `import()` and caches it permanently in `<head>`. Unscoped rules (e.g., `.card`, `.pareto-chart-wrap`) from any bundle bleed into every subsequent page because no bundle is ever unloaded. Always prefix every rule with the feature's root class (e.g., `.theme-hold-history .card`). Specificity 0-2-0 beats unscoped 0-1-0 regardless of injection order. Evidence: `hold-history-detail-flat-table` — unscoped `.pareto-chart-wrap { height: 360px }` in hold-history CSS overrode hold-overview's chart height on page switch.
- **CSS source fixes require `npm run build` to take effect**: The app serves from `src/mes_dashboard/static/dist/` (Flask static), not the Vite dev server. After editing any `frontend/src/*/style.css`, run `cd frontend && npm run build`. New builds generate hashed filenames (e.g., `style5.css`) rather than named files (e.g., `hold-history.css`) — stale named files in `dist/` are orphaned and not referenced by the new bundles.

## Modernization Policy Artifact Notes

- **Page additions/removals require updating two JSON files in `docs/migration/full-modernization-architecture-blueprint/`**: `asset_readiness_manifest.json` (maps route → required dist asset; read by `app.py:_validate_in_scope_asset_readiness()` at startup via `lru_cache` — stale entries crash gunicorn with `RuntimeError`) and `route_scope_matrix.json` (drives in-scope route classification). Neither file is reached by grepping Flask routes or Vite config alone. Add both to `## Allowed Paths` whenever a change adds or removes a page. Evidence: `remove-unused-pages` — `/tables` removal not reflected here caused gunicorn startup crash post-deploy.
- **`data/page_status.json` is a runtime-persisted registry that is never modified by code deletion**: `page_registry.py:_load()` reads it at runtime to build navigation drawers; a removed page's entry will continue rendering in the sidebar and emit "缺少 route contract: <route>" until the entry is manually removed from the `pages` array. Explicitly include `data/page_status.json` in `## Allowed Paths` and delete the page's object from the array as part of any page removal change. Evidence: `remove-unused-pages` — `/tables` entry persisted in sidebar after all code was deleted.

## WIP Service Architecture Notes

- `_get_wip_search_index` (in `wip_service.py`) builds the in-process filter-options search index. It has two paths: (a) incremental sync from `previous` cache, (b) full-rebuild fallback (`if index_payload is None:` block) that calls `_materialize_search_payload`. **Any new field added to the filter-options response** (e.g., a new dropdown category) must be appended to the `index_payload` dict in BOTH paths: after the `_materialize_search_payload` call in the full-rebuild branch, AND carried forward via `previous.get(...)` in the incremental branch. Adding only to a helper function that is never called from `_get_wip_search_index` will silently omit the field on every service restart. Evidence: `wip-hold-drilldown-filters` (workflows/bops/pjFunctions).

## QueryBuilder Architecture Notes

- **Two independent IN-list conditions require counter-forwarding**: When a single service function needs two separate `QueryBuilder` instances (e.g., `EQUIPMENTID IN (...)` and `WORKCENTER_GROUP IN (...)`), forward `wg_builder._param_counter = builder._param_counter` before calling `add_in_condition`, then `builder._param_counter = wg_builder._param_counter` and `builder.params.update(wg_builder.params)` after. Without this, both builders start at `p0` and Oracle raises `ORA-01006: bind variable does not exist` at runtime. Evidence: `src/mes_dashboard/services/query_tool_service.py:2558-2567` (`equipment-rejects-by-lots`).

## MES Domain Semantics Notes

- **`LOTWIPHISTORY.TRACKINQTY` is remaining-qty-per-partial, not original load.** Same upload session shares one `TRACKINTIMESTAMP` but has decrementing `TRACKINQTY` across partials (partial N+1 = partial N TRACKINQTY − partial N TRACKOUTQTY). To identify one session use only `TRACKINTIMESTAMP` as the group key; original load = `MAX(TRACKINQTY)` over the group; trackout = `SUM(TRACKOUTQTY)`; loss = `MAX(TRACKINQTY) − SUM(TRACKOUTQTY)`. Contract: `contracts/business/business-rules.md` PH-06. Evidence: lot `GA26041607-A00-005` (TRACKINQTY 99424 → 26624 = 99424 − 72800) — `prod-history-detail-partial-merge` initially used a 5-tuple key including TRACKINQTY and silently failed to merge any real partial-trackout on production data.
- **Fixture discipline for partial-trackout tests**: always include at least one fixture where partials of the same `TRACKINTIMESTAMP` have *different* `TRACKINQTY` values (use real arithmetic: TRACKINQTY[N+1] = TRACKINQTY[N] − TRACKOUTQTY[N]). A fixture with uniform `TRACKINQTY` across partials cannot distinguish a 4-key from a 5-key aggregation design — both pass. Evidence: `tests/test_production_history_sql_runtime.py::test_partial_merge_same_trackin_time_different_trackin_qty`.

## Context Governance

For context-governed changes, read `specs/changes/<change-id>/context-manifest.md` before using file-reading or broad search tools.

- Read only paths allowed by the manifest or approved expansions.
- If more context is needed, stop and write a Context Expansion Request in the manifest (`cdd-kit context request`).
- The full agent-log format (including `files-read:` schema) is defined in
  `~/.claude/skills/contract-driven-delivery/references/agent-log-protocol.md`.
  Read that once; do not paraphrase it elsewhere.
- In `context-manifest.md` `## Allowed Paths`, use directory-level paths (e.g., `frontend/src/core/`), not glob patterns (e.g., `frontend/src/core/**/*.ts`). `cdd-kit context check` rejects glob patterns and causes a preflight failure. Evidence: migrate-shared-ui-ts initial manifest.
