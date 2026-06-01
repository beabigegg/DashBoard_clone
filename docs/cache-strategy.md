# 快取策略總覽

> 調查日期：2026-05-29  
> 專案：MES Dashboard (DashBoard_vite)

---

## 一、Redis 全表 / 結果集快取

| 功能模組 | 服務檔案 | Key Pattern | TTL | Pre-warm | 備註 |
|---|---|---|---|---|---|
| WIP 全表 | `core/cache_updater.py` | `mes_wip:data:parquet` | 1800s (3×同步間隔) | ✓ 啟動強制載入 | 全表 DW_MES_LOT_V，每 10 分鐘檢查是否需要更新 |
| Resource 設備清單 | `services/resource_cache.py` | `mes_wip:resource_data` | 24h | ✓ | 全表 DW_MES_RESOURCE，含 package group lookup dict |
| Container Filter | `services/container_filter_cache.py` | `mes_wip:container_filter_cache:data` | 24h | ✓ | 4-tuple (PJ_TYPE, PRODUCTLINENAME, PJ_BOP, PJ_FUNCTION) 交叉過濾 |
| Reason Filter | `services/reason_filter_cache.py` | `mes_wip:reason_filter_cache:data` | 24h | ✓ | DISTINCT LOSSREASONNAME 最近 365 天 |
| Material 料號清單 | `services/material_consumption_service.py` | `mc:parts_list_v2` | 24h | ✓ | DISTINCT MATERIALPARTNAME + DESCRIPTION |
| Equipment 即時狀態 | `services/realtime_equipment_cache.py` | `{prefix}:equipment_data` | 30s | ✓ | 背景執行緒每 5 分鐘更新 |
| Batch Query 塊 | `core/batch_query_engine.py` | `batch:{prefix}:{hash}:chunk:{idx}` | 900s | ✗ | 分時間/ID 段快取 Oracle 查詢結果 |

---

## 二、DuckDB / Parquet Spool 快取

| 功能模組 | 服務檔案 | 存放路徑 | TTL | Pre-warm | 備註 |
|---|---|---|---|---|---|
| Resource History | `services/resource_history_duckdb_cache.py` | `tmp/resource_history.duckdb` | 每日全量重建（sliding 3 個月 window） | ✓ 啟動 | 每天第一次啟動從 Oracle 全量撈近 3 個月並 atomic rename 覆蓋舊檔；同日重啟 reuse；Oracle 補登舊日資料隔天自動修正 |
| Query Spool（通用） | `core/query_spool_store.py` | `tmp/query_spool/{namespace}/{id}.parquet` | 3h (可調) | ✗ | 所有大查詢結果的 Parquet 暫存層，上限 10 GB，每 5 分鐘清理 |
| Reject Dataset | `services/reject_dataset_cache.py` | `tmp/query_spool/reject_dataset/` | L1: 15m / L2: 3h | ✓ RQ warmup | 兩層：進程 LRU → Spool |
| Yield Alert Dataset | `services/yield_alert_dataset_cache.py` | `tmp/query_spool/yield_alert_dataset/` | L1: 30s-5m / L2: 3h | ✓ RQ warmup | 詳情 + linkage 分開存，支援串流寫入 |
| Hold Dataset | `services/hold_dataset_cache.py` | `tmp/query_spool/hold_dataset/` | L1: 15m / L2: 3h | ✓ RQ warmup | DuckDB 視圖層過濾 |
| Resource Dataset | `services/resource_dataset_cache.py` | `tmp/query_spool/resource_dataset/` + `resource_oee/` | L1: 15m（歷史: 24h）/ L2: 3h | ✓ RQ warmup | 歷史查詢 L1 TTL 拉長至 24h |

---

## 三、RQ 非同步 Job Queue

| 隊列名稱 | 環境變數 | 觸發情境 | 超時 | 重試 |
|---|---|---|---|---|
| `trace-events` | `TRACE_WORKER_QUEUE` | Lot 追蹤 / 材料追蹤 | 600s | 2 次 (30s, 60s) |
| `reject-query` | `REJECT_WORKER_QUEUE` | Reject history 大查詢 | 600s | 2 次 |
| `msd-analysis` | `MSD_WORKER_QUEUE` | Mid-section defect 分析 | 600s | 2 次 |
| `production-history-query` | `PRODUCTION_HISTORY_WORKER_QUEUE` | 生產歷史大查詢 | 600s | 2 次 |
| `yield-alert-query` | `YIELD_ALERT_WORKER_QUEUE` | 良率警報計算 | 600s | 2 次 |
| `material-consumption` | `MATERIAL_CONSUMPTION_WORKER_QUEUE` | 材料消耗統計 | 600s | 2 次 |
| `warmup` | `WARMUP_QUEUE_NAME` | 自動預熱（每小時由 spool_warmup_scheduler 排程） | 1800s | 無 |

---

## 四、分段查詢（Batch / Pagination）

