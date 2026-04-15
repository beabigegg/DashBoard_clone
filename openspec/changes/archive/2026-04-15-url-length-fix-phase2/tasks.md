## 1. 全域防護

- [x] 1.1 `src/mes_dashboard/app.py`：在 `create_app()` config 區段加入 `MAX_CONTENT_LENGTH`（預設 2 MB，可透過 `MAX_REQUEST_BODY_MB` env 覆寫）

## 2. 後端 — wip_routes.py

- [x] 2.1 `src/mes_dashboard/routes/wip_routes.py`：將 `/overview/hold` route decorator 改為 `methods=['GET', 'POST']`
- [x] 2.2 同檔：將 `api_overview_hold` 函數體的所有 `request.args.get(...)` 改為使用現有 `_get_wip_args()` 的 `args.get(...)`
- [x] 2.3 同檔：更新 `api_overview_hold` docstring 說明 POST 支援

## 3. 後端 — hold_overview_routes.py

- [x] 3.1 `src/mes_dashboard/routes/hold_overview_routes.py`：新增 `_get_request_args()` helper（POST 讀 JSON body，GET 讀 `request.args`）
- [x] 3.2 同檔：新增 `_coerce_int(value, default)` helper（用於 POST body 中的 page/per_page 型別轉換）
- [x] 3.3 同檔：重構 `_parse_reason_list()` — 加入 `args=None` 參數，支援 list 型別（POST JSON array）與 CSV 字串（GET），預設退回 `request.args`
- [x] 3.4 同檔：重構 `_parse_hold_type()` — 加入 `args=None` 參數，從 `args` 或 `request.args` 讀取
- [x] 3.5 同檔：`/api/hold-overview/summary` 改為 `methods=['GET', 'POST']`，函數體改用 `_get_request_args()`
- [x] 3.6 同檔：`/api/hold-overview/matrix` 改為 `methods=['GET', 'POST']`，函數體改用 `_get_request_args()`
- [x] 3.7 同檔：`/api/hold-overview/treemap` 改為 `methods=['GET', 'POST']`，函數體改用 `_get_request_args()`
- [x] 3.8 同檔：`/api/hold-overview/lots` 改為 `methods=['GET', 'POST']`，函數體改用 `_get_request_args()` + `_coerce_int()` 處理 page/per_page

## 4. 後端 — reject_history_routes.py

- [x] 4.1 `src/mes_dashboard/routes/reject_history_routes.py`：新增 `_get_request_args()` helper
- [x] 4.2 同檔：重構 `_parse_multi_param(name, args=None)` — 加入 `args` 參數；當 `source` 為 `dict` 時支援 list 型別、scalar、CSV 字串；保留 GET 路徑的 `MultiDict.getlist()` 行為
- [x] 4.3 同檔：重構 `_parse_common_bools(args=None)` — 加入 `args` 參數，處理 POST body 中 Python native `bool` 型別（`isinstance(raw, bool)` 判斷，避免 `str(False) == 'True'` 的陷阱）
- [x] 4.4 同檔：重構 `_parse_pareto_selection(args=None)` — 加入 `args` 參數，內部呼叫 `_parse_multi_param("pareto_values", args)`
- [x] 4.5 同檔：重構 `_parse_multi_pareto_selections(args=None)` — 加入 `args` 參數，內部所有 `_parse_multi_param` 呼叫加入 `args`
- [x] 4.6 同檔：`/api/reject-history/batch-pareto` 改為 `methods=['GET', 'POST']`；函數體加入 `args = _get_request_args()`；所有 `_parse_multi_param(...)` 呼叫加上 `args`；`query_id`、`metric_mode` 改從 `args.get(...)` 讀取；`_parse_common_bools(args)` 傳入 args
- [x] 4.7 同檔：`/api/reject-history/view` 改為 `methods=['GET', 'POST']`；函數體加入 `args = _get_request_args()`；`query_id`、`page`、`per_page`、`metric_filter`、`detail_reason`、bool 參數改從 `args.get(...)` 讀取（page/per_page 用 `_coerce_int` 或等效的 try/except）；所有 `_parse_multi_param(...)` 呼叫加上 `args`

