## Context

異常偵測系統已完成：後端 4 個 DuckDB SQL 偵測器（yield Z-score、reject spike、hold outlier、equipment deviation）+ 4 個 GET API 端點 + 前端 `AnomalyBadge.vue`。目前 badge 分散在各頁面，使用者需逐頁瀏覽才能掌握異常狀態。

Portal-shell header 右側現有 `HealthStatus` 元件（30 秒輪詢 `/health`），顯示連線/快取狀態。異常指標可放在其旁邊，採用相同的輪詢節奏。

## Goals / Non-Goals

**Goals:**
- 在 portal-shell header 提供一眼可見的異常計數指標
- 提供獨立的異常總覽頁面，集中展示 4 種偵測器的結果與計算邏輯
- 聚合 API 避免 header 每次輪詢發 4 個請求

**Non-Goals:**
- 不修改現有 4 個偵測端點的行為或參數
- 不引入通知/推播機制（僅 pull-based 輪詢）
- 不加入異常歷史趨勢追蹤

## Decisions

### D1: 聚合端點 vs 前端並行呼叫

**選擇: 新增 `GET /api/analytics/anomaly-summary` 聚合端點**

替代方案：前端直接並行呼叫 4 個現有端點。但 header 每 30 秒輪詢一次，每個連線用戶會產生 4×2/min = 8 req/min 的額外負載。聚合端點降為 2 req/min，且只回傳計數不回傳完整清單，回應體更小。

實作方式：`get_anomaly_summary()` 在 service 層內部呼叫 4 個現有 detect 函式，只提取計數。單一偵測器失敗時 fallback 為 count=0，不影響其他偵測器。

### D2: 聚合端點回應結構

```json
{
  "success": true,
  "data": {
    "total_count": 15,
    "severity": "critical",
    "breakdown": {
      "yield":     { "count": 5, "severity": "warning",  "label": "良率異常" },
      "reject":    { "count": 3, "severity": "warning",  "label": "報廢突增" },
      "hold":      { "count": 7, "severity": "critical", "label": "Hold 離群" },
      "equipment": { "count": 0, "severity": "ok",       "label": "稼動偏離" }
    }
  },
  "meta": { "timestamp": "...", "latency_s": 0.45 }
}
```

嚴重度分級：`ok` (count=0), `warning` (1-5), `critical` (>5)。overall = max。

### D3: Header 指標元件放置位置

**選擇: `<AnomalyIndicator />` 放在 `<HealthStatus />` 前面**

在 `.shell-header-right` 中順序為：AnomalyIndicator → HealthStatus → admin-entry。異常指標比連線狀態更需要即時關注，放在更靠前的位置。

### D4: 指標元件的 Feature Flag 處理

元件呼叫 summary API 時，若收到 404（feature flag 關閉），整個元件隱藏（`v-if` 控制），不顯示任何 UI。不需要額外的前端 feature flag。

### D5: 異常總覽頁面作為 Standalone Drilldown Route

**選擇: 加入 `STANDALONE_DRILLDOWN_ROUTES`**

替代方案：在側邊欄導航中加入選單項目。但此頁面主要從 header 指標進入，不需要佔據側邊欄空間。參照 `/wip-detail` 和 `/hold-detail` 的模式，作為不需要側邊欄入口的 drilldown 頁面。

### D6: 計算邏輯說明方式

**選擇: 靜態文字寫在前端元件中**

演算法參數（window 天數、threshold 值）目前是後端 service 的預設值，變動頻率極低。不需要從 API 動態取得，直接在前端卡片中以靜態中文文字呈現：

| 偵測器 | 說明文字 |
|--------|---------|
| 良率異常 | Z-score = (yield - rolling_avg) / rolling_std，window=7天，threshold=\|Z\|>2.0 |
| 報廢突增 | pct_change = (current - baseline) / baseline × 100，window=7天基線，threshold>50% |
| Hold 離群 | 95th percentile of hold_hours，超過此門檻的 hold 記錄 |
| 稼動偏離 | deviation = baseline_ou - current_ou，window=30天，threshold>15pp |

### D7: CSS 策略

| 元件 | CSS 位置 | 作用域 |
|------|---------|--------|
| AnomalyIndicator | `portal-shell/style.css` | Shell chrome 範疇（與 `.health-trigger` 同級） |
| anomaly-overview 頁面 | `anomaly-overview/style.css` | `.theme-anomaly-overview`（遵循 CSS 合約 §4.2、§4.3） |

所有顏色使用 `tailwind.config.js` 語義 token：
- 狀態色：`state.warning` (#f59e0b)、`state.danger` (#ef4444)
- 卡片：`bg-surface-card`、`border-stroke-soft`、`rounded-card`
- 文字：`text-text-primary`、`text-text-secondary`

動畫使用 motion design tokens：`--motion-fast (150ms)`、`--motion-normal (200ms)`、`--motion-ease`

### D8: 異常總覽頁面資料取得策略

頁面 onMount 時：
1. 呼叫 `GET /api/analytics/anomaly-summary` 取計數（快速渲染摘要卡片）
2. 並行呼叫 4 個現有詳細端點取完整清單（各區塊獨立 loading 狀態）

4 個詳細端點已存在且穩定，不需要新的 API。

### D9: 移除各頁面分散的 AnomalyBadge

**選擇: 完全移除，改由 header 集中管理**

各頁面（yield-alert-center、hold-history、reject-history、resource-history）目前各自：
1. import `AnomalyBadge` 元件
2. 宣告 `anomalyCount` / `anomalyItems` / `anomalyLoading` 等 ref
3. 在 `onMounted` 中呼叫對應的 anomaly API（fire-and-forget）
4. 在 template 中渲染 `<AnomalyBadge />`

這些全部移除。異常資訊改由 header `AnomalyIndicator` 統一呈現，點擊進入總覽頁面查看詳情。

**AnomalyBadge.vue 元件本身:** 移除後 4 個頁面都不再引用，無其他使用者，應一併刪除 `frontend/src/shared-ui/components/AnomalyBadge.vue`。

## Risks / Trade-offs

**[風險] 聚合端點延遲可能較高** — 內部序列呼叫 4 個偵測器，最差情況 ~2 秒。
→ 緩解：header 指標顯示上次成功結果 + loading 狀態，不阻塞 UI。各偵測器獨立 try/catch，單一失敗不影響其他。

**[風險] Feature flag 關閉時的 404 處理** — 首次載入時 AnomalyIndicator 會閃一下才隱藏。
→ 緩解：元件初始狀態為隱藏，只在首次成功回應後才顯示。

**[取捨] 計算邏輯靜態寫死在前端** — 若後端調整閾值，前端說明文字需手動同步。
→ 接受：閾值變動頻率極低（預估每季最多一次），同步成本可忽略。
