# Contracts Changelog

All notable contract surface changes belong here.
Format: Keep-a-Changelog (https://keepachangelog.com/).
Versions are semantic per contract type.

While a contract is at 0.x (draft), entries here are optional.
Once a contract reaches 1.0.0, every schema-version bump must have
a corresponding entry below.

## [data 1.0.1] — 2026-05-13
### Added (additive)
- Section 2.5: WIP Filter-Options Response shape documenting `workflows`, `bops`, `pjFunctions` arrays alongside existing arrays. All three are new additive fields from change `wip-hold-drilldown-filters`.
- Section 3.1.1: WIP Detail Lot Row sub-table with explicit column list; adds `pjType` (nullable string, from DB `PJ_TYPE`) as additive new field.
- Source: change `wip-hold-drilldown-filters`.

## [api 1.2.1] — 2026-05-13
### Added (additive)
- Section 10 Compatibility Note: documents three new optional query params (`workflow`, `bop`, `pj_function`) accepted by `/api/wip/overview/summary`, `/api/wip/overview/matrix`, `/api/wip/detail/<workcenter>`, `/api/wip/meta/filter-options`; `pjType` addition to lot rows; `workflows`/`bops`/`pjFunctions` addition to filter-options response.
- Source: change `wip-hold-drilldown-filters`.

## [api-inventory 1.1.1] — 2026-05-13
### Changed (additive)
- `wip_routes.py` scope line extended to document new optional params `workflow`/`bop`/`pj_function`, `pjType` lot field, and `workflows`/`bops`/`pjFunctions` filter-options arrays.
- Compatibility Notes: new entry for wip-hold-drilldown-filters additive changes.
- Source: change `wip-hold-drilldown-filters`.

## [ci 1.3.8] — 2026-05-13
### Changed
- Gate Compatibility Note added for `migrate-qc-gate-ts` (Phase 3 item #17). `tsconfig.json` `include` expanded with `"src/qc-gate/**/*"`, covering `main.ts`, `App.vue`, `composables/useQcGateData.ts`, `components/LotTable.vue`, `components/QcGateChart.vue`. Gate tier unchanged (informational). Additive prose only.
- Source: change `migrate-qc-gate-ts` Phase 3.

## [ci 1.3.7] — 2026-05-13
### Changed
- Gate Compatibility Note added for `migrate-wip-hold-ts` (Phase 3). `tsconfig.json` `include` expanded with `"src/wip-overview/**/*"`, `"src/wip-detail/**/*"`, `"src/hold-overview/**/*"`, `"src/hold-detail/**/*"`. Gate tier unchanged (informational). Additive prose only.
- Source: change `migrate-wip-hold-ts` Phase 3.

## [ci 1.3.6] — 2026-05-12
### Changed
- Gate Compatibility Note added for `migrate-hold-history-ts` (Phase 3 item #2). `tsconfig.json` `include` expanded with `"src/hold-history/**/*"`. Gate tier unchanged (informational). Additive prose only.
- Source: change `migrate-hold-history-ts` Phase 3.

## [ci 1.3.5] — 2026-05-12
### Changed
- Gate Compatibility Note added for `migrate-reject-history-ts` (Phase 3 item #1). `tsconfig.json` `include` expanded with `"src/reject-history/**/*"`. Gate tier unchanged (informational). Additive prose only.
- Source: change `migrate-reject-history-ts` Phase 3.

## [ci 1.3.4] — 2026-05-12
### Changed
- Gate Compatibility Notes: `frontend-type-check` Phase 1f scope expansion documented — `tsconfig.json include` widened from 5 scopes to also cover `src/wip-shared/**/*`; gate now covers 6 additional modules (3 Vue SFCs + 2 composables + 1 constants module). Also removes `@ts-expect-error` suppressions from `shared-composables/` and `shared-ui/` that were cross-phase placeholders pending this migration. Gate tier, command, and informational status unchanged.
- Source: change `migrate-wip-shared-ts` Phase 1f.

## [ci 1.3.3] — 2026-05-12
### Changed
- Gate Compatibility Notes: `frontend-type-check` Phase 1e scope expansion documented — `tsconfig.json include` widened from `src/core/**/* + src/shared-composables/**/* + src/shared-ui/**/* + src/admin-shared/**/*` to also cover `src/resource-shared/**/*`; gate now covers 3 additional modules (2 Vue SFCs + 1 constants module). Gate tier, command, and informational status unchanged.
- Source: change `migrate-resource-shared-ts` Phase 1e.

## [ci 1.3.2] — 2026-05-12
### Changed
- Gate Compatibility Notes: `frontend-type-check` Phase 1d scope expansion documented — `tsconfig.json include` widened from `src/core/**/* + src/shared-composables/**/* + src/shared-ui/**/*` to also cover `src/admin-shared/**/*`; gate now covers 5 additional modules (4 Vue SFCs + 1 composable). Gate tier, command, and informational status unchanged.
- Source: change `migrate-admin-shared-ts` Phase 2.

## [ci 1.3.1] — 2026-05-05
### Changed
- Gate Compatibility Notes: `frontend-type-check` Phase 1b scope expansion documented — `tsconfig.json include` widened from `src/core/**/*` to also cover `src/shared-composables/**/*`; gate now covers 21 core + 11 shared-composable `.ts` modules under `strict: true`. Gate tier, command, and informational status unchanged.
- Source: change `migrate-shared-composables-ts` Phase 1b.

## [ci 1.3.0] — 2026-05-05
### Added
- Workflow Configuration: updated Node version from 20 → 22 across all jobs; added `unit-and-integration-tests` row (backend-tests.yml) with Node 22 requirement; added Node version constraint note — all pytest-running jobs MUST include `setup-node@v4 node-version: "22"` because parity tests use `--experimental-strip-types`.
- Environment Constraints (conda): new section — `environment.yml` must pin `nodejs>=22.6`; documents conda PATH-shadowing in login-shell pytest runs.
- Source: change `migrate-core-to-typescript` Phase 1a close-out; evidence commits `05e8c99`, `b2fd91b`, `06eaad3`.

## [ci 1.2.1] — 2026-05-05
### Changed
- Gate Compatibility Notes: `frontend-type-check` scope expansion documented — Phase 0 covered only `src/core/index.ts` placeholder (~0 substantive files); Phase 1a widened `tsconfig.json include` to `src/core/**/*`, gate now covers all 21 core `.ts` modules under `strict: true`. No gate tier or command change; informational status unchanged.

## [ci 1.2.0] — 2026-05-05
### Added
- Gate Inventory: 新增 `frontend-type-check` gate（Tier 1，informational，`cd frontend && npm run type-check` / `vue-tsc --noEmit`）；wired in `.github/workflows/frontend-tests.yml`。屬 add-ts-toolchain Phase 0 TypeScript 工具鏈建立，達 promotion criteria 後提升為 required。

## [api 1.2.0] — 2026-05-05
### Added
- 完整 endpoint 表：從 30 個擴展至覆蓋全部 83+ 路徑（新增 WIP、Hold-Overview、Hold-Detail、Hold-History、QC-Gate、Resource、Resource-History、Reject-History、Yield-Alert、Production-History、Material-Trace、Trace、Mid-Section-Defect、Analytics、Query-Tool、Job-Query、Dashboard、Admin 所有端點）。

## [business 1.1.0] — 2026-05-05
### Added
- 新增 9 個 rule 群組：WIP（4 rules）、Hold-Overview（3）、QC-Gate（2）、Resource（3）、Resource-History（4）、Analytics（4）、Query-Tool（4）、Job-Query（4）、Dashboard（4）、Mid-Section-Defect（4）、Admin（5）。

## [ci 1.1.0] — 2026-05-05
### Changed
- Gate inventory: 以真實 pytest marker 命令取代 placeholder；新增 playwright-resilience、playwright-data-boundary、playwright-critical-journeys gate。
- Workflow Configuration: 新增 test directory → tier 對應表。
- nightly-integration gate 分離為獨立 job。

## [data 1.0.0] — 2026-05-05
### Changed (breaking)
- 從空 placeholder 升級為完整規範（0.x 為草稿，無實作依賴，升至 1.0.0 確立為正式版本）。
### Added
- 完整 API envelope shapes（success、error、async job 202、job status）。
- 常用 query result shapes（paginated list、summary+detail、hold-history today snapshot、truncated payload）。
- 逐欄 Required Columns 表（lot row、duration item、pareto row）。
- Invalid Data Behavior 對應表（含 test references）。
- Export/Import Format（CSV、Parquet、NDJSON）。
- Row Limit / Truncation Policy 表。

## [api 0.1.0] — 2026-04-27
Initial draft.

## [css 0.1.0] — 2026-04-27
Initial draft.

## [env 0.1.0] — 2026-04-27
Initial draft.

## [data 0.1.0] — 2026-04-27
Initial draft.

## [business 0.1.0] — 2026-04-27
Initial draft.

## [ci 0.1.0] — 2026-04-27
Initial draft.
