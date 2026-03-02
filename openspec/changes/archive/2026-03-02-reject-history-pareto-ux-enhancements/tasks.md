## 1. Frontend Pareto UX Enhancements

- [x] 1.1 在 `FilterPanel.vue` 將「Pareto 僅顯示累計前 80%」移至補充篩選區域並維持預設啟用
- [x] 1.2 在 `ParetoSection.vue` 新增 `全部顯示 / 只顯示 TOP 20` 控制（僅 `TYPE/WORKFLOW/機台` 顯示）
- [x] 1.3 在 `ParetoSection.vue` 支援圖表與表格點選多選、選取高亮與取消選取
- [x] 1.4 在 `App.vue` 新增 Pareto 多選狀態管理與 URL 狀態同步（dimension + selected values + display scope）

## 2. Backend Filter/Export Parity

- [x] 2.1 在 `reject_dataset_cache.py` 新增 Pareto 維度多選過濾 helper，供 view/export 共用
- [x] 2.2 擴充 `apply_view()` 支援 `pareto_dimension` + `pareto_values` 並套用到明細過濾
- [x] 2.3 擴充 `export_csv_from_cache()` 支援與 view 相同的 Pareto 多選過濾語意
- [x] 2.4 更新 `reject_history_routes.py` 的 `/view` 與 `/export-cached` 參數解析與維度驗證（非法維度回 400）

## 3. Validation and Regression Tests

- [x] 3.1 新增/更新 route 測試：驗證 `/view`、`/export-cached` 會傳遞 Pareto 多選參數且非法維度回 400
- [x] 3.2 新增/更新 cache service 測試：驗證 Pareto 多選在 `apply_view` 與 `export_csv_from_cache` 行為一致
- [x] 3.3 執行 reject-history 相關測試並確認無回歸
