## Context

`reject_dataset_cache.ensure_dataset_loaded()` 被 `cache_updater` 每 10 分鐘呼叫（warmup），2 個 worker 各自執行。當 reject dataset 已透過 engine path spill 到 spool parquet（226K rows, 59.7MB），`_has_cached_df` 仍回 `False`（L1 miss + Redis miss），因為它不檢查 spool metadata。

後續 `execute_primary_query` → `_get_cached_df` → `load_spooled_df` → `pd.read_parquet` 把 226K rows 全量載入 RAM，兩個 worker 同時做等於雙份 ~130MB DataFrame，在 6.9GB DEV 機上疊加其他 cache miss 即觸發 OOM。

關鍵：`query_spool_store.get_spool_file_path(namespace, query_id)` 已存在，做了完整的 TTL 驗證 + 檔案存在性檢查，且為 O(1) Redis 操作（不載入 parquet），可直接用於 `_has_cached_df`。

## Goals / Non-Goals

**Goals**
- 讓 `_has_cached_df` 感知 spool，避免 warmup 不必要觸發 execute path
- 零 API 行為改變（只影響 cache hit/miss 判斷的正確性）
- 最小改動量，pattern 可後續推廣到 hold/resource/yield_alert dataset cache

**Non-Goals**
- 不改變 `execute_primary_query` 內部的 `_get_cached_df` 行為（當真正需要資料時全量載入是正確的）
- 不改變 `load_spooled_df`（它的職責就是載入 DataFrame）
- 不改其他 dataset cache（本次只修 reject，驗證 pattern 後再推廣）

## Decisions

### D1. `_has_cached_df` 增加 spool 存在性檢查

- **Decision**: 在 `_redis_load_df` miss 之後，額外呼叫 `get_spool_file_path(_REDIS_NAMESPACE, query_id)`。若回傳非 None 則回 `True`。
- **Rationale**: `get_spool_file_path` 已做 TTL 過期清理 + 檔案存在性驗證，語意正確。是純 Redis metadata 讀取 + `path.exists()`，不載入 parquet 資料。
- **Impact**: warmup 在 spool 存在時直接短路，不觸發 `execute_primary_query`，不載入 DataFrame。

### D2. 不新增 `has_spool_file` 函式

- **Decision**: 直接使用已存在的 `get_spool_file_path`（回傳 `Optional[str]`），不額外包裝 `has_spool_file(→ bool)`。
- **Rationale**: `get_spool_file_path` 語意已足夠（None = 不存在），新增 wrapper 增加 API surface 卻無實質好處。若後續多處需要可再加。

### D3. import 方式使用 lazy import

- **Decision**: 在 `_has_cached_df` 函式內 lazy import `get_spool_file_path`，避免 module-level circular import。
- **Rationale**: `reject_dataset_cache.py` 已在多處使用 `from ..core.query_spool_store import ...`（如 line 362 `clear_spooled_df`），follow 相同 pattern。若已是 top-level import 則直接使用。

## Component Interactions

```
_has_cached_df(query_id)  【修改後】
━━━━━━━━━━━━━━━━━━━━━━━━

  L1: _dataset_cache.get(query_id)
       │ hit → return True
       │ miss ▼

  L2: _redis_load_df(query_id)
       │ hit (df is not None) → return True
       │ miss ▼

  L3: get_spool_file_path(_REDIS_NAMESPACE, query_id)  ← 新增
       │ 內部: Redis HGETALL(spool:metadata:...) → 檢查 TTL → Path.exists()
       │ hit (path is not None) → return True
       │ miss ▼

  return False


ensure_dataset_loaded() 行為改變：
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  改前: spool 存在 → _has_cached_df returns False → execute_primary_query
        → _get_cached_df → pd.read_parquet(226K rows) → RAM

  改後: spool 存在 → _has_cached_df returns True → return cache_hit=True
        → 不進入 execute path → 不載入 DataFrame → RAM 零增長
```

## Risk Assessment

1. **False positive (誤判 hit)**: `get_spool_file_path` 已驗證 TTL + file exists，spool 過期或被清理時會正確回 None。風險極低。

2. **L1 marker 不一致**: spool 存在但 L1 無 marker 時，`_has_cached_df` 仍需走到 L3 檢查。但 `ensure_dataset_loaded` 回傳 `cache_hit=True` 且不設 L1 marker — 下次呼叫仍走 L2/L3。**可接受**：warmup 每 10 分鐘才跑一次，L3 是 O(1)，不構成效能問題。

3. **其他 caller 影響**: `_has_cached_df` 目前只被 `ensure_dataset_loaded` 呼叫（grep 確認）。無其他 caller 受影響。

4. **Pattern 推廣風險**: hold/resource/yield_alert 的 `_has_cached_df` 結構類似但不完全相同，推廣時需逐一確認。本次不涉及。
