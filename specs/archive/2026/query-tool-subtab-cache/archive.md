# Archive: query-tool-subtab-cache

## Change Summary

Fixed a redundant-query bug in the query-tool 批次追蹤生產設備/設備生產批次追蹤 tabs: switching back to a sub-tab (生產紀錄/維修紀錄/報廢紀錄) that had already been queried under the current filter set re-issued the Oracle query instead of reusing the already-fetched rows. Added a cache-hit guard confined to `setActiveSubTab()` in both `useLotEquipmentQuery.ts` and `useEquipmentQuery.ts`, with cache invalidation wired generically into every filter-axis change (equipment_ids, container_ids/lot list, workcenter_groups, date range) via `invalidateQueryCache()`. Pure client-side, in-memory reuse of already-fetched Vue refs — no new caching infrastructure, no new endpoint, no persistent/cross-session storage. Zero API/data/business/CSS/CI contracts touched (same endpoints called, just fewer times).

## Final Behavior

Revisiting an already-queried sub-tab under an unchanged filter set redisplays cached rows instantly with no loading indicator and no new HTTP request/RQ job. Changing any filter axis invalidates all three sub-tabs' caches uniformly (via a shared `queried.*` flag reset), guaranteeing the next entry into any sub-tab re-queries and never displays stale pre-change data. An explicit user refresh always re-queries the active sub-tab even when filters are unchanged (cache-hit guard is confined to `setActiveSubTab()`, never leaks into `queryActiveSubTab()`/`queryLots()`/`queryJobs()`/`queryRejects()`).

## Final Contracts Updated

- None touched by the original implementation (client-side-only change, confirmed independently by both `change-classifier` and `ci-cd-gatekeeper`'s workflow path-filter analysis).
- This close-out (2026-07-13): `specs/changes/query-tool-subtab-cache/acceptance.yml` (new, ADR 0010) — human-authored acceptance oracle, two cases (revisit-same-filters-no-requery, filter_change_invalidates_cache). `interaction-design.md` (ADR 0012) drafted by `interaction-designer`, had zero Open Decisions; human explicit sign-off transcribed to `## Confirmed` and locked via `cdd-kit design confirm`. No interaction-design.md content edits were needed to pass the gate — the `data.data`/`empty dataset` citation failures were resolved entirely by the shared `contracts/data/data-shape-contract.md` heading fix and `contracts/api/api-contract.md` `EquipmentPeriodResponse` typing done as part of closing the sibling `fix-equipment-lots-trim` change (same underlying endpoint, `POST /api/query-tool/equipment-period`).

## Final Tests Added / Updated

- `frontend/tests/query-tool/useLotEquipmentQuery.test.js` (6 new tests) + `frontend/tests/query-tool/useEquipmentQuery.test.js` (7 new tests, new file) + 1 pinning test in `useLotDetail.pagination.test.js` — 29/29 in targeted files, 799/801 full suite (2 pre-existing skips).
- `frontend/tests/acceptance/query-tool-subtab-cache.test.js` (new, this close-out): ADR 0010 acceptance driver reusing the same `window.MesApi` boundary-fake convention as the sibling unit tests (fakes only the network boundary, never `useEquipmentQuery` itself), reading `input`/`expect` live from `acceptance.yml` via `frontend/tests/acceptance/acceptance.loader.ts` (new `js-yaml` devDependency — no new vulnerabilities introduced, confirmed via `npm audit`).

## Final CI/CD Gates

Tier-1 required gate only (`contract-driven-gates`) — confirms the zero-contract claim holds. No Tier 2-5 gate required (`ci-gates.md`): no backend/DB/Redis surface, no deploy-shape/env/infra change.

## Production Reality Findings

- `tier-floor-override` was correctly triggered and audited: a keyword scan matched `query`/`cache` from composable filenames and the change-id itself, flagging a mechanical tier-2-or-stricter floor requirement even though this is genuinely a tier-3 in-memory client change with no new caching infrastructure — the override with its documented reason was accepted by the gate as intended (recorded in `agent-log/audit.yml`).
- QA flagged (approved-with-risk) that the working tree commingled this change's diff with sibling `fix-equipment-lots-trim` in a shared file (`useLotEquipmentQuery.ts` had hunks from both) — a staging-hygiene risk, not a code defect, requiring hunk-level `git add -p` at commit time rather than a blanket commit.

## Lessons Promoted to Standards

None new for this change specifically — the two ADR 0012 citation-resolver lessons (exact-heading-text matching, no array-item traversal for Form-1 field citations) and the SQL-side Oracle CHAR TRIM() discipline lesson were already promoted during the sibling `fix-equipment-lots-trim` close (same underlying contract fix unblocked both changes' gates). See `specs/archive/2026/fix-equipment-lots-trim/archive.md` for the full evidence trail; `CLAUDE.md` "CDD Kit operations" / "Service architecture" sections already carry the promoted lines.

## Follow-up Work

None known. `useLotDetail.ts` was audited for the same `setActiveSubTab` re-query gap per AC-6 — result already recorded in `agent-log/frontend-engineer.yml` (no silent scope drop).

## Cold Data Warning

This archive is historical evidence. Current requirements live in `contracts/` and active project guidance (`CLAUDE.md`).
