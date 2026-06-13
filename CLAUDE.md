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

## Context Governance

For context-governed changes, read `specs/changes/<change-id>/context-manifest.md` before using file-reading or broad search tools.

- Read only paths allowed by the manifest or approved expansions.
- If more context is needed, stop and write a Context Expansion Request in the manifest (`cdd-kit context request`).
- The full agent-log format (including `files-read:` schema) is defined in
  `~/.claude/skills/contract-driven-delivery/references/agent-log-protocol.md`.
  Read that once; do not paraphrase it elsewhere.

<!-- cdd-kit:learnings:start -->
### Promoted Learnings

**CDD Kit operations** — see `docs/cdd-kit-patterns.md` for full detail:
- Keep local cdd-kit in sync with CI (no version pin → always installs latest); upgrade after any `spec traceability` CI failure — see docs/cdd-kit-patterns.md
- `ci-gates.md` must contain literal "workflow" / "promotion policy" / "rollback policy" section headers or `cdd-kit gate` fails — see docs/cdd-kit-patterns.md
- Section-6 tasks: 6.2/6.3 may be `done` when Tier-1 passes locally; 6.4 `skipped` when no nightly/weekly gates defined — see docs/cdd-kit-patterns.md
- Version entries must go to `contracts/CHANGELOG.md` only — `cdd-kit validate --versions` never checks individual contract files — see docs/cdd-kit-patterns.md
- `context-manifest.md` Allowed Paths must use directory-level paths, not glob patterns — see docs/cdd-kit-patterns.md

**Frontend patterns** — see `docs/architecture/frontend-patterns.md` for full detail:
- TS migration complete; `portal-shell/` non-entry modules and `main.js` entry points intentionally remain JS — see docs/architecture/frontend-patterns.md
- Node ≥22.6 required (`node --experimental-strip-types` parity tests) — see docs/architecture/frontend-patterns.md
- vue-echarts: bind `@click` on `<VChart>`, not imperative `.on()` — wrapper handles lifecycle cleanup — see docs/architecture/frontend-patterns.md
- `MultiSelect.vue` is shared by 12 apps; changes must be additive; grep consumers before editing — see docs/architecture/frontend-patterns.md
- Snapshot-diff filter composables must re-sync `_lastCommitted` from `selection` after every `fetchFilterOptions` — see docs/architecture/frontend-patterns.md
- Oracle DATE midnight UTC columns: inspect H/M/S via regex before `new Date()` to avoid ±8h TZ shift — see docs/architecture/frontend-patterns.md
- WAI-ARIA combobox close must `nextTick(() => triggerEl.focus())` to return keyboard focus — see docs/architecture/frontend-patterns.md

**CSS architecture** — see `docs/architecture/css-patterns.md` and `contracts/css/css-contract.md`:
- All feature CSS must be scoped under `.theme-<name>`; unscoped rules bleed permanently (enforced by `css:check` Rule 6) — see docs/architecture/css-patterns.md
- CSS source fixes require `npm run build`; hashed dist filenames orphan stale named files — see docs/architecture/css-patterns.md
- `<Teleport to="body">` breaks descendant selectors; wrap content in thin `<div class="theme-<feature>">` — see contracts/css/css-contract.md rule 4.4
- `resource-shared/styles.css` `:is()` groups must include every portal-shell page theme; use `sed` batch replace — see contracts/css/css-contract.md rule 4.5

**Cache & spool patterns** — see `docs/architecture/cache-spool-patterns.md` for full detail:
- Pre-warm cache namespace must exactly match the key pattern user queries read — see docs/architecture/cache-spool-patterns.md
- Multi-worker gunicorn startup: use file-based exclusive lock (`O_CREAT|O_EXCL` sentinel) for Oracle load tasks — see docs/architecture/cache-spool-patterns.md
- Parquet schema breaking changes: add `rm` to rollback runbook AND bump `_SCHEMA_VERSION` in same commit — see docs/architecture/cache-spool-patterns.md
- Multi-parquet spool: validate all interdependent files atomically before serving any (DA-11) — see contracts/business/business-rules.md §DA-11
- DuckDB prewarm TTL: use per-service env var (default 72000 s), never `CACHE_TTL_DATASET` — see contracts/env/env-contract.md §Cache Tuning
- query-tool has no persistent spool — skip parquet cleanup in all rollbacks — see docs/architecture/cache-spool-patterns.md
- hold-history spool: use `DESCRIBE`-based column detection for live schema compat without forced purge — see docs/architecture/cache-spool-patterns.md
- SQL-to-API rename layer at route boundary absorbs column renames; audit it before touching frontend — see docs/architecture/cache-spool-patterns.md
- SyncWorker: `COUNT > 0` guard before `TRUNCATE`/`DELETE`; version `REPLACE` still runs even when skipped — see docs/architecture/cache-spool-patterns.md
- `/api/resource/status/options` has its own inline filter dict independent of `query_resource_filter_options()` — see docs/architecture/cache-spool-patterns.md
- Oracle `CHAR` column lookups: apply `strip()` at both dict-build and per-record lookup — see docs/architecture/cache-spool-patterns.md
- Type-A spool frontend: read the route's `success_response(...)` call for exact JSON wrapper key — see docs/architecture/cache-spool-patterns.md
- Canonical spool: implement two-phase key resolution (superset warmup reuse + exact-match Oracle fallback) — see docs/architecture/cache-spool-patterns.md
- `spool_routes._ALLOWED_NAMESPACES`: add namespace AND parametrize test in the same PR as the spool write — see docs/architecture/cache-spool-patterns.md
- BatchQueryEngine `ROW_NUMBER()` chunking is incompatible with cross-row reductions; classify at design time — see docs/adr/0003-downtime-rowcount-chunking-exclusion.md
- Type B async: when inner fn can't accept `progress_callback`, use coarse bracket milestones 5→15→90→100 bracketing the call; avoid hash-mirroring unless per-chunk granularity is required — see docs/architecture/cache-spool-patterns.md

