## Why

`unified-lineage-engine` 完成後，後端追溯管線從 30-120 秒降至 3-8 秒，但對於大範圍查詢（日期跨度長、LOT 數量多）仍可能需要 5-15 秒。目前的 UX 模式是「使用者點擊查詢 → 等待黑盒 → 全部結果一次出現」，即使後端已加速，使用者仍感受不到進度，只有一個 loading spinner。

兩個頁面的前端載入模式存在差異：
- **mid-section-defect**: 一次 API call (`/analysis`) 拿全部結果（KPI + charts + detail），後端做完全部 4 個 stage 才回傳。
- **query-tool**: Vue 3 版本（`frontend/src/query-tool/`）已有手動順序（resolve → history → association），但部分流程仍可改善漸進載入體驗。

需要統一兩個頁面的前端查詢體驗，實現「分段載入 + 進度可見」的 UX 模式，讓使用者看到追溯的漸進結果而非等待黑盒。

**邊界聲明**：本變更負責新增分段 API endpoints（`/api/trace/*`）和前端漸進式載入 UX。後端追溯核心邏輯（`LineageEngine`、`EventFetcher`）由前置的 `unified-lineage-engine` 變更提供，本變更僅作為 API routing layer 呼叫這些模組。

## What Changes

### 後端：新增分段 API endpoints

新增 `trace_routes.py` Blueprint（`/api/trace/`），將追溯管線的每個 stage 獨立暴露為 endpoint。通過 `profile` 參數區分頁面行為：

**POST `/api/trace/seed-resolve`**
- Request: `{ "profile": "query_tool" | "mid_section_defect", "params": { ... } }`
  - `query_tool` params: `{ "resolve_type": "lot_id" | "serial_number" | "work_order", "values": [...] }`
  - `mid_section_defect` params: `{ "date_range": [...], "workcenter": "...", ... }` (TMTT detection 參數)
- Response: `{ "stage": "seed-resolve", "seeds": [{ "container_id": "...", "container_name": "...", "lot_id": "..." }], "seed_count": N, "cache_key": "trace:{hash}" }`
- Error: `{ "error": "...", "code": "SEED_RESOLVE_EMPTY" | "SEED_RESOLVE_TIMEOUT" | "INVALID_PROFILE" }`
- Rate limit: `configured_rate_limit(bucket="trace-seed", default_max_attempts=10, default_window_seconds=60)`
- Cache: L2 Redis, key = `trace:seed:{profile}:{params_hash}`, TTL = 300s

**POST `/api/trace/lineage`**
- Request: `{ "profile": "query_tool" | "mid_section_defect", "container_ids": [...], "cache_key": "trace:{hash}" }`
- Response: `{ "stage": "lineage", "ancestors": { "{cid}": ["{ancestor_cid}", ...] }, "merges": { "{cid}": ["{merge_source_cid}", ...] }, "total_nodes": N }`
- Error: `{ "error": "...", "code": "LINEAGE_TIMEOUT" | "LINEAGE_TOO_LARGE" }`
- Rate limit: `configured_rate_limit(bucket="trace-lineage", default_max_attempts=10, default_window_seconds=60)`
- Cache: L2 Redis, key = `trace:lineage:{sorted_cids_hash}`, TTL = 300s
- 冪等性: 相同 `container_ids` 集合（排序後 hash）回傳 cache 結果

**POST `/api/trace/events`**
- Request: `{ "profile": "query_tool" | "mid_section_defect", "container_ids": [...], "domains": ["history", "materials", ...], "cache_key": "trace:{hash}" }`
  - `mid_section_defect` 額外支援 `"domains": ["upstream_history"]` 和自動串接 aggregation
- Response: `{ "stage": "events", "results": { "{domain}": { "data": [...], "count": N } }, "aggregation": { ... } | null }`
- Error: `{ "error": "...", "code": "EVENTS_TIMEOUT" | "EVENTS_PARTIAL_FAILURE" }`
  - `EVENTS_PARTIAL_FAILURE`: 部分 domain 查詢失敗時仍回傳已成功的結果，`failed_domains` 列出失敗項
- Rate limit: `configured_rate_limit(bucket="trace-events", default_max_attempts=15, default_window_seconds=60)`
- Cache: L2 Redis, key = `trace:evt:{profile}:{domains_hash}:{sorted_cids_hash}`, TTL = 300s

