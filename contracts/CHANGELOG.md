# Contracts Changelog

All notable contract surface changes belong here.
Format: Keep-a-Changelog (https://keepachangelog.com/).
Versions are semantic per contract type.

While a contract is at 0.x (draft), entries here are optional.
Once a contract reaches 1.0.0, every schema-version bump must have
a corresponding entry below.

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
