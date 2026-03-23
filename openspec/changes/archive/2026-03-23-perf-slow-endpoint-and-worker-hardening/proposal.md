## Why

實測端點延遲發現嚴重效能問題：

- `msd/analysis` 冷啟動 **64.8 秒**同步等待（3 階段 pipeline: detection SQL → genealogy 解析 → upstream history SQL）
- `reject-history/options` 冷啟動 **35.3 秒**（首次建構 reject dataset）
- `yield-alert/*` 冷啟動 **21~29 秒**（首次建構 yield alert dataset）
- `resource-history/query 30d` **5.9 秒**
- `reject-history/* 30d` 即使 cached 仍需 **3.5 秒**（pandas 聚合瓶頸）

此外，RQ worker 系統缺乏失敗重試、timeout 過長（30 分鐘）、無主動告警。記憶體快取 L1 max_size=8 可能導致 worker 記憶體過高（峰值 776 MB）。

## What Changes

四階段改善：

### Phase 1 — RQ Worker 加強
- Job 失敗自動重試（`Retry(max=2, interval=[30, 60])`）
- Job timeout 從 1800s 調降至 600s
- Failed job metrics counter + warning log

### Phase 2 — 慢端點處理
- **msd/analysis 非同步化**：新增 `msd-analysis` rq queue，前端用 `useAsyncJobPolling` 輪詢
- **yield-alert / reject-history dataset 預熱**：`CacheUpdater` 啟動後背景預建 dataset，消除冷啟動
- **reject-history 30d 聚合優化**：categorical dtype 加速 groupby，或預計算常用維度

### Phase 3 — 快取架構微調
- Dataset L1 cache max_size 從 8 降至 3（節省 ~3 GB 記憶體）
- `MemoryTTLCache` (L0) 加 max_size 上限（256）

### Phase 4 — 觀測性補齊
- 統一 cache hit/miss metrics 進 `metrics_history`
- 慢查詢 SQL 加 caller tag 追蹤
- Dead worker 主動告警（queue_depth>0 且 workers=0）

## Capabilities

### New Capabilities
- `msd-async-analysis`: MSD 缺陷分析非同步執行 — rq queue + job service + 前端 polling
- `dataset-cache-warmup`: Dataset 快取預熱機制 — CacheUpdater 啟動時預建 reject/yield-alert dataset

### Modified Capabilities
- `async-query-job-service`: enqueue_job 新增 retry 參數，timeout 調降
- `reject-history-pareto-materialized-aggregate`: 30d 聚合效能優化
- `hold-dataset-cache`: L1 max_size 調降
- `resource-dataset-cache`: L1 max_size 調降
- `reject-history-api`: reject dataset L1 max_size 調降
- `yield-alert-center-api`: yield alert dataset L1 max_size 調降
- `cache-observability-hardening`: 統一 hit/miss metrics、dead worker 告警
- `slow-query-observability`: 慢查詢 caller tag

## Impact

- **後端修改 ~12 個模組**，新增 ~2 個模組（msd job service、warmup 任務）
- **前端修改 1 個頁面**（MSD analysis 改用 async polling）
- **部署新增 1 個 systemd unit**（msd-analysis worker）
- **不影響 API 契約**：現有回應格式不變（msd/analysis 新增 202 回應是向後相容）
- **記憶體使用預期降低 ~3 GB**（L1 cache 縮減）

## Scope

- 不做 SQL 下推（現有架構已合理）
- 不做 WebSocket（polling 已足夠）
- 不做 pandas 替換（快取層維度切片是正確設計）
- 不切換 task queue 框架（rq 已滿足需求）