**所有 endpoints 共通規則**:
- HTTP status: 200 (success), 400 (invalid params/profile), 429 (rate limited), 504 (stage timeout >10s)
- Rate limit headers: `Retry-After`（對齊 `rate_limit.py` 既有實作，回應 body 含 `retry_after_seconds` 欄位）
- `cache_key` 為選填欄位，前端可傳入前一 stage 回傳的 cache_key 作為追溯鏈標識（用於 logging correlation），不影響 cache 命中邏輯
- 每個 stage 獨立可呼叫——前端可按需組合，不要求嚴格順序（但 lineage 需要 seed 結果的 container_ids，events 需要 lineage 結果的 container_ids）

### 舊 endpoint 兼容

- `/api/mid-section-defect/analysis` 保留，內部改為呼叫分段管線（seed-resolve → lineage → events+aggregation）後合併結果回傳。行為等價，API contract 不變。
- `/api/query-tool/*` 保留不變，前端可視進度逐步遷移到新 API。

### 前端：漸進式載入

- 新增 `frontend/src/shared-composables/useTraceProgress.js` composable，封裝：
  - 三段式 sequential fetch（seed → lineage → events）
  - 每段完成後更新 reactive state（`current_stage`, `completed_stages`, `stage_results`）
  - 錯誤處理: 每段獨立，某段失敗不阻斷已完成的結果顯示
  - profile 參數注入
- **mid-section-defect** (`App.vue`): 查詢流程改為分段 fetch + 漸進渲染：
  - 查詢後先顯示 seed lots 列表（skeleton UI → 填入 seed 結果）
  - 血緣樹結構逐步展開
  - KPI/圖表以 skeleton placeholders + fade-in 動畫漸進填入，避免 layout shift
  - 明細表格仍使用 detail endpoint 分頁
- **query-tool** (`useQueryToolData.js`): lineage tab 改為 on-demand 展開（使用者點擊 lot 後才查血緣），主要強化漸進載入體驗。
- 兩個頁面新增進度指示器元件，顯示目前正在執行的 stage（seed → lineage → events → aggregation）和已完成的 stage。

### Legacy 檔案處理

- **廢棄**: `src/mes_dashboard/static/js/query-tool.js`（3056L, 126KB）——這是 pre-Vite 時代的靜態 JS 檔案，目前已無任何 template 載入（`query_tool.html` 使用 `frontend_asset('query-tool.js')` 載入 Vite 建置產物，非此靜態檔案）。此檔案為 dead code，可安全刪除。
- **保留**: `frontend/src/query-tool/main.js`（3139L）——這是 Vue 3 版本的 Vite entry point，Vite config 確認為 `'query-tool': resolve(__dirname, 'src/query-tool/main.js')`。此檔案持續維護。
- **保留**: `src/mes_dashboard/templates/query_tool.html`——Jinja2 模板，line 1264 `{% set query_tool_js = frontend_asset('query-tool.js') %}` 載入 Vite 建置產物。目前 portal-shell route 已生效（`/portal-shell/query-tool` 走 Vue 3），此模板為 non-portal-shell 路由的 fallback，暫不刪除。

## Capabilities

### New Capabilities

- `trace-staged-api`: 統一的分段追溯 API 層（`/api/trace/seed-resolve`、`/api/trace/lineage`、`/api/trace/events`）。通過 `profile` 參數配置頁面行為。每段獨立可 cache（L2 Redis）、可 rate limit（`configured_rate_limit()`），前端可按需組合。API contract 定義於本提案 What Changes 章節。
- `progressive-trace-ux`: 兩個頁面的漸進式載入 UX。`useTraceProgress` composable 封裝三段式 sequential fetch + reactive state。包含：
  - 進度指示器元件（顯示 seed → lineage → events → aggregation 各階段狀態）
  - mid-section-defect: seed lots 先出 → 血緣結構 → KPI/圖表漸進填入（skeleton + fade-in）
  - query-tool: lineage tab 改為 on-demand 展開（使用者點擊 lot 後才查血緣）

### Modified Capabilities

- `trace-staged-api` 取代 mid-section-defect 現有的單一 `/analysis` endpoint 邏輯（保留舊 endpoint 作為兼容，內部改為呼叫分段管線 + 合併結果，行為等價）。
- query-tool 現有的 `useQueryToolData.js` composable 改為使用分段 API。

## Impact

- **Affected code**:
  - 新建: `src/mes_dashboard/routes/trace_routes.py`, `frontend/src/shared-composables/useTraceProgress.js`
  - 重構: `frontend/src/mid-section-defect/App.vue`（查詢流程改為分段 fetch）
  - 重構: `frontend/src/query-tool/composables/useQueryToolData.js`（lineage 改分段）
  - 修改: `src/mes_dashboard/routes/mid_section_defect_routes.py`（`/analysis` 內部改用分段管線）
  - 刪除: `src/mes_dashboard/static/js/query-tool.js`（pre-Vite dead code, 3056L, 126KB, 無任何引用）
