# 防 OOM 與快取機制跨工具套用分析

> 基於報廢歷史 (reject-history) 已建立的防護體系，評估物料追溯、查詢工具、中段缺陷三個工具的現況缺口與改善建議。

## 標竿：報廢歷史已具備的機制

### 防 OOM（6 層縱深防禦）

| 層級 | 機制 | 檔案 | 作用 |
|------|------|------|------|
| A | Worker RSS 記憶體守衛 | `core/worker_memory_guard.py` | daemon 每 15s 檢查 RSS；70% 告警 → 85% 清快取+GC → 95% SIGTERM 重啟 |
| B | 互動式記憶體守衛 | `services/reject_dataset_cache.py` | 每次快取派生前：DataFrame > 96MB 拒絕；投影 RSS > 1100MB 拒絕 |
| C | 強制 GC | `services/reject_dataset_cache.py` | 每次互動計算後 `gc.collect()` |
| D | Chunk 記憶體限制 | `services/batch_query_engine.py` | 每個 Oracle 查詢分塊 > 192MB 丟棄 |
| E | 大結果溢出至 Parquet | `core/query_spool_store.py` | > 20 萬行或 48MB 寫磁碟，Redis 僅存指標；2GB 總量上限 |
| F | Gunicorn Worker 回收 | `gunicorn.conf.py` | 每 1200±300 request 自動回收 worker |

### 快取（4 層 + 2 加速器）

| 層級 | 機制 | 作用 |
|------|------|------|
| L1 | ProcessLevelCache（進程內 LRU+TTL） | dataset TTL=15min/8 entries |
| L2 | Redis（跨 worker） | DataFrame 存為 parquet bytes |
| L3 | Parquet Spool Store（磁碟溢出） | 大型結果寫磁碟，背景每 5 分鐘清理 |
| 加速器 1 | DuckDB SQL Runtime | 對 Parquet 跑 SQL 算 batch-pareto/view/export |
| 加速器 2 | Materialized Pareto 聚合 | 預計算 6 維指標 cube |
| 批次引擎 | Batch Query Engine | 長日期範圍分月拆解 + Redis 分塊快取 |

---

## 現況對照矩陣

| 防護機制 | 報廢歷史 | 物料追溯 | 查詢工具 | 中段缺陷 |
|----------|:---:|:---:|:---:|:---:|
| 互動式記憶體守衛 (RSS 投影) | ✅ | ⚠️ 僅 DataFrame 大小 | ❌ | ❌ |
| Parquet 磁碟溢出 | ✅ | ❌ | ❌ | ❌ |
| DuckDB SQL Runtime | ✅ | ❌ | ❌ | ❌ |
| 物化聚合快照 | ✅ | ❌ | ❌ | ❌ |
| 批次引擎 (時間分片) | ✅ | ❌ | ❌ | ✅ 偵測查詢 |
| fetchmany 迭代器 | ❌ | ❌ | ✅ EventFetcher | ✅ EventFetcher |
| 非同步 Job Queue (RQ) | ❌ | ❌ | ❌ | ✅ >20K CIDs |
| NDJSON 串流 | ❌ | ❌ | ❌ | ✅ |
| 分散式鎖防 stampede | ❌ | ❌ | ❌ | ✅ |
| 強制 GC | ✅ | ❌ | ❌ | ⚠️ 僅 >10K CIDs |
| Redis 快取 | ✅ 三層 | ❌ 完全無 | ✅ resolve+events | ✅ 多層 |
| SQL 行數上限 | ✅ | ⚠️ 僅反向 | ❌ | ❌ |
| 分頁/匯出重查 Oracle | ❌ cache-based | ✅ 每次重查 | 部分 | ❌ cache-based |

---

## 工具一：物料追溯 (Material Trace)

### 架構概述

- 路由：`routes/material_trace_routes.py`（3 端點：query / export / filter-options）
- 服務：`services/material_trace_service.py`（正向/反向查詢、CSV 匯出）
- 主表：`DWH.DW_MES_LOTMATERIALSHISTORY`（18M 行）
- 查詢模式：同步、無快取、每次分頁/匯出都完整重查 Oracle

