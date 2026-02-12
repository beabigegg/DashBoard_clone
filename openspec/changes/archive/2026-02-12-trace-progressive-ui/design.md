## Context

`unified-lineage-engine` 完成後，後端追溯管線從 30-120 秒降至 3-8 秒。但目前的 UX 模式仍是黑盒等待——mid-section-defect 的 `/analysis` GET 一次回傳全部結果（KPI + charts + trend + genealogy_status），query-tool 雖有手動順序（resolve → history → association）但 lineage 查詢仍在批次載入。

既有前端架構：
- mid-section-defect: `App.vue` 用 `Promise.all([apiGet('/analysis'), loadDetail(1)])` 並行呼叫，`loading.querying` 單一布林控制整頁 loading state
- query-tool: `useQueryToolData.js` composable 管理 `loading.resolving / .history / .association / .equipment`，各自獨立但無分段進度
- 共用: `useAutoRefresh` (jittered interval + abort signal), `usePaginationState`, `apiGet/apiPost` (timeout + abort), `useQueryState` (URL sync)
- API 模式: `apiGet/apiPost` 支援 `signal: AbortSignal` + `timeout`，錯誤物件含 `error.retryAfterSeconds`

## Goals / Non-Goals

**Goals:**
- 新增 `/api/trace/*` 三段式 API（seed-resolve → lineage → events），通過 `profile` 參數區分頁面行為
- 建立 `useTraceProgress` composable 封裝三段式 sequential fetch + reactive state
- mid-section-defect 漸進渲染: seed lots 先出 → 血緣 → KPI/charts fade-in
- query-tool lineage tab 改為 on-demand（點擊單一 lot 後才查血緣）
- 保持 `/api/mid-section-defect/analysis` GET endpoint 向下相容
- 刪除 pre-Vite dead code `static/js/query-tool.js`

**Non-Goals:**
- 不實作 SSE / WebSocket（gunicorn sync workers 限制）
- 不新增 Celery/RQ 任務隊列
- 不改動追溯計算邏輯（由 `unified-lineage-engine` 負責）
- 不改動 defect attribution 演算法
- 不改動 equipment-period 查詢

## Decisions

### D1: trace_routes.py Blueprint 架構

**選擇**: 單一 Blueprint `trace_bp`，三個 route handler + profile dispatch
**替代方案**: 每個 profile 獨立 Blueprint（`trace_msd_bp`, `trace_qt_bp`）
**理由**:
- 三個 endpoint 的 request/response 結構統一，僅內部呼叫邏輯依 profile 分支
- 獨立 Blueprint 會重複 rate limit / cache / error handling boilerplate
- profile 驗證集中在一處（`_validate_profile()`），新增 profile 只需加 if 分支

**路由設計**:
```python
trace_bp = Blueprint('trace', __name__, url_prefix='/api/trace')

@trace_bp.route('/seed-resolve', methods=['POST'])
@configured_rate_limit(bucket='trace-seed', default_max_attempts=10, default_window_seconds=60)
def seed_resolve():
    body = request.get_json()
    profile = body.get('profile')
    params = body.get('params', {})
    # profile dispatch → _seed_resolve_query_tool(params) or _seed_resolve_msd(params)
    # return jsonify({ "stage": "seed-resolve", "seeds": [...], "seed_count": N, "cache_key": "trace:{hash}" })

@trace_bp.route('/lineage', methods=['POST'])
@configured_rate_limit(bucket='trace-lineage', default_max_attempts=10, default_window_seconds=60)
def lineage():
    body = request.get_json()
    container_ids = body.get('container_ids', [])
    # call LineageEngine.resolve_full_genealogy(container_ids)
    # return jsonify({ "stage": "lineage", "ancestors": {...}, "merges": {...}, "total_nodes": N })

@trace_bp.route('/events', methods=['POST'])
@configured_rate_limit(bucket='trace-events', default_max_attempts=15, default_window_seconds=60)
def events():
    body = request.get_json()
    container_ids = body.get('container_ids', [])
    domains = body.get('domains', [])
    profile = body.get('profile')
    # call EventFetcher for each domain
    # if profile == 'mid_section_defect': run aggregation
    # return jsonify({ "stage": "events", "results": {...}, "aggregation": {...} | null })
```

