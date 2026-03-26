## Context

壓測 2026-03-10 揭露 reject-history `/query` 端點在高併發下的記憶體崩潰鏈：

1. **merge_chunks 全量載入** — `batch_query_engine.py:576-636` 將所有 chunk DataFrame 累積在 `dfs: List[pd.DataFrame]`，最後 `pd.concat()`。38 chunks × 50K rows/chunk = 190 萬列，峰值記憶體 ~2× 資料量。
2. **無入口背壓** — `/query` 是唯一無 rate limit 的 reject-history 端點，壓測時大量併發請求同時觸發 engine。
3. **跨端點級聯** — RSS 飆升後 trace（1100MB 閾值）與 query-tool（1100MB）一起被 503，看似全系統崩潰。
4. **gunicorn max_requests=1200** — 高壓時 worker 循環重啟降低容量，加劇問題。

現有防線（200K max_total_rows、RSS guard、三級 worker_memory_guard）已部分緩解，但不解決根因。

## Goals / Non-Goals

**Goals:**
- 消除 merge_chunks 全量載入的記憶體峰值（根因修復）
- 為 /query 加入 rate limit 與 RSS 前置檢查（入口背壓）
- SQL 層強制 per-chunk 行數上限（深度防禦）
- 減少高壓下 gunicorn worker 無謂重啟
- 所有合理範圍查詢仍回傳完整結果（不遺失資料）

**Non-Goals:**
- 不修改 worker_memory_guard 三級防線邏輯（已驗證正確）
- 不修改 trace_routes / query_tool_service 的 RSS 閾值（由上游攔截解決）
- 不重構 batch_query_engine 架構（僅新增串流路徑）
- 不處理前端重試策略

## Decisions

### D1: 串流合併使用 iterate_chunks + ParquetWriter → spool 檔案

**選擇**: 新增 `merge_chunks_to_spool()` 利用現有 `iterate_chunks()` generator 逐塊寫入 parquet spool。

**替代方案**:
- (A) 改良 merge_chunks 為分批 concat → 仍需全量在記憶體，只是分批執行，改善有限
- (B) 直接串流回 HTTP response → 無法支援後續 /view 分頁、/export 等需要隨機讀取的端點

**理由**: iterate_chunks 已存在（`batch_query_engine.py:639-658`），pyarrow.ParquetWriter 支持增量寫入。spool 檔案可被 /view、/export-cached 用 `pd.read_parquet()` 分頁讀取。峰值記憶體從全量 × 2 降至單 chunk × 1。

### D2: RSS 前置檢查閾值設 900MB（低於 trace/query-tool 的 1100MB）

**選擇**: reject /query 在 900MB 時自我拒絕，確保 RSS 不會被推高到影響其他端點。

**理由**: /query 是 RSS 壓力的**來源端**。若等到 1100MB 才擋，trace 和 query-tool 已經受影響。提早 200MB 攔截，讓其他端點保持可用。

### D3: SQL 層用 `ROWNUM <= N` 而非 `FETCH FIRST N ROWS ONLY`

**選擇**: `SELECT * FROM (...) WHERE ROWNUM <= {max_rows_per_chunk}` 包裹原 SQL。

**替代方案**: Oracle 12c `FETCH FIRST N ROWS ONLY` — 需要原 SQL 無 `ORDER BY` 衝突。

**理由**: ROWNUM 在所有 Oracle 版本通用，且 reject primary SQL 已經是複雜 subquery，外層包裹最安全。

### D4: Rate limit 預設 10/60s

**選擇**: `default_max_attempts=10, default_window_seconds=60`。

**理由**: /query 是最重的端點（觸發 engine 並行查詢）。正常使用者每分鐘不會發超過 5 次主查詢。10/60s 留有餘裕，且可透過 env var 動態調整。

### D5: gunicorn max_requests 提升至 5000

**選擇**: `GUNICORN_MAX_REQUESTS=5000, GUNICORN_MAX_REQUESTS_JITTER=1000`。

**理由**: RSS guard（95% hard limit）已負責記憶體驅動的 worker 回收。max_requests=1200 在高壓時造成過頻重啟，降低有效容量。5000 大幅減少循環重啟頻率。

## Risks / Trade-offs

- **[Spool 磁碟空間]** → 串流 spool 產生暫存 parquet 檔案。Mitigation: 沿用現有 spool TTL 機制（`_REJECT_ENGINE_SPOOL_TTL_SECONDS=21600`），到期自動清理。
- **[Schema 不一致]** → 不同 chunk 可能有微幅 schema 差異。Mitigation: 第一個 chunk 決定 schema，後續 chunk 做 column alignment 或 skip 不一致列。
- **[Rate limit 影響正常使用]** → 10/60s 可能在大量使用者同時操作時不足。Mitigation: 透過 env var 可動態調整，不需重新部署程式碼。
- **[900MB RSS 閾值過早]** → 可能在正常大查詢時就被擋。Mitigation: 串流 merge 實施後，單次查詢 RSS 增量大幅下降，900MB 閾值幾乎不會觸發。
- **[Partial failure metadata]** → 串流路徑需確保 partial failure flag 正確傳遞。Mitigation: `get_batch_progress()` 在 spool 寫入後、`redis_clear_batch()` 前讀取，與現有時序一致。
