## Context

Admin Dashboard（`admin-dashboard`）和 Admin Performance（`admin-performance`）是內部維運頁面，與業務頁面（resource-history、reject-history 等）共存於同一 portal-shell 下。目前有三個問題需要修正：

1. **RQ Worker 時區錯誤**：後端回傳的 `birth_date` 是 UTC naive datetime，前端當作 local time 解析，在 UTC+8 環境下運行時間虛增 8 小時。
2. **Pareto 物化層死面板**：CacheTab 顯示的 Pareto 物化層 telemetry 全為 0，因為功能從未啟用（flag=false），實際 Pareto 已由 DuckDB cache-sql 接管。
3. **外觀不一致**：Admin 頁面自訂 header 樣式（出血式底部圓角、1280px 窄版），與業務頁面的共用 `PageHeader` 元件和 `header-gradient`（四角圓角、1800px）視覺語言不同。

涉及的模組：
- 後端：`rq_monitor_service.py`、`admin_routes.py`
- 前端：`admin-dashboard/App.vue`、`admin-dashboard/style.css`、`admin-dashboard/tabs/CacheTab.vue`、`admin-dashboard/tabs/WorkerTab.vue`、`admin-performance/App.vue`、`admin-performance/style.css`
- 共用元件：`shared-ui/components/PageHeader.vue`
- 共用樣式：`resource-shared/styles.css`（`.header-gradient`）

## Goals / Non-Goals

**Goals:**
- RQ Worker 運行時間在 UTC+8 環境下顯示正確
- Admin API 所有時間欄位語義一致（timezone-aware ISO 8601）
- 移除無效的 Pareto 物化層監控面板，減少維運誤判
- Admin 頁面 header 和容器寬度對齊全站設計規範

**Non-Goals:**
- 不做全專案時區重構
- 不刪除 `reject_pareto_materialized.py` 模組
- 不新增 DuckDB cache-sql telemetry 面板
- 不改動 admin tab 互動邏輯和內容區佈局
- 不改動 `PageHeader` 元件本身

## Decisions

### D1: `birth_date` 在後端加 UTC 標記，而非前端加 "Z" 後綴

**選擇**：在 `rq_monitor_service.py` 中 `w.birth_date.replace(tzinfo=timezone.utc)` 後再 `.isoformat()`，輸出 `"2026-04-01T00:00:00+00:00"`。

**替代方案**：前端 `formatUptime()` 中 `new Date(birthDate + 'Z')`。

**理由**：API 回傳的語義應該自我描述，不應讓消費端猜測時區。後端修正後，所有 API 消費者（不只當前前端）都能正確解讀。前端 `formatUptime()` 和 `workerStartTimeDisplay` 不需任何修改。

### D2: `worker_start_time` 改用 `datetime.fromtimestamp(ts, tz=timezone.utc)` 統一為 UTC

**選擇**：統一為 UTC-aware datetime 輸出，而非維持 local naive datetime。

**理由**：與 D1 的 `birth_date` 保持一致的 API 語義。前端 `new Date()` 解析帶 `+00:00` 的字串時會自動轉換為本地時間顯示，`toLocaleString('zh-TW')` 結果不受影響。

### D3: 直接移除 Pareto 物化層面板，而非標示「未啟用」

**選擇**：移除 CacheTab 中整個 Pareto SectionCard 和相關 computed properties，同時移除後端 `api_performance_detail()` 中的 `pareto_materialization` 收集。

**替代方案**：保留面板但加「未啟用」提示。

**理由**：物化層已被 DuckDB cache-sql 完全取代，flag 從未開啟，沒有重新啟用的計畫。保留空面板只會持續造成混淆。後端 `reject_pareto_materialized.py` 模組本身不動（fallback chain 仍引用它），只是不再從 admin API 收集 telemetry。

### D4: Admin header 改用共用 `PageHeader` 元件

**選擇**：Admin Dashboard 和 Admin Performance 的 header 都改用 `shared-ui/components/PageHeader.vue`，搭配 `header-gradient` 樣式（來自 `resource-shared/styles.css`）。

**替代方案**：僅調整自訂 CSS 使其視覺接近 `header-gradient`。

**理由**：使用共用元件可確保未來全站 header 變更時 admin 頁面自動跟進，減少維護成本。`PageHeader` 支援 `showRefresh`、`refreshing` 等 props，admin 的自動更新和手動重新整理可直接映射。

Admin Dashboard 的 tab 列不屬於 `PageHeader`，需保留在 header 下方作為獨立元素。

### D5: 容器 max-width 調為 1800px

**選擇**：`.theme-admin-dashboard` 和 `.perf-dashboard` 的 `max-width` 從 `1280px` 改為 `1800px`。

**理由**：與業務頁面的 `.dashboard` class（`max-width: 1800px`）對齊。Admin 頁面的表格和趨勢圖在寬螢幕下受益於更多水平空間。

### D6: Admin theme 加入 `resource-shared/styles.css` 的 `:is()` selector 列表

**選擇**：將 `.theme-admin-dashboard` 和 `.theme-admin-performance` 加入 `resource-shared/styles.css` 中 `header-gradient` 相關的 `:is()` selector。

**替代方案**：在 admin `style.css` 中複製 `header-gradient` 樣式。

**理由**：避免樣式重複。`:is()` selector 列表已有 15+ 個 theme class，再加兩個是慣例延伸。

## Risks / Trade-offs

**[R1] PageHeader 的 slot 結構可能不完全覆蓋 admin 的需求** → Admin Dashboard 的 auto-refresh toggle（checkbox + label）需要放入 PageHeader 的 slot 中。`PageHeader` 目前有 `header-left` slot 和右側的 refresh button。Auto-refresh toggle 可以放入 `subtitle` slot 或新增一個 `header-actions` slot。如果 slot 不夠用，可在 PageHeader 下方獨立放置控制列，不需修改 PageHeader 本身。

**[R2] `birth_date` 格式變更可能影響其他 API 消費者** → `get_rq_worker_details()` 的 birth_date 目前只由 admin dashboard 前端消費。health endpoint 使用 `get_rq_monitor_summary()` 也會間接包含。但格式從 `2026-04-01T00:00:00` 變為 `2026-04-01T00:00:00+00:00`，對 ISO 8601 parser 是向後相容的。

**[R3] 移除 `pareto_materialization` 欄位可能影響外部監控** → 確認此欄位僅由 admin dashboard 前端讀取，不被 Grafana 或其他監控工具引用。admin performance-detail API 是內部 API，無外部消費者。
