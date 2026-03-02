## Context

目前 6 個服務各自處理大查詢，缺乏統一保護：

| 服務 | 查詢類型 | 現有保護 | 缺口 |
|------|---------|---------|------|
| reject-history | 日期 + 工單/Lot/GD 展開 | L1+L2 快取、`read_sql_df_slow` | 無記憶體守衛、`limit=999999999`、缺分塊查詢 |
| hold-history | 日期 | L1+L2 快取、`read_sql_df_slow` | 無記憶體守衛、缺時間分塊 |
| resource-history | 日期 + 設備 ID | L1+L2 快取、1000 筆分批 | 無記憶體守衛 |
| mid-section-defect | 日期 → 偵測 → 族譜 → 上游 | Redis 快取、EventFetcher 分批 | 無偵測數量上限 |
| job-query | 日期 + 設備 ID | 1000 筆分批、`read_sql_df_slow` | **無結果快取**、缺時間分塊 |
| query-tool | 多種 resolver → container ID | 輸入筆數限制、resolve route 短 TTL 快取、EventFetcher 快取 | 多數查詢仍走 `read_sql_df`（55s timeout）、缺統一分塊編排 |

參考實作：
- `EventFetcher`：batch 1000 + ThreadPoolExecutor(2) + `read_sql_df_slow_iter` streaming + Redis 快取 — **已是最佳實作**
- `LineageEngine`：batch 1000 + depth limit 20 — **族譜專用引擎**

目標：建立 `BatchQueryEngine` 共用模組，任何服務接入即獲得完整保護。

## Goals / Non-Goals

**Goals:**
- 統一 parquet-in-Redis 存取為共用模組（消除 3 處重複）
- 提供時間範圍分解（長日期 → ~31 天月份區間）
- 提供 ID 批次分解（工單/Lot/GD 展開後的大量 container ID → 1000 筆一批）
- 記憶體守衛：每個 chunk 結果檢查 memory_usage，超過閾值中止
- 結果筆數限制：可配置上限，超過時截斷並標記
- 受控並行：預設循序、可選並行、semaphore 感知
- Redis 分塊快取 + 部分命中
- 統一使用 `read_sql_df_slow`（300 秒 dedicated connection）
- 定義 query_hash 與 chunk 邊界語意，避免跨服務行為不一致
- 定義 chunk cache 與服務 L1/L2 dataset cache 互動規則

**Non-Goals:**
- 不修改 SQL 語句本身
- 不引入新的外部依賴
- 不改變前端 API 介面（前端無感知）
- 不替換 EventFetcher / LineageEngine（它們已各自最佳化，引擎提供可選接入點）
- 不改變 trace_job_service 的 RQ 非同步架構

## Decisions

### Decision 1: 提取 `redis_df_store.py` 共用模組

**選擇**：從 reject/hold/resource_dataset_cache 提取相同的 `_redis_store_df` / `_redis_load_df` 到 `src/mes_dashboard/core/redis_df_store.py`。

**替代方案**：(A) 保持各自複製 → 已有 3 處重複，維護困難。

**理由**：parquet-in-Redis 是 DataFrame 序列化工具，與快取策略（TTL、LRU）屬不同層次。

### Decision 2: `BatchQueryEngine` 作為工具類而非基底類別

**選擇**：提供獨立函式（`decompose_by_time_range`、`decompose_by_ids`、`execute_plan`、`merge_chunks`），各服務按需調用。

**替代方案**：(A) 抽象基底類別 `BaseDatasetCache` → 三個 dataset cache 差異大（SQL、policy filter、衍生計算），強制繼承會過度耦合。

**理由**：工具類模式讓服務保持現有結構，僅在主查詢路徑決定是否啟用分解。閾值以下的查詢完全不經過引擎。

### Decision 3: 預設循序、可選並行、semaphore 感知

**選擇**：`execute_plan(parallel=1)` 預設循序。實際並行上限 = `min(requested, semaphore_available - 1)`。

**替代方案**：(A) 預設並行 → 可能耗盡 semaphore；(B) 完全不並行 → 失去速度。

**理由**：Oracle 連線稀缺（Production 預設 `DB_SLOW_MAX_CONCURRENT=5`，Development 常見為 3）。reject_dataset_cache 查詢最重可設 parallel=2，其他預設循序最安全。

### Decision 4: 記憶體守衛 + 結果筆數限制

**選擇**：每個 chunk 查詢後檢查 `df.memory_usage(deep=True).sum()`，超過 `BATCH_CHUNK_MAX_MEMORY_MB`（預設 256MB）時中止該 chunk 並標記失敗。同時提供 `max_rows_per_chunk` 參數，在 SQL 中加入 `FETCH FIRST N ROWS ONLY`。

**替代方案**：(A) 無限制 → 現狀，OOM 風險高；(B) 全域限制 → 不夠靈活。

**理由**：chunk 級別的記憶體守衛是最後一道防線。分解後每個 chunk 的日期/ID 範圍已大幅縮小，記憶體超限通常代表異常資料，應中止而非繼續。

### Decision 5: 分塊快取 + 部分命中

**選擇**：Redis 鍵 `batch:{prefix}:{hash}:chunk:{idx}`，每個 chunk 獨立 SETEX。

**替代方案**：(A) 只快取最終結果 → 無法部分命中。

**理由**：使用者常見操作是「先查 1-6 月，再查 1-8 月」。分塊快取讓前 6 個月直接複用，只查 7-8 月。

### Decision 6: 引擎路徑統一使用 slow-query 路徑（且不佔用主 pool）