### 已有防護

- DataFrame 記憶體守衛 `_check_memory_guard()` — 256MB 上限（僅 DataFrame 大小，不投影 RSS）
- IN 子句批次拆分 `_IN_BATCH_SIZE=1000`
- 輸入數量限制：正向 200 筆、反向 50 筆
- 反向查詢 SQL 行數上限 `FETCH FIRST 10001 ROWS ONLY`
- 匯出行數上限 50,000
- Wildcard 前綴安全 `CONTAINER_RESOLVE_PATTERN_MIN_PREFIX_LEN=2`
- 限流：query 30/min、export 10/min

### 痛點

| 風險 | 嚴重度 | 說明 |
|------|:------:|------|
| 分頁重查 Oracle | 🔴 高 | 每翻一頁都重新跑完整 Oracle 查詢 + DataFrame 全量建構再切片 |
| Export 重查 Oracle | 🔴 高 | 獨立重查一次，5 萬行上限但整個 DataFrame 一次載入 |
| 正向查詢無行數上限 | 🟡 中 | 反向有 FETCH FIRST 但正向無 SQL 級行數限制 |
| 記憶體守衛不投影 RSS | 🟡 中 | 不考慮當前進程 RSS 狀態 |
| 無 GC | 🟢 低 | 靠 Worker RSS 守衛兜底 |

### 建議

| 優先序 | 措施 | 改動量 | 效益 |
|:---:|------|:---:|------|
| P0 | 加入查詢結果快取 — 首次結果存 Redis (key=mode+values hash, TTL=5min)，分頁/匯出讀快取 | ~80 行 | 消除 N+1 次 Oracle 查詢 |
| P1 | 升級記憶體守衛 — 加上 RSS 投影檢查 | ~30 行 | 高壓下拒絕大查詢 |
| P1 | 正向查詢加 SQL 行數上限 `FETCH FIRST 50001 ROWS ONLY` + truncation 標記 | ~25 行 | 防意外全表掃描 |
| P2 | Export 串流化 — 改為 generator yield rows | ~40 行 | 降低 export 瞬時記憶體 |
| P2 | 加強制 GC | ~5 行 | 及時釋放臨時 DataFrame |

---

## 工具二：查詢工具 (Query Tool)

### 架構概述

- 路由：`routes/query_tool_routes.py`（10 端點）
- 服務：`services/query_tool_service.py`（1868 行）+ `services/event_fetcher.py`
- 三大功能：批次追蹤（正向）、流水批反查（反向）、設備生產批次追蹤
- 主表：`DW_MES_LOTWIPHISTORY`（53M）、`DW_MES_LOTMATERIALSHISTORY`、`DW_MES_HM_LOTMOVEOUT`（48M, 無索引）
- 已有 EventFetcher fetchmany 迭代器 + Redis 快取（resolve 60s / events 180-300s）

### 已有防護

- Slow-query semaphore `DB_SLOW_MAX_CONCURRENT=5`
- fetchmany 迭代器避免 cursor.fetchall() 三重 materialize
- 輸入限制：LOT 100 / Serial 100 / WO 50 / Equipment 20 / 日期 365 天
- Container IDs 批次上限 `QUERY_TOOL_MAX_CONTAINER_IDS=200`
- Wildcard 展開限制：每 token 2000 / 總計 30,000
- EventFetcher 大量 CIDs 跳過快取寫入 (>10K)
- 限流：resolve 10/min、equipment 5/min、export 3/min

### 痛點

| 風險 | 嚴重度 | 說明 |
|------|:------:|------|
| 明細全量回傳 | 🔴 高 | lot-history / associations / equipment-lots 全部一次回傳，無 server-side 分頁 |
| 48M 行無索引表 | 🔴 高 | `DW_MES_HM_LOTMOVEOUT` split_merge_history 走全表掃描，30-120s |
| CSV export 全量 materialize | 🟡 中 | 先完整查詢建 DataFrame 再轉 CSV stream |
| 無互動式記憶體守衛 | 🟡 中 | EventFetcher 逐批但無整體 RSS 投影 |
| 無 Parquet 溢出 | 🟡 中 | 大結果只能在 Redis (512MB) 或記憶體中 |

