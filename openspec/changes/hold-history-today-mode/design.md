## Context

Hold History 頁面主軸是「區間內 Hold 事件回顧」，但使用者在實際工作中也需要「當下 + 今日」視角。把兩個語意硬塞在同一組 UI（日期區間 + Record Type）造成認知負擔，需要分離模式。

### 已驗證前提（hold-history-metric-refinement 已 land 或並行中）
- Oracle DB timezone = `+08:00`，SYSDATE 可信
- 07:30 班別切換邏輯在 `base_facts.sql` 已實作（`CASE WHEN TO_CHAR(HOLDTXNDATE, 'HH24MI') >= '0730' THEN TRUNC+1 ELSE TRUNC`）
- AVG / MAX HOLD_HOURS 計算（於 `metric-refinement` 中引入）可複用於當日模式卡片
- 品質重複觸發指標（於 `metric-refinement` 中引入）之邏輯可複用於當日模式

### 既有頁面狀態管理
- `useFilterOrchestrator` 管理 draft/committed 狀態與觸發時機（draft-apply / immediate）
- URL sync 由 `updateUrlState()` 手動維護
- Spool cache 以 `query_id` 為鍵，範圍由 `hold_day BETWEEN start AND end` 決定

## Goals / Non-Goals

**Goals:**
- 在不破壞既有區間模式行為的前提下，新增當日模式
- 當日模式以「當下快照 + 今日事件」為主軸，Record Type 語意重新定義
- 所有篩選 / 模式 / 卡片都有清楚的 label + tooltip 說明
- 模式切換 URL 可分享、可書籤、可瀏覽器前進後退
- Auto-refresh 在頁面可見時啟動，切走時停止，避免資源浪費
- 完整 CI/CD 回歸防護

**Non-Goals:**
- 不重寫 `hold-history-api`（既有 query/view 不動）
- 不做 Detail table 欄位 filter（Q3.2）
- 欄寬不持久化（Q3.3）
- 不做跨頁面共用的即時監控 framework（本次僅 hold-history 內）
- 不支援自訂 auto-refresh 間隔（後端 env 統一）

## Decisions

### Decision 1: 當日模式採「獨立 API」而非復用 query

**選擇**：新增 `POST /api/hold-history/today-snapshot`，獨立 cache namespace `hold_today:*`，TTL 60 秒

**替代方案**：擴充 `POST /api/hold-history/query` 用 `mode=today` 參數分流

**理由**：
- 當日模式的資料邊界（`RELEASETXNDATE IS NULL` 或 `release_day = today` 或 `hold_day = today`）與既有區間模式（`hold_day BETWEEN start AND end`）本質不同
- 獨立 API 讓 cache 策略（TTL、invalidation、namespace）可獨立最佳化
- 獨立 endpoint 在 route fuzz / real-infra smoke 中更容易斷言
- 既有 query/view endpoint 不受影響，降低回歸風險

### Decision 2: 當日模式 Record Type 語意重新定義，不沿用區間模式

**選擇**：
- `on_hold` → 所有現況仍在 hold 的 lot（`RELEASETXNDATE IS NULL`）**不限 hold_day**
- `new` → 今日新增（`hold_day = today`）
- `release` → 今日釋出（`release_day = today`）

**替代方案**：維持原 Record Type 語意（hold_day 在範圍內的 on_hold / new / released 子集）

**理由**：
- 當日模式使用者想問的是「現在狀況 / 今天動態」，和區間回顧的語意不同
- 區間模式下 Record Type 已於本 change 移除（使用者不會混用）
- 清楚的 label + tooltip 讓使用者理解「此 Record Type 在本模式下的意思」

### Decision 3: Auto-refresh 由前端計時器觸發，後端無推送

**選擇**：前端 `setInterval`（或 `setTimeout` 遞迴），頁面可見時啟動，不可見 / unmount 時清除

**替代方案**：SSE / WebSocket 推送

**理由**：
- TTL 60 秒的 pull 模式對 Oracle 壓力可預測（每人每分鐘一次 + 多人共享 cache）
- 不引入長連接複雜度
- 既有架構無 SSE / WebSocket 基礎，引入成本過高

**實作要點**：
- 使用 `document.visibilityState` + `visibilitychange` event 暫停背景計時
- 使用 `pagehide` / `beforeunload` 清除 timer
- auto-refresh 間隔讀 env（前端打 `/api/config` 取，或後端 render 時嵌入）；預設 60 秒

### Decision 4: 當日模式的「今日 Future Hold」採直覺定義 (Q1.3 選項 a)

**選擇**：`IS_FUTURE_HOLD = 1 AND hold_day = today`（單純看 `FUTUREHOLDCOMMENTS IS NOT NULL`）

**替代方案**：
- (b) `FUTURE_HOLD_FLAG = 0 AND hold_day = today`（PJMES043 原廠定義）
- (c) `IS_FUTURE_HOLD = 1 AND RN_FUTURE_REASON = 1 AND hold_day = today`（首次觸發）

**理由**（使用者已確認選 a）：
- 當日模式主打「今天發生了什麼」，使用者直覺上要看「今天有幾次 Future Hold 備註被填寫」
- PJMES043 原廠定義保留在區間模式的「累計 Future Hold」，兩邊語意並存不衝突
- Tooltip 文字需清楚區分兩種語意

### Decision 5: 模式切換的 URL state 管理

**選擇**：新增 `mode` 為 top-level URL param；模式切換時清空不適用的 params

