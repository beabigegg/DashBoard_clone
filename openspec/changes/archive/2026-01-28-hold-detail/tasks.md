# Hold Detail 實作任務

## 後端任務

### Task 1: 新增 Hold Detail 服務函數
- [x] 在 `wip_service.py` 新增 `get_hold_detail_summary()` 函數
- [x] 在 `wip_service.py` 新增 `get_hold_detail_distribution()` 函數
- [x] 在 `wip_service.py` 新增 `get_hold_detail_lots()` 函數（含分頁）

### Task 2: 新增 Hold Detail API 路由
- [x] 建立 `src/mes_dashboard/routes/hold_routes.py`
- [x] 實作 `GET /api/wip/hold-detail/summary` 端點
- [x] 實作 `GET /api/wip/hold-detail/distribution` 端點
- [x] 實作 `GET /api/wip/hold-detail/lots` 端點（含篩選參數）
- [x] 實作 `GET /hold-detail` 頁面路由
- [x] 在 `__init__.py` 註冊新的 blueprint

## 前端任務

### Task 3: 建立 Hold Detail 頁面模板
- [x] 建立 `src/mes_dashboard/templates/hold_detail.html`
- [x] 實作頁首區塊（返回連結、標題）
- [x] 實作摘要卡片區塊（5 張卡片）
- [x] 實作當站滯留天數分佈區塊（4 個可點擊卡片）
- [x] 實作分佈表格區塊（By Workcenter、By Package）
- [x] 實作 Lot Details 表格（含分頁）
- [x] 實作篩選指示器和清除按鈕

### Task 4: 實作前端互動邏輯
- [x] 實作資料載入函數（Summary、Distribution、Lots）
- [x] 實作篩選邏輯（點擊分佈項目篩選 Lot Details）
- [x] 實作分頁功能
- [x] 實作篩選狀態顯示和清除功能
- [x] 處理載入狀態和錯誤狀態

### Task 5: 修改 WIP Overview 連結
- [x] 在 `wip_overview.html` 的 Hold Summary 表格中，為 Hold Reason 加入連結
- [x] 連結格式：`/hold-detail?reason=<encoded_reason>`

## 樣式任務

### Task 6: 確保樣式一致性
- [x] 數值欄位不顯示單位文字
- [x] 數值欄位右對齊，文字欄位左對齊
- [x] 表格欄位間隔 16px
- [x] 可點擊項目顯示 cursor: pointer 和 hover 效果
- [x] 選中狀態使用高亮邊框

## 測試任務

### Task 7: 功能測試

**自動化測試** - `tests/test_hold_routes.py` (20/20 passed)
- [x] 頁面路由測試（無 reason 時重導向、有 reason 時顯示）
- [x] Summary API 測試（成功回傳、缺少參數錯誤、查詢失敗）
- [x] Distribution API 測試（成功回傳、缺少參數錯誤、查詢失敗）
- [x] Lots API 測試（成功回傳、篩選參數傳遞、分頁參數驗證）
- [x] Age Range 參數驗證（0-1, 1-3, 3-7, 7+）

**手動前端測試**（已通過）
- [x] 測試不同 Hold Reason 的資料載入
- [x] 測試各種篩選組合
- [x] 測試分頁功能
- [x] 測試篩選清除功能
- [x] 測試從 WIP Overview 導航到 Hold Detail
