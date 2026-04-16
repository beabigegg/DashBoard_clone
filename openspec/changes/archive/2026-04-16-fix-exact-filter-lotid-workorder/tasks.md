## 1. Backend — 新增 LOTID / WORKORDER Snapshot Index

- [x] 1.1 在 `src/mes_dashboard/services/wip_service.py` 的 `_build_wip_snapshot()` 中，於 index dict 新增 `"lotid": _build_value_index(filtered, "LOTID")` 與 `"workorder": _build_value_index(filtered, "WORKORDER")`
- [x] 1.2 確認 `_build_value_index()` 對 LOTID/WORKORDER 的 cardinality 不會造成記憶體問題（可 log index size 於 debug 模式）

## 2. Backend — 改用精確比對路徑

- [x] 2.1 在 `_select_with_snapshot_indexes()` 中，將 `workorder` 的處理從 `_contains_any_mask(result['WORKORDER'], workorder)` 改為 `_intersect_positions(selected_positions, _lookup_positions(indexes["workorder"], workorder))`
- [x] 2.2 在 `_select_with_snapshot_indexes()` 中，將 `lotid` 的處理從 `_contains_any_mask(result['LOTID'], lotid)` 改為 `_intersect_positions(selected_positions, _lookup_positions(indexes["lotid"], lotid))`
- [x] 2.3 確認 workorder/lotid 的篩選時機移至 `selected_positions` 交集階段（在 `result = frame.iloc[...]` 之前），而非在切出 result 後再做 mask

## 3. 文件更新

- [x] 3.1 更新 `src/mes_dashboard/routes/wip_routes.py` 中所有涉及 `lotid`、`workorder` 的 docstring，將 `fuzzy match` 改為 `exact match (case-insensitive)`
- [x] 3.2 更新 `src/mes_dashboard/routes/hold_overview_routes.py` 中相同的 docstring（若有 `fuzzy match` 標註）
- [x] 3.3 更新 `src/mes_dashboard/services/wip_service.py` 頂層相關函式的 docstring（lines 72-73、807-808、846 附近）

## 4. 測試驗證

- [x] 4.1 撰寫或更新單元測試：給定 lotid = "A100"，確認結果不包含 LOTID 為 "A1004" 的資料列
- [x] 4.2 撰寫或更新單元測試：給定 workorder = "WO001"，確認結果不包含 WORKORDER 為 "WO0010" 的資料列
- [x] 4.3 撰寫 index 存在性測試：`_build_wip_snapshot()` 回傳的 indexes dict 應包含 `"lotid"` 與 `"workorder"` key
- [x] 4.4 執行 `pytest tests/ -v -k "wip"` 確認現有 WIP 測試無回歸
- [x] 4.5 執行 `pytest tests/ -v -k "hold"` 確認現有 Hold 測試無回歸

## 5. 手動驗收

- [ ] 5.1 啟動伺服器，在 WIP Overview 選取單一 lotid（例如 `A100`），確認 Summary / Matrix 只回傳精確命中結果
- [ ] 5.2 在 WIP Overview 選取 100+ lotid，確認查詢在 1 秒內完成（vs 修改前的數秒）
- [ ] 5.3 在 Hold Overview 使用 lotid 篩選，確認結果精確
- [ ] 5.4 確認多個篩選條件同時套用（lotid + package + workcenter）結果正確（AND 交集）