## 5. 前端 — hold-overview/App.vue

- [x] 5.1 `frontend/src/hold-overview/App.vue`：import 加入 `apiPost`
- [x] 5.2 同檔：`fetchSummary()` 改為 `apiPost('/api/hold-overview/summary', buildAllFilterParams(), { timeout, signal })`
- [x] 5.3 同檔：`fetchMatrix()` 改為 `apiPost('/api/hold-overview/matrix', buildAllFilterParams(), { timeout, signal })`
- [x] 5.4 同檔：`fetchHold()` 改為 `apiPost('/api/wip/overview/hold', { ...buildAllFilterParams(), ...extraParams }, { timeout, signal })`
- [x] 5.5 同檔：`fetchLots()` 改為 `apiPost('/api/hold-overview/lots', buildLotsParams(), { timeout, signal })`

## 6. 前端 — reject-history/App.vue

- [x] 6.1 `frontend/src/reject-history/App.vue`：`fetchBatchPareto()` 改為 `apiPost('/api/reject-history/batch-pareto', buildBatchParetoParams(), { timeout })`
- [x] 6.2 同檔：`refreshView()` line 642 改為 `apiPost('/api/reject-history/view', params, { timeout })`
- [x] 6.3 同檔：`refreshDetailPage()` line 752 改為 `apiPost('/api/reject-history/view', params, { timeout })`

## 7. 測試

- [x] 7.1 `tests/test_wip_hold_pages_integration.py`：新增 `test_wip_hold_post_avoids_url_length_limit`（60 個 lotid via POST，mock `get_wip_hold_summary`，斷言 200 + service 收到正確 lotid）
- [x] 7.2 同檔：新增 `test_hold_overview_endpoints_accept_post`（四個端點各 POST 含大量 lotid + reason array，mock service，斷言 200 + 正確參數）
- [x] 7.3 同檔：新增 `test_hold_overview_reason_list_coercion`（reason 為 CSV 字串 GET 與 array POST 兩種格式，斷言 service 收到相同的 list）
- [x] 7.4 同檔：新增 `test_hold_overview_lots_post_pagination`（POST body 含 `page: 2, per_page: 80`，斷言 service 收到 int 2 和 80）
- [x] 7.5 新建 `tests/test_reject_history_post_contract.py`：`test_reject_batch_pareto_accepts_post`（mock `compute_batch_pareto`，POST 含大量 reasons + trend_dates，斷言 200 + service 收到 list）
- [x] 7.6 同檔：`test_reject_view_accepts_post`（mock `apply_view`，POST 含 query_id + packages + reasons + page/per_page，斷言 200 + int 型別正確）
- [x] 7.7 同檔：`test_reject_view_native_bool_post`（POST body `exclude_material_scrap: false`，斷言 service 收到 `False` 而非 `True`）
- [x] 7.8 同檔：`test_reject_batch_pareto_get_still_works`（GET with CSV 格式，斷言 200，確保向下相容）
- [x] 7.9 `tests/test_wip_hold_pages_integration.py`：新增 `test_max_content_length_rejects_oversized_body`（送 3 MB payload，斷言 413）

## 8. 合約文件同步

- [x] 8.1 `contract/api_inventory.md`：更新 `wip_routes.py` 行，加入 `/api/wip/overview/hold` 到 POST 支援列表
- [x] 8.2 同檔：更新 `hold_overview_routes.py` 行，加入 POST 支援說明（含 reason 可為 CSV 或 JSON array）
- [x] 8.3 同檔：更新 `reject_history_routes.py` 行，加入 `/batch-pareto` 與 `/view` 的 POST 支援說明