**選擇**：所有經過引擎的查詢統一使用 slow-query 路徑（300s timeout, semaphore 控制）；未經引擎的既有短查詢路徑保持原狀。
慢查詢執行策略採兩層：
1. 主路徑：使用既有獨立 `SLOW POOL`（小容量）做 checkout/checkin。
2. fallback：當 SLOW POOL 不可用時，降級為 slow direct connection。

**替代方案**：
(A) 引擎路徑混用 `read_sql_df`（主 pool, 55s timeout）→ 長查詢高超時風險且會壓縮一般 API 吞吐。
(B) 慢查詢直接共用主 pool → 高峰時造成 pool 爭用與整體延遲放大。

**理由**：經過引擎的查詢本身就是「已知可能很慢」的查詢。慢查詢與主 pool 隔離可避免互相影響；SLOW POOL 讓連線重用與隔離同時成立，fallback direct connection 保障可用性。

### Decision 7: 部分失敗處理

**選擇**：某個 chunk 失敗時記錄錯誤、繼續剩餘 chunk。`merge_chunks()` 回傳成功部分，metadata 標記 `has_partial_failure=True`。

**替代方案**：(A) 全部回滾 → 已成功的 chunk 浪費。

**理由**：歷史報表場景下，部分結果比完全失敗更有價值。metadata 標記讓服務可決定是否警告使用者。

### Decision 8: Chunk Cache 與服務 L1/L2 Dataset Cache 互動

**選擇**：先讀 chunk cache（Redis）組裝結果；組裝後回填既有 service dataset cache（L1 process + L2 Redis）以維持現有 `/view` 路徑與 `query_id` 行為。

**替代方案**：(A) 只使用 chunk cache，不回填 service cache → 現有 view/query_id 流程失效或重複查詢。

**理由**：需要兼容既有 two-phase dataset API（primary query + cached view），chunk cache 是引擎層優化，不應破壞服務層介面。

### Decision 9: query_hash 規格

**選擇**：query_hash 使用 canonical JSON（sorted keys、穩定 list 順序、字串正規化）後 SHA-256 前 16 碼；hash 僅包含會影響原始資料集合的參數（不含純前端呈現參數）。

**替代方案**：(A) 每服務自由實作 hash → 跨服務不可預測且難除錯。

**理由**：chunk key、progress key、merge key 需可重現，否則無法保證 cache 命中與部分重用。

### Decision 10: 時間分解邊界語意

**選擇**：採閉區間 chunk `[chunk_start, chunk_end]`；下一段從 `chunk_end + 1 day` 開始；最後一段可小於 grain_days；輸入日期以服務既有時區/日界線為準，不在引擎層重新解釋時區。

**替代方案**：(A) 半開區間或依月份動態切割但不定義邊界 → 容易重疊或漏資料。

**理由**：邊界語意固定後，merge 去重、統計一致性與測試可驗證性都會提升。

### Decision 11: 大結果採 Parquet 落地，Redis 僅保留 metadata/熱快取

**選擇**：對長查詢（尤其 reject-history）引入 spill-to-disk：
1. chunk 查詢與 chunk cache 保持現行（Redis，短 TTL）
2. merge 後若結果超過門檻（rows / memory / serialized size），寫入 Parquet 至本機 spool 目錄
3. Redis 僅保存 metadata（query_id, file_path, row_count, schema_hash, created_at, expires_at）
4. `/view`/`/export` 優先透過 metadata 讀取 parquet；metadata 不存在時回退現行 cache 行為
5. 背景清理器定期移除過期 parquet 與孤兒 metadata

**替代方案**：
(A) Redis 全量承載所有結果（現況）→ 記憶體壓力高，易引發 lock timeout/OOM 連鎖  
(B) 直接落 DB（例如 SQLite）→ 寫入鎖衝突與維運複雜度高（目前已有 `database is locked` 觀察）

**理由**：Redis 是記憶體快取，不適合長時間承載大結果；Parquet 落地可把大結果轉移到磁碟，降低 worker/Redis 記憶體峰值。

## Risks / Trade-offs

**[Redis 記憶體增長]** → 分塊快取增加 key 數量（365 天 ≈ 12 個 chunk key）。
→ 緩解：TTL 自動過期（900s）；chunk 結果經 parquet 壓縮（通常 10:1 壓縮比）。

**[Semaphore 爭用]** → 並行 chunk 消耗更多 permit。
→ 緩解：感知可用數量，不足時自動降級循序。預設 parallel=1。

**[時間分解後的資料一致性]** → 不同月份 chunk 在不同時間點查詢。
→ 緩解：歷史報表資料更新頻率低（日級），短窗口內變動極低。可接受。

**[遷移風險]** → 先修改 3 個 dataset cache，再擴展至其他服務，整體範圍仍大。
→ 緩解：閾值控制（短查詢不經過引擎）+ P0/P1/P2/P3 分階段導入 + 每階段獨立驗證。

**[磁碟 I/O 與容量壓力]** → Parquet 落地會增加磁碟讀寫，若清理策略失效可能累積大量檔案。
→ 緩解：設定 spool 容量上限、TTL 清理、啟動時 orphan 掃描、超限時回退到「不落地僅回應摘要」保護模式。

**[Stale metadata / orphan file]** → Redis metadata 與實體檔案可能不一致。
→ 緩解：讀取前校驗檔案存在與 schema hash；不一致時自動失效 metadata 並記錄告警。

## Open Questions

1. `mid_section_defect_service` 的 4 階段管線（偵測 → 族譜 → 上游歷史 → 歸因）中，哪些階段適合接入引擎？偵測查詢可日期分解，但族譜/上游已透過 EventFetcher 處理。
2. `query_tool_service` 有 15+ 種查詢類型，是否全部接入還是只處理最易超時的（split_merge_history、equipment_period）？
