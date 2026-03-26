## Context

The codebase already has a working browser-side compute pattern:

- `reject-history` and `yield-alert-center` download Parquet spool files, load them into DuckDB-WASM in a Web Worker, and stop calling server `/view` endpoints for supplementary interactions.
- `resource-history` and `hold-history` already use two-phase query flows (`POST /query` + `GET /view`) and already persist query results as Parquet spool files on the server.
- `resource-history` and `hold-history` still prefer server-side derivation for supplementary interactions, which means repeated filter and pagination changes continue to consume Flask worker CPU and memory even though the primary data is already cached and spoolable.

This change extends the existing pattern to the next two pages that already satisfy the hard preconditions:

1. deterministic `query_id`
2. a cached/spooled primary dataset
3. repeatable supplementary view derivation
4. existing parity reference on the server

The change is cross-cutting because it touches page behavior, shared frontend runtime, backend response metadata, and quality gates.

## Goals / Non-Goals

**Goals:**

- Reduce repeated server-side `/view` computation for Resource History and Hold History after the initial Oracle query completes.
- Reuse the existing DuckDB-WASM/Web Worker foundation instead of inventing a second client-compute stack.
- Keep response contracts and page UX stable enough that browser-side compute is an optimization, not a functional fork.
- Preserve server `/view` implementations as compatibility and fallback paths.
- Add explicit parity and fallback verification so Python and browser implementations do not drift.

**Non-Goals:**

- Moving Oracle primary queries into the browser.
- Removing Resource History or Hold History `/view` endpoints.
- Re-architecting Reject History or Yield Alert behavior beyond extracting reusable patterns where beneficial.
- Offloading query-tool or material-trace workloads, which are not simple repeated view-derivation pages.
- Changing CSV export semantics in this change.

## Decisions

### 1. Prefer client-side view derivation only for existing two-phase, spool-backed report pages

Resource History and Hold History are the next targets because they already have `query_id`-based workflows and Parquet spools. This minimizes backend churn and makes server-side SQL/Pandas derivation available as a parity oracle.

Alternative considered:
- Generalize immediately to all heavy pages. Rejected because pages like query-tool and material-trace have multi-query orchestration and resolution workflows that do not fit the same model.

### 2. Activate local compute from the primary query response, not only after a later `/view` call

`resource-history` and `hold-history` already return initial results from `POST /query`. To avoid an extra server round trip just to discover local-compute eligibility, the backend should include `spool_download_url` and `total_row_count` in primary query responses when spool metadata exists. View responses should continue to expose equivalent metadata for fallback and compatibility.

Alternative considered:
- Keep spool metadata on `/view` only. Rejected because these pages do not require an immediate post-query `/view` call today, so local-mode activation would lag or require a new unnecessary request.

### 3. Keep one shared DuckDB client/worker runtime, but use page-specific compute composables

The worker bootstrap, request protocol, and Parquet registration are already shared. Resource History and Hold History should each implement page-specific local derivation modules because their shapes differ materially:

- Resource History: KPI, trend, heatmap, workcenter comparison, hierarchical detail
- Hold History: trend, reason pareto, duration distribution, paginated list

This keeps shared infrastructure thin while allowing each page to mirror its server semantics closely.

Alternative considered:
- A single generic SQL/view DSL for all pages. Rejected for now because the page-specific business rules and response shapes are too different, and the added abstraction would slow delivery.

### 4. Preserve server DuckDB/Pandas view paths as authoritative fallback and parity references

Server-side `apply_view()` implementations remain required. Browser-side compute is preferred when available, but the backend view path is still needed for:

- unsupported browsers
- spool download failures or expiry
- feature-flag rollback
- parity comparison during rollout

Alternative considered:
- Remove server view logic after frontend rollout. Rejected because it increases rollout risk and weakens operational fallback.

### 5. Use explicit activation gates before downloading large Parquet files in the browser

Local mode should activate only when all of the following are true:

- `spool_download_url` is present
- row-count threshold is met
- browser supports Worker + WebAssembly
- file-size or memory heuristics do not indicate likely client overload
- page-level feature flag is enabled

This mirrors the current reject/yield pattern and avoids replacing server load with client instability.

Alternative considered:
- Always prefer browser compute whenever a spool exists. Rejected because low-memory devices and large files would regress UX.

### 6. Treat parity tests as a first-class deliverable, not optional cleanup

Any logic moved into browser code must have a server reference and automated parity coverage. Existing parity patterns in the repo should be extended to Resource History and Hold History local derivation, including key formulas, buckets, ordering, pagination, and empty-state behavior.

Alternative considered:
- Rely on manual UI testing. Rejected because dual Python/JS business logic will drift without deterministic coverage.

## Risks / Trade-offs

- [Browser memory/CPU pressure on large Parquet files] -> Gate activation by row count, file size, browser support, and keep server fallback.
- [Python/JS logic drift] -> Add parity fixtures/tests that compare local compute outputs against server references.
- [Spool expiry during activation or later interactions] -> Detect `410 spool_expired`/`cache_expired`, tear down local mode, and re-run primary query with last committed filters.
- [Operational ambiguity during rollout] -> Use explicit page-level feature flags and response metadata that make the active computation path visible.
- [Initial query still costs the server] -> Accept this trade-off; the goal is to cut repeated supplementary derivation, not remove Oracle from the architecture.
- [Shared abstraction grows too generic too early] -> Share only transport/runtime pieces first; keep page logic explicit until a stable common shape emerges.

## Migration Plan

1. Add backend metadata exposure for Resource History and Hold History primary/view responses so the frontend can discover spool eligibility without changing response envelopes.
2. Implement page-specific DuckDB local-compute composables for Resource History and Hold History on top of the shared DuckDB client/worker.
3. Wire page orchestration so supplementary filters/pagination prefer local computation when activation succeeds, otherwise retain current `/view` behavior.
4. Add parity, fallback, and stress/performance coverage.
5. Roll out behind feature flags enabled in non-production first, then production.

Rollback strategy:

- Disable the new page-level feature flags and the pages revert to existing server `/view` behavior.
- Because server view code remains intact, rollback does not require schema or data migration.

## Open Questions

- Should Resource History and Hold History use the same activation row-count threshold as Reject/Yield, or page-specific thresholds based on derived view complexity?
- Should the backend include spool file size in response metadata so the frontend can make a better activation decision without probing the download?
- During rollout, do we want lightweight client-visible metadata showing `view_source=frontend|server` for support/debugging, or keep that internal to tests and logs?
