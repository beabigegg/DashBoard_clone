## Context

### 現況

`EventFetcher.fetch_events()` 以 in-memory `defaultdict(list)` 累積所有 Oracle rows，
設有 `EVENT_FETCHER_MAX_TOTAL_ROWS = 500,000` 的 row guard；達到上限時設 `truncated=True`
並停止寫入，導致 MSD 前端顯示截斷警告。

`fetch_events_to_parquet()`（task 6.4）本應為 streaming 路徑，但目前實作仍呼叫
`fetch_events()`，guard 未解除。

`material_trace.execute_to_spool()` 呼叫 `_execute_batched_query()` 全量累積 DataFrame，
再呼叫 `_check_memory_guard()`（上限 256 MB），超限時拋出 MemoryError。

### 現有模式（可直接複用）

- `batch_query_engine.merge_chunks_to_spool()`：`read_sql_df_slow_iter` → `pa.Table` → `pq.ParquetWriter` 逐批 write，已在 reject-history、production-history 驗證
- `yield_alert_dataset_cache`：簡化版 streaming 模式
- `MsdDuckdbRuntime.get_summary()`：從 events spool parquet 以 DuckDB 計算 MSD aggregation，`_execute_trace_events_job` 寫完 spool 後立即可用

### 約束

- `fetch_events()` 不能修改（query_tool、report 等 interactive 路徑仍需 in-memory + quality_meta）
- `_build_job_msd_aggregation()` 目前直接呼叫 `build_trace_aggregation_from_events(domain_results)`，不走 DuckDB；需在此加 spool hit 路徑
- jobs domain 的 CONTAINERIDS 字串展開邏輯必須在 streaming 路徑中保留
- API 外部合約（HTTP 路徑、回應格式）不能改變

---

## Goals / Non-Goals

**Goals:**
- 讓 `fetch_events_to_parquet()` 真正 streaming，spool 路徑不再截斷
- 讓 `_execute_msd_compat_job()` 和 `_execute_trace_events_job()` MSD 分支都走 streaming spool
- 讓 `material_trace.execute_to_spool()` 走 streaming，移除 256 MB guard 對 spool 路徑的影響
- 保持向後相容（API 合約、非 spool 路徑行為不變）

**Non-Goals:**
- 修改 `fetch_events()` 本體
- 修改 interactive paths（`forward_query`、`reverse_query`、`export_csv`）的 memory guard
- 改動 `_execute_trace_events_job()` 非 MSD profile 的路徑
- 處理 reject_dataset / production_history（已無截斷問題）

---

## Decisions

### D1：`_stream_batches_to_writer()` 以 callback 解耦輸出層

**決策**：新增 `EventFetcher._stream_batches_to_writer(normalized_ids, domain, row_callback)`，
callback 接受 `(columns: List[str], rows: List[tuple])`；`fetch_events_to_parquet()` 的
ParquetWriter 邏輯放在外層，不進入 `_stream_batches_to_writer()`。

**理由**：讓 batch/threading/jobs-expansion 邏輯與 I/O 層（ParquetWriter）分離，
`_stream_batches_to_writer()` 可獨立測試。

**替代方案**：直接在 `_stream_batches_to_writer()` 內嵌 ParquetWriter — 耦合度高，
且 writer 初始化需在第一個 non-empty batch 時才能確定 schema，callback 模式更彈性。

---

### D2：`fetch_events_to_parquet()` 返回值升格為 `Tuple[int, Dict]`

**決策**：`fetch_events_to_parquet()` 返回 `(row_count: int, quality_meta: Dict[str, Any])`。

**理由**：呼叫方（`_execute_msd_compat_job`、`_execute_trace_events_job`）需要 quality_meta
以回報給 job result 和 spool 元數據。目前此函數無外部呼叫者，API 可安全修改。

**替代方案**：另外新增一個函數（如 `fetch_events_streaming()`）保持 `fetch_events_to_parquet()` 的舊 API — 無實際收益，增加 public surface。

---

### D3：`_write_msd_events_spool_from_paths()` streaming 合併多 domain parquet

**決策**：新增函數接受 `Dict[str, Path]`（domain → tmp parquet），
用 `pq.ParquetFile.iter_batches()` 依序 streaming 讀取各 domain parquet，
以 `pq.ParquetWriter` 寫入單一 MSD events spool。

**理由**：MSD events spool 把多 domain rows 合併成一個 parquet，供 DuckDB 用
`events.domain = '...'` 過濾。此步驟本身也需要 streaming，不能先 concat DataFrame 再寫。

