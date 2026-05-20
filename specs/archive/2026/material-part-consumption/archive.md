---
change-id: material-part-consumption
closed: 2026-05-20
tier: 1
status: closed
---

# archive.md — material-part-consumption

## Change Summary

Delivered the "原物料用量查詢" (Material Part Consumption) page as a complete new
report module. The feature adds a dedicated historical-analysis report for
factory engineers to query material part consumption by date range, granularity
(day/week/month/quarter), and product type (PJ_TYPE). The backend uses a
two-spool architecture (summary Parquet + detail Parquet) with DuckDB regrouping
for granularity switches — eliminating Oracle re-queries on every granularity
change. The frontend is a Vue3 SPA registered in the "查詢工具" drawer.

## Final Behavior

- Route `/material-consumption` is live in the "查詢工具" drawer.
- POST `/api/material-consumption/query` runs the Oracle summary SQL, caches to
  Parquet spool, and returns KPI + trend + type_breakdown.
- GET `/api/material-consumption/view` regrouped by DuckDB (week/month/quarter) in
  milliseconds; no Oracle re-query on granularity switch.
- POST `/api/material-consumption/detail` supports sync (≤30 k rows) and async RQ
  (>30 k rows, 202 + polling). Detail pagination is 20 rows/page.
- POST `/api/material-consumption/export` streams CSV from DuckDB in 5 k-row chunks.
- ConsumptionTrendChart shows one line per material_part (max 20 series).
- TypeBreakdownChart shows 100% stacked bar per material_part (percentage by part).
- DetailTable: LOT ID → CONTAINERNAME; date-only for midnight UTC records; 24 h
  timestamp for records with real time; pj_type labeled "TYPE"; 20 rows/page.
- MultiSelect dropdown in FilterPanel is not clipped (filter card has `overflow: visible`).

## Final Contracts Updated

- `contracts/api/material-consumption-api.md` — 7 new endpoints (filter-options,
  query, view, detail, detail/page, detail/job, export)
- `contracts/data/data-shape-contract.md §3.9` — summary + detail spool schemas
- `contracts/business/business-rules.md MC-01..MC-05` — granularity buckets,
  detail sync/async threshold, wildcard part filter, cache key without granularity,
  type filter via DuckDB only
- `contracts/css/ui-css-contract.md` — `.theme-material-consumption` CSS isolation
- `contracts/env/env-contract.md` — `MATERIAL_CONSUMPTION_WORKER_QUEUE` env var

## Final Tests Added / Updated

**Backend (pytest)**
- `tests/test_material_consumption_service.py` — 17 service unit tests (summary,
  view, detail sync/async, export, hash, cache paths)
- `tests/test_material_consumption_routes.py` — 14 route tests (all 7 endpoints,
  kwarg forwarding, 202 async, validation)
- `tests/routes/test_fuzz_routes.py` — fuzz coverage extended for new endpoints
- `tests/test_modernization_policy_hardening.py` — AC-8 assertions:
  asset_readiness_manifest key + drawer membership; drawer assertion updated
  from `drawer-2` → `drawer` when page was moved to 查詢工具
- `tests/stress/test_material_consumption_stress.py` — Tier 3 nightly stress
- `tests/integration/test_soak_workload.py` — Tier 4 weekly soak extension

**Frontend (vitest + playwright)**
- `frontend/src/material-consumption/__tests__/TrendChart.test.ts`
- `frontend/src/material-consumption/__tests__/useConsumptionQuery.test.ts`
- `frontend/src/material-consumption/__tests__/FilterPanel.test.ts`
- `frontend/tests/playwright/material-consumption.spec.ts` (6 E2E)
- `frontend/tests/playwright/material-consumption-resilience.spec.ts` (3 resilience)
- `frontend/tests/playwright/material-consumption-data-boundary.spec.ts` (4 boundary)

## Final CI/CD Gates

All Tier 1 gates green (CI confirmed): unit-mock-integration, frontend-unit,
css-governance, fuzz. Playwright gates defined in ci-gates.md; stress (Tier 3
nightly) and soak (Tier 4 weekly) configured in existing workflow discovery.

## Production Reality Findings (Surprises / Deviations)

1. **Granularity silently dropped by composable destructuring** — `useConsumptionQuery.ts`
   was doing `const { granularity: _g, ...postBody } = params` so the granularity was
   removed from the POST /query body. Post-implementation fix: pass `params` directly.

2. **Oracle DATE midnight UTC → 08:00:00 display in UTC+8** — `txn_date` fields stored
   as UTC midnight serialised as `"...T00:00:00"`. `new Date()` in a UTC+8 browser
   displayed as 08:00:00 for every record. Fix: inspect raw string time component
   (regex on `[T ]HH:MM:SS`) before any `Date()` call; return date-only when all
   time digits are "00".

3. **MultiSelect dropdown clipped by `.ui-card { overflow: hidden }`** — global
   tailwind.css sets `overflow: hidden` on every `.ui-card`. The filter panel card
   ancestor clipped the absolutely-positioned dropdown. Fix: add `filter-query-card`
   class to the filter panel wrapper; override `overflow: visible` in scoped CSS.

4. **Hardcoded drawer assertion drift** — `test_page_status_contains_material_consumption_in_drawer2`
   encoded `drawer-2` as a fixture. When the page was intentionally moved to `drawer`
   (查詢工具), the JSON was updated but the test was not, causing a CI failure.

5. **per_page default was 50, needed to be 20** — fixed in 3 places: service,
   duckdb_runtime, and composable.

## Lessons Promoted to Standards

| Lesson | Target | Location | Evidence |
|---|---|---|---|
| Oracle DATE midnight UTC → TZ shift in JS `Date()` | `CLAUDE.md` | New "Frontend Date Formatting Notes" section | `frontend/src/material-consumption/components/DetailTable.vue:58-81` |
| `.ui-card { overflow: hidden }` clips dropdowns | `contracts/css/css-contract.md` | New "Known Global Rule Interactions" section + Forbidden Practices; version bumped 1.2.1 → 1.3.0 | `frontend/src/styles/tailwind.css`; `frontend/src/material-consumption/style.css` |
| Drawer assertion drift in policy tests | `CLAUDE.md` | "Modernization Policy Artifact Notes" — new bullet | `tests/test_modernization_policy_hardening.py:86-97` |

## Follow-up Work

- CER-003 (PJ_TYPE column name resolution on Oracle) remains open; SQL tests for
  `_query_type_breakdown` are deferred until the column name is confirmed in DWH.
- Playwright E2E specs require a live staging environment; not run in CI currently.

## Cold Data Warning

This archive is historical evidence. Current requirements live in `contracts/` and active project guidance (`CLAUDE.md`/`CODEX.md`).