### 建議

| 優先序 | 措施 | 改動量 | 效益 |
|:---:|------|:---:|------|
| P0 | detail 端點加 server-side 分頁 — SQL 加 OFFSET/FETCH | ~60 行/端點 | 防大 LOT 數千筆 history 一次灌入 |
| P0 | EventFetcher 加 total-result 記憶體守衛 — 累積結果超限截斷+標記 | ~25 行 | 防累積結果超安全線 |
| P1 | 拓展 Parquet 溢出到 EventFetcher — 大結果寫 spool + DuckDB 讀取 | ~120 行 | equipment 365 天查詢安全運作 |
| P1 | 加 RSS 投影守衛 — 重型端點前檢查 projected RSS | ~30 行 | 跨端點整體防護 |
| P2 | split_merge_history 預設 fast 模式 — full 需手動啟用 | ~10 行 | 降低 48M 表衝擊 |
| P2 | 加強制 GC — heavy 端點 response 後 gc.collect() | ~10 行 | 配合 Worker RSS 守衛 |

---

## 工具三：中段缺陷 (Mid-Section Defect)

### 架構概述

- 路由：`routes/mid_section_defect_routes.py`（5 端點）+ `routes/trace_routes.py`（三階段管線）
- 服務：`services/mid_section_defect_service.py`（1350 行）
- 三階段漸進式管線：seed-resolve → lineage → events（含歸因統計）
- 主表：`DW_MES_LOTWIPHISTORY`（53M）、`DW_MES_LOTREJECTHISTORY`、`DW_MES_CONTAINER`（5.2M）
- 已有：RQ async job queue、NDJSON 串流、fetchmany 迭代器、Redis 分散式鎖、BatchQueryEngine

### 已有防護

- Worker RSS 記憶體守衛（全域）
- fetchmany 迭代器避免三重 materialize（2026-02-25 OOM 事件後加入）
- 非同步 RQ Job Queue — >20K CIDs 導向獨立 worker process
- NDJSON 串流 — 大結果漸進式傳送
- 分散式鎖防 cache stampede（120s lock, 90s wait）
- BatchQueryEngine — 偵測查詢 >10 天分月拆解
- EventFetcher 大量 CIDs 跳過快取
- 顯式 gc.collect() — >10K CIDs 後觸發
- systemd MemoryMax=6G 硬保護
- 限流：analysis 6/min、detail 15/min、export 3/min

### 痛點

| 風險 | 嚴重度 | 說明 |
|------|:------:|------|
| 無 CID 硬拒絕 | 🔴 高 | 設計上刻意不拒（資料完整性需求），114K CIDs 是真實場景，sync 路徑峰值 4-6GB |
| RQ 不可用時 fallback 到 sync | 🔴 高 | RQ worker 掛掉時 >20K CIDs 仍由 gunicorn worker 同步處理 |
| Aggregation 全量在記憶體 | 🟡 中 | `build_trace_aggregation_from_events()` 需完整 events dict 做歸因 |
| Cache stampede fail-open 90s | 🟡 中 | 管線 > 90s 時第二個 request 也開始跑，雙重 Oracle 負載 |
| Export 全量 materialize | 🟡 中 | 從快取讀全部 detail list 再 stream |
| SQL/Python workcenter 分類漂移 | 🟢 低 | CASE WHEN 與 Python dict 需手動同步 |

### 建議

