## Context

MES Dashboard 生產環境承載多個廠區、跨時區使用者，dashboard 頁面經常被長時間開啟 (跨班次、跨日)，並同時由 3–4 個 gunicorn worker + 多個 RQ worker 處理重查詢。目前測試覆蓋率雖看似數量充足 (155 pytest + 33 node:test + 27 e2e)，但存在三個結構性缺口：

1. **回傳格式邊界未系統化驗證** — `test_api_contract.py` 只是 AST 掃描 `jsonify` baseline，從未 runtime 呼叫路由驗證實際 envelope shape；service 層 Decimal/float/str 混雜問題僅在手動排錯時被發現；treemap/pareto 巢狀結構的空資料 (`children:null` vs `children:[]`) 無明確測試。
2. **分散式與生命週期情境完全未覆蓋** — 瀏覽器關分頁後 RQ orphan job、worker crash 後 zombie running state、Oracle 連線洩漏、分散式 Redis lock、跨 worker 結果傳遞、spool 原子 rename 皆無自動化驗證；這些情境在生產環境每月皆有案例。
3. **前端無 runtime 守門** — `core/api.js::unwrapApiResult` 的 wildcard fallback 會靜默吞掉非預期 shape；`unwrapApiResult` 本身竟在 10 個 App.vue 重複定義；無 TypeScript、無 zod/ajv；任何後端欄位微調都可能造成空白畫面卻無 error log。

使用者對本次變更已核定：執行全部三個 Wave (P0+P1+P2)、前端採手寫 `assertShape` + DEV 警告 (不導入 zod)、P0 即抽出 `unwrapApiResult` 到共用模組、前端測試遷移 Vitest + @vue/test-utils。本文件紀錄技術決策與權衡。

## Goals / Non-Goals

**Goals:**
- 所有 Flask 路由必須能被 runtime envelope sweep 自動驗證；新增路由若未登記 matrix 即 CI 失敗。
- `analytics_routes`、`trace_lineage_job_service`、`msd_duckdb_runtime`、`query_tool_sql_runtime`、`user_auth_routes`、`filter_cache` (generic) 覆蓋率 0% → ≥80%。
- 生產已知但未測試的分散式與生命週期情境全部有自動化驗證 (S6–S11 情境矩陣)。
- 前端對 5 個高風險端點 (hold-overview、reject-history、production-history、material-trace、anomaly-summary) 有 runtime schema 守門，DEV 模式下違規寫入 console warning 不影響 production bundle。
- 前端測試可掛載 `.vue` 元件，解鎖 DataTable/FilterPanel/HoldMatrix/ParetoGrid 等高風險元件測試。
- 3 個真實瀏覽器 Playwright E2E 流程作為最終 smoke gate。
- 使用者在超長區間、無效區間、session 過期、版本漂移等情境被前端主動阻止或明確引導，而非等後端 500。

**Non-Goals:**
- 不重寫前端為 TypeScript (與既有 JS 生態相容優先)。
- 不導入 zod/ajv/yup 等 schema 函式庫 (第一版手寫；若未來 warning 頻率過高再評估)。
- 不追求 100% 程式碼覆蓋率；聚焦「實際會被使用者觸發的路徑」。
- 不對 stress/load 測試做任何修改 (使用者明確排除)。
- 不做 UI 視覺/設計 token 調整 (只在既有元件加約束)。
- 不建立新的 Flask blueprint 或服務 (只在既有端點上補 edge case)。

## Decisions

### D1. Envelope 驗證：runtime sweep vs static AST 掃描
**選擇**：擴充既有 `test_api_contract.py` 加 `TestEnvelopeRuntimeSweep`，用 `app.test_client()` 實際呼叫，透過 `tests/fixtures/route_contract_matrix.py` 提供每條路由的 sample params 與預期 shape。

**理由**：靜態掃描只能抓 `jsonify(` 字面量是否出現，完全無法驗證 envelope 結構、error code 是否在允許清單、或 meta 欄位是否存在。runtime sweep 可自動覆蓋 90%+ 路由，且 matrix 登記機制會強制新路由同步契約。

**替代方案**：
- 手工每條路由寫 test → 成本高、易漏。駁回。
- 引入 OpenAPI schema 驗證 → 需要先產生 schema，工具鏈成本高。留作 P2 之後評估。

### D2. 前端 schema 守門：手寫 assertShape vs zod vs JSDoc
**選擇**：`frontend/src/core/schema-guard.js` 手寫 `assertShape(value, spec)` 遞迴驗證，spec 使用簡單字串 `'string'|'string?'|'number'|'number?'|'number-int'|'string-iso-date'|'array'` 或巢狀物件。

