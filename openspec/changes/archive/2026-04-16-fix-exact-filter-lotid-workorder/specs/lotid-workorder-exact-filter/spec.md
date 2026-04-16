## ADDED Requirements

### Requirement: LOTID and WORKORDER SHALL use pre-built snapshot indexes for exact matching
WIP snapshot 在建構時 SHALL 為 `LOTID` 與 `WORKORDER` 欄位建立 value index（同 `PACKAGE_LEF`、`WORKCENTER_GROUP` 等既有欄位的做法），使 `_select_with_snapshot_indexes()` 能以 O(1) dict lookup 執行精確篩選。

#### Scenario: Snapshot index includes LOTID and WORKORDER
- **WHEN** `_build_wip_snapshot()` 執行
- **THEN** 回傳的 index dict SHALL 包含 `"lotid"` 與 `"workorder"` 兩個 key
- **THEN** 每個 key 的值 SHALL 是 `{normalized_value → np.ndarray(row_positions)}` 的 dict（與其他欄位 index 格式相同）

#### Scenario: Exact match on LOTID filter
- **WHEN** `_select_with_snapshot_indexes()` 以 `lotid="A100,B200"` 呼叫
- **THEN** 結果 SHALL 只包含 `LOTID` 欄位值完全等於 `"A100"` 或 `"B200"` 的資料列（大小寫不敏感）
- **THEN** `LOTID` 為 `"A1000"`、`"XA100"`、`"A100-NG"` 等僅含子字串的資料列 SHALL NOT 出現在結果中

#### Scenario: Exact match on WORKORDER filter
- **WHEN** `_select_with_snapshot_indexes()` 以 `workorder="WO001,WO002"` 呼叫
- **THEN** 結果 SHALL 只包含 `WORKORDER` 完全等於 `"WO001"` 或 `"WO002"` 的資料列
- **THEN** `WORKORDER` 為 `"WO0011"`、`"XWO001"` 等僅含子字串的資料列 SHALL NOT 出現在結果中

#### Scenario: Large LOTID filter set performance
- **WHEN** 使用者選取 1000 筆以上 lot_id 後呼叫 WIP Overview Summary API
- **THEN** 快取命中時的篩選耗時 SHALL ≤ 500ms（P95）
- **THEN** 系統 SHALL NOT 執行 `str.contains()` 迴圈

#### Scenario: LOTID and WORKORDER filters combine correctly with other filters
- **WHEN** `_select_with_snapshot_indexes()` 同時接收 `lotid`、`package`、`workcenter` 等多個篩選
- **THEN** 結果 SHALL 為所有篩選條件的交集（AND 語意），與現有其他精確篩選欄位的組合行為一致
