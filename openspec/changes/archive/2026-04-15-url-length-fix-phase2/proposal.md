## Why

多選篩選條件透過 GET query string 傳送時，超過 Gunicorn 4094 bytes 的 request-line 限制，導致生產環境 414 錯誤。commit a5dae78 已修正 WIP Overview 相關端點，但同類問題仍存在於 Hold Overview、Reject History 的 spool-view 端點，以及 Flask 全域缺乏 body size 上限。

## What Changes

- `/api/wip/overview/hold` 加入 POST 支援（原 GET-only，但同 module 的 helper `_get_wip_args()` 已存在可直接復用）
- `/api/hold-overview/summary`、`/matrix`、`/treemap`、`/lots` 四個端點加入 POST 支援
- `/api/reject-history/batch-pareto`、`/view` 加入 POST 支援（這兩個端點以 `query_id` 為主鍵，但仍在 query string 傳送 `reasons`、`workcenter_groups`、`trend_dates` 等次要過濾器）
- `hold_overview_routes.py` 的 `_parse_reason_list()`、`_parse_hold_type()` 重構為接受 `args` 參數以支援 POST body
- `reject_history_routes.py` 的 `_parse_multi_param()`、`_parse_common_bools()`、`_parse_pareto_selection()`、`_parse_multi_pareto_selections()` 重構為接受可選 `args` 參數（未受影響的其他端點沿用 `args=None` 預設值，向下相容）
- 前端 `hold-overview/App.vue` 四個 fetch 函數從 `apiGet` 改為 `apiPost`
- 前端 `reject-history/App.vue` 的 `fetchBatchPareto`、`refreshView` 從 `apiGet` 改為 `apiPost`
- Flask app factory 加入 `MAX_CONTENT_LENGTH = 2 MB`（可透過 env 覆寫）
- `contract/api_inventory.md` 同步更新三個 blueprint 的端點描述

## Capabilities

### New Capabilities

（無）

### Modified Capabilities

- `hold-overview-api`：`/summary`、`/matrix`、`/treemap`、`/lots` 新增接受 POST + JSON body，`reason` 可為 CSV 字串或 JSON array
- `reject-history-api`：`/batch-pareto`、`/view` 新增接受 POST + JSON body，multi-value params 可為 JSON array
- `api-safety-hygiene`：Flask 全域加入 `MAX_CONTENT_LENGTH` 限制（現行缺漏）

## Impact

**後端**
- `src/mes_dashboard/routes/wip_routes.py` — 1 個 route 變更
- `src/mes_dashboard/routes/hold_overview_routes.py` — 新增 2 個 private helpers、4 個 route 變更
- `src/mes_dashboard/routes/reject_history_routes.py` — 重構 4 個 parsing helpers（簽名擴充）、2 個 route 變更
- `src/mes_dashboard/app.py` — 1 行 config 新增

**前端**
- `frontend/src/hold-overview/App.vue` — 4 個 fetch 函數改用 `apiPost`
- `frontend/src/reject-history/App.vue` — 2 個 fetch 函數改用 `apiPost`

**測試**
- `tests/test_wip_hold_pages_integration.py` — 追加 hold 端點大 payload POST 測試
- `tests/test_reject_history_post_contract.py`（新建）— batch-pareto/view POST 合約測試
- 全域 413 threshold 測試

**合約文件**
- `contract/api_inventory.md` — 三個 blueprint 說明更新
