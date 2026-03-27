## Context

MES Dashboard 使用雙連線池架構（main pool + slow pool）存取 Oracle，並以多個獨立 cache service 管理 filter 選項。目前存在幾個結構性問題：

1. **Slow pool 容量矛盾** — Semaphore 允許 5 個併發，但 pool 只有 2+1=3 條連線，導致第 4、5 個請求卡在 pool_timeout（30s）等待
2. **Slow path 缺乏保護** — `read_sql_df_slow` 沒有 circuit breaker（`read_sql_df` 有），也沒有 keep-alive
3. **Filter 查詢浪費 slow pool** — reject filter_options 每次完整執行 base CTE（5.85s），mid_section loss_reasons 佔用 slow 連線，這些資料幾乎不變
4. **殘留 direct connection** — `resource_routes.py` 和 `database.py` 的 table utilities 仍使用 `get_db_connection()` 繞過連線池

現有 cache 層：
- `filter_cache.py` — workcenter groups 等，TTL 1hr（`CACHE_TTL_FILTER_GENERAL = 3600`）
- `resource_cache.py` — families/departments/locations，TTL 4hr
- `production_history_service.py` — pj_types，TTL 24hr（已獨立實作）
- `cache_updater.py` — WIP snapshot + resource cache 定期同步

## Goals / Non-Goals

**Goals:**
- Slow pool size 與 semaphore 完全匹配，消除等待瓶頸
- `read_sql_df_slow` 獲得與 `read_sql_df` 同等的 circuit breaker 和 keep-alive 保護
- 所有 filter 選項改用 24hr 快取，不再即時查 Oracle
- 消除所有 `get_db_connection()` 直連呼叫（改走連線池）
- 統一 cache 更新流程，透過 `cache_updater` 集中管理

**Non-Goals:**
- 不重構 main pool 設定（目前運作正常）
- 不改變前端 filter UI 行為（後端保持向後相容）
- 不引入新的 cache infrastructure（繼續使用現有 L1 memory + L2 Redis）
- 不修改 WIP cache 的更新邏輯

## Decisions

### D1: Slow pool size 對齊 semaphore

**選擇**：Production 環境 pool_size=5, max_overflow=3, semaphore=8（完全匹配）

**替代方案**：
- 降低 semaphore 至 3 — 拒絕：會限制合法的慢查詢併發
- 使用動態 pool sizing — 拒絕：增加複雜度，靜態匹配已足夠

**理由**：pool_size + max_overflow 應等於 semaphore 值，確保拿到 semaphore 的請求一定能取得連線。

### D2: Slow path 共用 main circuit breaker

**選擇**：`read_sql_df_slow` 直接呼叫 `get_database_circuit_breaker()` 檢查和記錄

**替代方案**：
- 獨立的 slow circuit breaker — 拒絕：Oracle 故障通常是整體性的，兩個 breaker 狀態會不一致
- 不加 circuit breaker — 拒絕：Oracle 故障時 slow path 會持續嘗試直到 timeout

**理由**：main 和 slow 連向同一個 Oracle instance，circuit 狀態應該共享。

### D3: 新增兩個 filter cache module

**選擇**：
- `container_filter_cache.py` — packages (PRODUCTLINENAME) + pj_types (PJ_TYPE)，合併為一條 SQL
- `reason_filter_cache.py` — reject reasons (LOSSREASONNAME)，限最近 365 天

**替代方案**：
- 全部塞進現有 `filter_cache.py` — 拒絕：`filter_cache.py` 專注 workcenter 相關資料，職責不同
- 每個 filter 獨立模組 — 拒絕：packages 和 pj_types 來自同一張表，合併查詢更高效

**理由**：按資料來源表分組，同表欄位合併查詢減少 Oracle round-trip。

### D4: 統一所有 filter TTL 為 24hr

**選擇**：`CACHE_TTL_FILTER_GENERAL` 從 3600 → 86400

**替代方案**：
- 每個 cache 獨立 TTL — 拒絕：filter 選項變更頻率相似，統一管理更簡單
- 保留 1hr TTL — 拒絕：filter 選項幾乎不變，1hr 太頻繁

**理由**：filter 選項（workcenter groups、packages、reasons）都是維度資料，一天更新一次足夠。提供 `/admin/cache/refresh` 手動刷新作為安全網。

### D5: resource statuses 改用常數

**選擇**：`query_resource_filter_options` 中的 statuses 改用 `STATUS_CATEGORIES` 常數，刪除 `distinct_statuses.sql`

**替代方案**：
- 繼續查 Oracle — 拒絕：status 值是固定的分類，不需要動態查詢

**理由**：`STATUS_CATEGORIES` 已在 `constants.py` 定義，直接使用即可。

### D6: Direct connection 改走 engine.connect()

**選擇**：`database.py` 的 `get_table_columns/data/metadata` 改用 `engine.connect()`，`resource_routes.py` 的 `api_resource_status_values` 移至 service 層

**替代方案**：
- 保留 direct connection — 拒絕：繞過連線池，無法追蹤連線數量

**理由**：所有 DB 存取都應走連線池，便於監控和管理。

### D7: Keep-alive 擴展至 slow pool

**選擇**：在現有 `_keepalive_worker` 中增加對 slow engine 的 ping

**替代方案**：
- 獨立的 slow keep-alive thread — 拒絕：增加管理複雜度，一個 thread ping 兩個 pool 即可

**理由**：複用現有機制，避免 idle 連線被 firewall 切斷。

## Risks / Trade-offs

- **[風險] Slow pool 增大 → Oracle session 增加** — PRD 環境從 12 → 32 slow sessions。總計 72 sessions（確定數量），相比之前 52 + 不確定 direct sessions，實際更可控。→ 部署後監控 Oracle session 數
- **[風險] 24hr TTL → 新增的 reason/package 最多延遲一天出現** → 提供 admin 手動刷新 API 作為緩解
- **[風險] reject filter_options API 簽章改變（移除 date 參數）** → 後端忽略前端傳入的 date params，保持向後相容
- **[風險] circuit breaker 共享 → slow query 失敗會影響 main path** → 這是預期行為：Oracle 故障時兩條路徑都應快速失敗
- **[取捨] 增加兩個新的 cache module** → 增加程式碼量，但每個模組職責清晰，比塞進現有模組更好維護
