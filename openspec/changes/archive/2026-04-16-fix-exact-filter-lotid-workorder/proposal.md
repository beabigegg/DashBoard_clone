## Why

WIP Overview、WIP Detail、Hold Overview 的 `lotid` 與 `workorder` 篩選，在使用者從下拉清單選取後仍走模糊子字串比對（`str.contains()`），而非精確比對。這導致兩個問題：(1) 大量選取（如 8000 筆 lot_id）時效能極差，複雜度為 O(n × m)；(2) 結果不準確，例如選取 `A123` 會同時命中 `A1234`、`XA123` 等非預期資料。模糊搜尋的設計意圖僅用於下拉清單內的即時搜尋（UI 層），一旦使用者確認選取，傳入後端的值皆為完整精確值，應改用精確比對。

## What Changes

- **Backend `_contains_any_mask()`**：新增精確比對路徑，對 `LOTID` 與 `WORKORDER` 欄位改用 `isin()` 或預建 hash index，取代逐值 `str.contains()` 迴圈。
- **Snapshot index**：在 `_build_wip_snapshot()` 中為 `LOTID` 與 `WORKORDER` 建立預建精確 index（同 `package`、`workcenter` 等欄位現有做法）。
- **`_select_with_snapshot_indexes()`**：`lotid` 與 `workorder` 改走 `_lookup_positions()` 精確路徑，不再呼叫 `_contains_any_mask()`。
- **Hold Overview 路徑**：確認 `get_hold_detail_lots()` 透過同一 `_select_with_snapshot_indexes()` 取得相同修正，無需額外改動。
- **Hold Detail**：目前不接受 `lotid`/`workorder` 篩選，本次不異動。
- **前端無需改動**：前端已正確傳送精確選取值（comma-separated string），API 參數格式維持不變。

## Capabilities

### New Capabilities
- `lotid-workorder-exact-filter`：為 `LOTID` 與 `WORKORDER` 建立 snapshot index，使篩選從 O(n×m) 模糊掃描降為 O(1) index 查找，同時消除子字串誤命中問題。

### Modified Capabilities
- `wip-overview-page`：lotid / workorder 篩選行為由模糊改為精確（影響 Summary、Matrix API 回傳結果）。
- `wip-detail-page`：lotid / workorder 篩選行為由模糊改為精確。
- `hold-overview-page`：lotid / workorder 篩選行為由模糊改為精確（透過共用 `_select_with_snapshot_indexes()` 自動取得修正）。
- `hold-overview-api`：更新 API 文件，將 `lotid`/`workorder` 備註從 `fuzzy match` 改為 `exact match`。
- `cache-indexed-query-acceleration`：新增 `LOTID`、`WORKORDER` 兩個欄位至 snapshot index 清單。

## Impact

- **主要修改檔案**：
  - `src/mes_dashboard/services/wip_service.py`（`_build_wip_snapshot`、`_select_with_snapshot_indexes`、`_contains_any_mask` 相關段落）
  - `src/mes_dashboard/routes/wip_routes.py`（更新 docstring）
  - `src/mes_dashboard/routes/hold_overview_routes.py`（更新 docstring）
- **影響 API**：`/api/wip/overview/summary`、`/api/wip/overview/matrix`、`/api/wip/detail/<workcenter>`、`/api/hold/overview/lots`（所有接受 `lotid` 或 `workorder` 的端點）
- **行為變更**：篩選結果更嚴格（精確命中），先前因子字串誤命中而出現的額外資料將消失。這屬於 bug fix，不視為 breaking change。
- **效能預期**：8000 筆 lotid 篩選從數秒降至毫秒級（同 `package`、`workcenter` 等已索引欄位的現有表現）。
- **無影響**：前端、Hold Detail、Redis 快取格式、API 參數格式皆不異動。
