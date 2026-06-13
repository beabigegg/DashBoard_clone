# Change Classification

## Change Types
- primary: architecture-migration, api-behavior-change
- secondary: business-logic-change (compute relocation: cross-shift merge, job-bridge, category mapping moved server→browser), data-shape-change (raw parquet spool contract: base_events.parquet + job_bridge.parquet + taxonomy JSON), bug-fix (gunicorn worker OOM elimination), performance-change (instant local-SQL filtering)

## Risk Level
- high

Rationale: replaces the entire compute path of a released production page; changes the `/api/downtime-analysis/query` response contract; removes a deployed safety band-aid (90-day Oracle limit); relocates correctness-critical reductions (`_merge_cross_shift_events`, job overlap bridge) into browser SQL where ADR-0003 warns whole-dataset reductions are easy to silently corrupt. Contained to one page/module with an established working precedent (resource-history) and the OEE/prewarm cache layer is unchanged.

## Impact Radius
- cross-module

Spans backend routes/services (`downtime_analysis_routes.py`, `downtime_analysis_service.py`, `downtime_analysis_cache.py`), spool/data contract, the `downtime-analysis` frontend feature app, and shared frontend DuckDB infrastructure in `frontend/src/core/` (read-only reuse). Contained to the downtime-analysis vertical plus the shared core it consumes.

## Tier
- 0

## Architecture Review Required
- yes
- reason: Server→browser compute-architecture migration with changed API response contract, new data-shape (raw parquet spool) boundary, removal of deployed safety limit (90-day Oracle fallback), and relocation of full-dataset reductions (cross-shift merge, job-overlap bridge) that ADR-0003 explicitly flags as silent-corruption-prone. Module-boundary, data-flow, and rollback/compatibility trade-offs must be decided in `design.md` by `spec-architect` before `implementation-planner` runs. Design must also resolve: export (CSV) server-vs-browser-blob decision, fate of now-redundant `/view`/`/equipment-detail`/`/event-detail` endpoints, browser-memory ceiling for 184k-row parquet, parquet schema-versioning.

## Required Artifacts

Always required: `change-request.md`, `change-classification.md`, `implementation-plan.md`, `test-plan.md`, `ci-gates.md`, `tasks.yml`, `context-manifest.md`

Optional artifacts:

| artifact | create? | reason |
|---|---|---|
| current-behavior.md | yes | Prior server-side pandas pipeline must be captured as regression baseline for parity gate |
| proposal.md | no | Goal and target architecture are explicit in the change request |
| spec.md | no | Behavior parity is the requirement; captured in current-behavior + design |
| design.md | yes | Architecture Review Required = yes; spec-architect must decide module boundaries, API/data-shape contract, endpoint deprecation, export path, rollback, browser-memory ceiling |
| qa-report.md | yes | High-risk released-page migration; durable parity + OOM-elimination evidence needed |
| regression-report.md | yes | Existing released behavior replaced and deployed safety limit removed |
| visual-review-report.md | no | Views visually unchanged; route evidence to agent-log unless blocker found |
| monkey-test-report.md | no | Covered by E2E + data-boundary; promote only if fuzz finding needs durable prose |
| stress-soak-report.md | yes | OOM elimination is the stated purpose; load/soak evidence required |

## Required Contracts
- API: `contracts/api/api-contract.md` + `contracts/api/api-inventory.md` — `/query` response shape changes; `/view`/`/equipment-detail`/`/event-detail` become redundant (deprecate-2-minors policy); CHANGELOG entry required in `contracts/CHANGELOG.md`
- CSS/UI: no — no token or component styling change expected
- Env: conditional — only if a new env var gates browser-DuckDB cutover or parquet TTL; removing `_MAX_ORACLE_DAYS` (code constant, not env var) does not require env contract change; confirm during design
- Data shape: yes — `contracts/data/data-shape-contract.md` — new raw-parquet spool contract for `base_events.parquet` and `job_bridge.parquet` (column names/types) + taxonomy JSON shape; schema-versioning + post-deploy parquet-cleanup policy required
- Business logic: yes — `contracts/business/business-rules.md` — cross-shift merge and job-overlap bridge rules relocated to browser SQL; removal of 90-day query limit is a behavior-policy change
- CI/CD: conditional — only if browser-DuckDB E2E spec requires new Playwright/browser-install gate step

