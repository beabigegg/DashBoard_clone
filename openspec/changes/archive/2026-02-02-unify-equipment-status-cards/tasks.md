## 1. 後端 API 調整

- [x] 1.1 修改 `resource_service.py` 的 `get_resource_status_summary()` 函數，新增 OU%、Availability% 計算邏輯
- [x] 1.2 修改 `resource_service.py` 回傳資料結構，將 UDT/SDT 分開統計，新增 NST 統計
- [x] 1.3 修改 `resource_history_service.py` 的 `_build_kpi_from_df()` 函數，新增 SBY、NST 欄位
- [x] 1.4 修改 `resource_history_service.py` 新增各狀態佔比計算邏輯

## 2. 設備即時機況前端

- [x] 2.1 修改 `resource_status.html` 卡片 HTML 結構，調整為 9 張卡片
- [x] 2.2 新增 OU%、Availability% 卡片
- [x] 2.3 將 UDT/SDT 合併卡片拆分為兩張獨立卡片
- [x] 2.4 新增 NST 卡片
- [x] 2.5 調整機台數卡片位置至最後
- [x] 2.6 更新 `loadSummary()` JavaScript 函數，綁定新的資料欄位
- [x] 2.7 統一所有卡片的主標籤與副標籤文字

## 3. 設備歷史績效前端

- [x] 3.1 修改 `resource_history.html` 卡片 HTML 結構，調整為 9 張卡片
- [x] 3.2 新增 SBY、NST 卡片
- [x] 3.3 為所有狀態卡片新增佔比顯示區域
- [x] 3.4 調整機台數卡片位置至最後
- [x] 3.5 更新 `updateKpiCards()` JavaScript 函數，綁定新的資料欄位與佔比
- [x] 3.6 統一所有卡片的主標籤與副標籤文字

## 4. 測試與驗證

- [x] 4.1 驗證設備即時機況頁面 9 張卡片顯示正確
- [x] 4.2 驗證設備歷史績效頁面 9 張卡片顯示正確
- [x] 4.3 驗證兩頁面卡片排序一致
- [x] 4.4 驗證佔比計算公式正確（分母含 NST）
- [x] 4.5 驗證 OU%、Availability% 計算正確
- [x] 4.6 測試無資料或零值情況的顯示

## 備註

- 即時機況的「機台數」= resource_cache 中的總設備數
- 歷史績效的「機台數」= 查詢時間範圍內在 SHIFT 表中有資料的不重複機台數
- 兩者數量可能有差異（例如新設備或閒置設備），屬預期行為
