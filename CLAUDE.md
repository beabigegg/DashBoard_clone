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

# CDD
cdd-kit validate                      # 驗證所有 contracts
cdd-kit detect-stack                  # 偵測專案技術棧
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

## Context Governance

For context-governed changes, read `specs/changes/<change-id>/context-manifest.md` before using file-reading or broad search tools.

- Read only paths allowed by the manifest or approved expansions.
- If more context is needed, stop and write a Context Expansion Request in the manifest (`cdd-kit context request`).
- The full agent-log format (including `files-read:` schema) is defined in
  `~/.claude/skills/contract-driven-delivery/references/agent-log-protocol.md`.
  Read that once; do not paraphrase it elsewhere.

<!-- cdd-kit:learnings:start -->
### Promoted Learnings

**CDD Kit operations** — see `docs/cdd-kit-patterns.md`:
- No CI version pin; upgrade local cdd-kit after any `spec traceability` failure
- `ci-gates.md` needs literal "workflow" / "promotion policy" / "rollback policy" headers or the gate fails
- Tasks 6.2/6.3 `done` when Tier-1 passes locally; 6.4 `skipped` when no nightly/weekly gates defined
- Version entries go only in `contracts/CHANGELOG.md`, never per-contract files
- `context-manifest.md` Allowed Paths: directory-level only, no globs
- `pip install jsonschema` required before `cdd-kit validate --contracts` (CI and local)
- Inert concurrency code (zero callers, or all flags default-off): add `tier-floor-override` to `tasks.yml` (≥20 chars); expires on first real caller / first flag flip-on; keyword-scan false positives get a permanent override
- Concurrent backend+frontend agents both calling `cdd-kit test run` race on `test-evidence.yml` — last agent must re-run combining both stacks' commands
- Two uncommitted changes bumping the same contract's schema-version: `validate --versions` diffs working tree vs git HEAD, not changelog prose — wait for the other to commit, `--no-verify` only if it's the sole failure, or stage just your hunks via `git update-index` against a HEAD-reconstructed blob to commit a clean bump without waiting — see docs/cdd-kit-patterns.md
- `cdd-kit contract endpoint set` only mutates table cells (auth/request/response/errors/tests), never prose sections (Compatibility Notes/CHANGELOG) — a hook-blocked prose-only note is a legitimate deferral if documented elsewhere (e.g. business-rules.md), not a corner cut — see docs/cdd-kit-patterns.md
- Stage only the specific `specs/changes/<id>/`, never all of `specs/changes/` — sibling scaffolds fail the pre-commit hook
- `gate --strict` only runs the changed-area test ladder; before pushing a removal or shape change, grep the full test tree and run full pytest locally
- Full pytest run regenerates the whole contract sample set (180+ files, currently 182); `git checkout tests/contract/samples/` then re-stage only your change's samples
- Any `schema-version` bump to `contracts/api/api-contract.md` — even prose-only — requires re-running `cdd-kit openapi export` for both `contracts/openapi.json` and `contracts/api/openapi.json` before pushing, or the `openapi-sync` gate fails — see docs/cdd-kit-patterns.md
- ADR 0012 `data-shape: <condition>` citation resolver requires exact heading text `## Invalid Data Behavior` (no numeric prefix) — see `contracts/data/data-shape-contract.md` heading comment
- ADR 0012 Form-1 field citations can't traverse `type: array` items — cite the array field itself (e.g. `data.data`), put per-column type/nullability in the rationale text pointing at `data-shape-contract.md` instead

**Frontend patterns** — see `docs/architecture/frontend-patterns.md`:
- TS migration complete; `portal-shell/` non-entry modules and `main.js` entry points intentionally remain JS
- Node ≥22.6 required (`--experimental-strip-types` parity tests)
- vue-echarts: bind `@click` on `<VChart>`, not imperative `.on()`
- `MultiSelect.vue` shared by 16 apps — changes must be additive, grep consumers first
- Snapshot-diff filter composables: re-sync `_lastCommitted` from `selection` after every `fetchFilterOptions`
- Oracle DATE midnight UTC columns: inspect H/M/S via regex before `new Date()` (avoids ±8h TZ shift)
- WAI-ARIA combobox close must `nextTick(() => triggerEl.focus())`
- `fetchAllViews()` fan-out: per-endpoint staleness dict, not a shared counter (shared counter clears all in-flight flags on first response)

