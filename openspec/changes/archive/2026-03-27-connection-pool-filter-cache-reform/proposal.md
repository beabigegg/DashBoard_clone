# Change Proposal: Connection Pool Reform + Filter Cache Unification

## Summary

重整 Oracle 連線架構：修正 slow pool 與 semaphore 的容量矛盾、消除殘留 direct connection、統一 filter 快取為 24hr 全域快取，消除多個 5s+ 的 filter 查詢。

## Motivation

### 問題 1: Slow Pool 容量矛盾
- Semaphore 允許 5 個同時執行，但 slow pool 只有 2+1=3 條連線
- 第 4、5 個拿到 semaphore 的請求會卡在 pool_timeout (30s) 等連線歸還
- 生產環境 4 workers × 3 連線 = 12 條 slow 連線（不足）vs 4 × 30 = 120 條 main 連線（閒置）

### 問題 2: Slow Path 缺少保護
- `read_sql_df_slow` 沒有 circuit breaker — Oracle 故障時不會快速失敗
- Slow pool 沒有 keep-alive — 閒置連線可能被 firewall 切斷

### 問題 3: Filter 查詢佔用 Slow Pool
- `reject filter_options` 每次跑完整 base CTE 只為取 DISTINCT 值 → 5.85s
- `mid_section all_loss_reasons` 走 slow path 佔用寶貴的 slow 連線
- 這些 filter 選項幾乎不變，不需要即時查詢

### 問題 4: 殘留 Direct Connection
- `resource_routes.py:279` — route 層直接建連線，違反 thin route 原則
- `database.py` table utilities (3 處) — 繞過連線池

## Changes

### Part A: Slow Pool 調整

**修改 `config/settings.py`:**
- Production: `DB_SLOW_POOL_SIZE` 從 2 → 5
- Production: `DB_SLOW_POOL_MAX_OVERFLOW` 從 1 → 3
- Semaphore 8 = Pool 5+3（完全匹配）
- Development: 等比例調整

**修改 `core/database.py`:**
- `read_sql_df_slow` 加入 circuit breaker 檢查（共用 main breaker 或獨立）
- Slow pool 加入 keep-alive ping（複用 `_keepalive_worker` 邏輯）

### Part B: Filter 快取統一

**新增 `services/container_filter_cache.py`:**

| 快取欄位 | SQL | 來源表 |
|:--|:--|:--|
| packages (PRODUCTLINENAME) | `SELECT DISTINCT TRIM(PRODUCTLINENAME) FROM DW_MES_CONTAINER WHERE PRODUCTLINENAME IS NOT NULL` | DW_MES_CONTAINER |
| pj_types (PJ_TYPE) | `SELECT DISTINCT TRIM(PJ_TYPE) FROM DW_MES_CONTAINER WHERE PJ_TYPE IS NOT NULL` | DW_MES_CONTAINER |

- 兩個 DISTINCT 合併為一條 SQL (同一張表)
- L1 memory + L2 Redis，TTL 24hr
- 啟動時載入（走 main pool）
- cache_updater 每 24hr 更新

**新增 `services/reason_filter_cache.py`:**

| 快取欄位 | SQL | 來源表 |
|:--|:--|:--|
| reject_reasons (LOSSREASONNAME) | `SELECT DISTINCT TRIM(LOSSREASONNAME) FROM DW_MES_LOTREJECTHISTORY WHERE TXNDATE >= SYSDATE - 365 AND LOSSREASONNAME IS NOT NULL` | DW_MES_LOTREJECTHISTORY |

- L1 memory + L2 Redis，TTL 24hr
- 同時供 reject_history 和 mid_section_defect 使用
- 啟動時載入（走 main pool）

**修改 `services/reject_history_service.py`:**
- `get_filter_options()` 改為從快取讀取：
  - `workcenter_groups` ← filter_cache（已有）
  - `packages` ← container_filter_cache（新增）
  - `reasons` ← reason_filter_cache（新增）
- 移除 start_date/end_date 參數依賴（不再需要日期範圍來決定 filter 選項）
- 回應時間從 5.85s → < 10ms

