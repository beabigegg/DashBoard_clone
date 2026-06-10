# Change Request

## Original Request

Resource-history cache architecture fix: canonical spool, remove granularity from key, fix warmup, add view result cache.

## Business / User Goal

設備歷史績效頁面（resource-history）目前每次帶篩選條件的查詢都必須打 Oracle，使用者切換工站群組、型號、粒度時需等待 10–30 秒。目標是讓篩選條件切換和粒度切換在 cache warm 的情況下毫秒回應，只有「第一次查詢某段日期範圍」才需要去 Oracle。

## Non-goals

- 不修改 Oracle SQL 的資料來源（base_facts.sql / oee_facts.sql 欄位不變）
- 不改動前端 UI 或任何元件
- 不影響其他頁面（reject-history、hold-history 等）的快取邏輯

## Constraints

- 必須維持現有 API 回應格式（route contract 不變）
- 快取 key 變更需 bump schema_version 讓舊 spool 自然失效
- 必須通過現有 pytest 和 Vitest 測試套件

## Known Context

經過分析，目前存在以下問題：

1. 系統 B（canonical spool）從未生效：`ensure_dataset_loaded()` 檢查 canonical key 但寫入 filter-inclusive key，導致 `try_compute_query_from_canonical_spool()` 永遠回傳 SPOOL_MISS
2. Canonical key 含 `granularity`：切換粒度（日/週/月/年）觸發不同 key，無法共用同一份底層 parquet
3. 系統 A（filter-inclusive key）是唯一實際在用的路徑，每個篩選組合各自需要一次 Oracle 查詢
4. `apply_view()` 每次重算 DuckDB，結果未快取

相關檔案：
- `src/mes_dashboard/services/resource_dataset_cache.py`
- `src/mes_dashboard/services/resource_history_sql_runtime.py`
- `src/mes_dashboard/routes/resource_history_routes.py`

## Open Questions

- View result cache（Phase 2）的 TTL 建議 5 分鐘，是否合適？
- 廢棄系統 A（filter-inclusive key）是否在本 change 範圍內，或分開另立 change？

## Requested Delivery Date / Priority

高優先，影響生產環境使用者體驗。