**理由**：
- 零新 runtime 依賴 (專案 bundle 已被 echarts 撐大)。
- 專案無 TypeScript，zod 最大優勢 (型別推導) 失效，只剩 runtime 驗證能力。
- DEV 模式 `console.warn` + production tree-shake 可在不影響使用者的前提下快速反饋。
- 若未來 warning 類型收斂需要組合/transform/refinement，再遷移到 zod，介面層保持不變 (`guardResponse(endpoint, payload)` 為唯一呼叫點)。

**替代方案**：
- **zod**：+~12KB bundle、`.parse()` throw 風險、TS 優勢浪費。駁回。
- **JSDoc + 無 runtime 檢查**：只是文件，無法在 DEV 發警告，無法攔截真實漂移。駁回。

### D3. 前端測試框架：Vitest vs 繼續 node:test vs Jest
**選擇**：遷移到 Vitest + @vue/test-utils + jsdom，既有 33 個 `node:test` 檔轉換到 Vitest API (差異極小)，無法轉的移到 `tests/legacy/` 過渡。

**理由**：
- Vitest 重用 Vite config，零額外 bundler 設定。
- @vue/test-utils 是 Vue 官方支援的元件測試工具，可 mount `.vue` SFC，與 jsdom 搭配可測 DOM 互動。
- Jest 需要獨立 babel/transform 設定，與 Vite 生態不相容。
- node:test 無法處理 `.vue` SFC，無法滿足 Phase 2 目標。

**替代方案**：
- **繼續 node:test**：直接放棄元件測試。駁回。
- **Cypress component testing**：重型、需要啟動瀏覽器，快速單元測試不適合。留作 E2E 補充。

### D4. 分散式 Lock：Redis SET NX EX vs Redlock vs threading.Lock
**選擇**：Redis `SET key val NX EX ttl` 作為單 instance Redis 的分散式鎖，`ttl` 設為「預期最長查詢時間 + 安全邊際」(建議 300s)。`threading.Lock` 僅用於單 gunicorn worker 內的 process-level 同步，絕不用於跨 worker 場景。

**理由**：
- 專案已有單一 Redis (無 cluster)，Redlock 的多 instance 容錯不適用。
- `SET NX EX` 原子性足夠，holder crash 後 TTL 自動釋放，避免死鎖。
- 必須搭配「query fingerprint 而非 query_id」作為 lock key，避免兩個等價查詢重複執行。
- 針對 stampede protection 同時使用：第一個 worker 拿鎖 → refill cache；其他等待 + 讀新 cache。

**風險**：若 query 時間超過 TTL，鎖會提前釋放導致重複執行。Mitigation：TTL 寬鬆 (300s) + 監控查詢中位時間，必要時調整。

### D5. Spool 原子寫入：rename vs write-in-place
**選擇**：所有 spool parquet 產出必須 `write(tmp_path) → os.rename(tmp_path, final_path)`，由 `tests/test_spool_lifecycle.py::test_reader_never_sees_partial_write` 鎖定。

**理由**：POSIX `rename` 於同檔系統為原子操作；reader 要嘛看到舊檔要嘛看到新檔，絕不會看到半寫。若 reader 在 writer 寫到一半去讀 `read_parquet`，DuckDB 會拋例外或回錯誤資料。這是現生產環境懷疑但未驗證的問題。

### D6. 前端 in-flight dedup：per-endpoint vs global
**選擇**：`core/api.js` 內部維護 `Map<fingerprint, Promise>`，fingerprint = `method + URL + SHA1(body)`；若 pending 則回傳同 promise。`AbortController` 取消時從 map 移除。

**理由**：快速連點查詢、快速切分頁 race 的根因是「相同請求被重複送出」。dedup 在最上層攔截，不需要每個 composable 自己寫 guard。

**權衡**：若 body 內含時間戳或 nonce 會破壞 fingerprint；需審查高風險 composable 的 body 建構。

### D7. analytics anomaly-summary cache miss 辨識
**選擇**：於 envelope `meta.cache_state` 加 `'cold'|'warm'|'stale'` 三態，取代目前 silent fallback `{count:0, items:[]}`。

**理由**：現況客戶端無法區分「真的沒異常」與「cache 尚未 warm up」，導致 dashboard 顯示「0 件異常」時可能是假象。加 meta 欄位為向後相容異動，不影響既有 schema；schema-guard 將把 `cache_state` 列為必填。

### D8. 前端 DateRangePicker 區間上限：前端硬約束 vs 後端 400
**選擇**：兩層防禦。前端 DateRangePicker 根據端點 max_days (production=730、reject=365、resource=180、yield=90) 禁用超限區間並 tooltip 說明；後端仍保留 `VALIDATION_ERROR` 400 為最後防線。

**理由**：使用者永遠會想出方法繞過前端 (URL 手改、API 直打)，後端必須守住；但讓使用者在 UI 上被阻止是更好的 UX，避免 10 秒等待後才看到錯誤。

