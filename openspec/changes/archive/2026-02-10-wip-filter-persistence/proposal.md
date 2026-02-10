## Why

WIP Overview 和 WIP Detail 之間的篩選條件無法雙向保留。用戶在 Overview 設定的 filters（workorder, lotid, package, type）和 status filter（RUN/QUEUE/品質異常/非品質異常）在 drill down 到 Detail 時只部分傳遞（缺 status），而從 Detail 返回 Overview 時所有篩選狀態完全丟失。這迫使用戶反覆重新輸入篩選條件，破壞了 drill-down 的分析流程。

## What Changes

- Overview 頁面新增 URL 狀態管理：所有 filters 和 status filter 同步到 URL query params，頁面載入時從 URL 還原狀態
- Overview drill-down 導航額外傳遞 `status` 參數到 Detail
- Detail 頁面初始化時額外讀取 `status` URL 參數並還原 status filter 狀態
- Detail 頁面的 `updateUrlState()` 額外同步 `status` 參數
- Detail 的 Back button 改為動態 computed URL，攜帶當前所有 filter + status 回 Overview
- Detail 中 `toggleStatusFilter()` 操作後同步 URL 狀態

## Capabilities

### New Capabilities

_None — this change enhances existing capabilities._

### Modified Capabilities

- `wip-overview-page`: Overview 新增 URL 狀態管理（filters + status 雙向同步到 URL），drill-down 導航額外傳遞 status 參數
- `wip-detail-page`: Detail 新增 status URL 參數讀寫，Back button 改為動態 URL 攜帶所有 filter 狀態回 Overview

## Impact

- **Frontend**: `frontend/src/wip-overview/App.vue` — 新增 `initializePage()`、`updateUrlState()`，修改 `navigateToDetail()`、`applyFilters()`、`clearFilters()`、`removeFilter()`、`toggleStatusFilter()`
- **Frontend**: `frontend/src/wip-detail/App.vue` — 修改 `initializePage()` 加讀 status、`updateUrlState()` 加寫 status、`toggleStatusFilter()` 加呼叫 `updateUrlState()`、back button 改為 computed `backUrl`
- **No backend changes** — 所有 API endpoints 和 SQL 不需修改
- **No breaking changes** — URL params 為 additive，無參數時行為與現行相同
