## 1. 後端服務模組

- [x] 1.1 建立 `src/mes_dashboard/services/resource_history_service.py` 模組結構
- [x] 1.2 實作 `get_filter_options()` 函數：查詢可用的站點、型號列表
- [x] 1.3 實作 `query_summary()` 函數：查詢 KPI、趨勢、熱力圖、站點比較資料
- [x] 1.4 實作 `query_detail()` 函數：查詢階層式明細資料（支援分頁）
- [x] 1.5 實作 `export_csv()` 函數：串流輸出 CSV 格式資料
- [x] 1.6 實作時間粒度聚合邏輯（日/週/月/年 TRUNC 函數）
- [x] 1.7 實作 OU% 計算公式（PRD / (PRD+SBY+EGT+SDT+UDT) * 100）
- [x] 1.8 實作各 E10 狀態時數與佔比計算

## 2. API 路由

- [x] 2.1 建立 `src/mes_dashboard/routes/resource_history_routes.py` 路由模組
- [x] 2.2 實作 `GET /api/resource/history/options` 端點：篩選選項
- [x] 2.3 實作 `GET /api/resource/history/summary` 端點：摘要資料
- [x] 2.4 實作 `GET /api/resource/history/detail` 端點：明細資料
- [x] 2.5 實作 `GET /api/resource/history/export` 端點：CSV 匯出
- [x] 2.6 在 `__init__.py` 註冊新路由 Blueprint

## 3. 前端頁面模板

- [x] 3.1 建立 `src/mes_dashboard/templates/resource_history.html` 頁面模板
- [x] 3.2 實作篩選條件區（日期範圍、粒度按鈕、站點/型號下拉、checkbox）
- [x] 3.3 實作 KPI 摘要卡片區（OU%、PRD、UDT、SDT、EGT、機台數）
- [x] 3.4 實作頁面路由 `GET /resource-history`

## 4. 前端圖表

- [x] 4.1 實作 OU% 趨勢折線圖（ECharts line chart）
- [x] 4.2 實作 E10 狀態堆疊長條圖（ECharts stacked bar chart）
- [x] 4.3 實作工站 OU% 對比水平條形圖（ECharts horizontal bar）
- [x] 4.4 實作設備狀態熱力圖（ECharts heatmap）

## 5. 前端表格

- [x] 5.1 實作階層式明細表格結構
- [x] 5.2 實作站點層級展開/收合功能
- [x] 5.3 實作型號層級展開/收合功能
- [x] 5.4 實作「全部展開」按鈕
- [x] 5.5 實作表格欄位格式化（時數/佔比顯示）
- [x] 5.6 實作匯出按鈕與 CSV 下載

## 6. 前端互動邏輯

- [x] 6.1 實作查詢按鈕點擊事件與載入指示器
- [x] 6.2 實作日期範圍驗證（不超過 730 天 / 兩年）
- [x] 6.3 實作時間粒度切換邏輯
- [x] 6.4 實作篩選條件變更處理
- [x] 6.5 實作查詢失敗的錯誤處理與 toast 通知
- [x] 6.6 實作初始狀態提示（「請設定查詢條件」）

## 7. 測試與驗證

- [x] 7.1 驗證 API 回傳資料格式正確
- [x] 7.2 驗證 OU% 計算結果正確
- [x] 7.3 驗證各時間粒度聚合正確
- [x] 7.4 驗證階層式表格展開/收合正常
- [x] 7.5 驗證 CSV 匯出內容正確
- [x] 7.6 驗證大量資料查詢效能（日期範圍限制生效）

## 8. 後續優化

- [x] 8.1 放寬查詢日期範圍至 730 天（兩年）
- [x] 8.2 移除明細查詢筆數上限（原 5000 筆）
- [x] 8.3 修復 NaN 值造成 JSON 序列化錯誤
- [x] 8.4 修復 MesApi 成功回應後誤觸重試機制
- [x] 8.5 E10 狀態分布圖表 tooltip 加入百分比顯示
