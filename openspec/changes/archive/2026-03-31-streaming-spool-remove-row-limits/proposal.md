## Why

MSD (mid-section-defect) 查詢頻繁出現「事件資料已截斷，超出查詢限制」警告，material_trace 大範圍查詢因 256 MB DataFrame guard 失敗。根本原因是兩個功能的 spool 寫入路徑仍在 in-memory 全量累積後才寫磁碟，導致既有的 row/MB guard 持續觸發。`unified-spool-pipeline` 與 `event-fetcher-unified` 規格都明確規定：hard limits 需在對應路徑完成 spool-safe 遷移後才能解除。本次變更完成該遷移。

## What Changes

- `EventFetcher.fetch_events_to_parquet()` 改為真正的 streaming 路徑（Oracle cursor → `read_sql_df_slow_iter` → `pyarrow.ParquetWriter`），移除 spool 路徑的 `EVENT_FETCHER_MAX_TOTAL_ROWS` 500k row guard；返回值升格為 `(row_count, quality_meta)`
- 新增 `EventFetcher._stream_batches_to_writer()` — 提取 batch + threading + jobs domain CONTAINERIDS 展開邏輯，供 streaming 路徑使用
- `_execute_msd_compat_job()` 改用 `fetch_events_to_parquet()` streaming 路徑寫 spool，取代舊的 `fetch_events()` in-memory 路徑
- `_execute_trace_events_job()` MSD 分支改用 `fetch_events_to_parquet()` streaming 寫 spool；`_build_job_msd_aggregation()` 新增 DuckDB spool hit 路徑，aggregation 從 spool 讀取而非 in-memory dict
- 新增 `_write_msd_events_spool_from_paths()` — streaming 合併多個 domain parquet 至單一 MSD events spool
- `material_trace.execute_to_spool()` 改用新增的 `_execute_batched_query_to_parquet()` streaming 路徑，移除 `_check_memory_guard()` / 256 MB guard 對 spool 路徑的限制
- `fetch_events()` 本體不動（非 spool interactive 路徑保留 row guard）

## Capabilities

### New Capabilities

（無新 capability；本次變更為現有 capability 的實作遷移）

### Modified Capabilities

- `event-fetcher-unified`: `fetch_events_to_parquet()` 現定義為真正的 streaming spool 寫入路徑；row guard 退休條件（spool-safe 遷移完成）現已滿足，spool 路徑不再截斷
- `unified-spool-pipeline`: MSD trace events 及 material-trace spool 寫入路徑正式完成 streaming 遷移，對應的 in-memory guard 隨舊路徑退休而解除

## Impact

**後端修改**
- `src/mes_dashboard/services/event_fetcher.py` — 新增 `_stream_batches_to_writer()`；改寫 `fetch_events_to_parquet()`
- `src/mes_dashboard/services/trace_job_service.py` — 新增 `_write_msd_events_spool_from_paths()`；改寫 `_execute_trace_events_job()` MSD 分支；`_build_job_msd_aggregation()` 新增 DuckDB hit 路徑
- `src/mes_dashboard/services/mid_section_defect_service.py` — 改寫 `_execute_msd_compat_job()` event fetch loop
- `src/mes_dashboard/services/material_trace_service.py` — 新增 `_execute_batched_query_to_parquet()`；改寫 `execute_to_spool()`

**不影響**
- API 外部合約不變（HTTP 路徑、請求/回應格式皆不變）
- `fetch_events()` in-memory 路徑不變（interactive 路徑保留 row guard）
- 前端程式碼不需修改
- `_check_memory_guard()` 定義保留，interactive paths 仍使用

**依賴**
- `pyarrow` (已有)、`read_sql_df_slow_iter` (已有)、`MsdDuckdbRuntime` (已有)
