## Why

現有 155 個 pytest + 33 個 node:test + 27 個 in-process E2E 看似數量充足，但實際對「資料端點回傳格式邊界」、「Oracle/Redis/DuckDB spool 跨 worker 傳遞」、「長時間開頁/客戶端中斷/併發鎖」等生產關鍵情境覆蓋嚴重不足。前端 `unwrapApiResult` 在 10 個 App.vue 重複定義、無任何 runtime schema 驗證、`Number(payload?.pagination?.page)` 有 NaN 風險、spool URL 未檢 Content-Type；任何後端回傳 shape 的微小漂移都會靜默破壞 UI。我們需要系統化補齊缺口，並在前端加上輕量 runtime 守門，避免線上使用者遇到未預期的空白畫面或查詢失敗。

## What Changes

- **後端合約 runtime sweep**：擴充 `test_api_contract.py` 實際呼叫所有已註冊路由驗證 envelope shape，配合 `route_contract_matrix.py` 強制新增路由同步登記。
- **端點邊界測試**：系統化補齊空資料、型別/精度漂移、超長區間、複雜 JOIN timeout、Unicode、極端 pagination、時區、thundering herd 等情境於 hold-overview / reject-history / production-history / yield-alert / material-trace / resource-history / ai-query / analytics 端點。
- **分散式與生命週期測試**：新增 RQ orphan 清理、worker crash reconciliation、Oracle 連線洩漏偵測、分散式 Redis lock 正確性、跨 worker 結果傳遞、spool 原子 rename、長開頁面 session 過期與 schema 版本漂移測試。
- **前端測試框架遷移**：由 `node:test` 升級為 Vitest + @vue/test-utils + jsdom，解鎖 `.vue` 元件測試。
- **前端 runtime 守門** (NEW)：新增 `core/schema-guard.js` 手寫 `assertShape` + `core/endpoint-schemas.js` + `core/dev-warnings.js`，對 hold-overview / reject-history / production-history / material-trace / anomaly-summary 五個高風險端點作 DEV 警告。
- **前端結構修正**：抽出 `core/unwrap-api-result.js` 共用模組 (10 個 App.vue 重複)、`core/api.js` 新增 per-endpoint in-flight dedup、預設 fetch timeout、envelope `meta.app_version` 版本漂移橫幅、`core/pending-jobs-registry.js` 追蹤關頁前未完成 async job。
- **前端使用者約束**：DateRangePicker 超限區間禁用 + tooltip、ActionButton double-click lock、LoadingOverlay 長等待顯示 cancel 按鈕。
- **後端小幅異動**：envelope `meta` 加入 `app_version`；新增 `POST /api/job/<id>/abandon`；`QUERY_SPOOL_DIR` 啟動時驗證共用 volume (Docker 佈署熱點)；analytics anomaly-summary cache miss 加 `meta.cache_state='cold'` 讓客戶端可辨識空狀態。
- **Playwright 真實瀏覽器 E2E**：hold-overview / reject-history / query-tool 三個高價值流程，重用 `~/.cache/ms-playwright` 共用瀏覽器。
- **OpenSpec 合約測試**：從 5 個關鍵 spec (api-response-contract-unification、anomaly-summary-api、cache-plane-architecture、async-query-job-service、api-safety-hygiene) 自動驗證 runtime 合約。

## Capabilities

### New Capabilities
- `frontend-runtime-schema-guard`: 前端 runtime 回傳格式 assertion 層與 DEV 警告系統，含 `schema-guard.js`、`endpoint-schemas.js`、`dev-warnings.js`、`unwrap-api-result.js` 共用模組、`app-version-check.js`、`pending-jobs-registry.js` 與 `api.js` 的 in-flight dedup/fetch timeout/version hook。
- `cross-worker-result-integrity`: 多 gunicorn/RQ worker 間查詢結果傳遞、分散式 Redis lock、spool 原子 rename、`_ProcessLevelCache` 使用邊界、`QUERY_SPOOL_DIR` 共用 volume 驗證的不變量。
- `long-running-client-lifecycle`: 長時間開啟頁面、瀏覽器/電腦關閉、RQ worker 崩潰、Oracle 連線洩漏、session 過期輪詢、dataset 版本漂移的端到端生命週期行為。

### Modified Capabilities
- `backend-unit-test-coverage`: 新增 analytics_routes、trace_lineage_job_service、msd_duckdb_runtime、query_tool_sql_runtime、user_auth_routes、filter_cache (generic)、OEE 浮點精度、datetime 正規化的單元測試；envelope runtime sweep 擴充。
- `backend-integration-test-coverage`: 新增 Oracle pool exhaustion、cache lifecycle、spool lifecycle、async job timeout、RQ orphan cleanup、worker crash recovery、Oracle 連線洩漏、rate limit、distributed lock、cross-worker sharing、sync_worker deadlock 回歸、circuit breaker integration、heavy join、thundering herd 的整合測試。
- `frontend-test-coverage`: 從 node:test 遷移到 Vitest + @vue/test-utils + jsdom；新增高風險元件測試 (DataTable、LoadingOverlay、FilterPanel、HoldMatrix、ParetoGrid、DateRangePicker、ActionButton)、AbortController 回歸、per-composable validation sweep、shared-composable 生命週期測試。
- `e2e-test-coverage`: 新增 Playwright 真實瀏覽器 E2E 三個高價值流程並與既有 in-process e2e 並存。
- `api-response-contract-unification`: envelope `meta` 新增 `app_version` 欄位；anomaly-summary cache miss 必須有 `meta.cache_state` 讓客戶端可辨識空狀態；所有路由必須可被 runtime sweep 自動驗證。
- `field-contract-governance`: 數字型別 (Decimal/float/str) 於 service 層統一為 float、TIMESTAMP 統一為 ISO-8601 UTC 字串、OEE/yield rate 固定 4 位小數、envelope 欄位 drift 由 route_contract_matrix 自動偵測。

## Impact

- **後端程式碼**：`src/mes_dashboard/core/response.py` (meta.app_version)、`routes/job_routes.py` (新 abandon endpoint)、`services/analytics_service.py` (cache_state meta)、啟動檢查 (spool dir 共用性)、若干 service 型別正規化。
- **前端程式碼**：`frontend/src/core/{api.js,unwrap-api-result.js,schema-guard.js,endpoint-schemas.js,dev-warnings.js,app-version-check.js,pending-jobs-registry.js}`、`frontend/package.json` (devDeps vitest/@vue/test-utils/jsdom)、10 個 App.vue (改 import)、DateRangePicker/ActionButton/LoadingOverlay 元件約束。
- **測試碼**：後端 ~25 個新/擴充檔案；前端 ~20 個新測試檔 + vitest.config.js + playwright.config.js；fixtures/route_contract_matrix.py。
- **依賴**：前端新增 devDependencies `vitest`、`@vue/test-utils`、`jsdom` (無 runtime bundle 影響)。
- **CI**：pre-merge 加跑 envelope sweep + vitest + unit tests；nightly 加跑 `--run-integration`、`--run-e2e`、playwright。
- **契約文件**：`contract/api_inventory.md` 更新 envelope meta 增欄；`openspec/specs/` 六個 capability spec 同步。
