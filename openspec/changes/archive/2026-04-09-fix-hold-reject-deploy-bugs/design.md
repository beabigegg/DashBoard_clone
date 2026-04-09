## Context

Three independent bugs affecting hold-detail navigation, reject-history data display, and Docker deployment reliability. All are isolated fixes with no cross-cutting architectural impact.

**Current state:**
- Hold detail (`hold-detail/App.vue:395`) uses `<a :href>` for the back link, which triggers a full page reload in portal-shell SPA context instead of using the router bridge.
- Reject history DuckDB WASM composable (`useRejectHistoryDuckDB.js:206`) omits `WORKFLOWNAME` from the `detailCols` array and row mapping, causing blank workflow cells when DuckDB mode activates (≥ 5,000 rows). The backend `reject_cache_sql_runtime.py:789` correctly includes this column.
- Docker deployment logs "failed to register..." during spool operations. Root cause needs confirmation via SQLite log store or container logs.

## Goals / Non-Goals

**Goals:**
- Fix hold-detail back navigation to reliably return to hold-overview in portal-shell context
- Display WORKFLOWNAME in reject-history detail table under DuckDB-WASM mode
- Diagnose and fix Docker "failed to register" spool error

**Non-Goals:**
- Refactoring the portal-shell navigation system
- Adding new columns or features to reject-history
- Changing the spool architecture or DuckDB runtime design

## Decisions

### D1: Hold detail — use click handler + `navigateToRuntimeRoute` instead of `<a href>`

The `<a :href="backToOverviewHref">` at `hold-detail/App.vue:395` causes a full browser navigation. In portal-shell, this reloads the entire SPA; during startup the dynamic routes aren't registered yet, and the fallback route redirects to `/` → first drawer page (WIP overview).

**Fix:** Replace the `<a>` tag with a `<button>` (or `<a>` with `@click.prevent`) that calls `navigateToRuntimeRoute('/hold-overview')`. This uses the shell router bridge (`window.__MES_PORTAL_SHELL_NAVIGATE__`) for SPA navigation without reload, and falls back to `window.location.href` for standalone mode.

**Alternative considered:** Keep `<a>` with href but add `@click.prevent` + programmatic navigation — this preserves the href for middle-click/right-click "open in new tab". This is the preferred approach for accessibility.

### D2: Reject history — add WORKFLOWNAME to DuckDB detail query

Add `'WORKFLOWNAME'` to the `detailCols` array in `useRejectHistoryDuckDB.js` `queryDetail()` (after `SPECNAME`, mirroring the backend column order at `reject_cache_sql_runtime.py:789`). Add the corresponding row mapping: `WORKFLOWNAME: row.WORKFLOWNAME != null ? String(row.WORKFLOWNAME).trim() : null`.

The parquet spool file already contains this column (written by `reject_dataset_cache.py:1430`), so the DuckDB SQL will find it.

**No alternative needed** — straightforward parity fix.

### D3: Docker deploy — diagnose via logs, then fix path or config

**Step 1: Diagnose.** Check the SQLite log store (admin dashboard → logs) or `docker logs <container>` for the exact "failed to register" message. The error is logged at:
- `query_spool_store.py:509` — `Failed to register spool file (query_id=...): <exception>`
- `spool_pipeline.py:109/137` — `failed to register stage/final spool`

The exception message will reveal whether it's a path error (`FileNotFoundError`, `OSError`), Redis error, or permission issue.

**Step 2: Fix based on diagnosis.** Likely causes:
- Spool directory not created for all namespaces — each service creates subdirectories under `QUERY_SPOOL_DIR`, but the parent must exist
- Cross-device move if temp files are written to `/tmp` but spool is on a different mount — `Path.replace()` fails across filesystems
- Redis unavailable at container startup (worker starts before Redis is ready)

**Deferred to implementation:** The fix depends on the actual error message. If it's a path issue, ensure `Dockerfile` creates all required directories. If it's a cross-device move, use `shutil.move` instead of `Path.replace`.

## Risks / Trade-offs

- **D1 risk: Standalone mode regression** → `navigateToRuntimeRoute` already handles standalone mode (falls back to `window.location.href`), so this is safe. The `<a>` tag with `@click.prevent` preserves right-click behavior.
- **D2 risk: Column missing from old parquet files** → If a cached spool was written before `WORKFLOWNAME` was added to `reject_dataset_cache.py`, the column would be missing from parquet. DuckDB would return NULL, which the row mapping handles gracefully (`null`). No risk.
- **D3 risk: Diagnosis may reveal a different root cause** → The fix is deferred until logs are checked. If the cause is different from expected, the implementation task will adapt.
