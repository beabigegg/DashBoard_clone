## 1. 清理舊程式碼

- [x] 1.1 刪除 `src/mes_dashboard/templates/wip_report.html`
- [x] 1.2 保留 `src/mes_dashboard/config/workcenter_groups.py`（被 dashboard_service.py 使用）
- [x] 1.3 重寫 `src/mes_dashboard/services/wip_service.py`（使用 DWH.DW_PJ_LOT_V）
- [x] 1.4 重寫 `src/mes_dashboard/routes/wip_routes.py`（新 API 端點）

## 2. 後端資料服務

- [x] 2.1 建立新的 `wip_service.py` - 基礎查詢函數（連接 `DWH.DW_PJ_LOT_V`）
- [x] 2.2 實作 `get_wip_summary()` - KPI 摘要查詢
- [x] 2.3 實作 `get_wip_matrix()` - 工站×產品線矩陣查詢
- [x] 2.4 實作 `get_wip_hold_summary()` - Hold 摘要查詢
- [x] 2.5 實作 `get_wip_detail()` - 工站細部查詢（含分頁、篩選）
- [x] 2.6 實作 `get_workcenters()` - 工站列表查詢
- [x] 2.7 實作 `get_packages()` - Package 列表查詢

## 3. 後端 API 路由

- [x] 3.1 建立 `routes/wip.py` Blueprint
- [x] 3.2 實作 `GET /api/wip/overview/summary`
- [x] 3.3 實作 `GET /api/wip/overview/matrix`
- [x] 3.4 實作 `GET /api/wip/overview/hold`
- [x] 3.5 實作 `GET /api/wip/detail/<workcenter>`
- [x] 3.6 實作 `GET /api/wip/meta/workcenters`
- [x] 3.7 實作 `GET /api/wip/meta/packages`
- [x] 3.8 註冊 Blueprint 到 app factory（沿用現有 register_routes）

## 4. 前端 - WIP Overview 頁面

- [x] 4.1 建立 `templates/wip_overview.html` 基本結構
- [x] 4.2 實作 KPI 摘要卡片區塊
- [x] 4.3 實作工站×產品線矩陣表格
- [x] 4.4 實作矩陣資料載入與渲染
- [x] 4.5 實作點擊工站跳轉至 Detail 功能
- [x] 4.6 實作 Hold 摘要表格
- [x] 4.7 實作更新時間顯示

## 5. 前端 - WIP Detail 頁面

- [x] 5.1 建立 `templates/wip_detail.html` 基本結構
- [x] 5.2 實作篩選器區塊（Package/Status 下拉選單）
- [x] 5.3 實作工站摘要卡片（總/在機/待料/Hold）
- [x] 5.4 實作 Lot 明細表格（固定欄位：Lot ID/設備/狀態/Package + 動態 Spec 欄位）
- [x] 5.5 實作 Spec 橫向展開（依 SPECSEQUENCE 排序，在對應 Spec 顯示 QTY）
- [x] 5.6 實作 Hold 狀態紅色標示與 Hold Reason 顯示
- [x] 5.7 實作分頁功能
- [x] 5.8 實作篩選器與資料連動

## 6. 前端 - 自動刷新機制

- [x] 6.1 在各頁面內建 auto-refresh JavaScript（非獨立模組）
- [x] 6.2 實作 10 分鐘定時刷新（setInterval）
- [x] 6.3 實作 DOM 局部更新（避免整頁重渲染）
- [x] 6.4 實作 CSS transition 數值變化效果
- [x] 6.5 實作 subtle loading indicator（spinner + success/error 指示）
- [x] 6.6 實作錯誤處理（保留現有資料，顯示錯誤指示）
- [x] 6.7 實作手動刷新按鈕
- [x] 6.8 實作頁面可見性處理（visibilitychange event）

## 7. 樣式設計

- [x] 7.1 設計 Overview 頁面 CSS 樣式
- [x] 7.2 設計 Detail 頁面 CSS 樣式
- [x] 7.3 設計響應式佈局（RWD）
- [x] 7.4 設計 transition/animation 效果

## 8. 頁面路由整合

- [x] 8.1 新增 `/wip-overview` 頁面路由
- [x] 8.2 新增 `/wip-detail` 頁面路由
- [x] 8.3 更新導航選單連結
- [x] 8.4 移除舊的 `/wip` 路由

## 9. 測試與驗證

- [x] 9.1 測試後端 API 函數正常運作
- [x] 9.2 測試 Overview 頁面載入與資料顯示
- [x] 9.3 測試 Detail 頁面載入與篩選功能
- [x] 9.4 測試自動刷新機制
- [x] 9.5 測試手動刷新功能
- [x] 9.6 測試頁面可見性處理
- [x] 9.7 測試 API 錯誤時的降級處理
