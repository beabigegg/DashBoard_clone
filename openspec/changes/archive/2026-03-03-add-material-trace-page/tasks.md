## 1. SQL 查詢檔

- [x] 1.1 建立 `src/mes_dashboard/sql/material_trace/` 目錄
- [x] 1.2 新增 `forward_by_lot.sql`：以 CONTAINERID IN (:ids) 查詢 `DW_MES_LOTMATERIALSHISTORY`，LEFT JOIN `DW_MES_CONTAINER` 取 CONTAINERNAME，含可選 WORKCENTERNAME IN 篩選
- [x] 1.3 新增 `forward_by_workorder.sql`：以 PJ_WORKORDER IN (:ids) 查詢，結構與 forward_by_lot 相同
- [x] 1.4 新增 `reverse_by_material_lot.sql`：以 MATERIALLOTNAME IN (:ids) 查詢，LEFT JOIN `DW_MES_CONTAINER` 取 CONTAINERNAME，含 FETCH FIRST 10001 ROWS ONLY 上限，含可選 WORKCENTERNAME IN 篩選
- [x] 1.5 新增 `resolve_container_ids.sql`：批次將 CONTAINERNAME 轉換為 CONTAINERID

## 2. 後端 Service

- [x] 2.1 新增 `src/mes_dashboard/services/material_trace_service.py`，包含 `forward_query(mode, values, workcenter_groups, page, per_page)` 函式
- [x] 2.2 在 `forward_query` 中實作 LOT ID 模式：呼叫 `resolve_container_ids.sql` 將 CONTAINERNAME 批次轉換為 CONTAINERID，記錄未解析的名稱到 `meta.unresolved`
- [x] 2.3 在 `forward_query` 中實作工單模式：直接以 PJ_WORKORDER 查詢
- [x] 2.4 實作 `reverse_query(values, workcenter_groups, page, per_page)` 函式，以 MATERIALLOTNAME 查詢，檢查結果是否超過 10,000 筆並設定 `meta.truncated`
- [x] 2.5 實作共用 `_enrich_workcenter_group(df)` 函式：使用 `filter_cache.get_workcenter_mapping()` 對 DataFrame 添加 WORKCENTER_GROUP 欄位
- [x] 2.6 實作共用 `_apply_workcenter_group_filter(workcenter_groups)` 函式：透過 `filter_cache.get_workcenter_mapping()` 將站群組名稱解析為 WORKCENTERNAME 清單，供 SQL WHERE 使用
- [x] 2.7 實作 `export_csv(mode, values, workcenter_groups)` 函式，結果上限 50,000 筆，回傳 UTF-8 BOM CSV

## 3. 後端 Route

- [x] 3.1 新增 `src/mes_dashboard/routes/material_trace_routes.py`，建立 `material_trace_bp` Blueprint，prefix `/api/material-trace`
- [x] 3.2 實作 `POST /query` 端點：驗證 mode（lot/workorder/material_lot）、values 非空、筆數上限（正向 200 / 反向 50）；根據 mode 呼叫 `forward_query` 或 `reverse_query`；回傳分頁結果
- [x] 3.3 實作 `POST /export` 端點：與 query 相同參數驗證，呼叫 `export_csv`，回傳 CSV response
- [x] 3.4 實作 `GET /filter-options` 端點：回傳 `filter_cache.get_workcenter_groups()` 供前端站群組下拉選單使用
- [x] 3.5 加入 rate limiting：query 30/60s，export 10/60s
- [x] 3.6 在 `routes/__init__.py` 註冊 `material_trace_bp`

## 4. 前端頁面基礎

- [x] 4.1 新增 `frontend/material-trace.html` Vite entry point
- [x] 4.2 新增 `frontend/src/material-trace/main.js` 初始化 Vue app
- [x] 4.3 新增 `frontend/src/material-trace/App.vue` 主元件：包含 queryMode（forward/reverse）、forwardInputType（lot/workorder）、inputText、workcenterGroups、results、pagination、loading、error 等 reactive state
- [x] 4.4 新增 `frontend/src/material-trace/style.css`，沿用 reject-history 的表格/banner 樣式基礎
- [x] 4.5 在 `vite.config.js` 加入 `material-trace` entry
- [x] 4.6 在 Flask 後端 `templates/` 新增頁面路由（或 Jinja template），確認頁面可存取

## 5. 前端元件

- [x] 5.1 實作查詢模式切換 tab（正向查詢 / 反向查詢），切換時清空輸入和結果
- [x] 5.2 實作正向模式的輸入類型選擇（LOT ID / 工單），切換時清空輸入
- [x] 5.3 實作多筆輸入 textarea，使用 `parseMultiLineInput()` 解析，顯示已輸入筆數
- [x] 5.4 實作前端輸入筆數驗證（正向 200 筆 / 反向 50 筆），超過時顯示 error banner 並阻止查詢
- [x] 5.5 實作站群組多選篩選下拉（options 從 `/api/material-trace/filter-options` 載入）
- [x] 5.6 實作 `executePrimaryQuery()` 函式：呼叫 `/api/material-trace/query` API，處理結果、分頁、error、unresolved、truncated 警告
- [x] 5.7 實作結果表格，含 13 個欄位（CONTAINERNAME、PJ_WORKORDER、WORKCENTER_GROUP、WORKCENTERNAME、MATERIALPARTNAME、MATERIALLOTNAME、VENDORLOTNUMBER、QTYREQUIRED、QTYCONSUMED、EQUIPMENTNAME、TXNDATE、PRIMARY_CATEGORY、SECONDARY_CATEGORY）
- [x] 5.8 實作分頁控制（上一頁/下一頁/頁碼顯示），server-side 分頁
- [x] 5.9 實作匯出 CSV 按鈕，呼叫 `/api/material-trace/export`，無結果時 disabled
- [x] 5.10 實作 loading overlay、error banner、warning banner（unresolved LOT / 結果截斷）

## 6. 導覽整合

- [x] 6.1 在 sidebar/drawer 導覽列新增「原物料追溯查詢」頁面入口

## 7. 測試

- [x] 7.1 新增 `tests/test_material_trace_service.py`：測試正向 LOT 模式查詢（mock Oracle 回傳），驗證 CONTAINERID resolve + 結果 enrichment
- [x] 7.2 測試正向工單模式查詢，驗證 PJ_WORKORDER 直接查詢
- [x] 7.3 測試反向查詢，驗證結果上限 10,000 筆截斷邏輯
- [x] 7.4 測試站群組篩選：mock `get_workcenter_mapping()` 回傳 mapping，驗證 WORKCENTERNAME IN 過濾
- [x] 7.5 測試未解析 LOT ID 的 `meta.unresolved` 回傳
- [x] 7.6 新增 `tests/test_material_trace_routes.py`：測試輸入驗證（mode 無效、values 空、超過筆數上限）回傳 HTTP 400
- [x] 7.7 測試 query 端點回傳正確分頁結構
- [x] 7.8 測試 export 端點回傳 CSV content-type 和 UTF-8 BOM