**CSS architecture** — see `docs/architecture/css-patterns.md` and `contracts/css/css-contract.md`:
- Feature CSS must be scoped under `.theme-<name>`; unscoped rules bleed permanently (`css:check` Rule 6)
- Local Playwright/E2E runs serve pre-built `dist/`, not live source — `npm run build` before testing CSS/JS/Vue changes
- `<Teleport to="body">` breaks descendant selectors — wrap content in a `.theme-<feature>` div (rule 4.4)
- `resource-shared/styles.css` `:is()` groups must include every page theme that reuses resource-shared component classes (rule 4.5) — a few themes (e.g. admin-pages, material-consumption) intentionally replicate rules locally instead of joining the group
- Relocating a component's classes into a different `.theme-X` scope with its own component library: grep the target theme's `style.css` for name collisions first (`css:check` catches unscoped, not colliding-but-scoped duplicates) — see contracts/css/css-contract.md §Known Global Rule Interactions

**Cache & spool patterns** — see `docs/architecture/cache-spool-patterns.md`:
- Pre-warm namespace must exactly match the key pattern user queries read
- Multi-worker gunicorn Oracle loads: file-based exclusive lock (`container_filter_cache.py` uses `O_CREAT|O_EXCL`; `resource_history_duckdb_cache.py` moved to `flock(LOCK_EX|LOCK_NB)` to avoid a stale-sentinel deadlock)
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
- `*_USE_UNIFIED_JOB` flags must match between gunicorn and RQ worker env (frozen at boot) — see contracts/env/env-contract.md §Worker Feature-Flag Env-Var Parity
- Coarse spool key: inject fine-filter WHERE at `_register_runtime_views`, not spool-write time; `trace_query_id`-keyed stage spools should be pre-filtered

**Service architecture** — see `docs/architecture/service-patterns.md`:
- `downtime_analysis_service`: patch `load_downtime_events` at `downtime_analysis_cache`, not the service module
- `_get_wip_search_index`: new filter fields need both incremental and full-rebuild paths
- `rq_monitor_service`: patch at `get_rq_monitor_summary`, not `redis_client`
- `QueryBuilder`: two independent `IN`-list builders need counter-forwarding between them
- `_PARTIAL_NONKEY_COLS_LOT`: add new non-key columns atomically with the SQL change, pin with a membership test
- SQL CTE changes: update both the CTE SELECT list and the outer SELECT; when two functions must reconcile results, extract one shared CTE-builder function rather than maintaining parallel WHERE clauses (pin with a structural same-builder test) — see docs/architecture/service-patterns.md
- SQL-frontend column gap: cross-check SQL output against the Vue template, not just the route response
- New SQL SELECT columns from Oracle CHAR fields: `TRIM()` each one explicitly — don't assume it follows an adjacent already-trimmed sibling column (`equipment_lots.sql` lacked `TRIM(CONTAINERNAME)` next to `TRIM(PRODUCTLINENAME)`)
- AI pipeline `raw_params` callables require `dispatch: raw_params` in `ai_functions.yaml`
- AI pipeline `advance_query_state` pops the entire `_SESSION_STORE` — extract/restore cross-turn state around it
- `_AI_SESSION` is a module-level `requests.Session` — patch `ai_query_service._AI_SESSION`, not `requests.post`
- `AI_MODE=leader`: leader 只做 planning/dispatch/synthesis，工具執行一律委派 `process_agent_turn`（函式優先、query_database SQL fallback）— see docs/architecture/service-patterns.md §AI Pipeline — Leader/Subagent Mode
- Every `execute_*_job` worker must wire `acquire_heavy_query_slot` before its `*_USE_RQ` flag ships — see docs/architecture/service-patterns.md §RQ Worker Concurrency Gate
- Every new `execute_*_job` worker must wire BOTH `deploy/*.service` AND the dev launcher `scripts/start_server.sh`, and never pass `rq worker --job-execution-timeout` (invalid under pinned rq<2.0.0; timeout is set at enqueue) — see contracts/ci/ci-gate-contract.md §New RQ Worker Deploy Checklist
- COUNT(*) fail-open pre-check for domains without a date range must fail open to sync, never 503 — see docs/architecture/service-patterns.md §Async Routing Pre-Check Pattern
- `DW_MES_WIP` has no `CONTAINERID` index (`CONTAINERNAME`/`TXNDATE` only, 95M+ rows) — bridge `CONTAINERID`→`CONTAINERNAME` via indexed `DW_MES_CONTAINER` before joining — see docs/architecture/service-patterns.md

