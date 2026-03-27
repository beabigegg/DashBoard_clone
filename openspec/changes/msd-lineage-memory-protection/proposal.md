## Why

MSD（中段不良追溯）頁面的 trace pipeline 在大日期範圍查詢時會導致系統 OOM 崩潰。2026-03-27 事故中，station_detection 回傳 56,796 unique lots，LineageEngine 對每個 lot 做 `CONNECT BY NOCYCLE` 產生 93,264 nodes 與約 260 個 slow queries，記憶體從 86.8% 飆到 94.2% 後系統掛掉。根本原因是 MSD 在 trace pipeline 的三個階段（seed-resolve、lineage、events）都缺乏大查詢保護：lineage 階段沒有 seed 數量上限，events 階段刻意豁免 CID limit (`is_msd` bypass)，整條路徑都在 Gunicorn worker 同步執行，沒有 parquet spool 或 DuckDB 等記憶體隔離機制。

## What Changes

- **MSD lineage 階段加入 seed 數量閥值 + async 分批處理**：當 seed lots 超過閥值時，lineage 解析搬到 RQ worker 執行，結果 spool 到 parquet 磁碟暫存，避免 Gunicorn worker OOM
- **LineageEngine 加入 RSS guard + 分批 yield 模式**：在 `resolve_full_genealogy()` 和 `resolve_forward_tree()` 入口加 seed 數量上限與 RSS 預測檢查，大量 seeds 自動分批處理
- **trace_routes /events 移除 MSD `is_msd` CID limit 豁免**：MSD profile 不再跳過 `TRACE_EVENTS_CID_LIMIT` 檢查，改為自動 fallback 到 async job（與其他 profile 一致）
- **MSD trace pipeline 整合 parquet spool + DuckDB runtime**：lineage 結果和 event fetch 結果存 parquet，後續 aggregation 用 DuckDB 計算，記憶體上界固定可控

## Capabilities

### New Capabilities
- `msd-lineage-spool`: MSD lineage 解析的 async 分批執行與 parquet spool 暫存機制
- `lineage-admission-control`: LineageEngine 的 seed 數量閥值、RSS guard、分批處理保護機制

### Modified Capabilities
- `trace-staged-api`: 移除 events endpoint 的 `is_msd` CID limit 豁免，MSD 超過 CID limit 時自動 fallback async
- `lineage-engine-core`: 新增 seed count guard、RSS check、分批 yield 模式，保持 API 向後相容

## Impact

- **後端**：`lineage_engine.py`、`trace_routes.py`、`mid_section_defect_service.py`、`msd_query_job_service.py`
- **基礎設施**：新增 MSD lineage spool 的 parquet 目錄（複用 `query_spool_store.py`），可能需要擴展 `batch_query_engine.py` 支援 lineage 分批
- **前端**：無變更（`useTraceProgress` 已支援 async polling + NDJSON streaming）
- **其他 LineageEngine 調用者**：`query_tool_service.py`（max 100 lots）和 `production_history_service.py`（手動輸入）不受影響，輸入量遠低於閥值
