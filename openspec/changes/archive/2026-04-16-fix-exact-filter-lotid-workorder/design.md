## Context

WIP snapshot (`_build_wip_snapshot`) 在快取命中後會提供一個預建 index dict，供 `_select_with_snapshot_indexes()` 做 O(1) dict lookup 篩選。目前已索引的欄位：`WORKCENTER_GROUP`、`PACKAGE_LEF`、`PJ_TYPE`、`FIRSTNAME`、`WAFERDESC`、`WIP_STATUS`、`HOLD_TYPE`。

`LOTID` 與 `WORKORDER` 不在索引內，在 `_select_with_snapshot_indexes()` 中由 `_contains_any_mask()` 以 `str.contains()` 逐值做子字串掃描，複雜度為 O(n × m)。前端 MultiSelect 下拉清單送出的是精確完整值（comma-separated），後端卻用模糊比對，導致效能慢且結果可能有誤命中。

WIP Overview、WIP Detail、Hold Overview 三條路徑都經由同一個 `_select_with_snapshot_indexes()`，修一處即全部修到。

## Goals / Non-Goals

**Goals:**
- 將 `LOTID`、`WORKORDER` 加入 WIP snapshot index（同其他已索引欄位的做法）
- 在 `_select_with_snapshot_indexes()` 中改用 `_lookup_positions()` 精確比對取代 `_contains_any_mask()`
- 消除 O(n × m) 子字串掃描，使大量篩選（如 8000 筆 lot_id）降至毫秒級
- 結果準確性：選 `A123` 只回傳 `LOTID = 'A123'`，不再誤命中 `A1234`

**Non-Goals:**
- 不修改 Oracle fallback 路徑（`_build_wip_oracle_query`）——Oracle 側本來就用 `LIKE` 或 `IN`，不在此次範圍
- 不修改 `_apply_filter_baseline()`（供 snapshot 建構前的初篩使用，行為不變）
- 不修改前端（MultiSelect 已正確送出精確值，不需改動）
- 不新增 API 參數或改變 request/response 格式
- Hold Detail 頁面不接受 lotid/workorder 篩選，本次不異動

## Decisions

### D1：使用 `_build_value_index()` 為 LOTID 與 WORKORDER 建立 snapshot index

**選擇**：在 `_build_wip_snapshot()` 的 index dict 中新增：
```python
"lotid":     _build_value_index(filtered, "LOTID"),
"workorder": _build_value_index(filtered, "WORKORDER"),
```

**理由**：`_build_value_index()` 已被所有其他精確比對欄位採用，它以 `str(value).upper()` 為 key 建立 `{value → row_positions}` dict，lookup 為 O(1)，不需引入新的資料結構或依賴。

**備選方案**：用 pandas `isin()` 在查詢時即時篩選——可行但複雜度仍為 O(m)（m = filter 值數量），且無法利用現有 index 交集邏輯 `_intersect_positions()`；預建 index 一致性更好。

### D2：在 `_select_with_snapshot_indexes()` 改用 `_lookup_positions()` 取代 `_contains_any_mask()`

**選擇**：
```python
# Before
if workorder:
    result = result[_contains_any_mask(result['WORKORDER'], workorder)]
if lotid:
    result = result[_contains_any_mask(result['LOTID'], lotid)]

# After
if workorder:
    selected_positions = _intersect_positions(
        selected_positions, _lookup_positions(indexes["workorder"], workorder)
    )
if lotid:
    selected_positions = _intersect_positions(
        selected_positions, _lookup_positions(indexes["lotid"], lotid)
    )
# 後續統一由 selected_positions 切出 result（同現有 package 等欄位做法）
```

**理由**：與現有 workcenter/package 等欄位完全對齊，使用 `_intersect_positions()` 交集邏輯，可正確組合多個篩選條件，不需在已切出 `result` 後再做 mask 篩選。

### D3：index key 的大小寫正規化沿用現有 `_build_value_index()` 行為

`_build_value_index()` 以 `str(v).upper()` 為 key；`_lookup_positions()` 在查詢時也會做 `str(v).upper()`，大小寫不敏感正確對齊，不需額外處理。

## Risks / Trade-offs

- **記憶體增加**：LOTID 與 WORKORDER 的 cardinality 遠高於 PACKAGE 等欄位（可能數萬筆 unique 值），index dict 佔用記憶體將顯著增加。→ 緩解：index 只儲存 row position（numpy int32 array）指標，不複製資料；實際增量預估在數 MB 以內，在可接受範圍。
- **Snapshot 建構時間略增**：每次 snapshot refresh 需多建兩個 index。→ 緩解：snapshot 30 秒 TTL 內只建一次，對 P95 latency 影響微小。
- **行為變更（精確取代模糊）**：使用者若習慣用部分字串篩選（如輸入 `A123` 期望命中 `A1234`），此路徑將不再支援。→ 此為設計意圖修正：下拉清單的模糊搜尋發生在 UI 層（`/api/wip/meta/search`），篩選套用時應精確；若有使用者直接手打 URL 帶部分值的場景，需另行評估。

## Migration Plan

1. 修改 `_build_wip_snapshot()`：新增 LOTID、WORKORDER index 建構
2. 修改 `_select_with_snapshot_indexes()`：將 lotid/workorder 改走 `_lookup_positions()` 路徑
3. 更新 `wip_routes.py`、`hold_overview_routes.py` docstring（`fuzzy match` → `exact match`）
4. 執行現有 WIP/Hold 相關測試確認無回歸
5. 無需資料庫 migration、無需 Redis flush（snapshot 在下次 TTL 到期後自動以新邏輯重建）

**Rollback**：git revert 即可，無持久化狀態依賴。

## Open Questions

- 是否有已知使用者以手動 URL 帶部分 lotid 字串篩選的場景？（若有，需在 UI 層加提示或保留模糊路徑作為 fallback）