## Required Agents
1. spec-architect — author `design.md` BEFORE implementation-planner
2. contract-reviewer — verify api/data/business/conditional-env/ci contracts + CHANGELOG
3. test-strategist — AC→Test mapping, parity matrix on 184k-row fixtures
4. ci-cd-gatekeeper — `ci-gates.md` before implementation
5. implementation-planner — execution packet after all above are complete
6. backend-engineer — route response cutover, raw-parquet spool writer, taxonomy JSON, `_MAX_ORACLE_DAYS` removal
7. frontend-engineer — browser-DuckDB composable (useDowntimeDuckDB.ts) + view wiring
8. e2e-resilience-engineer — E2E parity + failure-injection + data-boundary tests (Tier 0)
9. monkey-test-engineer — adversarial inputs (Tier 0)
10. stress-soak-engineer — OOM-elimination load/soak evidence (Tier 0)
11. ui-ux-reviewer — confirm four views render unchanged (agent-log)
12. visual-reviewer — pixel-level view parity (agent-log)
13. qa-reviewer — release readiness, parity sign-off (qa-report.md)

## Inferred Acceptance Criteria
- AC-1: `POST /api/downtime-analysis/query` returns `{base_spool_url, jobs_spool_url, query_id, taxonomy}` and no longer returns server-pre-aggregated view payloads; each key is present and non-null for a valid query.
- AC-2: The server writes raw `base_events.parquet` and `job_bridge.parquet` spool files (no `_merge_cross_shift_events`/pandas reduction on the request path); the 3-month server-side DuckDB prewarm cache remains functional and unchanged.
- AC-3: Browser DuckDB-WASM reproduces byte/row-equivalent results to the prior Python pandas output for cross-shift merge, job-overlap bridge, KPI summary, BigCategory chart, DailyTrend chart, EquipmentDetail table, and EventDetail table on the 184k-row reference dataset.
- AC-4: Category taxonomy (`_map_big_category`) is delivered as JSON in the `/query` response and drives browser-side BigCategory aggregation identically to the prior server mapping.
- AC-5: A filter change on the loaded page executes entirely as local browser SQL and issues zero new API round-trips.
- AC-6: The 90-day Oracle fallback limit is removed — `_MAX_ORACLE_DAYS` and its check in `_validate_dates()` no longer exist, and a >90-day date range is accepted and served end-to-end.
- AC-7: Under the constrained 6 GB/no-swap profile, concurrent and large-range downtime queries do not OOM-kill gunicorn workers; browser-side compute stays within client memory limits with a graceful error on failure rather than a silent empty table.
- AC-8: CSV export continues to work via the design-selected path (server-side or browser blob), returning data equivalent to the prior export for the same query.

## Tasks Not Applicable
- 2.2 (CSS/UI contract): skipped — no token or component styling change; confirm with contract-reviewer
- Visual-review-report and monkey-test-report tasks: skipped (optional artifacts marked no)

## Clarifications / Assumptions
- Assumption: 90-day limit removal is in-scope (only safe to remove because the new browser architecture eliminates the OOM that motivated the band-aid).
- Assumption: 3-month server-side DuckDB prewarm cache is unchanged.
- Open question for design: fate of `/view`/`/equipment-detail`/`/event-detail` — deprecate-in-place vs remove now.
- Open question for design: CSV export path (server-side vs browser blob).
- Open question for design: browser-memory ceiling and fallback; parquet schema-versioning + post-deploy `rm` cleanup policy.
- Note (CLAUDE.md): `load_downtime_events` must be patched at definition site `mes_dashboard.services.downtime_analysis_cache.load_downtime_events`.
- Note (ADR-0003): cross-shift merge and job-bridge require full dataset; browser must load complete parquet before running these reductions.
