## Phase 1: 後端 trace_routes.py Blueprint

- [x] 1.1 建立 `src/mes_dashboard/routes/trace_routes.py`：`trace_bp` Blueprint（`url_prefix='/api/trace'`）
- [x] 1.2 實作 `POST /api/trace/seed-resolve` handler：request body 驗證、profile dispatch（`_seed_resolve_query_tool` / `_seed_resolve_msd`）、response format
- [x] 1.3 實作 `POST /api/trace/lineage` handler：呼叫 `LineageEngine.resolve_full_genealogy()`、response format、504 timeout 處理
- [x] 1.4 實作 `POST /api/trace/events` handler：呼叫 `EventFetcher.fetch_events()`、mid_section_defect profile 自動 aggregation、`EVENTS_PARTIAL_FAILURE` 處理
- [x] 1.5 為三個 endpoint 加入 `configured_rate_limit()`（seed: 10/60s, lineage: 10/60s, events: 15/60s）
- [x] 1.6 為三個 endpoint 加入 L2 Redis cache（seed: `trace:seed:{profile}:{params_hash}`, lineage: `trace:lineage:{sorted_cids_hash}`, events: `trace:evt:{profile}:{domains_hash}:{sorted_cids_hash}`，TTL=300s）
- [x] 1.7 在 `src/mes_dashboard/routes/__init__.py` 匯入並註冊 `trace_bp` Blueprint（維持專案統一的 route 註冊入口）
- [x] 1.8 API contract 測試：驗證 200/400/429/504 status code、`Retry-After` header、error code 格式、snake_case field names

## Phase 2: 前端共用元件

- [x] 2.1 建立 `frontend/src/shared-composables/useTraceProgress.js`：reactive state（`current_stage`, `completed_stages`, `stage_results`, `stage_errors`, `is_running`）+ `execute()` / `reset()` / `abort()` methods
- [x] 2.2 實作 sequential fetch 邏輯：seed-resolve → lineage → events，每段完成後立即更新 reactive state，錯誤記錄到 stage_errors 不拋出
- [x] 2.3 建立 `frontend/src/shared-composables/TraceProgressBar.vue`：三段式進度指示器（props: `current_stage`, `completed_stages`, `stage_errors`），完成=green、進行中=blue pulse、待處理=gray、錯誤=red

## Phase 3: mid-section-defect 漸進渲染

- [x] 3.1 在 `frontend/src/mid-section-defect/App.vue` 中引入 `useTraceProgress({ profile: 'mid_section_defect' })`
- [x] 3.2 改造 `loadAnalysis()` 流程：從 `apiGet('/analysis')` 單次呼叫改為 `trace.execute(params)` 分段 fetch
- [x] 3.3 加入 skeleton placeholders：KpiCards（6 cards, min-height 100px）、ParetoChart（6 charts, min-height 300px）、TrendChart（min-height 300px），灰色脈動動畫
- [x] 3.4 加入 fade-in transition：stage_results.events 完成後 KPI/charts 以 `opacity 0→1, 300ms ease-in` 填入
- [x] 3.5 用 `TraceProgressBar` 取代 filter bar 下方的 loading spinner
- [x] 3.6 整合 `useAutoRefresh`：`onRefresh` → `trace.abort()` + `trace.execute(committedFilters)`
- [x] 3.7 驗證 detail 分頁不受影響（仍使用 `/api/mid-section-defect/analysis/detail` GET endpoint）
- [x] 3.8 Golden test：`/api/mid-section-defect/analysis` GET endpoint 回傳結果與重構前完全一致（浮點 tolerance ±0.01%）

## Phase 4: query-tool on-demand lineage

- [x] 4.1 在 `useQueryToolData.js` 新增 `lineageCache` reactive object + `loadLotLineage(containerId)` 函數
- [x] 4.2 `loadLotLineage` 呼叫 `POST /api/trace/lineage`（`profile: 'query_tool'`, `container_ids: [containerId]`），結果存入 `lineageCache`
- [x] 4.3 在 lot 列表 UI 新增 lineage 展開按鈕（accordion pattern），點擊觸發 `loadLotLineage`，已快取的不重新 fetch
- [x] 4.4 `resolveLots()` 時清空 `lineageCache`（新一輪查詢）
- [x] 4.5 驗證既有 resolve → lot-history → lot-associations 流程不受影響

## Phase 5: Legacy cleanup

- [x] 5.1 刪除 `src/mes_dashboard/static/js/query-tool.js`（3056L, 126KB pre-Vite dead code）
- [x] 5.2 `grep -r "static/js/query-tool.js" src/ frontend/ templates/` 確認 0 結果
- [x] 5.3 確認 `frontend_asset('query-tool.js')` 正確解析到 Vite manifest 中的 hashed filename
