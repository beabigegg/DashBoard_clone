## Context

Phase 0 基線盤點（`docs/phase0_baseline_assessment.md`）確認 MES Dashboard gunicorn 的 RAM 熱點集中在三個面向：WIP 雙重 Redis 表示、dataset L1 cache 過大、resource/equipment cache 無 TTL 保護。Phase 1 是最低風險的第一步——只整理 hot cache 層，不改 API contract、不改前端、不改查詢架構。

**現況關鍵數據：**
- WIP Redis: `mes_wip:data` (JSON ~14 MB) + `mes_wip:data:parquet` (~10 MB)，雙份共 ~24 MB
- Dataset L1: reject/hold/resource 各 max_size=3, yield-alert max_size=2, 4 workers × 11 entries = 44 份大型 DF
- Resource/Equipment Redis: pipeline write 無 EX，updater 停止時舊資料永駐

## Goals / Non-Goals

**Goals:**
- 降低 gunicorn worker RSS（壓縮 L1 cache 副本數）
- 降低 Redis memory（移除 WIP JSON 雙存）
- 增加 cache 安全性（resource/equipment TTL 防止 stale data 永駐）
- 補齊 Phase 0 發現的 telemetry 缺口（spool 磁碟用量、Redis memory 估算）

**Non-Goals:**
- 不改前端 API response 結構
- 不把 WIP / resource status 改成 RQ async
- 不移除 dataset 的 Redis 大型 payload（Phase 2 範圍）
- 不移除 pandas fallback（Phase 3 範圍）
- 不統一 resource_cache / equipment_cache 的自製 `_ProcessLevelCache` 為共用版本（風險較高，留後續）

## Decisions

### D1: WIP cache 保留 Parquet，移除 JSON

**選擇：** 只保留 `mes_wip:data:parquet`，移除 `mes_wip:data` JSON 寫入與讀取。

**替代方案：** 保留 JSON、移除 Parquet（JSON 對 debug 較友善）。

**理由：** Parquet 是 binary columnar 格式，parse 到 DataFrame 更快且記憶體效率更高。目前 `cache.py:471-486` 已是 Parquet-first，JSON 只是 fallback。移除 JSON 可省 ~14 MB Redis + 簡化讀取路徑。Debug 需求可透過 admin API 查 DataFrame schema/row_count 替代。

**影響範圍：**
- 寫入端：`cache_updater.py:280`（移除 JSON staging + rename）
- 讀取端：`cache.py:481-486`（移除 JSON fallback branch）
- 需確認無外部系統直接消費 `mes_wip:data` key

### D2: dataset L1 max_size 統一降至 1

**選擇：** reject/hold/resource/yield-alert 全部 `max_size=1`。

**替代方案 A：** 降至 2（保留前一次查詢 cache）。
**替代方案 B：** 透過環境變數控制，不改 code default。

**理由：** 這些 dataset cache TTL 為 15min（yield-alert 5min），同一時間使用者通常只查一個日期範圍。max_size=1 每 worker 只持 1 份 DF，4 域 × 4 workers = 16 份（vs 現在最多 44 份）。若需要可透過既有環境變數 override 回高值。直接改 code default 而非只改 env，因為 env 在部署時容易遺漏。

**影響範圍：**
- `reject_dataset_cache.py:82` → `_CACHE_MAX_SIZE = 1`
- `hold_dataset_cache.py:46` → `_CACHE_MAX_SIZE = 1`
- `resource_dataset_cache.py:37` → `_CACHE_MAX_SIZE = 1`
- `yield_alert_dataset_cache.py:61` → default `"1"`

### D3: resource_cache / equipment_cache Redis 加 EX 300s

**選擇：** 在 Redis pipeline write 加 `EX 300`（5 分鐘）。

**替代方案：** 加更長 TTL（如 1800s）或不加 TTL 但加 health alert。

**理由：** 兩者的 updater sync interval 通常 30-60s，正常運作時 300s TTL 不會觸發過期。但 updater 停止時，5 分鐘後舊資料自動清除，避免顯示錯誤的即時狀態。300s 是 sync interval 的 5-10 倍，足夠容忍偶發延遲。

**影響範圍：**
- `resource_cache.py:587-592` pipeline → 加 `EX 300`
- `realtime_equipment_cache.py:357-364` pipeline → 加 `EX 300`

### D4: filter cache 維持現狀

**選擇：** 不做變更。

**理由：** Phase 0 確認 filter/container_filter/reason_filter 已是 Redis 24h + 無 L1 mirror。JSON parse 開銷對 filter 資料量（通常 <100 KB）可忽略。加 L1 mirror 的收益不值得增加複雜度。

### D5: telemetry 補齊用 admin API 擴充

**選擇：** 在現有 `/admin/api/performance-detail` 回應中新增 spool 磁碟用量和 Redis per-namespace memory 估算。

**替代方案：** 新建獨立 endpoint。

**理由：** 現有 admin performance-detail 已整合 Redis/cache/DB 資訊，追加在同一處對前端 admin page 最自然。spool 用量用 `os.scandir` 統計各 namespace 目錄大小。Redis memory 用 `MEMORY USAGE` command 抽樣代表性 key。

## Risks / Trade-offs

| Risk | Mitigation |
|------|------------|
| WIP JSON 移除後若有外部系統讀 `mes_wip:data` 會斷 | 部署前用 `redis-cli OBJECT FREQ mes_wip:data` 或 monitor 確認無外部消費者 |
| L1 max_size=1 高併發下增加 Redis round-trip | dataset TTL=15min，同時段通常只查一個範圍；若有問題可透過 env var override |
| resource/equipment TTL=300s 在 updater 長時間停止時頁面顯示空 | 搭配 health check 已有的 updater 存活偵測；前端已有 stale data warning |
| `MEMORY USAGE` command 在大 key 上可能慢 | 只抽樣 5-10 個代表性 key，不掃全部；加 timeout 保護 |