**Service architecture** — see `docs/architecture/service-patterns.md` for full detail:
- `downtime_analysis_service`: patch `load_downtime_events` at definition site (`downtime_analysis_cache`), not the service module — see docs/architecture/service-patterns.md
- `_get_wip_search_index`: new filter fields must be added in BOTH incremental and full-rebuild paths — see docs/architecture/service-patterns.md
- `rq_monitor_service` module-level import: patch at service boundary (`get_rq_monitor_summary`), not `redis_client` — see docs/architecture/service-patterns.md
- `QueryBuilder`: two independent `IN`-list builders require counter-forwarding between them — see docs/architecture/service-patterns.md
- `_PARTIAL_NONKEY_COLS_LOT`: add new non-key column atomically with SQL change; pin with membership test — see docs/architecture/service-patterns.md
- SQL CTE changes: update both the CTE SELECT list and the outer SELECT (two-location edits) — see docs/architecture/service-patterns.md
- SQL-frontend column gap: cross-check SQL output against Vue template rendering, not just the route response — see docs/architecture/service-patterns.md
- AI pipeline `raw_params` callables: require `dispatch: raw_params` flag in `ai_functions.yaml` — see docs/architecture/service-patterns.md
- AI pipeline `advance_query_state`: pops entire `_SESSION_STORE`; extract/restore cross-turn state before/after — see docs/architecture/service-patterns.md
- `_AI_SESSION` is a module-level `requests.Session`; patch at `ai_query_service._AI_SESSION`, not `requests.post` — see docs/architecture/service-patterns.md

**MES domain semantics:**
- `LOTWIPHISTORY.TRACKINQTY` is remaining-qty-per-partial (decrements across partials); use only `TRACKINTIMESTAMP` as session key — see contracts/business/business-rules.md §PH-06

**Modernization policy** — see `docs/architecture/modernization-policy.md` for full detail:
- Page add/remove: update BOTH `asset_readiness_manifest.json` AND `route_scope_matrix.json` in `docs/migration/` — see docs/architecture/modernization-policy.md
- `data/page_status.json`: manually delete page entry on code removal (never auto-updated by code deletion) — see docs/architecture/modernization-policy.md
- `drawer_id` change in `page_status.json`: update corresponding test assertion and rename method — see docs/architecture/modernization-policy.md

**Test coverage discipline** — see `docs/architecture/test-discipline.md` for full detail (8 rules against silent-drop filter bugs):
- Use `call_args.kwargs[key]` per-kwarg assertions, not `assert_called_once_with()` whitelist — see docs/architecture/test-discipline.md
- Assert route forwarding per-kwarg with non-default values — see docs/architecture/test-discipline.md
- Test BOTH snapshot and Oracle fallback paths for every filter kwarg — see docs/architecture/test-discipline.md
- Filter fixtures must include every column the function filters on — see docs/architecture/test-discipline.md
- Cross-filter narrowing has its own test surface: assert "selecting A narrows B" — see docs/architecture/test-discipline.md
- Module-level constants: `monkeypatch.setattr()` not `setenv` (frozen at import); module-level side-effects (e.g. `register_job_type()`): use `importlib.reload()` after clearing the dict to re-run registration — `setattr` alone does not re-execute them — see docs/architecture/test-discipline.md
- Env-var contract tests must pin default values, not just assert var name presence — see docs/architecture/test-discipline.md
- Check `pytestmark` before adding mock tests to `tests/integration/` — see docs/architecture/test-discipline.md
- Use `ast.parse()` + walk `ast.Call` to prove absence of removed startup calls — see docs/architecture/test-discipline.md
- Partial-trackout fixtures: include rows with different `TRACKINQTY` per session (real arithmetic) — see docs/architecture/test-discipline.md

**CI workflow & GunicornHarness** — see `docs/architecture/ci-workflow.md` for full detail:
- New Playwright specs: add `npx playwright install --with-deps chromium` step in CI before running tests — see docs/architecture/ci-workflow.md
- `GunicornHarness`: use `mes_dashboard:create_app()` app URI and prepend `src/` to `PYTHONPATH` — see docs/architecture/ci-workflow.md
- `GunicornHarness`: pop `FLASK_ENV`/`FLASK_TESTING`/`PYTEST_CURRENT_TEST`, set `REDIS_ENABLED=true` before `Popen` — see docs/architecture/ci-workflow.md
- `start_duckdb_prewarm()`: assert "background thread started" sentinel, not "prewarm complete" — see docs/architecture/ci-workflow.md
- `GunicornHarness`: set both `REGISTER_INTERNAL_METRICS=true` and `INTERNAL_METRICS_ENABLED=1` for `/internal/metrics` — see docs/architecture/ci-workflow.md

<!-- cdd-kit:learnings:end -->
