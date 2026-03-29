## Why

Phase 0 基線盤點（`docs/phase0_baseline_assessment.md`）確認 MES Dashboard 的 RAM 有三大熱點：

1. **WIP JSON + Parquet 雙重表示** — Redis 同時存 `mes_wip:data`（JSON, 14+ MB）和 `mes_wip:data:parquet`（Parquet+base64, ~10 MB），每個 gunicorn worker 的 L1 cache 還各持一份 parsed DataFrame。
2. **dataset cache L1 max_size 過大** — reject/hold/resource 各 `max_size=3`、yield-alert `max_size=2`，4 workers × 11 entries = 最多 44 份大型 DataFrame 常駐記憶體。
3. **resource_cache / realtime_equipment_cache Redis 端無 TTL** — updater 停止時，舊資料永不過期，無法被回收。

Phase 1 目標是在**不改變前端 API contract**的前提下，透過 hot cache 整理拿到最低風險的 RAM 收益。

## What Changes

- **1.1 WIP cache 改為 Parquet-only**：停止寫入 `mes_wip:data`（JSON），保留 `mes_wip:data:parquet` 作為唯一 canonical 表示。移除 `cache.py` 中的 JSON fallback 讀取路徑。預估 Redis -14 MB，parse 路徑簡化。
- **1.2 dataset cache L1 max_size 縮小**：reject/hold/resource/yield-alert 的 `ProcessLevelCache` max_size 全部降至 `1`。每 worker 從最多 11 份降到 4 份大型 DataFrame。透過環境變數或直接修改 code。
- **1.3 resource_cache / realtime_equipment_cache Redis 加 TTL**：在 Redis pipeline write 加上 `EX 300`（5 分鐘）。updater 正常運作時不會過期，updater 異常停止時 5 分鐘後自動清除陳舊資料。
- **1.4 filter cache 評估**：Phase 0 確認 filter/container_filter/reason_filter 已是 Redis 24h + 無 L1 mirror。若 JSON parse 開銷可接受，維持現狀。
- **1.5 補齊低風險 telemetry**：新增 spool namespace 磁碟用量和 per-namespace Redis memory 估算到 admin API。

## Capabilities

### Modified Capabilities
- `cache-observability-hardening`: 新增 spool 磁碟用量和 Redis memory 估算 telemetry
- `resource-cache-representation-normalization`: resource_cache Redis pipeline 加 TTL
- `system-memory-monitoring`: dataset cache max_size 調降的監控數據變化

### New Capabilities
- `wip-cache-parquet-only`: WIP 快取從 JSON+Parquet 雙存改為 Parquet-only

## Impact

- **後端 core**：
  - `core/cache_updater.py`（line 280）：移除 JSON staging/rename 寫入 `mes_wip:data`
  - `core/cache.py`（lines 471-486）：移除 JSON fallback 讀取路徑，保留 Parquet-only
- **後端 services**：
  - `resource_cache.py`（lines 587-592）：pipeline 加 `EX 300`
  - `realtime_equipment_cache.py`（lines 357-364）：pipeline 加 `EX 300`
  - `reject_dataset_cache.py`（line 82）：`_CACHE_MAX_SIZE` 3 → 1
  - `hold_dataset_cache.py`（line 46）：`_CACHE_MAX_SIZE` 3 → 1
  - `resource_dataset_cache.py`（line 37）：`_CACHE_MAX_SIZE` 3 → 1
  - `yield_alert_dataset_cache.py`（line 61）：default 2 → 1
- **後端 routes**：
  - `admin_routes.py`：新增 spool 磁碟用量 endpoint / Redis MEMORY USAGE 抽樣
- **前端**：無影響（不改 API contract）
- **API contract**：無影響（response 結構不變）
- **風險**：
  - WIP JSON 移除後，若有外部系統直接讀 `mes_wip:data` Redis key 會斷。需確認無外部消費者。
  - L1 max_size=1 在高併發下可能增加 Redis round-trip，但 TTL=15min 的 dataset 通常同一時間只查一個日期範圍。
  - resource/equipment TTL=300s 在 updater 正常時不影響（sync interval 遠低於 300s），但 updater 停止超過 5 分鐘後頁面會拿到空資料。需搭配 health check alert。