| 優先序 | 措施 | 改動量 | 效益 |
|:---:|------|:---:|------|
| P0 | RQ 健康監控 + 降級提示 — 定期驗證 RQ worker 存活，不可用時前端顯示警告 | ~50 行 | 防靜默 fallback 到 sync 撐爆 worker |
| P0 | Sync 路徑加 RSS 投影守衛 — 超限返回 503 + retry-after | ~35 行 | 保護 gunicorn worker |
| P1 | Parquet 溢出 for events — 大結果寫 spool，aggregation 改用 DuckDB GROUP BY | ~200 行 | 114K CIDs 場景記憶體從 ~4GB 降到 ~500MB |
| P1 | 延長 stampede lock timeout — 從 90s 提高到 180s 或改 pub/sub 通知 | ~20 行 | 減少雙重查詢 |
| P2 | Workcenter 分類統一源 — 從 Python dict 自動生成 SQL CASE WHEN | ~60 行 | 消除隱性資料遺漏 |
| P2 | Export 改 DuckDB 串流 — spool 存在時用 fetchmany generator | ~40 行 | 降低 export 峰值記憶體 |

---

## 跨工具共用方案

### 從報廢歷史推廣的通用元件

| 元件 | 推廣對象 | 理由 |
|------|---------|------|
| `_enforce_interactive_memory_guard()` | 全部三個 | 零改架構，插入式防護，~30 行 |
| Parquet spool + DuckDB SQL | 查詢工具、中段缺陷 | EventFetcher 大結果目前僅 in-memory |
| 查詢結果 Redis 快取 | 物料追溯 | 唯一完全零快取的工具 |

### 從中段缺陷推廣的元件

| 元件 | 推廣對象 | 理由 |
|------|---------|------|
| RQ async job queue | 查詢工具 (equipment 長查詢) | 365 天設備查詢可能跑 2-3 分鐘 |
| 分散式鎖防 stampede | 物料追溯（若加快取） | 避免快取冷啟動時多 request 同時打 Oracle |
| sessionStorage 前端快取 | 物料追溯、查詢工具 | 頁面切換回頭不需重查 |

---

## 建議執行順序

```
Phase 1（快速加固, 1-2 天）:
  ├─ 全部三個: 加 _enforce_interactive_memory_guard + 強制 GC
  ├─ 物料追溯: 加 Redis 查詢結果快取（消除分頁/匯出重查）
  └─ 物料追溯: 正向查詢加 SQL 行數上限

Phase 2（結構性改善, 3-5 天）:
  ├─ 查詢工具: detail 端點加 server-side 分頁
  ├─ 中段缺陷: RQ 健康監控 + sync 路徑 RSS 守衛
  └─ 中段缺陷: stampede lock timeout 延長

Phase 3（進階優化, 5-7 天）:
  ├─ 共用: EventFetcher 拓展 Parquet spool 支援
  ├─ 中段缺陷: aggregation 改用 DuckDB SQL
  └─ 查詢工具: 大結果走 spool + DuckDB
```

---

## 相關檔案索引

| 類別 | 關鍵檔案路徑 |
|------|-------------|
| 標竿：報廢歷史快取 | `services/reject_dataset_cache.py` |
| 標竿：DuckDB runtime | `services/reject_cache_sql_runtime.py` |
| 標竿：Parquet spool | `core/query_spool_store.py` |
| 標竿：記憶體守衛 | `core/worker_memory_guard.py` |
| 標竿：批次引擎 | `services/batch_query_engine.py` |
| 物料追溯 service | `services/material_trace_service.py` |
| 物料追溯 routes | `routes/material_trace_routes.py` |
| 查詢工具 service | `services/query_tool_service.py` |
| 查詢工具 routes | `routes/query_tool_routes.py` |
| 查詢工具 EventFetcher | `services/event_fetcher.py` |
| 中段缺陷 service | `services/mid_section_defect_service.py` |
| 中段缺陷 routes | `routes/mid_section_defect_routes.py` |
| 中段缺陷 trace 管線 | `routes/trace_routes.py` |
| 中段缺陷 async job | `services/trace_job_service.py` |
| 中段缺陷 lineage 引擎 | `services/lineage_engine.py` |
| 共用快取層 | `core/cache.py` |
| 共用 database | `core/database.py` |