**Profile dispatch 內部函數**:
```
_seed_resolve_query_tool(params) → 呼叫 query_tool_service 既有 resolve 邏輯
_seed_resolve_msd(params)        → 呼叫 mid_section_defect_service TMTT 偵測邏輯
_aggregate_msd(events_data)      → mid-section-defect 專屬 aggregation (KPI, charts, trend)
```

**Cache 策略**:
- seed-resolve: `trace:seed:{profile}:{params_hash}`, TTL=300s
- lineage: `trace:lineage:{sorted_cids_hash}`, TTL=300s（profile-agnostic，因為 lineage 不依賴 profile）
- events: `trace:evt:{profile}:{domains_hash}:{sorted_cids_hash}`, TTL=300s
- 使用 `LayeredCache` L2 Redis（對齊 `core/cache.py` 既有模式）
- cache key hash: `hashlib.md5(sorted(values).encode()).hexdigest()[:12]`

**錯誤處理統一模式**:
```python
def _make_stage_error(stage, code, message, status=400):
    return jsonify({"error": message, "code": code}), status

# Timeout 處理: 每個 stage 內部用 read_sql_df() 的 55s call_timeout
# 若超時: return _make_stage_error(stage, f"{STAGE}_TIMEOUT", "...", 504)
```

### D2: useTraceProgress composable 設計

**選擇**: 新建 `frontend/src/shared-composables/useTraceProgress.js`，封裝 sequential fetch + reactive stage state
**替代方案**: 直接在各頁面 App.vue 內實作分段 fetch
**理由**:
- 兩個頁面共用相同的三段式 fetch 邏輯
- 將 stage 狀態管理抽離，頁面只需關注渲染邏輯
- 對齊既有 `shared-composables/` 目錄結構

**Composable 簽名**:
```javascript
export function useTraceProgress({ profile, buildParams }) {
  // --- Reactive State ---
  const current_stage = ref(null)       // 'seed-resolve' | 'lineage' | 'events' | null
  const completed_stages = ref([])       // ['seed-resolve', 'lineage']
  const stage_results = reactive({
    seed: null,                          // { seeds: [], seed_count: N, cache_key: '...' }
    lineage: null,                       // { ancestors: {...}, merges: {...}, total_nodes: N }
    events: null,                        // { results: {...}, aggregation: {...} }
  })
  const stage_errors = reactive({
    seed: null,                          // { code: '...', message: '...' }
    lineage: null,
    events: null,
  })
  const is_running = ref(false)

  // --- Methods ---
  async function execute(params)         // 執行三段式 fetch
  function reset()                       // 清空所有 state
  function abort()                       // 中止進行中的 fetch

  return {
    current_stage,
    completed_stages,
    stage_results,
    stage_errors,
    is_running,
    execute,
    reset,
    abort,
  }
}
```

**Sequential fetch 邏輯**:
```javascript
async function execute(params) {
  reset()
  is_running.value = true
  const abortCtrl = new AbortController()

  try {
    // Stage 1: seed-resolve
    current_stage.value = 'seed-resolve'
    const seedResult = await apiPost('/api/trace/seed-resolve', {
      profile,
      params,
    }, { timeout: 60000, signal: abortCtrl.signal })
    stage_results.seed = seedResult.data
    completed_stages.value.push('seed-resolve')

    if (!seedResult.data?.seeds?.length) return  // 無 seed，不繼續

    // Stage 2: lineage
    current_stage.value = 'lineage'
    const cids = seedResult.data.seeds.map(s => s.container_id)
    const lineageResult = await apiPost('/api/trace/lineage', {
      profile,
      container_ids: cids,
      cache_key: seedResult.data.cache_key,
    }, { timeout: 60000, signal: abortCtrl.signal })
    stage_results.lineage = lineageResult.data
    completed_stages.value.push('lineage')

    // Stage 3: events
    current_stage.value = 'events'
    const allCids = _collectAllCids(cids, lineageResult.data)
    const eventsResult = await apiPost('/api/trace/events', {
      profile,
      container_ids: allCids,
      domains: _getDomainsForProfile(profile),
      cache_key: seedResult.data.cache_key,
    }, { timeout: 60000, signal: abortCtrl.signal })
    stage_results.events = eventsResult.data
    completed_stages.value.push('events')

  } catch (err) {
    if (err?.name === 'AbortError') return
    // 記錄到當前 stage 的 error state
    const stage = current_stage.value
    if (stage) stage_errors[_stageKey(stage)] = { code: err.errorCode, message: err.message }
  } finally {
    current_stage.value = null
    is_running.value = false
  }
}
```

