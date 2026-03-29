## Context

目前 reject/hold/resource 三個歷史域在主查詢完成後透過 `redis_df_store.redis_store_df()` 將完整 DataFrame 序列化（Parquet+base64）存入 Redis。這是「直連路徑」（direct-path，短查詢）的 L2 快取策略，針對「短查詢小資料可以直接存 Redis」設計。大查詢（Engine 路徑）已改用 `query_spool_store.store_spooled_df()` + spool 檔案。

現況兩路徑並存：
- 直連路徑（≤10 天）→ `_store_df()` → `redis_store_df()`（Parquet+base64，5–100 MB）
- Engine 路徑（長查詢）→ `store_spooled_df()` / `register_spool_file()` → spool meta pointer

yield-alert 大型 detail 資料已在前一次變更（streaming spool）移至 spool-only；linkage_df（~20KB）維持 Redis，不在本 Phase 範圍。

參考模型：production-history、material-trace、MSD 全部走 `query_spool_store` metadata pointer，不存 DataFrame payload。

## Goals / Non-Goals

**Goals:**
- 移除 reject/hold/resource 直連路徑的 `redis_store_df()` 大型 payload 寫入
- Redis 對這三個域只存 `{ns}:spool_meta:{query_id}` pointer（< 1KB）和輔助 key（dates、partial_failure）
- 提供 `PHASE2_METADATA_ONLY` 環境變數 feature flag，可在不重新部署程式碼的情況下切換
- 不改動外部 API contract

**Non-Goals:**
- yield-alert linkage_df（~20KB，已有 spec 確認維持 Redis）
- batch_query chunk Redis 儲存（小片段、不同用途，`redis_df_store` 保留）
- 修改 spool TTL（維持現行 900s）
- 前端元件或 API response 結構
- Phase 3 的 pandas fallback 移除（view path 的 `load_spooled_df` fallback 是 Phase 3 範圍）

## Decisions

### D1：直連路徑改為「永遠 spool」，移除大小判斷

**決定**：`_store_df()` 一律呼叫 `store_spooled_df()`，不再依查詢大小判斷是否走 Redis。

**理由**：原本「短查詢小資料可以存 Redis」的前提在實際量測中不成立——5–20MB 的 Parquet+base64 仍是 Redis 的主要壓力來源。消除 threshold 判斷也簡化了雙路徑邏輯。

**備選方案**：保留 threshold（例如 < 1MB 才走 Redis）。拒絕理由：難以在 runtime 準確估算序列化大小，且 1MB 以下的查詢數量有限，Redis 節省效果不顯著。

---

### D2：Feature flag 為全域環境變數，不做 per-domain 切換

**決定**：`PHASE2_METADATA_ONLY`（預設 `1`），設為 `0` 回退三個域的舊 Redis 寫入。

**理由**：三個域風險輪廓相似（同樣的 `redis_df_store`、同樣的 TTL），不需要個別控制。全域 flag 降低 rollback 複雜度。

**備選方案**：`PHASE2_{DOMAIN}_METADATA_ONLY`。拒絕理由：增加操作負擔，且在問題發生時全域回退即可。

---

### D3：讀取路徑：spool first，Redis fallback（過渡期保留）

**決定**：`_get_cached_df()` / `_load_df_on_demand()` 改為先查 spool metadata，找不到再嘗試 `redis_load_df()`（過渡期 fallback，處理部署前的 in-flight Redis key）。

**理由**：滾動部署時，可能有舊路徑已寫入 Redis 的 key，新程式碼需能讀到。過渡期 fallback 確保不中斷。穩定後（下一次部署）移除 Redis fallback。

**備選方案**：部署時清空對應 Redis namespace。拒絕理由：清空動作不可逆且 downtime 風險較高。

---

### D4：直接使用現有 `query_spool_store.store_spooled_df()`，不新增 helper

**決定**：`_store_df()` 直接呼叫 `store_spooled_df(namespace, query_id, df, ttl_seconds=_CACHE_TTL)`，不新增額外 wrapper。

**理由**：`query_spool_store` 已有容量保護（`_ensure_capacity()`）、TTL 管理、`columns_hash` 一致性驗證，完全符合需求。新增 wrapper 只增加抽象層數。

---

### D5：不修改 reject 的 engine 路徑

**決定**：`_store_query_result()`（reject engine 路徑）已走 `store_spooled_df()` + `register_spool_file()`，本次不動。

**理由**：engine 路徑已是 metadata-only，無需更改。

## Risks / Trade-offs

| 風險 | 緩解措施 |
|------|---------|
| 磁碟 I/O 增加（短查詢也要寫 spool 檔） | L1 in-process cache 保護大多數 worker 內 cache-hit 路徑，不需要磁碟讀；`_ensure_capacity()` 保護空間上限 |
| spool 檔案數量增加（短查詢原本只有 Redis key） | 同樣 900s TTL，archive log rotation 機制不變；spool 磁碟用量已在 Phase 1 telemetry 監控 |
| 部署過渡期 in-flight Redis key（舊格式） | D3 的 spool-first + Redis fallback 讀取策略處理，不需要維護窗口 |
| `store_spooled_df()` 失敗（磁碟滿） | 現有 `_ensure_capacity()` 保護；寫入失敗時已有 503 回傳機制（yield-alert 模式） |

## Migration Plan

1. **部署前**：確認 `redis_namespace_memory` telemetry 可讀（Phase 1 已上線），記錄 baseline
2. **部署**：新程式碼上線，`PHASE2_METADATA_ONLY=1`（預設啟用）
3. **觀察 2–4 小時**：Redis `reject_dataset:`, `hold_dataset:`, `resource_dataset:` namespace 記憶體應在 TTL 900s 後逐步降至接近 0
4. **回退條件**：若出現查詢 cache miss 率異常或錯誤率上升，設定 `PHASE2_METADATA_ONLY=0`，重啟 workers
5. **穩定後**：下一次部署時移除 feature flag + Redis fallback 讀取路徑（產生 cleanup PR）

## Open Questions

- `batch_query_engine.py` 的 chunk Redis payload（1–10 MB/chunk）是否納入後續 Phase？目前維持現行，可作 Phase 3+ 的補充項目
- hold-history 的 `_store_query_dates()` 輔助 Redis key（存 start_date/end_date）應繼續保留（僅幾十 bytes，不是 payload 問題）
