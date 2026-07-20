# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

MES Dashboard 是一個供工廠工程師自助查詢 MES 生產數據的 Web 報表平台（Flask + Vue3/Vite），支援 WIP、Hold、良率、設備、材料追溯等報表頁面（現行清單見 `docs/migration/full-modernization-architecture-blueprint/route_scope_matrix.json`），並整合 AI 自然語言查詢、異常偵測排程與系統管理儀表板。

## Dev commands

```bash
# conda env
conda activate mes-dashboard          # 啟動環境
conda run -n mes-dashboard <cmd>      # 單次執行

# Backend
PYTHONPATH=src flask --app mes_dashboard.app:create_app run      # 開發 server（需先 activate）
PYTHONPATH=src gunicorn -c gunicorn.conf.py 'mes_dashboard.app:create_app()'  # production

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
```

## Architecture

```
src/mes_dashboard/
  app.py                  # Flask app factory；Blueprint 掛載；runtime-contract 驗證
  routes/                 # 29 個 Blueprint 模組（每個功能模組一個檔案）
  services/               # 業務邏輯層（routes 呼叫 services，禁止直接 DB）
  core/response.py        # success_response / error_response 統一回應輔助函式
  config/settings.py      # 環境設定（從 .env 載入）
  workers/                # RQ async job workers（downtime/eap_alarm/production_history/reject_history/resource_history）

frontend/
  src/
    portal-shell/         # 主 SPA shell（路由、導覽、權限守衛）
    <feature>/            # 每個報表功能獨立 Vue 應用（wip/hold/resource 等）
    shared-ui/, shared-composables/  # 共用元件與 composables（跨多個 apps）
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

`contracts/` documents intended API, business-rule, CSS, env, and data-shape behavior; `specs/archive/` holds historical change records. Both are reference material — read them when useful. This repo no longer drives changes through the cdd-kit CLI (`/cdd-new`, `cdd-kit gate`, etc.); it was left in a broken/unmaintained state, so treat any leftover mention of it in docs/tests/CI as historical, not something to invoke.

## Engineering notes

**Frontend patterns** — see `docs/architecture/frontend-patterns.md`:
- TS migration complete; `portal-shell/` non-entry modules and `main.js` entry points intentionally remain JS
- Node ≥22.6 required (`--experimental-strip-types` parity tests)
- vue-echarts: bind `@click` on `<VChart>`, not imperative `.on()`
- `MultiSelect.vue` shared by 16 apps — grep consumers first, changes must be additive
- Snapshot-diff filter composables: re-sync `_lastCommitted` from `selection` after every `fetchFilterOptions`
- Oracle DATE midnight UTC columns: inspect H/M/S via regex before `new Date()` (avoids ±8h TZ shift)
- WAI-ARIA combobox close must `nextTick(() => triggerEl.focus())`
- `fetchAllViews()` fan-out: per-endpoint staleness dict, not a shared counter

**CSS architecture** — see `docs/architecture/css-patterns.md` and `contracts/css/css-contract.md`:
- Feature CSS must be scoped under `.theme-<name>`; unscoped rules bleed permanently (`css:check` Rule 6)
- Local Playwright/E2E runs serve pre-built `dist/`, not live source — `npm run build` before testing CSS/JS/Vue changes
- `<Teleport to="body">` breaks descendant selectors — wrap content in a `.theme-<feature>` div (rule 4.4)
- `resource-shared/styles.css` `:is()` groups must include every theme that reuses its component classes (rule 4.5) — admin-pages/material-consumption intentionally replicate locally instead
- Relocating classes into a different `.theme-X` scope: grep the target theme's `style.css` for name collisions first (`css:check` only catches unscoped, not colliding-but-scoped)

**Cache & spool patterns** — see `docs/architecture/cache-spool-patterns.md`:
- Pre-warm namespace must exactly match the key pattern user queries read
- Multi-worker gunicorn Oracle loads need a file-based exclusive lock (`O_CREAT|O_EXCL` or `flock(LOCK_EX|LOCK_NB)`, per-cache)
- Parquet schema breaks: add `rm` to rollback runbook AND bump `_SCHEMA_VERSION` in the same commit
- Legacy vs. unified spool paths with different columns: document each path's columns separately — never a blanket "UNCHANGED"
- query-tool has no persistent spool — skip parquet cleanup in its rollbacks
- hold-history spool: DESCRIBE-based column detection, no forced purge
- SQL-to-API rename layer at the route boundary absorbs column renames — audit it before touching frontend
- SyncWorker: `COUNT > 0` guard before `TRUNCATE`/`DELETE`; version `REPLACE` still runs when skipped
- `/api/resource/status/options` has its own inline filter dict, independent of `query_resource_filter_options()`
- Oracle `CHAR` column lookups: `strip()` at both dict-build and per-record lookup
- Type-A spool frontend: read the route's `success_response()` call for the exact JSON wrapper key
- Canonical spool: two-phase key resolution (superset warmup reuse + exact-match Oracle fallback)
- `spool_routes._ALLOWED_NAMESPACES`: add namespace + parametrized test in the same PR as the spool write
- Type B async without `progress_callback` support: coarse bracket milestones 5→15→90→100
- `*_USE_UNIFIED_JOB` flags: gunicorn/RQ worker env must match — see contracts/env/env-contract.md §Worker Feature-Flag Env-Var Parity
- Coarse spool key: inject fine-filter WHERE at `_register_runtime_views`, not spool-write time; `trace_query_id`-keyed stage spools should be pre-filtered

**Service architecture** — see `docs/architecture/service-patterns.md`:
- `downtime_analysis_service`: patch `load_downtime_events` at `downtime_analysis_cache`, not the service module
- `_get_wip_search_index`: new filter fields need both incremental and full-rebuild paths
- `rq_monitor_service`: patch at `get_rq_monitor_summary`, not `redis_client`
- `QueryBuilder`: two independent `IN`-list builders need counter-forwarding between them
- `_PARTIAL_NONKEY_COLS_LOT`: add new non-key columns atomically with the SQL change, pin with a membership test
- SQL CTE changes: update both the CTE SELECT list and the outer SELECT; when two functions must reconcile results, extract one shared CTE-builder function rather than parallel WHERE clauses
- SQL-frontend column gap: cross-check SQL output against the Vue template, not just the route response
- New SQL SELECT columns from Oracle CHAR fields: `TRIM()` each one explicitly — don't assume it follows an already-trimmed sibling column
- AI pipeline `raw_params` callables require `dispatch: raw_params` in `ai_functions.yaml`
- AI pipeline `advance_query_state` pops the entire `_SESSION_STORE` — extract/restore cross-turn state around it
- `_AI_SESSION` is a module-level `requests.Session` — patch `ai_query_service._AI_SESSION`, not `requests.post`
- `AI_MODE=leader`: leader only does planning/dispatch/synthesis; tool execution always delegates to `process_agent_turn` — see §AI Pipeline — Leader/Subagent Mode
- Every `execute_*_job` worker must wire `acquire_heavy_query_slot` before its `*_USE_RQ` flag ships — see §RQ Worker Concurrency Gate
- Every new `execute_*_job` worker must wire BOTH `deploy/*.service` AND `scripts/start_server.sh`; never pass `rq worker --job-execution-timeout` — see contracts/ci/ci-gate-contract.md §New RQ Worker Deploy Checklist
- COUNT(*) fail-open pre-check for domains without a date range must fail open to sync, never 503 — see §Async Routing Pre-Check Pattern
- `DW_MES_WIP` has no `CONTAINERID` index — bridge `CONTAINERID`↔`CONTAINERNAME` via indexed `DW_MES_CONTAINER` before joining — see §DW_MES_WIP Has No CONTAINERID Index
- `SQLLoader.load_with_params` substitutes `{{ NAME }}` via a **global** string replace — builder-function fragments must never embed a newline and template doc-comments must never spell out the literal placeholder token, or the header comment gets corrupted and Oracle raises `ORA-00900` — see docs/architecture/service-patterns.md §SQLLoader.load_with_params

**MES domain semantics:**
- `LOTWIPHISTORY.TRACKINQTY` is remaining-qty-per-partial (decrements across partials); use only `TRACKINTIMESTAMP` as session key — see contracts/business/business-rules.md §PH-06

**Modernization policy** — see `docs/architecture/modernization-policy.md`:
- Page add/remove: update `asset_readiness_manifest.json` + `route_scope_matrix.json`, `vite.config.ts` `INPUT_MAP`, and `portal-shell/routeContracts.js` `ROUTE_CONTRACTS` — omitting `INPUT_MAP` blocks boot, omitting `ROUTE_CONTRACTS` only warns
- `data/page_status.json`: manually delete page entry on code removal (never auto-updated)
- `drawer_id` lives in `portal-shell/navigationManifest.js`, not `page_status.json` — update the corresponding test assertion when renamed

**Test coverage discipline** — see `docs/architecture/test-discipline.md`:
- Use `call_args.kwargs[key]` per-kwarg assertions, not `assert_called_once_with()` whitelist
- Assert route forwarding per-kwarg with non-default values
- Test BOTH snapshot and Oracle fallback paths for every filter kwarg
- Filter fixtures must include every column the function filters on
- Cross-filter narrowing has its own test surface: assert "selecting A narrows B"
- One-of-N-required filter axes: test each axis EMPTY while a sibling is populated
- Module-level constants: `monkeypatch.setattr()` not `setenv`; registration side-effects need `importlib.reload()` after clearing; in threaded tests all `setattr()` calls must complete before threads launch
- Env-var contract tests must pin default values, not just assert var-name presence
- Closed-enum validation feeding an exact-match SQL clause: verify enum format equals real column values first
- New feature-flag rows in `env-contract.md` must also get `enum` + `default` in `contracts/env/env.schema.json`
- Check `pytestmark` before adding mock tests to `tests/integration/`
- Use `ast.parse()` + walk `ast.Call` to prove absence of removed startup calls
- Cross-change spec gaps: mark `xfail(strict=True)`, not `xfail`/`skip`, so it tripwires when the gap closes
- Partial-trackout fixtures: include rows with different `TRACKINQTY` per session
- New `oracle_arrow_reader`/`base_chunked_duckdb_job` callers: add to `_APPROVED_CALLERS` and update the job-registry count test, same PR
- `BaseChunkedDuckDBJob` domain migrations need a dual-tier parity test (mock chunk-seam unit + real-path parquet diff on business key)
- Over-limit boundary tests must strictly exceed the cap, not equal it
- Route tests mocking `enqueue_query_job`/`enqueue_job_dynamic` must also `inspect.signature(worker_fn).bind(**kwargs)` — a mocked-enqueue shape mismatch only fails at worker runtime

**CI workflow & GunicornHarness** — see `docs/architecture/ci-workflow.md`:
- New Playwright specs: add `npx playwright install --with-deps chromium` in CI before running tests
- `GunicornHarness` subprocess setup: `mes_dashboard:create_app()` app URI + `src/` on `PYTHONPATH`; pop `FLASK_ENV`/`FLASK_TESTING`/`PYTEST_CURRENT_TEST` and set `REDIS_ENABLED=true` before `Popen`; set both `REGISTER_INTERNAL_METRICS=true` and `INTERNAL_METRICS_ENABLED=1` for `/internal/metrics`; assert "background thread started" for prewarm, not "prewarm complete"
- Playwright `page.route()` is LIFO: register catch-all routes first, specific routes last
- reject-history/reject-material specs: click submit in `beforeEach` before asserting `DetailTable` content
- Resilience specs: use `page.goto(...).catch(()=>{})`, not `page.request.post()` (`loginViaApi`) — not interceptable, throws ECONNREFUSED in CI
- Playwright no-server skip: `<50`-char body-text check must GATE (return early, before calling) `waitForFunction` at all — never just shorten its timeout value, since `waitForFunction` does not reliably honor `timeout` on a frame whose navigation just failed; `pageRendered` must check app-specific content, not `bodyText.length > 100`
- Async-gated route unit tests: mock `is_async_available()=True` + enqueue fn, not spool-hit mocks — CI has no Redis