**設計重點**:
- `stage_results` 為 reactive object，每個 stage 完成後立即賦值，觸發依賴該 stage 的 UI 更新
- 錯誤不拋出到頁面——記錄在 `stage_errors` 中，已完成的 stage 結果保留
- `abort()` 方法供 `useAutoRefresh` 在新一輪 refresh 前中止上一輪
- `profile` 為建構時注入（不可變），`params` 為執行時傳入（每次查詢可變）
- `cache_key` 在 stage 間傳遞，用於 logging correlation

### D3: mid-section-defect 漸進渲染策略

**選擇**: 分段渲染 + skeleton placeholders + CSS fade-in transition
**替代方案**: 保持一次性渲染（等全部 stage 完成）
**理由**:
- seed stage ≤3s 可先顯示 seed lots 數量和基本資訊
- lineage + events 完成後再填入 KPI/charts，使用者感受到進度
- skeleton placeholders 避免 layout shift（chart container 預留固定高度）

**App.vue 查詢流程改造**:
```javascript
// Before (current)
async function loadAnalysis() {
  loading.querying = true
  const [summaryResult] = await Promise.all([
    apiGet('/api/mid-section-defect/analysis', { params, timeout: 120000, signal }),
    loadDetail(1, signal),
  ])
  analysisData.value = summaryResult.data  // 一次全部更新
  loading.querying = false
}

// After (progressive)
const trace = useTraceProgress({ profile: 'mid_section_defect' })

async function loadAnalysis() {
  const params = buildFilterParams()
  // 分段 fetch（seed → lineage → events+aggregation）
  await trace.execute(params)
  // Detail 仍用舊 endpoint 分頁（不走分段 API）
  await loadDetail(1)
}
```

**渲染層對應**:
```
trace.completed_stages 包含 'seed-resolve'
  → 顯示 seed lots 數量 badge + 基本 filter feedback
  → KPI cards / charts / trend 顯示 skeleton

trace.completed_stages 包含 'lineage'
  → 顯示 genealogy_status（ancestor 數量）
  → KPI/charts 仍為 skeleton

trace.completed_stages 包含 'events'
  → trace.stage_results.events.aggregation 不為 null
  → KPI cards 以 fade-in 填入數值
  → Pareto charts 以 fade-in 渲染
  → Trend chart 以 fade-in 渲染
```

**Skeleton Placeholder 規格**:
- KpiCards: 6 個固定高度 card frame（`min-height: 100px`），灰色脈動動畫
- ParetoChart: 6 個固定高度 chart frame（`min-height: 300px`），灰色脈動動畫
- TrendChart: 1 個固定高度 frame（`min-height: 300px`）
- fade-in: CSS transition `opacity 0→1, 300ms ease-in`

**Auto-refresh 整合**:
- `useAutoRefresh.onRefresh` → `trace.abort()` + `trace.execute(committedFilters)`
- 保持現行 5 分鐘 jittered interval

**Detail 分頁不變**:
- `/api/mid-section-defect/analysis/detail` GET endpoint 保持不變
- 不走分段 API（detail 是分頁查詢，與 trace pipeline 獨立）

### D4: query-tool on-demand lineage 策略

**選擇**: per-lot on-demand fetch，使用者點擊 lot card 才查血緣
**替代方案**: batch-load all lots lineage at resolve time
**理由**:
- resolve 結果可能有 20+ lots，批次查全部 lineage 增加不必要的 DB 負擔
- 大部分使用者只關注特定幾個 lot 的 lineage
- per-lot fetch 控制在 ≤3s，使用者體驗可接受

