## Tasks

### ~~Task 1: 修改 `_has_cached_df` 增加 spool 檢查~~ ✓ [x]

**File**: `src/mes_dashboard/services/reject_dataset_cache.py`

修改 `_has_cached_df` 函式（約 line 344-349），在 Redis miss 後增加 spool 存在性檢查：

```python
def _has_cached_df(query_id: str) -> bool:
    """Check if query_id has cached data (L1 marker, Redis, or spool exists)."""
    if _dataset_cache.get(query_id) is not None:
        return True
    df = _redis_load_df(query_id)
    if df is not None:
        return True
    # L3: check spool metadata (O(1) Redis + path.exists, no parquet load)
    spool_path = get_spool_file_path(_REDIS_NAMESPACE, query_id)
    return spool_path is not None
```

確認 `get_spool_file_path` 的 import：檢查檔案頂部是否已有 `from ..core.query_spool_store import get_spool_file_path`。若無則加入（同檔已 import `clear_spooled_df` 等，follow 相同位置）。

**驗證**:
- `_has_cached_df` 只被 `ensure_dataset_loaded` 呼叫（grep 確認）
- 改後不影響 `execute_primary_query` 內部行為

### ~~Task 2: 更新測試~~ ✓ [x]

**File**: `tests/test_reject_dataset_cache.py`

新增或修改測試案例：
- 測試 `_has_cached_df` 在 L1 miss + Redis miss + spool 存在時回 `True`
- 測試 `_has_cached_df` 在 L1 miss + Redis miss + spool 不存在時回 `False`
- 測試 `ensure_dataset_loaded` 在 spool 存在時短路回 `cache_hit=True`，不呼叫 `execute_primary_query`

### ~~Task 3: 確認其他 dataset cache 是否有相同問題（僅記錄，不修改）~~ ✓ [x]

Grep 確認 hold/resource/yield_alert dataset cache 的 `_has_cached_df` 或等效函式是否也缺少 spool 檢查。記錄結果供後續推廣。

**結果：**
- `resource_dataset_cache.py` line 101：`_has_cached_df` 只檢查 L1 + Redis，**缺少 spool 檢查**，同樣有此問題。
- `yield_alert_dataset_cache.py`：無 `_has_cached_df`；`_get_cached_payload` 已在 line 524 呼叫 `get_spool_file_path` — 不受影響。
- `hold_history_sql_runtime.py`：無 `_has_cached_df` / `ensure_dataset_loaded`，使用不同 cache 架構 — 不受影響。
