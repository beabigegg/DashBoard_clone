# Archive: resource-status-package-group

> **Cold Data Warning**: This archive is historical evidence. Current requirements live in `contracts/` and active project guidance.

## Change Summary

Added Package Group (封裝群組) information to the 設備及時概況 (`/portal-shell/resource`) page. Data is sourced by joining `DW_MES_EQUIPMENTSTATUS_WIP_V.RESOURCEID` → `DW_MES_RESOURCE.PACKAGEGROUPID` → `DW_MES_RESOURCE_PACKAGEGROUP.PACKAGEGROUPNAME`. A 46-row in-process lookup dict was added to `resource_cache.py` with an independent 7-day TTL (separate from the existing 24h resource-cache cycle) to serve live package group data without introducing a new Oracle query on every request.

## Final Behavior

- **FilterBar**: New 封裝群組 MultiSelect filter; `package_groups` param forwarded via GET CSV to `/status`, `/summary`, `/matrix`, and surfaced from `/status/options`.
- **EquipmentCard**: PACKAGEGROUPNAME text row rendered below 位置; hidden (`v-if`) when null (covers ~91% of resources with NULL PACKAGEGROUPID).
- **MatrixSection**: Package dimension column appended after OU% column.
- **FloatingTooltip** (pre-existing bug fixed): `<Teleport to="body">` moved the tooltip DOM outside `.theme-resource`, making all scoped CSS non-matching. Fixed by wrapping teleported content in `<div class="theme-resource">` ancestor.

## Final Contracts Updated

| Contract | Version | Change |
|---|---|---|
| `contracts/api/api-contract.md` | 1.9.0 → 1.10.0 | 4 resource endpoints updated; `package_groups` param + `PACKAGEGROUPNAME` field documented |
| `contracts/api/api-inventory.md` | 1.1.8 → 1.1.9 | resource_routes.py inventory entry updated |
| `contracts/data/data-shape-contract.md` | 1.8.0 → 1.9.0 | §3.10 added: PACKAGEGROUPNAME field, NULL semantics, filter semantics |
| `contracts/css/css-contract.md` | 1.3.0 → 1.4.0 | Resource-Status UI Surface Rules section added |

Evidence: `agent-log/backend-engineer.yml` artifacts; `contracts/CHANGELOG.md` entries dated 2026-05-21.

## Final Tests Added / Updated

**Backend** (evidence: `agent-log/backend-engineer.yml`):
- `tests/test_resource_cache.py::TestPackageGroupLookup` — 6 new tests (dict build, TTL independence, CHAR normalization, sorted list, NULL pgid, trailing space strip)
- `tests/test_resource_service.py::TestGetMergedResourceStatusPackageGroup` — 8 new tests (name resolution, null id, dict miss, filter exclude, filter exclude null, warm-cache path, oracle-fallback path)
- `tests/test_resource_service.py::TestQueryResourceFilterOptions` — 2 new tests (returns list, excludes null entries)
- `tests/test_resource_routes.py` — 5 new tests (per-kwarg forwarding on /status /summary /matrix, options field, multi-value CSV split)

**Frontend** (evidence: `agent-log/frontend-engineer.yml`):
- `frontend/tests/legacy/resource-status.test.js` — 7 new tests for FilterBar, EquipmentCard, MatrixSection package group behavior

Final counts: 82/82 backend, 413/413 frontend (vitest), 22/22 contract tests.

## Final CI/CD Gates

| Gate | Tier | Command |
|---|---|---|
| contract-validate | 0 | `cdd-kit validate` |
| backend-unit | 1 | `pytest tests/test_resource_cache.py tests/test_resource_service.py tests/test_resource_routes.py` |
| frontend-unit | 1 | `cd frontend && npm run test` |
| css-governance | 1 | `cd frontend && npm run css:check` |
| contract-tests | 1 | `pytest tests/test_api_contract.py tests/test_resource_routes.py::test_resource_status_options_returns_package_groups_field` |
| type-check | 2 (informational) | `cd frontend && npm run type-check` |

No new workflow files. All gates run under existing `backend-tests.yml` / `frontend-tests.yml` / `contract-driven-gates.yml`. CI PASS confirmed on commit `590c3ef`.

## Production Reality Findings

- **`/status/options` route has its own inline dict** and does NOT call `query_resource_filter_options()`. Adding `package_groups` required patching both the service function and the inline route dict independently. This was not obvious from reading the service layer alone.
- **CHAR column key normalization**: Oracle `PACKAGEGROUPID` is a CHAR column; both the dict-build path and the per-record lookup path require `str(pgid).strip()` to avoid silent key misses.
- **FloatingTooltip Teleport CSS bug** (pre-existing, surfaced during testing): `<Teleport to="body">` renders outside the feature CSS scope. The fix is a thin `<div class="theme-resource">` wrapper around the teleported content — no CSS changes needed.

## Lessons Promoted to Standards

| # | Lesson | Target | Evidence |
|---|---|---|---|
| 1 | `/api/resource/status/options` has its own inline dict, independent of `query_resource_filter_options()` — patch both independently | `CLAUDE.md` § Cache Architecture Notes | `agent-log/backend-engineer.yml`; `resource_routes.py:352-385` |
| 2 | Oracle CHAR lookup dicts: apply `str(value).strip()` at both dict-build time AND per-record lookup | `CLAUDE.md` § Cache Architecture Notes | `test_resource_cache.py::test_package_group_lookup_char_trailing_space` |
| 3 | `<Teleport to="body">` breaks `.theme-<feature> .component` CSS; fix with thin `<div class="theme-<feature>">` wrapper | `contracts/css/css-contract.md` rule 4.4 (1.4.0 → 1.5.0) + `CLAUDE.md` § Portal-Shell CSS Architecture Notes | `FloatingTooltip.vue` fix commit 590c3ef |

## Follow-up Work

None identified. Package column position (after OU%) and label (封裝群組) are final per ui-ux-reviewer approval.