| 機制 | 服務檔案 | 切法 | 閾值 | 備註 |
|---|---|---|---|---|
| 時間範圍分塊 | `services/batch_query_engine.py` | 每 N 天一段 | `BATCH_QUERY_TIME_THRESHOLD_DAYS=10` | 每塊最多 192 MB，超出丟出 OOM Guard |
| ID 批量分塊 | `services/batch_query_engine.py` | 每 1000 ID 一批 | `BATCH_QUERY_ID_THRESHOLD=1000` | 用於設備 ID / Lot ID 大清單查詢 |
| SQL 分頁 | 各 service | OFFSET + LIMIT | 20–50 列/頁 | Reject/Yield/Hold history 前端分頁 |

---

## 五、進程級快取（in-process）

| 類型 | 使用位置 | 大小 / TTL | 備註 |
|---|---|---|---|
| `functools.lru_cache` | SQL loader、modernization policy、field contracts | maxsize=1/4/16/100 | 進程生命期 |
| `ProcessLevelCache`（自定義） | reject/yield/hold/resource dataset、realtime equipment | 1–32 項，30s–24h | threading.Lock 保護，OrderedDict + TTL |

---

## 六、整體架構

```
使用者查詢
    │
    ▼
L1: ProcessLevelCache (進程記憶體, 秒~分鐘級)
    │ miss
    ▼
L2: Redis / Spool Parquet (共享, 分鐘~小時級)
    │ miss
    ▼
L3: Oracle DB（直接查詢 or 經 RQ 非同步 or Batch 分段）
```

---

## 七、環境變數參考

### Redis

| 變數 | 預設值 | 說明 |
|---|---|---|
| `REDIS_ENABLED` | `true` | 是否啟用 Redis |
| `REDIS_URL` | `redis://localhost:6379/0` | 資料平面連線 |
| `REDIS_CONTROL_URL` | — | 控制平面（不被驅逐），用於 RQ job meta |
| `REDIS_KEY_PREFIX` | `mes_wip` | 所有 key 的命名空間前綴 |

### Cache Updater

| 變數 | 預設值 | 說明 |
|---|---|---|
| `CACHE_CHECK_INTERVAL` | `600` | 背景執行緒檢查間隔（秒） |
| `WIP_CACHE_TTL_SECONDS` | `0` (= 3×interval) | WIP 快取 TTL |
| `RESOURCE_SYNC_INTERVAL` | `86400` | 設備清單同步間隔（秒） |
| `FILTER_CACHE_SYNC_INTERVAL` | `86400` | Filter 快取同步間隔（秒） |

### DuckDB / Spool

| 變數 | 預設值 | 說明 |
|---|---|---|
| `RESOURCE_HISTORY_DUCKDB_PATH` | `tmp/resource_history.duckdb` | DuckDB 持久化路徑 |
| `RESOURCE_HISTORY_PREWARM_MONTHS` | `3` | 預熱月份數 |
| `QUERY_SPOOL_DIR` | `tmp/query_spool` | Parquet spool 根目錄 |
| `QUERY_SPOOL_TTL_SECONDS` | `10800` | Spool 檔案 TTL（秒） |
| `QUERY_SPOOL_MAX_BYTES` | `10737418240` | Spool 最大容量（10 GB） |
| `QUERY_SPOOL_CLEANUP_INTERVAL_SECONDS` | `300` | 清理背景執行緒間隔 |
| `QUERY_SPOOL_ORPHAN_GRACE_SECONDS` | `600` | 孤立檔案寬限期 |
| `QUERY_SPOOL_ENABLED` | `true` | 是否啟用 Spool |

### Warmup / RQ

| 變數 | 預設值 | 說明 |
|---|---|---|
| `WARMUP_SCHEDULER_ENABLED` | `true` | 是否啟用自動預熱排程 |
| `WARMUP_QUEUE_NAME` | `warmup` | RQ 預熱隊列名稱 |
| `WARMUP_INTERVAL_SECONDS` | `3600` | 預熱間隔（秒） |
| `WARMUP_JOB_TIMEOUT` | `1800` | 預熱 Job 超時（秒） |

### Batch Query

| 變數 | 預設值 | 說明 |
|---|---|---|
| `BATCH_CHUNK_MAX_MEMORY_MB` | `192` | 每塊記憶體上限 |
| `BATCH_QUERY_TIME_THRESHOLD_DAYS` | `10` | 時間分塊天數 |
| `BATCH_QUERY_ID_THRESHOLD` | `1000` | ID 批量分塊大小 |

---

## 八、關鍵設計決策

1. **Spool 用 Parquet 而非 Redis JSON** — 節省 2–5 倍記憶體，支援 DuckDB 直接 `read_parquet` 查詢，大結果集不序列化進 Redis
2. **分布式鎖防多 Worker 衝突** — file-based `O_CREAT|O_EXCL` sentinel 鎖，防止多 gunicorn worker 同時打 Oracle 做全表載入
3. **Warmup 領導者選舉** — Redis 鎖 `spool_warmup_leader` (120s TTL)，只讓一個 worker 排程 RQ warmup，其他 worker 等待
4. **Redis 資料/控制平面分離** — `REDIS_URL` (資料，可驅逐) vs `REDIS_CONTROL_URL` (控制，不驅逐)，RQ job meta 不被 eviction 清除
5. **OOM Guard** — Batch Query Engine 每塊限制 192 MB，超出時拋出例外而非 OOM crash