**MES domain semantics:**
- `LOTWIPHISTORY.TRACKINQTY` is remaining-qty-per-partial (decrements across partials); use only `TRACKINTIMESTAMP` as session key — see contracts/business/business-rules.md §PH-06

**Modernization policy** — see `docs/architecture/modernization-policy.md`:
- Page add/remove: update `asset_readiness_manifest.json` + `route_scope_matrix.json` (`docs/migration/`), `vite.config.ts` `INPUT_MAP`, and `portal-shell/routeContracts.js` `ROUTE_CONTRACTS` — omitting `INPUT_MAP` blocks boot, omitting `ROUTE_CONTRACTS` only warns
- `data/page_status.json`: manually delete page entry on code removal (never auto-updated)
- `drawer_id` lives in `portal-shell/navigationManifest.js`, not `page_status.json` (which only stores route→status) — update the corresponding test assertion and rename method there

**Test coverage discipline** — see `docs/architecture/test-discipline.md`:
- Use `call_args.kwargs[key]` per-kwarg assertions, not `assert_called_once_with()` whitelist
- Assert route forwarding per-kwarg with non-default values
- Test BOTH snapshot and Oracle fallback paths for every filter kwarg
- Filter fixtures must include every column the function filters on
- Cross-filter narrowing has its own test surface: assert "selecting A narrows B"
- One-of-N-required filter axes: test each axis EMPTY while a sibling is populated
- Module-level constants: `monkeypatch.setattr()` not `setenv`; module-level registration side-effects need `importlib.reload()` after clearing; in threaded tests, all `setattr()` calls must complete before threads launch
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
- Route tests mocking `enqueue_query_job`/`enqueue_job_dynamic` must also `inspect.signature(worker_fn).bind(**kwargs)` — a mocked-enqueue shape mismatch only fails at worker runtime, see docs/architecture/test-discipline.md §Async Route↔Worker Signature Contract

**CI workflow & GunicornHarness** — see `docs/architecture/ci-workflow.md`:
- New Playwright specs: add `npx playwright install --with-deps chromium` in CI before running tests
- `GunicornHarness`: use `mes_dashboard:create_app()` app URI, prepend `src/` to `PYTHONPATH`
- `GunicornHarness`: pop `FLASK_ENV`/`FLASK_TESTING`/`PYTEST_CURRENT_TEST`, set `REDIS_ENABLED=true` before `Popen`
- `start_duckdb_prewarm()`: assert "background thread started", not "prewarm complete"
- `GunicornHarness`: set both `REGISTER_INTERNAL_METRICS=true` and `INTERNAL_METRICS_ENABLED=1` for `/internal/metrics`
- Playwright `page.route()` is LIFO: register catch-all routes first, specific routes last
- reject-history/reject-material specs: click submit in `beforeEach` before asserting `DetailTable` content
- Resilience specs: use `page.goto(...).catch(()=>{})`, not `page.request.post()` (`loginViaApi`) — not interceptable, throws ECONNREFUSED in CI
- Playwright no-server skip: FAST `<50`-char body pre-check (~5s) before any `waitForFunction`, not per-test full-timeout waits (N tests × timeout × retries stalls CI for tens of minutes); `pageRendered` itself must check app-specific content, not `bodyText.length > 100` — see docs/architecture/ci-workflow.md §Playwright CI-Safe Specs
- Async-gated route unit tests: mock `is_async_available()=True` + enqueue fn, not spool-hit mocks — CI has no Redis

<!-- cdd-kit:learnings:end -->