**修改 `services/mid_section_defect_service.py`:**
- `query_all_loss_reasons()` 改為從 reason_filter_cache 讀取
- 移除對 `read_sql_df`（aliased from slow）的呼叫
- 不再佔用 slow pool 連線

**修改 `services/resource_service.py`:**
- `query_resource_filter_options()` 中的 statuses 改用 `STATUS_CATEGORIES` 常數
- 移除 Oracle 查詢 `resource/distinct_statuses`
- 可刪除 `sql/resource/distinct_statuses.sql`

**修改 `services/production_history_service.py`:**
- `get_type_options()` 改為從 container_filter_cache 讀取 pj_types
- 移除獨立的 Oracle 查詢

**統一現有快取 TTL:**
- `filter_cache` (workcenter_groups 等): 從 1hr → 24hr
- `resource_cache` (families/departments/locations): 從 4hr → 24hr

### Part C: 消除殘留 Direct Connection

**修改 `routes/resource_routes.py`:**
- `api_resource_status_values()` 移到 resource_service 層
- 改用 `read_sql_df()` (main pool)

**修改 `core/database.py`:**
- `get_table_columns()` 改用 `engine.connect()` (main pool)
- `get_table_data()` 改用 `engine.connect()` (main pool)
- `get_table_column_metadata()` 改用 `engine.connect()` (main pool)

### Part D: cache_updater 整合

**修改 `core/cache_updater.py`:**
- 新增 filter registry 更新任務
- 啟動時統一載入所有 filter 快取
- 每 24hr 統一刷新
- Redis 分散式鎖避免多 worker 同時更新

```
啟動序列:
  1. filter_cache.init()           ← 已有
  2. resource_cache.init()         ← 已有
  3. container_filter_cache.init() ← 新增
  4. reason_filter_cache.init()    ← 新增
  5. scrap_exclusion_cache.init()  ← 已有

每日更新:
  cache_updater → refresh_all_filter_caches()
  → Redis lock per cache key
  → 走 main pool (read_sql_df)
  → 失敗時保留舊快取 (fail-open)
```

## Impact Analysis

### 效能改善

| 指標 | 改前 | 改後 |
|:--|:--|:--|
| reject filter_options 回應 | 5.85s | < 10ms |
| mid_section loss_reasons 首次 | ~2s (佔 slow pool) | < 10ms |
| resource filter statuses | ~0.5s (查 Oracle) | 0ms (常數) |
| production_history pj_types | ~1s (查 Oracle) | < 10ms |
| slow pool 可用連線 | 3 (矛盾 semaphore=5) | 8 (匹配 semaphore=8) |
| direct connection 數量 | 5 處 | 0 處 |

### Oracle Session 影響 (PRD, 4 workers)

| 指標 | 改前 | 改後 |
|:--|:--|:--|
| Main pool sessions | 4 × 10 = 40 | 4 × 10 = 40 (不變) |
| Slow pool sessions | 4 × 3 = 12 | 4 × 8 = 32 |
| Direct sessions | 無上限 | 0 |
| 總計 | ~52 + 不確定 | 72 (確定) |

## Risk

- **中風險** — 涉及多個 service 的 import 和 filter 邏輯變更
- reject_history `get_filter_options` 的 API 簽章改變（移除 date 參數）
  - 需確認前端是否仍傳 date params（後端忽略即可，保持向後相容）
- filter 快取 24hr 更新可能遺漏新增的 reason/package
  - 可提供手動刷新 API (`/admin/cache/refresh`) 做為安全網

## Acceptance Criteria

- [ ] Slow pool size 匹配 semaphore
- [ ] `read_sql_df_slow` 有 circuit breaker 保護
- [ ] Slow pool 有 keep-alive
- [ ] reject filter_options 回應 < 100ms
- [ ] mid_section loss_reasons 不再走 slow path
- [ ] resource statuses 使用常數
- [ ] 0 處 `get_db_connection()` 呼叫（excel_query 已移除）
- [ ] 所有 filter 快取統一 24hr 更新
- [ ] cache_updater 啟動時載入所有 filter
- [ ] `pytest tests/ -v` 全部通過
