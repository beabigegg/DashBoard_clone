## Context

`/mid-section-defect` 頁面已上線，功能完整但缺乏生產環境保護機制。Code review 揭示 6 個問題，依嚴重度分為 P0-P3。現有基礎建設（`try_acquire_lock`、`configured_rate_limit`、`createAbortSignal`）均可直接複用，無需新增框架。

**現有架構**：
- Backend: `query_analysis()` (line 82-184) 含 5min Redis 快取 → `query_analysis_detail()` (line 187-224) 呼叫前者取快取結果再分頁
- Frontend: `Promise.all([summary, detail])` 平行載入 → `useAutoRefresh` 5min 自動刷新
- 上游歷史: SQL 查全量 → Python `get_workcenter_group()` 逐行分類 + order 4-11 過濾

## Goals / Non-Goals

**Goals:**
- 消除首次查詢的雙倍 Oracle 管線執行（P0）
- 保護高成本路由免受暴衝流量（P1a）
- 確保 UI 篩選變更不會汙染進行中的 API 呼叫（P1b）
- 新查詢自動取消舊的進行中請求（P2a）
- 善用 Oracle Server 做 workcenter 分類，支援全線歷程追蹤（P2b）
- 基礎測試覆蓋防止回歸（P3）

**Non-Goals:**
- 不改變 API response 格式
- 不重構 `query_analysis()` 管線邏輯
- 不加入前端 UI 新功能
- 不處理 `export_csv()` 的串流效能（目前可接受）
- 不做 DuckDB 中間層或背景預計算

## Decisions

### D1: 分散式鎖策略 — Redis SET NX 輪詢等待

**選擇**: 使用既有 `try_acquire_lock()` + 輪詢 `cache_get()` 等待模式。
**替代方案**: (A) Pub/Sub 通知 — 複雜度高，需新增 channel 管理；(B) 前端序列化 — 改 `Promise.all` 為先 summary 再 detail，但仍有自動刷新與手動查詢並行問題。
**理由**: 鎖機制在 service 層統一保護所有入口（包含未來新路由），fail-open 設計確保 Redis 故障不阻塞。輪詢 0.5s 間隔在 5-35s 典型管線執行時間下損耗可忽略。

### D2: Rate limit 預設值 — 依路由成本分級

**選擇**: `/analysis` 6/60s、`/detail` 15/60s、`/export` 3/60s。
**理由**: `/analysis` 冷查詢 35s，每分鐘最多 6 次已足夠（含自動刷新）。`/detail` 分頁翻頁頻率高但走快取，15 次寬裕。`/export` 觸發全量串流，3 次防誤操作。`/loss-reasons` 已有 24h 快取，無需限速。

### D3: 篩選分離 — committedFilters ref 快照

**選擇**: 新增 `committedFilters` ref，按「查詢」時從 `filters` reactive 快照。所有 API 函式讀 `committedFilters`。
**替代方案**: (A) deep watch + debounce — 會在使用者輸入中途觸發查詢；(B) URL params 持久化 — 此頁面不需要書籤分享功能。
**理由**: 最小改動，與 `resource-history/App.vue` 的 `buildQueryString()` 模式一致。`filters` reactive 繼續作為 UI 雙向繫結，`committedFilters` 是「上次查詢使用的參數」。

### D4: AbortController — keyed signal 設計

**選擇**: `'msd-analysis'` key 用於查詢（summary + detail page 1 共用），`'msd-detail'` key 用於獨立翻頁。
**理由**: 新查詢取消舊查詢的所有請求（含翻頁中的 detail），翻頁取消前一次翻頁但不影響進行中的查詢。與 `wip-detail/App.vue` 相同模式。

### D5: 上游歷史 SQL 端分類 — CASE WHEN 全線保留

**選擇**: SQL CTE 內加 `CASE WHEN` 將 `WORKCENTERNAME` 分類為 `WORKCENTER_GROUP`（12 組 + NULL fallback），Python 端直接讀取分類結果，不過濾任何站點。
**替代方案**: (A) Oracle 自訂函式 — 需 DBA 部署；(B) 維持 Python 端分類但移除過濾 — 仍有 10K+ 行逐行 regex 開銷。
**理由**: CASE WHEN 在 Oracle 查詢引擎內原生執行，無 row-by-row function call 開銷。分類邏輯與 `workcenter_groups.py` 的 patterns 完全對齊，但需注意 CASE 順序（exclude-first: `元件切割` 在 `切割` 之前）。

## Risks / Trade-offs

- **[P0 鎖等待超時]** 若管線執行 >90s（極大日期範圍），等待方可能超時後自行查詢 → 緩解：API_TIMEOUT 本身 120s，鎖 TTL 120s 會自動釋放，最壞情況退化為當前行為（雙查詢）
- **[P2b SQL 分類與 Python 不一致]** 若 `workcenter_groups.py` 新增/修改 pattern 但忘記同步 SQL → 緩解：SQL 的 NULL fallback 確保不會遺失行，僅分類名稱可能為 NULL
- **[Rate limit 誤擋]** 高頻翻頁或自動刷新可能觸發限速 → 緩解：`/detail` 15/60s 已足夠正常翻頁（每 4s 一頁），自動刷新 5min 間隔遠低於 `/analysis` 6/60s 門檻
