## 1. RQ Worker 時區修正（後端）

- [x] 1.1 在 `rq_monitor_service.py` 的 `get_rq_worker_details()` 中，將 `w.birth_date` 加上 UTC timezone info（`replace(tzinfo=timezone.utc)`）後再呼叫 `.isoformat()`
- [x] 1.2 在 `admin_routes.py` 的 `api_worker_status()` 中，將 `datetime.fromtimestamp(process.create_time())` 改為 `datetime.fromtimestamp(process.create_time(), tz=timezone.utc)`
- [x] 1.3 在 `tests/test_rq_monitor_service.py` 中新增測試：驗證 `birth_date` 輸出包含 `+00:00` 後綴，且 null birth_date 回傳 null

## 2. Pareto 物化層面板移除

- [x] 2.1 在 `admin_routes.py` 的 `api_performance_detail()` 中移除 `pareto_materialization` 的 try/except 收集區塊和 response dict 中的對應 key
- [x] 2.2 在 `CacheTab.vue` 中移除 Pareto 物化層的 SectionCard template 區塊（包含命中率、建構次數、fallback 原因表格等）
- [x] 2.3 在 `CacheTab.vue` 中移除 Pareto 相關的 computed properties（`paretoHitRateDisplay`、`paretoBuildLatencyDisplay`、`paretoPayloadDisplay`、`paretoFallbackReasons`）
- [x] 2.4 在 `admin-dashboard/style.css` 中移除 `.pareto-fallback-reasons` 樣式規則

## 3. Admin Dashboard 外觀標準化

- [x] 3.1 在 `admin-dashboard/App.vue` 中引入 `PageHeader` 元件，替換自訂 `.dashboard-header` template 區塊；保留 tab 列作為 header 下方獨立元素
- [x] 3.2 將 auto-refresh toggle 和 refresh button 整合到 `PageHeader` 的 slot 或下方控制列
- [x] 3.3 在 `admin-dashboard/style.css` 中將 `.theme-admin-dashboard` 的 `max-width` 從 `1280px` 改為 `1800px`
- [x] 3.4 在 `admin-dashboard/style.css` 中移除自訂 header CSS（`.dashboard-header`、`.dashboard-header-inner`、`.dashboard-title`、`.dashboard-header-actions`）
- [x] 3.5 在 `resource-shared/styles.css` 的 `:is()` selector 列表中加入 `.theme-admin-dashboard`，使 `header-gradient` 樣式生效

## 4. Admin Performance 外觀標準化

- [x] 4.1 在 `admin-performance/App.vue` 中引入 `PageHeader` 元件，替換自訂 `.perf-header` template 區塊
- [x] 4.2 將 auto-refresh toggle 和 refresh button 整合到 `PageHeader` 的 slot 或下方控制列
- [x] 4.3 在 `admin-performance/style.css` 中將 `.perf-dashboard` 的 `max-width` 從 `1280px` 改為 `1800px`
- [x] 4.4 在 `admin-performance/style.css` 中移除自訂 header CSS（`.perf-header`、`.perf-header-inner`、`.perf-title`、`.perf-header-actions`）
- [x] 4.5 在 `resource-shared/styles.css` 的 `:is()` selector 列表中加入 `.theme-admin-performance`，使 `header-gradient` 樣式生效

## 5. 驗證

- [x] 5.1 執行 `pytest tests/test_rq_monitor_service.py -v` 確認時區測試通過
- [x] 5.2 執行 `npm run build` 確認前端建構成功無錯誤