**替代方案**：讓每個 domain 有獨立 spool，DuckDB 查詢時 UNION ALL — 可行，但改動
`MsdDuckdbRuntime` schema 較多，且現有格式已有 domain column。

---

### D4：`_build_job_msd_aggregation()` 優先走 DuckDB spool hit

**決策**：在 `_build_job_msd_aggregation()` 開頭新增 DuckDB spool hit 嘗試：
若 `trace_query_id` 已有 spool，呼叫 `MsdDuckdbRuntime(trace_query_id).get_summary()`；
成功則把 `domain_quality_meta` 注入 summary 並返回，不走 in-memory `build_trace_aggregation_from_events()`。

**理由**：`_execute_trace_events_job()` streaming 路徑執行完 `_write_msd_events_spool_from_paths()` 後，spool 立即可用；DuckDB aggregation 與 in-memory aggregation 結果等效，且無記憶體壓力。

若 spool 不可用（Redis 故障等極端情況），fallback 傳入 `domain_results={}` → aggregation 返回 None → job 以 error 結束（可接受，極罕見）。

**替代方案**：保留 `domain_results` 於記憶體作為 fallback — 等於讓 streaming 改造對此路徑無實際效果。

---

### D5：`material_trace._execute_batched_query_to_parquet()` inline enrichment

**決策**：在 streaming 迴圈內，對每個 `df_chunk` 直接 map `WORKCENTER_GROUP`，
不需 `concat` 後再 map。

**理由**：現有 `_execute_batched_query()` 在組完整 DataFrame 後呼叫 `_enrich_workcenter_group()`；
streaming 版本在 chunk 層級做 enrichment，記憶體消耗降至 O(chunk_size)。

**Dedup 策略（wildcard overlap）**：exact token 路徑（`allow_patterns=False`）無 overlap；
wildcard 路徑在多 batch 間有極小機率重複。初版不做 streaming dedup，
接受極少量重複（實際查詢量少，DuckDB 查詢可加 DISTINCT）。

---

## Risks / Trade-offs

**[Risk] jobs domain 展開邏輯在 streaming 中的正確性**
`jobs` domain 的 CONTAINERIDS 是逗號分隔字串，需在 Python 中展開，每個 cid 複製一份 row。
→ 在 `_stream_batches_to_writer()` 中保留現有 `_fetch_and_group_batch()` 的 jobs 處理邏輯，
加單元測試驗證展開行為。

**[Risk] DuckDB spool hit 失敗時 MSD aggregation 無 fallback**
`_build_job_msd_aggregation()` 的 DuckDB path 若失敗（spool miss），傳 `domain_results={}` 會導致 job error。
→ 接受此風險；spool 剛被 `_write_msd_events_spool_from_paths()` 寫入，
miss 的唯一可能是 Redis metadata 或 filesystem 異常，此時 job error 是正確行為。

**[Risk] Schema 對齊失敗（不同 batch 欄位型別不一致）**
Oracle 可能對同一 domain 不同 batch 回傳略有差異的型別（NULL column 推斷差異）。
→ 使用現有 `table.cast(schema, safe=False)` 模式（與 `merge_chunks_to_spool()` 相同），
第一個 non-empty batch 確定 schema，後續 cast 對齊。

**[Risk] `fetch_events_to_parquet()` 返回值破壞相容性**
此函數目前無外部呼叫者（grep 確認），返回值從 `int` 改為 `Tuple[int, Dict]` 無相容問題。
→ 已驗證。若未來意外有呼叫者，型別錯誤會在執行期立即顯現。

---

## Migration Plan

1. 實作 `_stream_batches_to_writer()` + 單元測試 → 不影響任何現有行為
2. 改寫 `fetch_events_to_parquet()` → 僅影響此函數本身（目前無呼叫者）
3. 新增 `_write_msd_events_spool_from_paths()` → 不影響現有路徑
4. 更新 `_execute_msd_compat_job()` 呼叫鏈 → MSD compat job 路徑走 streaming
5. 更新 `_build_job_msd_aggregation()` + `_execute_trace_events_job()` MSD 分支 → trace job 路徑走 streaming
6. 新增 `_execute_batched_query_to_parquet()` → 不影響 interactive 路徑
7. 改寫 `execute_to_spool()` → RQ worker 的 spool 路徑走 streaming

每步驟均可獨立 deploy；步驟 4 以後才真正解除 guard。

**Rollback**：每個呼叫點可加環境變數 feature flag（`FETCH_EVENTS_LEGACY_PARQUET=true`、`MATERIAL_TRACE_LEGACY_SPOOL=true`）快速回退至舊路徑。

---

## Open Questions

（無，設計已充分研究）
