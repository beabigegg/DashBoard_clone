## 1. WIP Overview — URL 狀態管理

- [x] 1.1 新增 `updateUrlState()` 函式：將 filters (workorder, lotid, package, type) 和 activeStatusFilter 同步到 URL via `history.replaceState`，只 append 非空值
- [x] 1.2 新增 `initializePage()` 函式：從 URL params 讀取 filters + status，還原到 `filters` reactive 和 `activeStatusFilter` ref，然後呼叫 `loadAllData(true)`；取代目前的 `void loadAllData(true)` 直接呼叫
- [x] 1.3 修改 `applyFilters()`、`clearFilters()`、`removeFilter()` 三個函式：每次操作後呼叫 `updateUrlState()`
- [x] 1.4 修改 `toggleStatusFilter()`：操作後呼叫 `updateUrlState()`

## 2. WIP Overview — Drill-Down 帶 Status

- [x] 2.1 修改 `navigateToDetail()`：在組建 URL params 時，若 `activeStatusFilter.value` 非 null，append `status` 參數

## 3. WIP Detail — 讀取 Status URL 參數

- [x] 3.1 修改 `initializePage()`：新增 `activeStatusFilter.value = getUrlParam('status') || null`，在 filters 讀取之後、`loadAllData` 之前
- [x] 3.2 修改 `updateUrlState()`：若 `activeStatusFilter.value` 非 null，`params.set('status', activeStatusFilter.value)`
- [x] 3.3 修改 `toggleStatusFilter()`：操作後呼叫 `updateUrlState()`

## 4. WIP Detail — Back Button 動態 URL

- [x] 4.1 新增 computed `backUrl`：從當前 filters + activeStatusFilter 組出 `/wip-overview?...`（只含非空值，不含 workcenter）
- [x] 4.2 將 template 中 `<a href="/wip-overview">` 改為 `<a :href="backUrl">`

## 5. 驗證

- [x] 5.1 驗證：Overview 設定 filter + status → drill down → Detail 正確還原所有狀態
- [x] 5.2 驗證：Detail 中變更 filter/status → 點 Back → Overview 正確還原變更後的狀態
- [x] 5.3 驗證：無參數直接訪問 `/wip-overview` 和 `/wip-detail` 行為與現行相同
- [x] 5.4 驗證：Overview 的 clearFilters 清除所有 filter + status 並更新 URL
