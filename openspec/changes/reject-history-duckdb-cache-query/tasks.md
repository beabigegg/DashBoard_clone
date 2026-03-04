## 1. SQL Runtime Foundation

- [ ] 1.1 新增 reject-history cache-SQL runtime 模組（DuckDB 連線管理、來源解析、參數綁定 helper）
- [ ] 1.2 新增 parquet spool 優先讀取與來源 fallback 策略（含 deterministic fallback reason）
- [ ] 1.3 新增 runtime feature flags（全域與 endpoint 級開關）與預設值
- [ ] 1.4 補齊依賴設定（`requirements.txt` / `pyproject.toml` / `environment.yml`）與啟動相容性檢查

## 2. Batch Pareto SQL-first 路徑

- [ ] 2.1 將 `batch-pareto` 在 materialized miss/stale/build-fail 時接入 cache-SQL 計算路徑
- [ ] 2.2 保留並驗證 exclude-self cross-filter、`top80`、`top20` 行為一致
- [ ] 2.3 實作 SQL 不可用時的 fallback policy（legacy 或 fail-fast）
- [ ] 2.4 補上 batch-pareto parity 測試（SQL vs legacy）與 fallback metadata 測試

## 3. View SQL 化

- [ ] 3.1 以 SQL 重建 `summary` 與 `trend` 聚合計算（保持欄位與精度契約）
- [ ] 3.2 以 SQL 實作 detail 查詢、排序與分頁（含 policy/supplementary/trend/pareto selections）
- [ ] 3.3 將 `/api/reject-history/view` 切到 SQL-first 路徑並保留 schema 相容
- [ ] 3.4 補上 view parity 測試與 cache-expired 行為回歸測試

## 4. Export Cached 串流化

- [ ] 4.1 將 `export-cached` 改為 generator/streaming CSV 輸出
- [ ] 4.2 確保 export 與 detail 使用同一套 filter 組合邏輯，維持 scope parity
- [ ] 4.3 移除全量 rows list / `to_dict` 依賴，避免匯出前全載入記憶體
- [ ] 4.4 補上大資料匯出測試（串流輸出、欄位契約、篩選一致性）

## 5. Observability, Guard, Rollout

- [ ] 5.1 新增 SQL runtime telemetry（來源、fallback reason、耗時、列數）
- [ ] 5.2 保留既有 memory guards，調整 guard 觸發點與訊息以符合 SQL-first 流程
- [ ] 5.3 制定 rollout 策略（batch -> view -> export）與對應回退開關
- [ ] 5.4 更新操作文件與驗證清單（前端提示、匯出不受顯示限制影響、壓測項目）
