## Context

MES Dashboard 實測發現多個端點冷啟動延遲嚴重（msd/analysis 64.8s、reject-history/options 35.3s、yield-alert/* 21-29s）。系統已有成熟的 rq 非同步框架（trace-events、reject-query）和多層快取架構（L0 route → L1 process → L2 Redis → L3 Oracle），但覆蓋不完整。RQ worker 缺乏重試機制和主動告警。

現有基礎設施：
- `async_query_job_service.py` — 通用 enqueue/status/complete 框架
- `useAsyncJobPolling.js` — 前端 polling composable
- `CacheUpdater` — 背景定時快取更新（目前只管 resource sync）
- `metrics_history` — SQLite 快照（30s 間隔），已記錄 latency/pool/rq 指標
- `rq_monitor_service.py` — on-demand worker/queue 狀態查詢
- Systemd units — trace-worker、reject-worker，`Restart=always`，`MemoryMax=4G`

## Goals / Non-Goals

**Goals:**
- 消除 >5s 冷啟動同步等待（msd/analysis、yield-alert、reject-history/options）
- RQ job 暫態失敗自動恢復（重試 2 次）
- 降低 worker 記憶體峰值 ~3 GB（L1 cache 縮減）
- 補齊 cache hit/miss metrics 和 dead worker 告警

**Non-Goals:**
- SQL 查詢重寫或下推（現有架構合理）
- WebSocket 替代 polling
- 替換 pandas 或 rq 框架
- 前端 UI 重設計（僅 msd/analysis 頁面加 loading 狀態）

## Decisions

### Decision 1: msd/analysis 走 rq 非同步（而非 dataset 預熱）

**選擇：rq 非同步化**

理由：
- msd/analysis 是 3 階段 pipeline（detection SQL → genealogy → upstream history），不是單純的 dataset 建構
- 參數組合多（start_date × end_date × station × loss_reasons × direction），預熱不實際
- 已有 `async_query_job_service` + `useAsyncJobPolling` 框架可複用

替代方案（放棄）：
- 預熱：參數組合太多，無法有效覆蓋
- SQL 優化：3 階段串聯，單一 SQL 無法完成

### Decision 2: yield-alert / reject dataset 走 CacheUpdater 預熱（而非 rq 非同步）

**選擇：CacheUpdater 背景預熱**

理由：
- 這些 dataset 建構後 cached 效果極佳（29s → 5ms），問題僅在冷啟動
- Dataset 參數固定（全量建構），適合定時預熱
- CacheUpdater 已存在且運作穩定，只需新增 warmup 任務
- 預熱讓用戶完全無感，UX 優於非同步（不需看 loading）

### Decision 3: L1 max_size 調降至 3（而非完全移除）

**選擇：保留 L1 但縮小**

理由：
- L1 避免重複 parquet 反序列化（Redis L2 → DataFrame），仍有價值
- max_size=3 覆蓋最常用查詢組合，同時大幅降低記憶體
- 完全移除會在高併發下增加 Redis 壓力

### Decision 4: Job timeout 600s + Retry(max=2) 組合

**選擇：縮短單次 timeout，搭配重試**

理由：
- 實測最慢查詢 ~65s，600s 有充裕 buffer
- 暫態失敗（DB 短暫斷線）30s 後重試通常可恢復
- 總等待上限 600s × 3 = 30min，與原本 1800s 相當但更有韌性

### Decision 5: MemoryTTLCache 加 max_size=256

**選擇：LRU eviction 而非保持無限制**

理由：
- 目前無 max_size，理論上 route cache 可無限增長
- 256 entries 覆蓋所有活躍 route 組合綽綽有餘
- 超出時 LRU 淘汰最不常用的，不影響命中率

## Architecture

### msd/analysis 非同步流程

```
Browser                    Flask Route                    RQ Worker
  │                           │                              │
  ├── POST /analysis ────────▶│                              │
  │                           ├── enqueue_job()              │
  │                           │   queue: msd-analysis        │
  │◀── 202 {job_id} ─────────┤                              │
  │                           │                              │
  │   poll (2s)               │                              ├── _run_backward_pipeline()
  ├── GET /analysis/job/{id} ─▶── get_job_status() ─────────│   1. detection SQL
  │◀── {status: running} ─────┤                              │   2. genealogy resolve
  │                           │                              │   3. upstream history
  │   poll (2s)               │                              │   4. attribution + charts
  ├── GET /analysis/job/{id} ─▶── get_job_status()           │
  │◀── {status: finished} ────┤                              ├── complete_job(query_id)
  │                           │                              │
  ├── GET /analysis/job/{id}/result                          │
  │◀── {kpi, charts, ...} ───┤◀── redis_df_store.load() ───┘
```

### CacheUpdater 預熱流程

```
CacheUpdater (background thread, interval=600s)
  │
  ├── _check_wip_cache()           ← 既有
  ├── _check_resource_sync()       ← 既有
  ├── _warmup_reject_dataset()     ← 新增
  │     └── reject_dataset_cache.ensure_dataset_loaded()
  ├── _warmup_yield_alert_dataset()← 新增
  │     └── yield_alert_dataset_cache.ensure_dataset_loaded()
  └── _warmup_reject_options()     ← 新增
        └── reject_dataset_cache.get_filter_options()
```

### 記憶體影響

```
Before:
  4 dataset caches × 8 entries × ~50MB = 1.6 GB per worker
  3 workers = 4.8 GB peak

After:
  4 dataset caches × 3 entries × ~50MB = 0.6 GB per worker
  3 workers = 1.8 GB peak

  Savings: ~3 GB
```

## File Impact

### New Files
| File | Purpose |
|------|---------|
| `services/msd_query_job_service.py` | MSD analysis rq job enqueue/execute |
| `deploy/mes-dashboard-msd-worker.service` | MSD worker systemd unit |

### Modified Files
| File | Changes |
|------|---------|
| `services/async_query_job_service.py` | enqueue_job() 加 retry 參數、timeout 調降 |
| `services/mid_section_defect_service.py` | query_analysis() 支援非同步 path |
| `routes/mid_section_defect_routes.py` | analysis 端點回 202 + job status/result 端點 |
| `core/cache_updater.py` | 新增 reject/yield-alert/options warmup 任務 |
| `services/hold_dataset_cache.py` | L1 max_size 8→3 |
| `services/resource_dataset_cache.py` | L1 max_size 8→3 |
| `services/reject_dataset_cache.py` | L1 max_size 8→3、expose ensure_dataset_loaded() |
| `services/yield_alert_dataset_cache.py` | L1 max_size 3→2、expose ensure_dataset_loaded() |
| `core/cache.py` | MemoryTTLCache 加 max_size=256 + LRU eviction |
| `core/metrics_history.py` | 新增 cache_hit_count/cache_miss_count 欄位 |
| `routes/health_routes.py` | dead worker 告警條件 |
| `core/database.py` | read_sql_df slow log 加 caller tag |
| `scripts/start_server.sh` | 新增 msd worker 啟停 |
| `frontend/.../MsdAnalysis*.vue` | 改用 useAsyncJobPolling |
