# Archive: fix-equipment-lots-trim

## Change Summary

Fixed a bug in the query-tool "批次追蹤生產設備" (Equipment Lot Tracking) tab where equipment resolution succeeded ("找到 N 台設備") but the 生產紀錄 (production records) sub-tab rendered zero rows. Two independent root causes: (1) `equipment_lots.sql` selected `CONTAINERNAME` without `TRIM()`, so Oracle CHAR blank-padding broke the frontend's exact-match filter against already-trimmed resolved lot names; (2) `useLotEquipmentQuery.ts`'s `fetchEquipmentPeriod()` had no handling for the async 202 RQ-job envelope that wide-date-range queries get dispatched as, so the 202 body was treated as final data. Also added an optional `container_names` server-side push-down filter (narrows before the 500-row pagination clamp) and regression tests on both stacks.

## Final Behavior

`POST /api/query-tool/equipment-period` (`query_type=lots`) now returns CONTAINERNAME trimmed of Oracle CHAR padding, matching the sibling PRODUCTLINENAME treatment. The endpoint accepts an optional `container_names: string[]` field that narrows server-side via `UPPER(TRIM(c.CONTAINERNAME)) IN (...)` before pagination. The frontend now polls async (202) equipment-period responses to completion via the same `pollJobUntilComplete()` pattern already used by the sibling `useEquipmentQuery.ts` composable, so wide-date-range queries no longer silently render as empty.

## Final Contracts Updated

- `contracts/api/api-contract.md`: `POST /api/query-tool/equipment-period` request gained optional `container_names` field (schema-version 1.38.2 → 1.38.3, original implementation); response type later retyped from `GenericSuccessResponse` to new `EquipmentPeriodResponse` (schema-version → 1.39.0, this close-out) so ADR 0012 interaction-design.md field citations can resolve.
- `contracts/api/api-contract.md`: `POST /api/query-tool/lot-equipment-lookup` response retyped from `GenericSuccessResponse` to new `LotEquipmentLookupResponse` (same 1.39.0 bump), for the same reason.
- `contracts/data/data-shape-contract.md`: fixed `## 4. Invalid Data Behavior` → `## Invalid Data Behavior` (exact-heading-text bug, see Lessons below); added `non-empty dataset` condition row (schema-version → 1.38.0).
- `specs/changes/fix-equipment-lots-trim/acceptance.yml` (new, ADR 0010): human-authored acceptance oracle, case `production-records-nonempty-after-trim-fix` grounded in the real production numbers from this change's own `change-request.md` addendum (25 equipment resolved, 1249 lot records).
- `specs/changes/fix-equipment-lots-trim/interaction-design.md` (ADR 0012): full derivation chain drafted by `interaction-designer`; one Open Decision (state-loading/state-async-pending UX beyond a plain spinner) resolved by the user (Option A — plain spinner, matches shipped behavior) and locked via `cdd-kit design confirm`.

## Final Tests Added / Updated

- `tests/test_query_tool_service.py::TestGetEquipmentLots` (6 tests): CHAR-padded TRIM correctness, sibling SQL structural pin, non-empty rows, `container_names` filter semantics (SQL-level, not Python post-filter), backward compatibility when field omitted.
- `tests/test_query_tool_routes.py::TestEquipmentPeriodEndpoint`: `container_names` kwarg forwarding (per-kwarg assertion), pagination forwarding regression.
- `tests/integration/test_query_tool_rq_async.py::TestEquipmentPeriodLotsParity`: sync/async parity, including `inspect.signature(execute_query_tool_job).bind(**kwargs)` worker-signature check.
- `frontend/tests/query-tool/useLotEquipmentQuery.test.js` (3 tests): CHAR-padded/case-variant CONTAINERNAME regression, async-polling regression (mocked `pollJobUntilComplete`).
- `tests/acceptance/test_fix_equipment_lots_trim_acceptance.py` (new, this close-out): ADR 0010 acceptance driver — SQL-text structural pin for `TRIM(c.CONTAINERNAME)` (the mocked-boundary DB-execution-result pattern cannot represent CHAR padding, since Oracle's own TRIM() already ran before the mock boundary) + `get_equipment_lots()` row-count/non-empty proof at production scale, reading `input`/`expect` live from `acceptance.yml` (never hardcoded — cdd-kit gate's hardcoded-expect scanner enforces this, including in comments/docstrings).

## Final CI/CD Gates

Tier-1 required gates only (backend-tests, frontend-tests, contract-driven-gates, openapi-sync) — existing workflows fully cover this change's surface, no new workflow needed. No nightly/weekly/manual-dispatch gate required (`ci-gates.md`).

## Production Reality Findings

- The originally reported bug had **two independent root causes**, discovered sequentially: the TRIM fix alone did not resolve the user's real-world retest (`logs/rq_query_tool_worker.log` showed `Equipment lots: 1249 records` found server-side, but the sub-tab still rendered empty) — the async-polling gap was a second, separate defect only surfaced by re-testing against real production data/log volume after the first fix shipped.
- `get_equipment_lots()`'s `total` field reflects the full matched-record count even when the returned page is clamped to `QUERY_TOOL_DETAIL_MAX_PER_PAGE` (500) — discovered while writing this change's acceptance driver (initial driver asserted `len(data) == total`, which fails once total exceeds the pagination clamp; the correct assertion is `total == <full count>` and `len(data) > 0`).

## Lessons Promoted to Standards

Reviewed by `contract-reviewer` (2026-07-13). All three classified promote-to-guidance (no contract schema-version bump needed — contract-level facts already correctly recorded in `contracts/data/data-shape-contract.md` and `contracts/CHANGELOG.md`); added to `CLAUDE.md`:

1. **CDD Kit operations**: "ADR 0012 `data-shape: <condition>` citation resolver requires exact heading text `## Invalid Data Behavior` (no numeric prefix) — see `contracts/data/data-shape-contract.md` heading comment." Evidence: `contracts/data/data-shape-contract.md` heading-comment (added this close-out), `contracts/CHANGELOG.md` `[data 1.38.0]`.
2. **CDD Kit operations**: "ADR 0012 Form-1 field citations can't traverse `type: array` items — cite the array field itself (e.g. `data.data`), put per-column type/nullability in the rationale text pointing at `data-shape-contract.md` instead." Evidence: `specs/changes/fix-equipment-lots-trim/interaction-design.md` Presented Information table.
3. **Service architecture**: "New SQL SELECT columns from Oracle CHAR fields: `TRIM()` each one explicitly — don't assume it follows an adjacent already-trimmed sibling column (`equipment_lots.sql` lacked `TRIM(CONTAINERNAME)` next to `TRIM(PRODUCTLINENAME)`)." Evidence: `tests/test_query_tool_service.py::TestGetEquipmentLots::test_equipment_lots_sql_trims_containername_like_productlinename`.

Confirmed distinct from the existing CLAUDE.md line "Oracle `CHAR` column lookups: `strip()` at both dict-build and per-record lookup" (that covers Python-side post-fetch handling; lesson 3 above covers SQL-side `TRIM()` in the query text itself).

## Follow-up Work

None known. `materials`/`jobs`/`status_hours` query sub-types do not get `container_names` (lots-only per AC-4/change-request scope) — not a defect, an intentional scope boundary already documented in `test-plan.md`.

## Cold Data Warning

This archive is historical evidence. Current requirements live in `contracts/` and active project guidance (`CLAUDE.md`).
