## Context

歷史查詢頁面（reject-history、hold-history、resource-history、job-query、excel-query）
目前使用 `read_sql_df`（connection pool，55s `call_timeout`），大範圍查詢容易 timeout。
前端 AbortController timeout 為 60~120s。Gunicorn worker timeout 為 130s。

現有 `read_sql_df_slow` 函式（`database.py:573`）已提供獨立連線路徑，
但只被 `query_tool_service.py` 的 `full_history` 模式使用，且 timeout 寫死 120s，
無並行控制。

## Goals / Non-Goals

**Goals:**
- 歷史查詢 service 全面遷移到 `read_sql_df_slow`（獨立連線，不佔用 pool）
- `read_sql_df_slow` 的 timeout 從寫死 120s 改為 config 驅動（預設 300s）
- 加入 global semaphore 限制並行 slow query 數量，保護 Oracle 不被大量連線壓垮
- Gunicorn 和前端 timeout 配合調整，確保查詢不會在任何層被過早截斷
- 即時監控頁完全不受影響

**Non-Goals:**
- 不改動 `read_sql_df` 本身（pool path 保持 55s）
- 不改動 EventFetcher、LineageEngine（小查詢，走 pool 即可）
- 不引入非同步任務佇列（Celery 等）
- 不對即時監控頁做任何修改
- 不修改 Oracle SQL 本身（查詢優化不在此範圍）

## Decisions

### D1: Import alias 遷移模式

**決策**：各 service 用 `from ... import read_sql_df_slow as read_sql_df` 取代原本的 `read_sql_df` import。

**理由**：兩個函式的 `(sql, params)` 簽名相容，alias 後所有 call site 零改動。
比在 `read_sql_df` 加 flag 更乾淨——不污染 pool path 的邏輯。

**替代方案**：在 `read_sql_df` 加 `slow=True` 參數 → 增加 pool path 複雜度，rejected。

### D2: Semaphore 限制並行數

**決策**：在 `database.py` 加 module-level `threading.Semaphore`，`read_sql_df_slow` 執行前 acquire，finally release。預設 3 並行（可由 `DB_SLOW_MAX_CONCURRENT` 環境變數調整）。

**理由**：Gunicorn gthread 模式 2 workers × 4 threads = 8 request threads。
限制 3 個 slow 連線確保至少 5 個 threads 仍可服務即時頁。
Oracle 端不會同時看到超過 3 個長查詢連線。

**Semaphore acquire timeout**：60 秒。超時回傳明確錯誤「查詢繁忙，請稍後再試」。

### D3: Timeout 數值選擇

| 層 | 修改前 | 修改後 | 理由 |
|---|---|---|---|
| `read_sql_df_slow` | 120s 寫死 | 300s config | 5 分鐘足夠大多數歷史查詢 |
| Gunicorn worker | 130s | 360s | 300s + 60s overhead |
| 前端 historical | 60~120s | 360s | 與 Gunicorn 對齊 |

### D4: excel_query_service 特殊處理

**決策**：excel_query_service 不用 `read_sql_df`，而是直接用 `get_db_connection()` + cursor。
改為在取得連線後設定 `connection.call_timeout = slow_call_timeout_ms`。

**理由**：保持現有 cursor batch 邏輯不變，只延長 timeout。

### D5: resource_history_service 並行查詢

**決策**：`query_summary` 用 `ThreadPoolExecutor(max_workers=3)` 並行 3 條查詢。
遷移後每條查詢佔 1 個 semaphore slot（共 3 個），單次請求可能佔滿所有 slot。

**接受此風險**：3 條查詢並行完成很快，slot 很快釋放。其他 slow 請求最多等 60s。

## Risks / Trade-offs

| 風險 | 緩解措施 |
|------|---------|
| Semaphore deadlock（exception 未 release） | `finally` block 保證 release |
| 3 並行 slot 不夠用（多人同時查歷史） | `DB_SLOW_MAX_CONCURRENT` 可動態調整，無需改 code |
| 長查詢佔住 Gunicorn thread 影響即時頁 | Semaphore 限制最多 3 個 thread 被佔用，其餘 5 個可用 |
| Circuit breaker 不再保護歷史查詢 | 歷史查詢為使用者手動觸發、非自動化，可接受 |
| `resource_history_service` 一次用完 3 slot | 查詢快速完成，slot 迅速釋放；可視需要降低 max_workers |