**useQueryToolData.js 改造**:
```javascript
// 新增 lineage state
const lineageCache = reactive({})  // { [containerId]: { ancestors, merges, loading, error } }

async function loadLotLineage(containerId) {
  if (lineageCache[containerId]?.ancestors) return  // 已快取

  lineageCache[containerId] = { ancestors: null, merges: null, loading: true, error: null }
  try {
    const result = await apiPost('/api/trace/lineage', {
      profile: 'query_tool',
      container_ids: [containerId],
    }, { timeout: 60000 })
    lineageCache[containerId] = {
      ancestors: result.data.ancestors,
      merges: result.data.merges,
      loading: false,
      error: null,
    }
  } catch (err) {
    lineageCache[containerId] = {
      ancestors: null,
      merges: null,
      loading: false,
      error: err.message,
    }
  }
}
```

**UI 行為**:
- lot 列表中每個 lot 有展開按鈕（或 accordion）
- 點擊展開 → 呼叫 `loadLotLineage(containerId)` → 顯示 loading → 顯示 lineage tree
- 已展開的 lot 再次點擊收合（不重新 fetch）
- `lineageCache` 在新一輪 `resolveLots()` 時清空

**query-tool 主流程保持不變**:
- resolve → lot-history → lot-associations 的既有流程不改
- lineage 是新增的 on-demand 功能，不取代既有功能
- query-tool 暫不使用 `useTraceProgress`（因為它的流程是使用者驅動的互動式，非自動 sequential）

### D5: 進度指示器元件設計

**選擇**: 共用 `TraceProgressBar.vue` 元件，props 驅動
**替代方案**: 各頁面各自實作進度顯示
**理由**:
- 兩個頁面顯示相同的 stage 進度（seed → lineage → events）
- 統一視覺語言

**元件設計**:
```javascript
// frontend/src/shared-composables/TraceProgressBar.vue
// (放在 shared-composables 目錄，雖然是 .vue 但與 composable 搭配使用)

props: {
  current_stage: String | null,    // 'seed-resolve' | 'lineage' | 'events'
  completed_stages: Array,          // ['seed-resolve', 'lineage']
  stage_errors: Object,             // { seed: null, lineage: { code, message } }
}

// 三個 step indicator:
// [●] Seed → [●] Lineage → [○] Events
//  ↑ 完成(green)  ↑ 進行中(blue pulse) ↑ 待處理(gray)
//                   ↑ 錯誤(red)
```

**Stage 顯示名稱**:
| Stage ID | 中文顯示 | 英文顯示 |
|----------|---------|---------|
| seed-resolve | 批次解析 | Resolving |
| lineage | 血緣追溯 | Lineage |
| events | 事件查詢 | Events |

**取代 loading spinner**:
- mid-section-defect: `loading.querying` 原本控制單一 spinner → 改為顯示 `TraceProgressBar`
- 進度指示器放在 filter bar 下方、結果區域上方

### D6: `/analysis` GET endpoint 向下相容橋接

**選擇**: 保留原 handler，內部改為呼叫分段管線後合併結果
**替代方案**: 直接改原 handler 不經過分段管線
**理由**:
- 分段管線（LineageEngine + EventFetcher）在 `unified-lineage-engine` 完成後已是標準路徑
- 保留原 handler 確保非 portal-shell 路由 fallback 仍可用
- golden test 比對確保結果等價

**橋接邏輯**:
```python
# mid_section_defect_routes.py — /analysis handler 內部改造

@mid_section_defect_bp.route('/analysis', methods=['GET'])
@configured_rate_limit(bucket='msd-analysis', ...)
def api_analysis():
    # 現行: result = mid_section_defect_service.query_analysis(start_date, end_date, loss_reasons)
    # 改為: 呼叫 service 層的管線函數（service 內部已使用 LineageEngine + EventFetcher）
    # response format 完全不變
    result = mid_section_defect_service.query_analysis(start_date, end_date, loss_reasons)
    return jsonify({"success": True, "data": result})
```

**實際上 `/analysis` handler 不需要改**——`unified-lineage-engine` Phase 1 已將 service 內部改為使用 `LineageEngine`。本變更只需確認 `/analysis` 回傳結果與重構前完全一致（golden test 驗證），不需額外的橋接程式碼。

**Golden test 策略**:
- 選取 ≥3 組已知查詢參數（不同日期範圍、不同 loss_reasons 組合）
- 比對重構前後 `/analysis` JSON response 結構和數值
- 允許浮點數 tolerance（defect_rate 等百分比欄位 ±0.01%）

### D7: Legacy static JS 清理

