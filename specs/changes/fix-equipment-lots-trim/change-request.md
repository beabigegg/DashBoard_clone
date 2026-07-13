# Change Request

## Original Request

User-reported symptom (query-tool "批次追蹤生產設備" / Equipment Lot Tracking tab): querying 21 work orders across 6 workcenter groups resolves equipment successfully ("找到 25 台設備 (資料區間 2025-01-19 ~ 2026-01-10)"), but the 生產紀錄 (production records) sub-tab renders the correct columns with zero rows. User asked: "並且查詢後怎呢會是有設備沒資料?" (why is there equipment found but no data?). User then said "四個都做" (do all four) in response to a proposed fix plan with four parts.

Confirmed root cause (via prior bug-fix-engineer investigation, not yet implemented): `src/mes_dashboard/sql/query_tool/equipment_lots.sql` selects `c.CONTAINERNAME` (from `DWH.DW_MES_CONTAINER`, an Oracle CHAR-padded column) without `TRIM()`, while the very next line already correctly does `TRIM(c.PRODUCTLINENAME) AS PRODUCTLINENAME`. 9 other SQL files in this codebase already `TRIM()` this same column. The frontend (`frontend/src/query-tool/composables/useLotEquipmentQuery.ts`, `queryLots()`/`queryRejects()`) does an exact-match client-side filter (`Set.has()`) comparing this untrimmed `CONTAINERNAME` against already-trimmed resolved lot names — every row fails the match deterministically. The equipment-resolution step succeeds because it compares inside Oracle, where CHAR blank-padding comparison semantics neutralize the same missing-TRIM defect.

Approved fix scope (all four parts requested by user):
1. Minimal fix: add `TRIM(c.CONTAINERNAME) AS CONTAINERNAME` in `equipment_lots.sql`.
2. Defensive frontend fix: add `.trim()` before `.toUpperCase()` in the `queryLots()`/`queryRejects()` exact-match filters in `useLotEquipmentQuery.ts`.
3. Architectural push-down: add an optional `container_names: List[str]` server-side filter to `get_equipment_lots()` (wired through both the sync route and the async RQ job path for parity), using `UPPER(TRIM(c.CONTAINERNAME)) IN (...)` — this also mitigates a related, separate bug where the frontend requests `per_page=9999` but the backend clamps to 500 (`QUERY_TOOL_DETAIL_MAX_PER_PAGE`), so narrowing before pagination avoids silently dropping relevant rows.
4. Regression tests on both backend (`tests/test_query_tool_service.py`, `tests/test_query_tool_routes.py`) and frontend (new test file for `useLotEquipmentQuery.ts`, none currently exists) proving CHAR-padded/case-variant `CONTAINERNAME` values are matched correctly after the fix.

This is an additive, backward-compatible change: one bug fix (missing TRIM) plus one new optional request field on an existing endpoint (`POST /api/query-tool/equipment-period`, `query_type='lots'`). No breaking changes, no new endpoints.

## Addendum (2026-07-09, post-fix real-world retest)

User restarted the service and re-ran the exact reported scenario (21 work orders, 6 workcenter groups, wide ~1-year date range). Confirmed via `logs/rq_query_tool_worker.log`: the TRIM fix and `container_names` push-down ARE live and working — the backend RQ job log shows `container_names=[...]` correctly forwarded and `Equipment lots: 1249 records` found. However, the 生產紀錄 sub-tab still showed "目前沒有資料".

**Second root cause found**: this query's wide date range causes the backend to classify it as an ASYNC query (dispatched to the `query-tool` RQ worker, returning HTTP 202 `{async: true, job_id, status_url, result_url}`). `frontend/src/query-tool/composables/useLotEquipmentQuery.ts`'s `fetchEquipmentPeriod()` (shared by `queryLots()`/`queryJobs()`/`queryRejects()`) has NO handling for this async envelope — it just returns the 202 body as if it were the final data, so `Array.isArray(payload?.data)` is false and the row list ends up empty, even though the backend already computed the correct result.

The sibling composable `frontend/src/query-tool/composables/useEquipmentQuery.ts` (the "設備生產批次追蹤" tab) already handles this correctly via the shared `pollJobUntilComplete()` helper (`frontend/src/shared-composables/useAsyncJobPolling.ts`) — `useLotEquipmentQuery.ts` needs the identical pattern added to its `fetchEquipmentPeriod()`.

This is being folded into the same change (not a new tracked change) because it directly blocks AC-2 ("production-records sub-tab renders non-empty rows... using the reported 21-work-order / 6-workcenter-group scenario shape") — the real-world scenario that motivated this whole change never actually completes without this fix, since it always falls on the async path.

## Business / User Goal

## Non-goals

## Constraints

## Known Context

## Open Questions

## Requested Delivery Date / Priority
