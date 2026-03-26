## Why

2026-03-24 20:28 DEV 機（6.9GB RAM）崩潰，error.log 記錄 `System memory pressure CRITICAL: 96.3% used`。

根因追蹤：`cache_updater` 每 10 分鐘 warmup 時，2 個 Gunicorn worker 各自呼叫 `reject_dataset_cache.ensure_dataset_loaded()`。呼叫鏈：

```
ensure_dataset_loaded()
  → _has_cached_df(query_id)
    → _dataset_cache.get()        → miss (L1 無)
    → _redis_load_df(query_id)    → miss (資料已 spill 到 spool，Redis 無存)
    → return False                 ← 沒檢查 spool metadata，誤判為 miss
  → execute_primary_query()
    → _get_cached_df(query_id)     ← 再查一次，這次找到 spool
      → load_spooled_df()
        → pd.read_parquet(path)    ← 226K rows 全量載入 RAM (~60MB parquet → ~130MB DataFrame)
```

問題有兩層：
1. **`_has_cached_df` 不感知 spool** — spool 存在也回 `False`，每次 warmup 都進入 execute path
2. **execute path 中 `_get_cached_df` → `pd.read_parquet` 全量載入** — 兩個 worker 同時做等於雙份 DataFrame

日誌佐證：
- `20:21:15` merge_chunks_to_spool complete (rows=226130, size=59.7MB)
- `20:21:16` Stored query result via parquet spill
- `20:21:16` Reject query reused completed in-flight result（第二 worker 重用）
- `20:21:23 / 20:21:24` 兩個 worker 連續 warmup complete
- `20:22:43` system_mem_used 從 81% 飆到 88%（-497MB available）
- `20:28:26` 96.3% → CRITICAL reject flag → 系統不穩

## What Changes

修正 `_has_cached_df` 使其感知 spool metadata，並讓 warmup 路徑不需要全量載入 DataFrame。

1. **`_has_cached_df` 增加 spool 存在性檢查**：在 L1 miss + Redis miss 之後，額外呼叫 `has_spool_file(namespace, query_id)` 檢查 spool metadata 是否存在。若存在即回 `True`，避免進入 execute path。

2. **新增 `has_spool_file` 輕量檢查函式**：在 `query_spool_store.py` 新增 `has_spool_file(namespace, query_id) → bool`，僅讀取 Redis spool metadata key（O(1) 操作），不載入 parquet 檔案。

3. **Warmup 路徑短路**：`ensure_dataset_loaded` 在確認 spool 存在後直接 return，不觸發 `execute_primary_query`，不載入 DataFrame。

## Capabilities

### Modified Capabilities
- `reject-dataset-cache`：`_has_cached_df` 增加 spool awareness；warmup 不再全量載入

### New Capabilities
- `query_spool_store.has_spool_file`：輕量 spool 存在性檢查（metadata only）

## Scope

### In Scope
- `src/mes_dashboard/services/reject_dataset_cache.py`：修正 `_has_cached_df`
- `src/mes_dashboard/core/query_spool_store.py`：新增 `has_spool_file`
- 相關測試更新

### Out of Scope
- `merge_chunks_to_spool` streaming pipeline（已正確運作）
- 其他 dataset cache（hold、resource、yield_alert）的相同問題 — 可後續套用相同 pattern
- `execute_primary_query` 的全量載入行為（這次只修 warmup 路徑的不必要觸發）
- `load_spooled_df` 本身（它的全量載入在真正需要資料時是正確行為）
