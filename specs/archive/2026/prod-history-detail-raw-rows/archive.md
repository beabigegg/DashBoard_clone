---
change-id: prod-history-detail-raw-rows
status: closed
closed-on: 2026-05-14
tier: 2
---

# Archive: prod-history-detail-raw-rows

## Change Summary

Tier 2 data-model change: production-history detail query rewritten to return one row per LOTWIPHISTORY partial track-out instead of aggregated MIN/MAX/SUM per (container, …, equipment) group. PJ_FUNCTION column added to spool schema as pre-staging for Change 3 filter UI. Goal: eliminate detail-data ambiguity (multi-partial containers, mid-flow re-batching) by exposing raw values to the user.

## Final Behavior

- Detail query (`/api/production-history/query`, `/api/production-history/page`) returns N rows per multi-partial container; each row is one raw LOTWIPHISTORY track-out event.
- Aggregated SQL aliases (`TRACKIN_TS`, `TRACKOUT_TS`, `TRACKIN_QTY`, `TRACKOUT_QTY`) removed; raw Oracle column names (`TRACKINTIMESTAMP`, `TRACKOUTTIMESTAMP`, `TRACKINQTY`, `TRACKOUTQTY`) are now contract-of-record at the spool layer. Backend's snake_case JSON API keys preserved for frontend backward compat (`trackin_time`, `trackout_time`, `trackin_qty`, `trackout_qty`).
- Spool parquet schema gains `PJ_FUNCTION` column (15 columns total per data-shape §3.4). Carried through Oracle → spool → DuckDB → CSV export.
- Matrix lot-count semantics unchanged: `COUNT(DISTINCT CONTAINERNAME)` in DuckDB; empirically equal to prior aggregated lot count per (WC, Spec, Equipment × Month) cell.
- Detail table sort: `TRACKINTIMESTAMP ASC NULLS LAST, CONTAINERNAME`. No "partial #" column (Resolved Decision 2 of change-request).
- Frontend `ProductionDetailTable.vue` adds "PJ Function" column between BOP and WorkOrder, matching CSV export order.

## Final Contracts Updated

- `contracts/data/data-shape-contract.md` §3.4 Production-History Detail Row added (15 columns + row-grain rule + Matrix `COUNT(DISTINCT)` semantics). Schema-version bumped 1.0.2 → 1.1.0.
- `contracts/business/business-rules.md` Production-History Rules group added (PH-01..PH-04). Schema-version bumped 1.1.0 → 1.2.0.
- `contracts/CHANGELOG.md` entries for `data 1.1.0` and `business 1.2.0`.

## Final Tests Added / Updated

- `tests/test_production_history_sql_runtime.py` — 13 new tests across 4 new test classes:
  - `TestMainQueryRowGrain` — no GROUP BY, raw columns, PJ_FUNCTION present
  - `TestDetailPagePjFunction` — pj_function key in API response
  - `TestExportColumns` — CSV "Function" column + raw column names
  - filter-where raw column usage tests
- Total production-history pytest: 75/75 (62 pre-existing + 13 new)
- Frontend tests: no rebase required (validation tests check envelope only; abort tests have no column-name assertions)

## Final CI/CD Gates

All seven PR-required gates green on CI (commit b303e6a):
- `npm run type-check` — 0 errors
- `npm run build` — 15.07s
- `npm run test` (vitest) — 302/302 (30 files)
- `pytest tests/test_production_history_*.py` — 75/75
- `pytest tests/test_frontend_*_parity.py tests/test_job_query_frontend_safety.py` — 10/10
- `npm run css:check` — 0 errors
- `cdd-kit validate --contracts` — passed

Manual gates resolved during qa-reviewer (2026-05-14, live measurement against running gunicorn):
- AC-7 latency: warm query p95 81ms; pagination p95 30ms
- AC-7 spool: 25,103 bytes / 555 rows / 116 distinct containers / 4.78× partial expansion ratio
- AC-3 Matrix parity: 72/72 cells match (0 diverging) — NEW `COUNT(DISTINCT CONTAINERNAME)` per cell == OLD-equivalent GROUP BY row count per cell

## Production Reality Findings

1. **PJ_FUNCTION availability already proven elsewhere in codebase**: backend-engineer found `c.PJ_FUNCTION` already in production SQL at `src/mes_dashboard/sql/reject_history/performance_daily_lot.sql:31`, `src/mes_dashboard/sql/yield_alert/reason_detail.sql:29`, `src/mes_dashboard/sql/wip/detail.sql:23`. The classifier's flagged "BLOCKING precheck" turned out to be already satisfied by existing code — no fixture-level verification was required.

2. **Frontend alias rename audit was a no-op**: frontend-engineer found zero occurrences of old aggregated aliases (`TRACKIN_TS / TRACKOUT_TS / TRACKIN_QTY / TRACKOUT_QTY`) in frontend code. Backend's existing pandas/DuckDB rename map at `production_history_sql_runtime.py:184-205, 242-251` already converts raw column names to the snake_case JSON keys that frontend's `DetailRow` interface uses. Only the new `pj_function` key needed adding to the interface.

3. **Empirical 4.78× partial expansion on a 7-day × 3-pj_type window**: not the worst case but representative of typical traffic. Per-row size ≈ 45 B (parquet compression); PJ_FUNCTION added < 2 B/row. Worst case observed in fixture: GA26032432-A02 with 15 partials. Total spool inflation factor ≈ 5–7× over old aggregated grain; well within MEMORY_GUARD budget — no `_meta.truncated` triggered on the measured window.

4. **Cold first-query latency 15.7s** for a 3-pj_type × 7-day window. Subsequent warm queries (DuckDB spool hit) p95 = 81ms. This is consistent with the documented cache pattern; not a regression.

5. **Spool schema breaking change requires deploy-time cleanup**: existing `tmp/query_spool/production_history/*.parquet` files have OLD column names. The deploy runbook must include `rm tmp/query_spool/production_history/*.parquet` (documented in ci-gates.md §Rollback step 4 and qa-report.md Recommendation 3).

## Lessons Promoted to Standards

Two durable lessons promoted to `CLAUDE.md` §Cache Architecture Notes:

1. **Spool schema breaking changes require post-deploy parquet cleanup** — generalizable deploy-runbook rule for any spool-based service. Evidence: ci-gates.md §Rollback step 4 + qa-report.md Recommendation 3 + Production Reality Finding #5.
2. **Backend SQL-to-API rename layer isolates frontend from Oracle column renames** — audit-first guidance for future per-app Oracle column renames. Evidence: agent-log/frontend-engineer.yml (zero alias hits) + agent-log/backend-engineer.yml (rename map at production_history_sql_runtime.py:184-205, 242-251) + Production Reality Finding #2.

`cdd-kit validate --contracts` + `cdd-kit context-scan` run after promotion.

## Follow-up Work

- **Change 3 (`prod-history-first-tier-cache-filters`)**: scaffolded but not yet started. Surfaces Package/BOP/PJ_FUNCTION as first-tier dropdown filters (cache-backed) plus 工單號/LOT ID/Wafer LOT as multi-line + `*` wildcard filters. PJ_FUNCTION column carried by this change is the pre-staging for the dropdown source.
- **Production deploy runbook**: include the spool parquet cleanup step before the next deploy.

## Cold Data Warning

This archive is historical evidence. Current requirements live in `contracts/` and active project guidance (`CLAUDE.md`).
