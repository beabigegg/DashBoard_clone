## Why

目前各歷史報表服務（reject-history、hold-history、resource-history）、查詢工具（query-tool）、中段不良分析（mid-section-defect）和 Job 查詢（job-query）各自實作不同的批次查詢、快取和並行執行模式，缺乏統一編排與保護。主要問題：

1. **Oracle 超時**：長日期範圍（365+ 天）或大量 Container ID（工單展開後可達數千筆）的查詢可能超過 300 秒 call_timeout
2. **OOM 風險**：reject/hold dataset cache 以 `limit: 999999999` 取回全部資料，無記憶體上限守衛
3. **保護分散**：`EventFetcher` 已有 ID 分批 + 快取，但 reject/hold/resource dataset cache 仍各自維護查詢與快取策略
4. **重複程式碼**：3 個 dataset cache 各自複製相同的 parquet-in-Redis 序列化邏輯
5. **ID 展開膨脹**：工單 resolve 後 container ID 可能大量擴張，缺乏跨服務一致的分批/合併流程
6. **重查成本高**：延長查詢範圍（例如 1-6 月改 1-8 月）無法有效重用已查區段結果
7. **query-tool 超時風險高**：多數查詢仍走 `read_sql_df`（主 pool / 55s timeout），大查詢下容易超時

需要一個**可穩定複用的查詢引擎模組**，任何服務接入後自動獲得分解、快取、記憶體保護和超時保護。

## What Changes

- 新增 `BatchQueryEngine` 共用模組，提供：
  - **時間範圍分解**：長日期 → ~31 天月份區間，每段獨立查詢
  - **時間分解語意**：明確定義 chunk 邊界（閉區間）、跨月切割與最後一段不足月行為
  - **ID 批次分解**：大量 ID（工單/Lot/GD Lot/流水批展開後）→ 1000 筆一批
  - **query_hash 規格**：統一 canonicalization 與雜湊欄位，確保 chunk/cache key 穩定
  - **記憶體守衛**：每個 chunk 結果檢查 `DataFrame.memory_usage()`，超過閾值時中止並警告
  - **結果筆數限制**：可配置的最大結果筆數，超過時截斷並標記
  - **受控並行執行**：預設循序、可選並行，嚴格遵守 slow query semaphore
  - **Redis 分塊快取**：每個 chunk 獨立快取，支援部分命中（延長查詢範圍時複用已查過的區間）
  - **快取層互動**：明確定義 chunk cache 與服務既有 L1/L2 dataset cache 的讀寫順序
  - **進度追蹤**：Redis HSET 記錄進度，可供前端顯示
- 新增「**大結果落地層（Parquet spill）**」設計：
  - 當長查詢結果超過記憶體/列數門檻時，將合併後結果以 Parquet 寫入本機持久目錄（例如 `tmp/query_spool/`）
  - Redis 僅保存 metadata（query_id → parquet path / schema / rows / created_at / ttl）
  - `/view` 與 `/export` 讀取流程優先走 Redis metadata + Parquet，避免整包 DataFrame 常駐 worker RAM
  - 定時清理（TTL + 背景清理器）刪除過期 parquet，避免磁碟持續膨脹
- 新增 `redis_df_store` 共用模組，將 parquet-in-Redis 存取邏輯從 3 個 dataset cache 提取為共用工具
- 所有**引擎接管的 chunk 查詢**統一使用 slow 路徑（300 秒級 timeout）
  - 使用既有「**獨立 SLOW POOL（小容量）**」做慢查詢連線重用
  - 明確**不使用主查詢 pool** 承載慢查詢，避免拖垮一般 API
  - 當 SLOW POOL 不可用時，降級為 slow direct connection（不影響主 pool）

## Capabilities

### New Capabilities
- `batch-query-engine`: 統一批次查詢引擎模組，涵蓋分解策略（時間/ID）、記憶體守衛、結果限制、受控執行、Redis 分塊快取、進度追蹤、結果合併

### Modified Capabilities
- `reject-history-api`: 主查詢改為透過引擎執行；date_range 模式自動時間分解，container 模式（工單/Lot/GD Lot 展開後）自動 ID 分批
- `hold-dataset-cache`: 主查詢改為透過引擎執行，長日期自動分解
- `resource-dataset-cache`: 主查詢改為透過引擎執行，長日期自動分解
- `event-fetcher-unified`: 保持既有最佳化（batch + streaming + cache），僅在需要統一監控/進度模型時再評估導入

## Impact

- **後端**：新增 2 個共用模組（`batch_query_engine.py`、`redis_df_store.py`），優先修改 3 個 dataset cache 主查詢路徑（reject/hold/resource）
- **受影響服務**（優先順序）：
  - P0：reject-history（最容易超時/OOM — 長日期 + 工單展開 + 目前 `limit=999999999`）
  - P1：hold-history、resource-history（相同架構，直接套用）
  - P2：mid-section-defect（4 階段管線，偵測查詢 + 上游歷史）、job-query（缺快取 + 日期分解）
  - P3：query-tool（優先處理 `read_sql_df` 高風險路徑並導入慢查詢保護）、event-fetcher（保持可選）
- **資料庫**：不改 SQL，僅縮小每次查詢的 bind parameter 範圍
- **資料庫連線策略**：慢查詢與一般 pooled query 隔離，避免資源互相干擾
- **Redis**：新增 `batch:*` 前綴的分塊快取鍵
- **儲存層**：新增 Parquet 結果落地目錄與清理機制（Redis 轉為索引/metadata，不再承載全部大結果）
- **記憶體**：引擎強制單 chunk 記憶體上限（預設 256MB），超過時中止
- **可用性**：Redis 設定 `maxmemory` + eviction 後仍可透過 Parquet metadata 回復查詢結果（cache 不命中不等於資料遺失）
- **向下相容**：短查詢（< 60 天、< 1000 ID）走現有路徑，零額外開銷；既有 route/event 快取策略保持不變
- **前端**：可選性變更，長查詢可顯示進度條（非必要）

## Parquet 落地的預期效果與副作用

**預期效果：**
- 大幅降低 worker 在「merge + cache 回填」階段的峰值記憶體（避免單 worker 突增到 GB 級）
- Redis 記憶體由「存整包資料」轉為「存索引/熱資料」，降低 OOM 與 lock timeout 連鎖風險
- 服務重啟後，若 parquet 尚未過期，仍可恢復查詢結果（搭配 metadata）

**可能副作用（Side Effects）：**
- 磁碟 I/O 增加：查詢高峰時會有 parquet 寫入/讀取尖峰
- 磁碟容量風險：清理策略失效時，spool 目錄可能持續膨脹
- 資料一致性風險：metadata 指向檔案若被外部刪除/損壞，會出現 stale pointer
- 安全與治理：落地檔案需納入權限控管、備份/清理與稽核策略

**緩解方向：**
- 強制 TTL + 定期掃描清理（以 metadata 與檔案 mtime 雙重判斷）
- 啟動時做 orphan/stale 檢查與自動修復（刪 metadata 或刪孤兒檔）
- 先以 reject-history 長查詢為 P0，逐步擴展到其他服務
