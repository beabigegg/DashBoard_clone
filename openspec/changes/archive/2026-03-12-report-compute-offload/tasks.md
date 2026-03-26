## 1. Phase 0：resource-history Parquet Spool 輸出

- [x] 1.1 修改 `resource_dataset_cache.py`：primary query 完成後呼叫 `merge_chunks_to_spool()` 將 chunks 流式合併為 Parquet spool 檔案，並在 Redis 記錄 spool metadata（namespace=`resource_dataset`）
- [x] 1.2 修改 `resource_dataset_cache.py`：移除 view 階段的 `enforce_dataset_memory_guard` 呼叫（分段處理已提供保護）
- [x] 1.3 驗證 resource-history primary query 產出的 Parquet spool 檔案可被 DuckDB `read_parquet()` 正確讀取，欄位與現有 DataFrame 一致

## 2. Phase 0：hold-history Parquet Spool 輸出

- [x] 2.1 修改 `hold_dataset_cache.py`：primary query 完成後呼叫 `merge_chunks_to_spool()` 將 chunks 流式合併為 Parquet spool 檔案，並在 Redis 記錄 spool metadata（namespace=`hold_dataset`）
- [x] 2.2 修改 `hold_dataset_cache.py`：移除 view 階段的 `enforce_dataset_memory_guard` 呼叫
- [x] 2.3 驗證 hold-history primary query 產出的 Parquet spool 檔案欄位與現有 DataFrame 一致

## 3. Track A：resource-history DuckDB SQL Runtime

- [x] 3.1 新增 `resource_history_sql_runtime.py`：實作 `try_compute_view_from_spool()` 入口函式，讀取 spool Parquet 並回傳 view dict
- [x] 3.2 實作 KPI summary SQL：GROUP BY 後 SUM hours，計算 OU% 和 AVAIL%，COUNT DISTINCT HISTORYID
- [x] 3.3 實作 trend SQL：依 granularity (day/week/month/year) 分桶 GROUP BY，計算每期 OU%
- [x] 3.4 實作 heatmap SQL：GROUP BY (workcenter, date)，計算 OU% 矩陣，workcenter 依 seq 排序
- [x] 3.5 實作 workcenter comparison SQL：GROUP BY workcenter，OU% DESC 排序，LIMIT 15
- [x] 3.6 實作 detail SQL：per-resource 指標 + LIMIT/OFFSET 分頁，合併 resource_cache 維度資料
- [x] 3.7 新增 feature flag `RESOURCE_HISTORY_SQL_VIEW_ENABLED`（預設 True），在 view 路徑加入 try SQL → fallback Pandas 邏輯
- [x] 3.8 驗證 DuckDB 與 Pandas 路徑的 view 輸出一致（parity 測試）

## 4. Track A：hold-history DuckDB SQL Runtime

- [x] 4.1 新增 `hold_history_sql_runtime.py`：實作 `try_compute_view_from_spool()` 入口函式
- [x] 4.2 實作 trend SQL：依 date GROUP BY，套用 07:30 shift boundary，支援 quality/non_quality/all hold_type
- [x] 4.3 實作 reason Pareto SQL：GROUP BY HOLDREASONNAME，計算 count/qty/pct/cumPct，DESC 排序
- [x] 4.4 實作 duration SQL：CASE 表達式分 4 桶 (<4h, 4-24h, 1-3d, >3d)，計算 count/pct
- [x] 4.5 實作 list SQL：hold_type + reason 篩選，HOLDTXNDATE DESC 排序，LIMIT/OFFSET 分頁
- [x] 4.6 新增 feature flag `HOLD_HISTORY_SQL_VIEW_ENABLED`（預設 True），在 view 路徑加入 try SQL → fallback Pandas 邏輯
- [x] 4.7 驗證 DuckDB 與 Pandas 路徑的 view 輸出一致（parity 測試）

## 5. Track B：Parquet 下載 API

- [x] 5.1 新增 route `GET /api/spool/{namespace}/{query_id}.parquet`：驗證 namespace 白名單 + query_id 格式 + CSRF token
- [x] 5.2 實作 spool 檔案串流回傳：Content-Type=application/octet-stream + Content-Length + Content-Disposition headers
- [x] 5.3 實作過期/不存在的 spool 回傳 HTTP 410 (Gone)
- [x] 5.4 更新 `contract/api_inventory.md` 加入新 endpoint

## 6. Track B：前端 DuckDB-WASM 基礎建設

- [x] 6.1 安裝 `@duckdb/duckdb-wasm` npm 依賴
- [x] 6.2 新增 `frontend/src/workers/duckdb-worker.js`：初始化 DuckDB-WASM instance，處理 query/register 訊息
- [x] 6.3 新增 `frontend/src/core/duckdb-client.js`：封裝 Worker 通訊（lazy init、sendQuery、registerParquet、destroy）
- [x] 6.4 新增 `frontend/src/core/risk-score.js`：實作 `calcRiskScore(yieldPct, scrapQty, threshold)` 和 `calcRiskLevel()` 前端公式
- [x] 6.5 Vite 配置確認：確保 `?worker` import 正常運作，評估 COOP/COEP headers 需求

## 7. Track B：yield-alert-center 前端 View 遷移

- [x] 7.1 修改 yield-alert /view 的 server response：大資料集時加入 `spool_download_url` 和 `total_row_count` 欄位
- [x] 7.2 修改 `yield-alert-center/App.vue`：根據 total_row_count 判斷使用 JSON 模式或 Parquet + DuckDB-WASM 模式
- [x] 7.3 實作前端 yield-alert sub-view SQL：summary、trend、heatmap、station_summary、package_summary、alerts detail（移植後端 SQL）
- [x] 7.4 實作前端 filter/sort/page 操作走本地 DuckDB-WASM 查詢，不再呼叫 /view API
- [x] 7.5 驗證前端計算結果與 server-side 結果 parity

## 8. Track B：reject-history 前端 View 遷移

- [x] 8.1 修改 reject-history /view 的 server response：大資料集時加入 `spool_download_url` 和 `total_row_count` 欄位
- [x] 8.2 修改 `reject-history/App.vue`：根據 total_row_count 判斷使用 JSON 模式或 Parquet + DuckDB-WASM 模式
- [x] 8.3 實作前端 reject-history sub-view SQL：analytics_raw、summary、detail、batch_pareto（移植後端 SQL）
- [x] 8.4 實作前端 filter/sort/page 操作走本地 DuckDB-WASM 查詢
- [x] 8.5 驗證前端計算結果與 server-side 結果 parity

## 9. 整合測試與回歸驗證

- [x] 9.1 後端 parity 測試：resource-history DuckDB vs Pandas 各 sub-view 輸出對比
- [x] 9.2 後端 parity 測試：hold-history DuckDB vs Pandas 各 sub-view 輸出對比
- [x] 9.3 前端 parity 測試：yield-alert DuckDB-WASM vs server-side 各 sub-view 輸出對比
- [x] 9.4 前端 parity 測試：reject-history DuckDB-WASM vs server-side 各 sub-view 輸出對比
- [x] 9.5 Fallback 測試：feature flag 關閉時確認 Pandas 路徑正常、DuckDB-WASM 不可用時確認 server fallback 正常
- [x] 9.6 效能基準：比較遷移前後的 server view latency 和前端 filter 回應時間