### D9. Playwright E2E 與既有 in-process e2e 並存
**選擇**：保留 `tests/e2e/*.py` (Flask test client) 為快速合約檢查；新增 `frontend/tests/playwright/*.spec.js` 作為 nightly smoke；pre-merge 只跑前者，nightly 跑兩者。

**理由**：Flask test client e2e 快 (秒級)、無瀏覽器開銷，適合每次 commit 跑；Playwright 真瀏覽器測試慢 (分鐘級) 但可發現 JS runtime error、CSS 佈局、AbortController 真實行為，適合 nightly。兩者互補不重複。

### D10. Vue 元件中 unwrapApiResult 的 10 份重複
**選擇**：P0 即抽出 `frontend/src/core/unwrap-api-result.js`，10 個 App.vue 改為 `import`。不等 P1。

**理由**：重構本身是 Line-level 異動 (extract + import)，但解鎖整個前端 runtime 守門、測試可 reach 同一實作、未來所有新 endpoint 自動守護。「小改動 大槓桿」，不做會讓 P0 的 schema-guard 無法真正生效 (每個 App.vue 會繞過 guard)。

## Risks / Trade-offs

- **[Risk] Envelope runtime sweep 對某些需要複雜 session state 的路由無法直接呼叫** → Mitigation：`route_contract_matrix.py` 可標註 `skip_runtime_sweep=True` 加說明；這類路由在專屬 test 中補足。確保跳過清單不超過 10%。
- **[Risk] 手寫 schema-guard 若需要支援 union type / refinement 會膨脹** → Mitigation：spec 語法刻意保守，只接受 7 種 primitive 標示 + nested object + array。遇到複雜情境直接寫專屬 validator，不讓 schema-guard 過度設計。
- **[Risk] Vitest 遷移 33 個既有測試可能有 node:test 特有 API 使用** → Mitigation：先跑 compatibility 檢查，不相容的保留於 `tests/legacy/` 與 Vitest 並行；不強迫一次遷完。
- **[Risk] Redis 分散式鎖 TTL 估錯導致重複執行** → Mitigation：監控查詢中位時間 + p95；於 `tests/test_distributed_lock.py` 加 `test_lock_ttl_covers_p95_query_time` 作為回歸守門。
- **[Risk] `POST /api/job/<id>/abandon` 作為 best-effort 清理可能被惡意使用者濫用取消他人 job** → Mitigation：驗證 job 的 owner session 一致；加 rate limit。
- **[Risk] Playwright 在 CI 環境啟動需要瀏覽器 binary** → Mitigation：強制使用 `~/.cache/ms-playwright` 共用快取 (遵守 `panjit-infra`)，禁止 `playwright install`。
- **[Risk] DEV warning 太吵被忽略** → Mitigation：每類 warning 首次觸發才印 (記 Set)，避免 spam；提供 `localStorage.setItem('schema-guard-verbose','1')` 切換詳細模式。
- **[Trade-off] 增加 ~45 個新測試檔會拖慢 CI** → 以 `pytest -x --ff` + 分組平行化抵銷；integration/e2e 改 nightly 不阻 pre-merge。
- **[Trade-off] envelope `meta.app_version` 為向後相容異動，但所有後端回傳路徑需同步** → 集中於 `core/response.py::success_response/error_response` 一次加入，無分散異動。

## Migration Plan

1. **Wave P0 (1 週)**：完成 envelope sweep + analytics + 高風險 edge cases + unwrapApiResult 抽出 + schema-guard 首批 2 端點 + devmode warnings NaN/unknown-envelope。
2. **Wave P1 (1.5 週)**：缺失 unit tests + 端點剩餘 edge cases + Oracle/Redis/DuckDB 整合 + Vitest 遷移 + 元件測試 + AbortController 回歸 + schema-guard 擴充至 5 端點 + dev-warnings 剩餘 3 類。
3. **Wave P2 (1 週)**：OpenSpec 合約測試 + per-composable validation sweep + Playwright 3 流程 + CI nightly 整合。
4. **回滾策略**：所有新測試與前端守門模組皆為 additive；envelope `meta.app_version` 與 `meta.cache_state` 為新增欄位不破壞既有客戶端。若 schema-guard 造成 DEV 模式過吵，可將 `guardResponse` 改為 no-op 恢復原行為。`POST /api/job/<id>/abandon` 可獨立停用。

## Open Questions

- `QUERY_SPOOL_DIR` 在 Docker 佈署下是否已掛共用 volume？若否，`cross-worker-result-integrity` capability 會在第一次測試即失敗，需要運維同步確認。
- `core/api.js` 現行預設 timeout 是多少？若缺則新增 90s；若已有則沿用。需於實作階段 grep 確認。
- `auto memory` 中的 `filter_cache` 是否等同 `services/filter_cache.py`？若為同檔則 P1.1 測試對應，否則需要重命名澄清。
- Playwright 在 headless 模式下對 `zh-TW` locale 字體渲染是否穩定？可能需要 font fallback 設定。
