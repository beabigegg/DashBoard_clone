# Contracts Changelog

All notable contract surface changes belong here.
Format: Keep-a-Changelog (https://keepachangelog.com/).
Versions are semantic per contract type.

While a contract is at 0.x (draft), entries here are optional.
Once a contract reaches 1.0.0, every schema-version bump must have
a corresponding entry below.

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