| URL param | range 模式 | today 模式 |
| :--- | :--- | :--- |
| `mode` | `range` (或省略) | `today` |
| `start_date` / `end_date` | 必須 | 忽略（由 server 決定） |
| `hold_type` | 保留 | 保留（跨模式通用） |
| `record_type` | 忽略（本 change 移除此篩選） | 保留（新語意） |
| `reason` | 保留 | 保留 |
| `duration_range` | 保留 | 保留 |
| `page` / `per_page` | 保留 | 保留 |

模式切換邏輯：
- range → today：清空 `start_date` / `end_date`，`record_type` 重置為 default（`on_hold`）
- today → range：清空 `record_type`，日期回到 default（當月第一天 ~ 當月最後一天）
- 瀏覽器前進後退：讀 URL 的 mode 恢復該模式狀態

### Decision 6: 當日模式是否啟用前端 DuckDB-WASM local compute

**選擇**：**不啟用**——當日快照直接由 server 回傳已聚合結果，前端只顯示

**理由**：
- 當日模式的資料量相對小（現況 on_hold + 今日 new/release），server 聚合成本低
- Auto-refresh 需要確保資料新鮮，DuckDB-WASM 的 local cache 模型不適合
- 簡化前端邏輯，避免兩種模式維護兩套 compute path

### Decision 7: Detail table 欄寬實作

**選擇**：純 CSS grid-template-columns + JS pointer event 拖拉邊界，state 存 Vue reactive ref（非 localStorage）

**替代方案**：引入 `@tanstack/vue-table` 或 `vue-resizable-columns` library

**理由**：
- 欄位數量固定、功能單純，不值得引入 library
- 拖拉邏輯 < 50 行 JS，可控
- State 不持久化符合 Q3.3

### Decision 8: Pareto / Duration 圖在當日模式下的呈現

**選擇**：顯示，與當日 Record Type 連動
- `on_hold` → 現況所有 hold 的 reason 分佈 / duration 分佈（duration 用 SYSDATE - HOLDTXNDATE）
- `new` → 今日新增的 reason 分佈 / duration 分佈（新增不久，duration 可能都在 `<4h`）
- `release` → 今日 release 的 reason 分佈 / duration 分佈（已解除）

**替代方案**：當日模式隱藏 Pareto / Duration（資料量可能稀疏）

**理由**（使用者 Q1.4 確認顯示 + RecordType 連動）：
- 現場會想看「今天新增的 Hold 都是什麼原因」「現況還在 Hold 的原因分佈」
- 有數據就顯示，無數據時 EmptyState 提示
- 統一三種 Record Type 的圖表行為，不特殊化

## Risks / Trade-offs

| Risk | Mitigation |
| :--- | :--- |
| Auto-refresh 在多人線上時加重 Oracle 負擔 | TTL 60 秒 + cache 共享；soak test 跑 30 min 驗證 Oracle connection pool 不爆 |
| 當日「on_hold 全體」資料量大（跨月老 lot） | 後端 limit（`FETCH FIRST 10000 ROWS ONLY`）+ detail list pagination；超量時回傳警示 meta |
| 模式切換 URL state 踩邊界（前進後退、同開多頁） | E2E 大量覆蓋；useFilterOrchestrator 做單元測試 |
| 「on_hold 不限 hold_day」和區間模式資料源邏輯不同，parity 難驗證 | 本 change 不做 parity；當日 snapshot 獨立，靠 E2E + real-infra smoke 驗證 |
| auto-refresh 背景執行被瀏覽器 throttle | 使用 `requestIdleCallback` + visibility check；記錄 miss count 超過 3 次時顯示「已暫停自動更新」 |
| 欄寬拖拉在 touch device 不穩 | `pointerdown/move/up` 統一事件；不支援 touch 時 degrade 為固定寬 |
| 新 API 未通過 real-infra-smoke 被誤 merge | Stage 4a smoke 必須把 POST /today-snapshot 納入 dispatch list |
| Detail table 的 list 在當日模式下的 data source（區間 spool vs today snapshot） | Decision 3 確認當日模式 list 也從 today-snapshot 回傳，不用區間 spool |

## Migration Plan

1. **前置**：`hold-history-metric-refinement` 已 land（或平行 feature branch merge）
2. **後端**：新增 today-snapshot SQL / service / route，env 設定；單元 + 路由 fuzz 綠燈
3. **前端**：FilterBar 模式切換、App.vue mode-aware 渲染、SummaryCards mode prop、auto-refresh timer；E2E 跑通
4. **CI 更新**：
   - real-infra-smoke 納入 POST /today-snapshot
   - soak-tests 新增 auto-refresh 穩定性 job
   - released-pages-hardening-gates 包含模式切換驗證
5. **部署**：單次部署；rollout note 標註「需清理使用者書籤中的 URL（舊 record_type=...格式可能失效）」

**Rollback**：
- 後端 today-snapshot 可獨立下線（保留 endpoint 回 404），前端偵測失敗後回到 range-only
- 前端模式切換可 feature flag `HOLD_TODAY_MODE_ENABLED`；flag=false 時只顯示 range 模式

## Open Questions

- **auto-refresh 間隔**：60 秒 vs 120 秒 vs 180 秒？需和實際使用場景確認（業務方希望多快刷新）
- **on_hold 資料量上限**：10000 行 vs 不設上限（相信 Oracle）？需跑實際公司資料驗證
- **Tab 設計**：FilterBar 上用按鈕切換 vs 用 Tab 組件 vs 頁面最上方 Radio？交付 UX review
- **「今日 Future Hold」文案**：如何和區間模式的「累計 Future Hold」區別，避免使用者混淆？
- **auto-refresh 的視覺提示**：右上角倒數計時？脈衝動畫？無提示？
- **Feature flag 範圍**：要不要讓部分使用者先試用（基於 user id）？還是全體開放？