- **Runtime/deploy**: 無新依賴。新增 3 個 API endpoints（`/api/trace/*`），原有 endpoints 保持兼容。
- **APIs/pages**: 新增 `/api/trace/seed-resolve`、`/api/trace/lineage`、`/api/trace/events` 三個 endpoints（contract 定義見 What Changes 章節）。原有 `/api/mid-section-defect/analysis` 和 `/api/query-tool/*` 保持兼容但 `/analysis` 內部實作改為呼叫分段管線。
- **UX**: 查詢體驗從「黑盒等待」變為「漸進可見」。mid-section-defect 使用者可在血緣解析階段就看到 seed lots 和初步資料。

## Verification

**前端漸進載入驗收**:

| 指標 | 現況 | 目標 | 條件 |
|------|------|------|------|
| mid-section-defect 首次可見內容 (seed lots) | 全部完成後一次顯示（30-120s, unified-lineage-engine 後 3-8s） | seed stage 完成即顯示（≤3s） | ≥10 seed lots 查詢 |
| mid-section-defect KPI/chart 完整顯示 | 同上 | lineage + events 完成後顯示（≤8s） | skeleton → fade-in, 無 layout shift |
| query-tool lineage tab | 一次載入全部 lot 的 lineage | 點擊單一 lot 後載入該 lot lineage（≤3s） | on-demand, ≥20 lots resolved |
| 進度指示器 | 無（loading spinner） | 每個 stage 切換時更新進度文字 | seed → lineage → events 三階段可見 |

**API contract 驗收**:
- 每個 `/api/trace/*` endpoint 回傳 JSON 結構符合 What Changes 章節定義的 schema
- 400 (invalid params) / 429 (rate limited) / 504 (timeout) status code 正確回傳
- Rate limit header `Retry-After` 存在（對齊既有 `rate_limit.py` 實作）
- `/api/mid-section-defect/analysis` 兼容性: 回傳結果與重構前完全一致（golden test 比對）

**Legacy cleanup 驗收**:
- `src/mes_dashboard/static/js/query-tool.js` 已刪除
- grep 確認無任何程式碼引用 `static/js/query-tool.js`
- `query_tool.html` 中 `frontend_asset('query-tool.js')` 仍正常解析到 Vite 建置產物

## Dependencies

- **前置條件**: `unified-lineage-engine` 變更必須先完成。本變更依賴 `LineageEngine` 和 `EventFetcher` 作為分段 API 的後端實作。

## Non-Goals

- 不實作 SSE (Server-Sent Events) 或 WebSocket 即時推送——考慮到 gunicorn sync workers 的限制，使用分段 API + 前端 sequential fetch 模式。
- 不改動後端追溯邏輯——分段 API 純粹是將 `LineageEngine` / `EventFetcher` 各 stage 獨立暴露為 HTTP endpoint，不改變計算邏輯。
- 不新增任務隊列（Celery/RQ）——維持同步 request-response 模式，各 stage 控制在 <10s 回應時間內。
- 不改動 mid-section-defect 的 defect attribution 演算法。
- 不改動 query-tool 的 equipment-period 查詢（已有 `read_sql_df_slow` 120s timeout 處理）。
- 不改動 DB schema、不建立 materialized view——所有最佳化在應用層完成。

## Risks

| 風險 | 緩解 |
|------|------|
| 分段 API 增加前端複雜度（多次 fetch + 狀態管理） | 封裝為 `useTraceProgress` composable，頁面只需提供 profile + params，內部處理 sequential fetch + error + state |
| 前後端分段 contract 不匹配 | API contract 完整定義於本提案 What Changes 章節，含 request/response schema、error codes、cache key 格式。CI 契約測試驗證 |
| 舊 `/analysis` endpoint 需保持兼容 | 保留舊 endpoint，內部改為呼叫分段管線 + 合併結果。golden test 比對重構前後輸出一致 |
| 刪除 `static/js/query-tool.js` 影響功能 | 已確認此檔案為 pre-Vite dead code：`query_tool.html` 使用 `frontend_asset('query-tool.js')` 載入 Vite 建置產物，非此靜態檔案。grep 確認無其他引用 |
| mid-section-defect 分段渲染導致 chart 閃爍 | 使用 skeleton placeholders + fade-in 動畫，避免 layout shift。chart container 預留固定高度 |
| `cache_key` 被濫用於跨 stage 繞過 rate limit | cache_key 僅用於 logging correlation，不影響 cache 命中或 rate limit 邏輯。每個 stage 獨立計算 cache key |
