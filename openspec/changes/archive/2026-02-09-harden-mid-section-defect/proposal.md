## Why

Code review 發現中段製程不良追溯分析（`/mid-section-defect`）有 6 個問題：首次查詢觸發雙倍 Oracle 管線（P0）、高成本路由無節流（P1a）、篩選與查詢狀態耦合（P1b）、無請求取消機制（P2a）、上游歷史 workcenter 分類在 Python 端逐行計算而非善用 DB Server（P2b）、零測試覆蓋（P3）。需在功能穩定後立即修復，防止 DB 過載與前端競態問題。

## What Changes

- **P0 分散式鎖**：`query_analysis()` 加入 `try_acquire_lock` / `release_lock` 包裹計算區段，第二個平行請求等待快取而非重跑管線
- **P1a 路由限速**：`/analysis`（6/60s）、`/analysis/detail`（15/60s）、`/export`（3/60s）加入 `configured_rate_limit` decorator
- **P1b 篩選分離**：新增 `committedFilters` ref，所有 API 呼叫（翻頁/自動刷新/匯出）讀取已提交的篩選快照
- **P2a 請求取消**：`loadAnalysis()` 和 `loadDetail()` 加入 `createAbortSignal(key)` keyed abort，新查詢自動取消舊請求
- **P2b SQL 端分類**：上游歷史 SQL 加入 `CASE WHEN` workcenter group 分類（全線歷程不排除任何站點），移除 Python 端 `get_workcenter_group()` 逐行呼叫與 order 4-11 過濾
- **P3 測試覆蓋**：新增 `test_mid_section_defect_routes.py`（9 個測試）和 `test_mid_section_defect_service.py`（9 個測試）

## Capabilities

### New Capabilities

（無新增能力，本次為既有功能的強化修復）

### Modified Capabilities

- `api-safety-hygiene`: 新增 mid-section-defect 3 個路由的 rate limit 與分散式鎖機制
- `vue-vite-page-architecture`: mid-section-defect 前端加入 committedFilters 篩選分離與 AbortController 請求取消

## Impact

- **Backend**: `mid_section_defect_service.py`（分散式鎖 + 移除 Python 端 workcenter 過濾）、`mid_section_defect_routes.py`（rate limit）、`upstream_history.sql`（CASE WHEN 分類）
- **Frontend**: `mid-section-defect/App.vue`（committedFilters + abort signal）
- **Tests**: 2 個新測試檔案（`test_mid_section_defect_routes.py`、`test_mid_section_defect_service.py`）
- **API 行為變更**: 超過限速門檻回傳 429；上游歷史回傳含 `WORKCENTER_GROUP` 欄位（但 API response 格式不變，分類邏輯內部調整）
- **無破壞性變更**: API response 結構、快取 key、前端元件介面均不變
