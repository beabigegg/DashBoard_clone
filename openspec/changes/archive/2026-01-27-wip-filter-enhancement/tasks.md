## 1. 後端 - DUMMY 排除邏輯

- [x] 1.1 修改 `get_wip_summary()` 加入 DUMMY 排除條件
- [x] 1.2 修改 `get_wip_matrix()` 加入 DUMMY 排除條件
- [x] 1.3 修改 `get_wip_hold_summary()` 加入 DUMMY 排除條件
- [x] 1.4 修改 `get_wip_detail()` 加入 DUMMY 排除條件
- [x] 1.5 修改 `get_workcenters()` 加入 DUMMY 排除條件
- [x] 1.6 修改 `get_packages()` 加入 DUMMY 排除條件
- [x] 1.7 新增 `include_dummy` 參數支援（可選覆蓋預設行為）

## 2. 後端 - 搜尋 API

- [x] 2.1 實作 `search_workorders(q, limit)` 函數
- [x] 2.2 實作 `search_lot_ids(q, limit)` 函數
- [x] 2.3 新增 `GET /api/wip/meta/search` 路由端點
- [x] 2.4 加入輸入驗證（最少 2 字元、limit 上限）

## 3. 後端 - 篩選參數擴充

- [x] 3.1 修改 `get_wip_summary()` 支援 workorder/lotid 參數
- [x] 3.2 修改 `get_wip_matrix()` 支援 workorder/lotid 參數
- [x] 3.3 修改 `get_wip_hold_summary()` 支援 workorder/lotid 參數
- [x] 3.4 修改 `get_wip_detail()` 支援 workorder/lotid 參數
- [x] 3.5 修改對應的 API 路由接收新參數

## 4. 前端 - Autocomplete 元件

- [x] 4.1 實作 autocomplete 搜尋框 JavaScript 函數
- [x] 4.2 實作 debounce 機制（300ms）
- [x] 4.3 實作下拉選單 UI（使用 datalist 或自訂）
- [x] 4.4 實作 loading 指示器

## 5. 前端 - WIP Overview 整合

- [x] 5.1 新增 WORKORDER 搜尋框 HTML
- [x] 5.2 新增 LOT ID 搜尋框 HTML
- [x] 5.3 整合篩選器與資料載入邏輯
- [x] 5.4 修改 KPI/矩陣/Hold 更新函數接受新篩選參數
- [x] 5.5 新增清除篩選按鈕

## 6. 前端 - WIP Detail 整合

- [x] 6.1 新增 WORKORDER 搜尋框 HTML
- [x] 6.2 新增 LOT ID 搜尋框 HTML
- [x] 6.3 整合篩選器與現有 Package/Status 篩選邏輯
- [x] 6.4 修改資料載入函數接受新篩選參數
- [x] 6.5 更新清除篩選功能包含新篩選器

## 7. 測試與驗證

- [x] 7.1 測試 DUMMY 排除在所有 API 正常運作（單元測試）
- [x] 7.2 測試搜尋 API 回傳正確結果（單元測試）
- [x] 7.3 測試 Overview 頁面篩選功能（手動測試）
- [x] 7.4 測試 Detail 頁面篩選功能（手動測試）
- [x] 7.5 測試多重篩選條件組合（單元測試）
- [x] 7.6 測試 autocomplete 防抖機制（手動測試）
- [x] 7.7 撰寫單元測試（搜尋函數）
