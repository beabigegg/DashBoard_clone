---
name: downtime-analysis-page-redesign-archive
description: Close-out record for downtime-analysis page redesign (chart cross-filter + three-tier table)
metadata:
  type: project
---

## Change Summary

移除 downtime-analysis 頁面的三 tab 架構（Charts / Equipment / Events），改為圖表在上、三層展開表在下的單頁佈局。新增圖表 cross-filter（BigCategoryChart 扇形點擊、DailyTrendChart legend 切換）帶動三層設備表聯動；第三層事件以 lazy-load 方式按需展開。Backend 在 `apply_view()` 加入 `big_category`、`status_types`、`resource_id` 三個 in-memory spool 過濾參數（不觸發 Oracle 重查）；equipment-detail `page_size` 上限由 200 提升至 1000。後續 hotfix commit 追加：頂 50 台設備 per status group、DW_MES_JOB.JOBID 欄位貫通整條 pipeline（取代 JOBORDERNAME）、Tier 2 視覺縮排。

## Final Behavior

- 頁面載入後自動執行 7 天預設查詢，無需切換 tab
- BigCategoryChart 點擊扇形 → 只顯示有該大類別事件的機台（in-memory filter，不重查 Oracle）
- DailyTrendChart legend 點擊 → 隱藏對應 UDT/SDT/EGT 分組
- 三層展開：Tier 1 = 狀態分組（UDT/SDT/EGT）→ Tier 2 = 最多前 50 台設備（依時數 DESC）→ Tier 3 = 該機台在該狀態下的事件列表（lazy-load）
- 事件表 JOB ID 欄顯示 DW_MES_JOB.JOBID（UUID 格式），不再顯示 JOBORDERNAME
- 重新查詢 → chartFilter 歸零、Tier 3 cache 清空

## Final Contracts Updated

- `contracts/api/api-contract.md` § downtime-analysis: 新增 `big_category`、`status_types`、`resource_id` query params 到 equipment-detail 和 event-detail；equipment-detail `page_size` max=1000
- `contracts/data-shapes/data-shape-contract.md` §3.12.6: event_detail response wrapper key `events`（非 bare array）；Tier 3 cache key `${resource_id}|${status_type}`
- `contracts/CHANGELOG.md`: `## [api 1.14.0]` entry

## Final Tests Added / Updated

- `tests/test_downtime_analysis_service.py::TestApplyViewFilter` (8 tests): big_category/status_types/resource_id 過濾邏輯
- `tests/test_downtime_analysis_routes.py::TestEquipmentDetailFilterRoute` (5), `::TestEventDetailFilterRoute` (3), `::TestFilterDataBoundary` (5)
- `frontend/src/downtime-analysis/components/__tests__/StatusMachineJobTable.test.ts` (新)
- `frontend/src/downtime-analysis/components/__tests__/MachineEventRows.test.ts` (新，含 wrapper-key pin for `events`)
- `frontend/tests/playwright/downtime-analysis.spec.js`: 新增 cross-filter、三層展開、no-tab-switcher 等 E2E 場景
- CI: 122 backend tests pass; 497/498 frontend tests pass (1 skipped)

## Final CI/CD Gates

所有 Tier 1 gates 由既有 `.github/workflows/frontend-tests.yml` 涵蓋，無需修改 workflow：
- pytest（backend unit + integration）
- npm run type-check（continue-on-error: true，Tier 0 本地強制）
- npm run css:check
- npm run build（vite）
- npx playwright test tests/playwright/downtime-analysis.spec.js
- cdd-kit validate

CI PASS confirmed on commit `50bad47`.

## Production Reality Findings

- **Inline import patch path**: `apply_view()` 內部用 function-level `import` 引入 `load_downtime_events`（不是 module-level），因此測試 patch 路徑必須是 `mes_dashboard.services.downtime_analysis_cache.load_downtime_events`，而非 `mes_dashboard.services.downtime_analysis_service.load_downtime_events`。第一次寫測試時遇到 patch 失效即因此。
- **page_size cap 雙重位置**: `_build_equipment_detail_page()` 服務層本身有一個內部 cap（`min(page_size, 1000)`），route handler 也有 `page_size = min(...)` 邏輯。兩處都需要同步修改，否則其中一個靜默截斷。
- **頁面一直轉圈**: 重新設計後使用者報告頁面持續 loading，初步排查後端正常（Gunicorn on 8080，options endpoint OK）；可能為 Oracle 查詢耗時長導致 360 s timeout，或瀏覽器快取舊版 JS。尚未完全定位，留為 follow-up。
- **JOB ID 欄位**: SHIFT 表的 `JOBID` 欄（Path A 直接比對）與 DW_MES_JOB 的 `JOBID` UUID 為兩個不同欄位，但最終 pipeline 需要的是 DW_MES_JOB.JOBID（維修工單 UUID），透過 `jobs_df` join 後從 `job.get('JOBID')` 取得。

## Lessons Promoted to Standards

- **CLAUDE.md — 新增 `## Downtime Analysis Service Architecture Notes`**: `downtime_analysis_service` 在四個 call site 使用 function-body import（非 module-level），因此 patch 路徑必須指向 `mes_dashboard.services.downtime_analysis_cache.load_downtime_events`，而非 service module 本身。Evidence: `src/mes_dashboard/services/downtime_analysis_service.py:606,986,1164,1210`。Contract-reviewer accepted; Lesson B (page_size dual cap) rejected as one-off cold data.
- **contract-reviewer agent log saved to**: `specs/changes/downtime-analysis-page-redesign/agent-log/` (inline in this close session)

## Follow-up Work

- 頁面轉圈問題仍需後續確認（Oracle timeout vs. 瀏覽器快取）
- `msd_seed_job_service.py` 為另一個未 commit 的進行中變更，待另行處理
- Tier 2 最多 50 台限制是前端截斷；若業務需求要查看更多設備，需考慮分頁

## Cold Data Warning

This archive is historical evidence. Current requirements live in `contracts/` and active project guidance (`CLAUDE.md`).