**選擇**: 直接刪除 `src/mes_dashboard/static/js/query-tool.js`
**理由**:
- 此檔案 3056L / 126KB，是 pre-Vite 時代的靜態 JS
- `query_tool.html` template 使用 `frontend_asset('query-tool.js')` 載入 Vite 建置產物，非此靜態檔案
- Vite config 確認 entry point: `'query-tool': resolve(__dirname, 'src/query-tool/main.js')`
- `frontend_asset()` 解析 Vite manifest，不會指向 `static/js/`
- grep 確認無其他引用

**驗證步驟**:
1. `grep -r "static/js/query-tool.js" src/ frontend/ templates/` → 0 結果
2. 確認 `frontend_asset('query-tool.js')` 正確解析到 Vite manifest 中的 hashed filename
3. 確認 `frontend/src/query-tool/main.js` 為 active entry（Vite config `input` 對應）

### D8: 實作順序

**Phase 1**: 後端 trace_routes.py（無前端改動）
1. 建立 `trace_routes.py` + 三個 route handler
2. 在 `app.py` 註冊 `trace_bp` Blueprint
3. Profile dispatch functions（呼叫既有 service 邏輯）
4. Rate limit + cache 配置
5. 錯誤碼 + HTTP status 對齊 spec
6. API contract 測試（request/response schema 驗證）

**Phase 2**: 前端共用元件
1. 建立 `useTraceProgress.js` composable
2. 建立 `TraceProgressBar.vue` 進度指示器
3. 單元測試（mock API calls，驗證 stage 狀態轉換）

**Phase 3**: mid-section-defect 漸進渲染
1. `App.vue` 查詢流程改為 `useTraceProgress`
2. 加入 skeleton placeholders + fade-in transitions
3. 用 `TraceProgressBar` 取代 loading spinner
4. 驗證 auto-refresh 整合
5. Golden test: `/analysis` 回傳結果不變

**Phase 4**: query-tool on-demand lineage
1. `useQueryToolData.js` 新增 `lineageCache` + `loadLotLineage()`
2. lot 列表加入 lineage 展開 UI
3. 驗證既有 resolve → history → association 流程不受影響

**Phase 5**: Legacy cleanup
1. 刪除 `src/mes_dashboard/static/js/query-tool.js`
2. grep 確認零引用
3. 確認 `frontend_asset()` 解析正常

## Risks / Trade-offs

| Risk | Mitigation |
|------|-----------|
| 分段 API 增加前端複雜度（3 次 fetch + 狀態管理） | 封裝在 `useTraceProgress` composable，頁面只需 `execute(params)` + watch `stage_results` |
| `/analysis` golden test 因浮點精度失敗 | 允許 defect_rate 等百分比 ±0.01% tolerance，整數欄位嚴格比對 |
| mid-section-defect skeleton → chart 渲染閃爍 | 固定高度 placeholder + fade-in 300ms transition，chart container 不允許 height auto |
| `useTraceProgress` abort 與 `useAutoRefresh` 衝突 | auto-refresh 觸發前先呼叫 `trace.abort()`，確保上一輪 fetch 完整中止 |
| query-tool lineage per-lot fetch 對高頻展開造成 DB 壓力 | lineageCache 防止重複 fetch + trace-lineage rate limit (10/60s) 保護 |
| `static/js/query-tool.js` 刪除影響未知路徑 | grep 全域確認 0 引用 + `frontend_asset()` 確認 Vite manifest 解析正確 |
| cache_key 傳遞中斷（前端忘記傳 cache_key） | cache_key 為選填，僅用於 logging correlation，缺少不影響功能 |

## Open Questions

- `useTraceProgress` 是否需要支援 retry（某段失敗後重試該段而非整體重新執行）？暫不支援——失敗後使用者重新按查詢按鈕即可。
- mid-section-defect 的 aggregation 邏輯（KPI、charts、trend 計算）是放在 `/api/trace/events` 的 mid_section_defect profile 分支內，還是由前端從 raw events 自行計算？**決定: 放在後端 `/api/trace/events` 的 aggregation field**——前端不應承擔 defect attribution 計算責任，且計算邏輯已在 service 層成熟。
- `TraceProgressBar.vue` 放在 `shared-composables/` 還是獨立的 `shared-components/` 目錄？暫放 `shared-composables/`（與 composable 搭配使用），若未來 shared 元件增多再考慮拆分。
