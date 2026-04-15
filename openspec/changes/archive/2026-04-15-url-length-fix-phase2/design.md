## Context

Gunicorn 預設 `--limit-request-line 4094`。當 GET query string 超過此限制，Gunicorn 直接回 400（或在某些版本回 414），請求甚至不會到達 Flask。

第一階段（commit a5dae78）已修正 WIP 相關端點（`/overview/summary`、`/overview/matrix`、`/detail/<workcenter>`、`/meta/filter-options`）採用 POST + JSON body 模式，並在前端改用 `apiPost`。本設計文件針對第二階段：Hold Overview、`/api/wip/overview/hold`、Reject History spool-view 端點，以及全域 body size 限制。

**現行狀態**

- `wip_routes.py` 已有 `_get_wip_args()` helper（method 判斷一次取 JSON body 或 `request.args`）
- `hold_overview_routes.py` 的 parsing helpers（`_parse_reason_list`、`_parse_hold_type`）直接讀 `request.args`，無法在 POST 路徑複用
- `reject_history_routes.py` 的 `_parse_multi_param`、`_parse_common_bools` 等同樣直接讀 `request.args`，但影響範圍更廣（約 13+ 個端點呼叫）

## Goals / Non-Goals

**Goals:**
- 補齊三組受影響後端端點（`/api/wip/overview/hold`、hold-overview × 4、reject-history `/batch-pareto` `/view`）支援 POST + JSON body
- 不破壞 GET 路徑，既有 curl / 整合測試繼續有效
- 重構 parsing helpers 時不改動其他端點的行為
- 前端對應端點改用 `apiPost`
- 全域加入 `MAX_CONTENT_LENGTH` 防禦

**Non-Goals:**
- 不遷移 reject-history legacy GET 端點（`/options`、`/summary`、`/trend`、`/analytics` 等），前端已遷移至 spool 架構不再直接呼叫
- 不遷移 yield-alert endpoints（前端僅呼叫 POST `/query` + GET `/view` with `query_id`，主要過濾器非問題路徑）
- 不更改 Gunicorn 設定（`--limit-request-line` 調高是緩兵之計，不治本）

## Decisions

### D1：Parsing helper 重構策略 — `args=None` 選用參數

**選擇**：擴充現有 helper 簽名加入 `args=None`，預設 `None` 時退回讀 `request.args`，讓呼叫端傳入 `_get_request_args()` 的結果。

**為何不建新 helper 或改名**：13+ 個呼叫點不動、不造成 diff noise、保留原函數可作為 GET fallback 的語意。

**為何不把所有端點一起改**：本次目標是修 URL 長度問題，其他 GET 端點（`/list`、`/export`）在前端不傳大量值、且有 spool 架構隔開，風險不高；擴大範圍會增加測試負擔與 regression 機率。

**替代方案**：在每個 route 函數頂部 inline 所有參數解析，不依賴共用 helper。缺點：程式碼重複，且未來若新增參數需在多處同步修改。

### D2：POST body 支援 list 型別（`_parse_multi_param` 行為擴充）

**選擇**：`_parse_multi_param` 當 `source` 為 `dict`（POST JSON body）時，若值為 Python list 則直接展開；若為字串則仍走 CSV split；兩路後統一去重。

**為何這樣做**：前端 `apiPost` 可直接傳陣列（`packages: ["A","B"]`），不需強迫 CSV 化，可減少序列化/反序列化開銷，也使 POST body 更易閱讀。GET 路徑仍走 `MultiDict.getlist()` 支援重複 key（`?a=A&a=B`），向下相容。

### D3：Hold Overview 端點的 `_parse_hold_type` 回傳 tuple 不變

`_parse_hold_type` 回傳 `(hold_type, error)` tuple，路由函數做 `if error: return error`。重構時保持此 shape，只讓函數從 `args` 或 `request.args` 讀取，不動 error handling 邏輯。

### D4：`MAX_CONTENT_LENGTH` 預設 2 MB，可 env 覆寫

選 2 MB 而非更小（如 256 KB）的理由：未來若有 bulk import 或 AI query 的大請求，不想頻繁調整。2 MB 對任何合理的篩選 JSON 而言綽綽有餘（60 lotid × 30 bytes ≈ 1.8 KB），且 Flask 內建的 413 response 對前端而言是明確可處理的錯誤。env `MAX_REQUEST_BODY_MB` 允許各部署環境調整。

### D5：`reject-history/export-cached` 本次不動

`export-cached` 由前端用 `window.fetch()` 直接呼叫（非 `apiPost`），且攜帶的篩選參數與 `view` 幾乎相同。本次不動的理由：改動 `window.fetch` 呼叫需要額外處理 CSRF header，且該端點產生 CSV 回應（非 JSON），`apiPost` 不適用。可留作獨立 task。

## Risks / Trade-offs

- **`_parse_multi_param` 行為改變影響 GET path**：`isinstance(source, dict)` 判斷在 GET 時不會觸發（`request.args` 是 `MultiDict`），風險極低，但需測試 GET + CSV format 的 regression。

- **`bool` 參數在 POST body 為原生 bool（非字串）**：Python `json.loads` 會還原 `true/false` 為 `bool`，而既有程式用 `str(...).lower() == 'true'` 比較。`bool` 本身的 `str()` 是 `'True'`（大寫 T）。需在 parsing 函數中增加 `isinstance(raw, bool)` 判斷，否則 `exclude_material_scrap: false` 會被誤判為 `True`。這是本次改動最容易出錯的點，需要測試覆蓋。

- **`_parse_pareto_selection` 的錯誤回傳 shape**：目前回傳 `(error_tuple, dim, values)`，路由用 `pareto_error[0].get(...)` 取 message。改造時若不小心改動 tuple shape 會讓既有路由靜默出錯。需逐行確認不改 shape。

- **前端 `buildBatchParetoParams()` 目前回傳 array 作為參數值**（`params.packages = [...]`）：`apiGet` 會把 array 序列化為 `packages[]=A&packages[]=B`（因 axios 的 `paramsSerializer`）。改成 `apiPost` 後直接傳 JSON array，後端新的 `_parse_multi_param` 需正確處理 `list` 型別。需確認現有測試不依賴 `packages[]` 的 query string 格式。

## Migration Plan

1. 後端先部署（routes + app.py），支援 GET + POST 雙模式
2. 後端測試通過後前端部署，切換為 `apiPost`
3. 無需資料遷移或 feature flag，雙模式在過渡期即可共存
4. 回滾：前端若有問題，只需 revert App.vue 的 `apiGet` → `apiPost` 改動，後端保持雙模式可繼續服務

## Open Questions

- `reject-history/export-cached` 是否也需本次修正（前端用 `window.fetch` 呼叫，需另外處理 CSRF + Content-Type）？本次列 pending，視生產回報決定優先序。
