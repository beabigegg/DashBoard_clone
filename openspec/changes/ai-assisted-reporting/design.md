## Context

MES Dashboard 目前有 15+ 分析頁面，每個頁面有獨立的篩選器、圖表和明細表。操作員日常需要：
1. 在多頁面間切換以交叉比對數據
2. 人工判斷圖表趨勢是否異常
3. 手動操作多層篩選器進行鑽研

後端已有成熟的基礎設施：
- DuckDB SQL runtime 對 Parquet spool 執行分析查詢（3 個既有模組）
- 完整的 service 層（~40 個公開函式）覆蓋所有查詢領域
- QueryBuilder + SQLLoader 提供安全參數化查詢
- Redis DataFrame cache + Parquet 序列化
- RQ async job 處理長時間查詢

部署限制：7GB VM，MemoryHigh=5GB / MemoryMax=6GB，Oracle 連線池 5+10。

## Goals / Non-Goals

**Goals:**
- 提供系統化的統計異常偵測，取代人工看圖判斷（Phase 1）
- 提供自然語言查詢介面，降低跨頁面鑽研的操作門檻（Phase 2）
- 零新依賴實現 Phase 1（延伸 DuckDB）
- 製造資料不離開內網（LLM 僅做意圖解析）
- Token 成本可控（日均 < $1 USD）

**Non-Goals:**
- 不建置本地 ML 模型訓練/推論基礎設施（Phase 3 保留評估，不在此次範圍）
- 不讓 LLM 生成或接觸 SQL — 只呼叫已驗證的 service 函式
- 不做預測性分析（良率預測、設備故障預測）
- 不取代現有頁面 — AI 是輔助入口，不是替代品
- 不處理自然語言寫入操作（Hold/Release 等）

## Decisions

### Decision 1: Phase 1 使用 DuckDB 窗口函數而非 ML 模型

**選擇**：DuckDB SQL 窗口函數（STDDEV_POP, PERCENTILE_CONT, moving average）

**替代方案**：scikit-learn Isolation Forest / Prophet 時間序列

**理由**：
- 零新依賴 — DuckDB 已在 3 個 SQL runtime 模組中使用
- 記憶體影響極小 — 不需載入模型或額外 library
- 統計方法（Z-score > 2σ, 95th percentile）對製造數據的異常偵測已足夠
- 可直接在現有 Parquet spool 上執行，不需資料搬運
- 遵循 `reject_cache_sql_runtime.py` 既有模式，維護成本低

### Decision 2: LLM 採用「Function Registry + 意圖解析」而非「Text-to-SQL」

**選擇**：LLM 從能力目錄中選擇函式 + 填入參數 → 後端調度現有 service

**替代方案**：LLM 直接生成 SQL 查詢

**理由**：
- 安全性 — 不需要把 table schema 和 column names 送給 LLM
- 可靠性 — 函式參數有 enum 限制和 schema validation，幻覺造成的損害有上界
- 維護性 — 新增查詢能力只需在 registry 加一個 entry，不需重新訓練或調整 prompt
- 現有 service 層已涵蓋所有查詢場景（~40 個函式），不需要 SQL 層的靈活性
- QueryBuilder bind variables 自動防止 SQL injection

### Decision 3: 三級 Token 控制策略

**選擇**：Level 0（純意圖解析，~3K tokens）為預設；Level 1（壓縮摘要，~5K tokens）按需啟用

**替代方案**：完整結果回傳 LLM（~15-20K tokens/次）

**理由**：
- 成本控制 — Level 0 + Haiku 每次查詢 < $0.001
- 隱私保護 — Level 0 完全不將查詢結果送出
- 實用性 — 大多數查詢只需意圖解析，前端直接渲染圖表即可
- 後端 `ai_result_summarizer.py` 將 Pareto 50 項壓縮為 ~80 tokens，在需要 LLM 分析時仍保持低成本
- 清單/明細類結果永遠不送 LLM（只回傳「共 N 筆」）

### Decision 4: 後端代理模式呼叫 LLM API

**選擇**：Flask 後端代理 LLM API 請求

**替代方案**：前端直接呼叫 LLM API

**理由**：
- API key 不上前端 — 避免 key 洩漏
- 無需 CSP 變更 — 不需在 `connect-src` 加外部域名
- 集中審計 — 所有 AI 查詢在後端記錄
- Rate limit 在後端統一控制

### Decision 5: 意圖解析用 Haiku，摘要分析用 Sonnet

**選擇**：雙模型策略

**理由**：
- 意圖解析是結構化 JSON 輸出，Haiku 足以勝任且速度快、成本低
- 摘要分析需要較強的推理能力，Sonnet 品質更好
- 混合使用日成本 $0.10-0.50（vs 全用 Sonnet 的 $1-3）

## Frontend Architecture

### 元件層級與歸屬

```
frontend/src/
├── portal-shell/
│   └── App.vue                          # 整合 AiChatTrigger + AiChatPanel
│
├── shared-ui/components/
│   ├── AiChatTrigger.vue               # [新增] 固定位置觸發按鈕（右下角 FAB）
│   ├── AiChatPanel.vue                 # [新增] 右側滑出對話面板
│   ├── AiChatMessage.vue               # [新增] 單則訊息渲染（問題/回應/錯誤）
│   ├── AiChartRenderer.vue             # [新增] 根據 query_used 自動選擇圖表類型
│   ├── AnomalyBadge.vue                # [新增] 通用異常標記（含 popover）
│   └── StatusBadge.vue                 # [既有] 參考其 tone 模式
│
├── shared-composables/
│   └── useAiChat.js                    # [新增] AI 對話狀態管理
│
├── yield-alert-center/App.vue          # [修改] 整合 AnomalyBadge
├── reject-history/App.vue              # [修改] 整合 AnomalyBadge
├── hold-overview/App.vue               # [修改] 整合 AnomalyBadge
└── resource-status/App.vue             # [修改] 整合 AnomalyBadge
```

### Decision 6: AI Chat Panel 採用右側滑出面板而非 Modal/內嵌區塊

**選擇**：固定位置右側滑出面板（類似 customer support chat widget）

**替代方案 A**：Modal 彈窗
**替代方案 B**：頁面內嵌聊天區塊

**理由**：
- Portal shell 現有架構是「左側 sidebar + 右側 main content」— 右側面板自然對稱
- 滑出面板不遮擋主頁面內容 — 操作員可同時看圖表和 AI 回應
- Modal 會完全中斷操作流，且無法同時參照頁面數據
- 內嵌區塊需修改每個頁面的 layout，影響範圍過大
- 面板關閉後對話保留，隨時可重開 — 符合多輪鑽研的工作流

### Decision 7: AnomalyBadge 基於既有 StatusBadge tone 模式擴展

**選擇**：新建 `AnomalyBadge.vue`，參考 `StatusBadge.vue` 的 tone 系統（neutral/success/warning/danger），增加 popover 展開

**替代方案**：直接修改 StatusBadge 加入 popover

**理由**：
- StatusBadge 是純展示元件（無互動），加入 popover 會改變其職責
- AnomalyBadge 需要額外的 props（items、type）和點擊互動
- 分離保持 StatusBadge 的簡單性，避免影響 100+ 處既有引用

### AI Chat Panel 佈局設計

```
┌─────────────────────────────────────────────────────────────┐
│ Portal Shell                                                │
│ ┌──────────┬───────────────────────────┬──────────────────┐ │
│ │          │                           │   AI Chat Panel  │ │
│ │ Sidebar  │     Main Content          │ ┌──────────────┐ │ │
│ │ (既有)   │     (既有頁面)             │ │ 📋 AI 助手   │ │ │
│ │          │                           │ │ [新對話]  [✕] │ │ │
│ │          │                           │ ├──────────────┤ │ │
│ │          │                           │ │              │ │ │
│ │          │                           │ │ 對話歷史     │ │ │
│ │          │                           │ │ ┌──────────┐ │ │ │
│ │          │                           │ │ │ 使用者問題│ │ │ │
│ │          │                           │ │ └──────────┘ │ │ │
│ │          │                           │ │ ┌──────────┐ │ │ │
│ │          │                           │ │ │ AI 回應   │ │ │ │
│ │          │                           │ │ │ [圖表]    │ │ │ │
│ │          │                           │ │ │ ─────────│ │ │ │
│ │          │                           │ │ │ 建議 chips│ │ │ │
│ │          │                           │ │ └──────────┘ │ │ │
│ │          │                           │ │              │ │ │
│ │          │                           │ ├──────────────┤ │ │
│ │          │                           │ │ [輸入問題...]│ │ │
│ │          │                           │ │         [送出]│ │ │
│ │          │  [🤖]← AiChatTrigger     │ └──────────────┘ │ │
│ └──────────┴───────────────────────────┴──────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

**面板規格：**
- 寬度：`380px`（desktop），`100vw`（mobile ≤ 768px 全螢幕）
- 高度：`calc(100vh - var(--shell-header-height))`（與 shell content 同高）
- 位置：`position: fixed; right: 0; top: var(--shell-header-height)`
- Z-index：與 sidebar 同層級（sidebar 用 1000，chat panel 用 1001）
- 動畫：`transform: translateX(100%)` → `translateX(0)`，使用 `--motion-normal (200ms)` + `--motion-ease`
- 背景遮罩：mobile 時加半透明 overlay（同 sidebar mobile 模式）

**觸發按鈕 (AiChatTrigger)：**
- 位置：`position: fixed; right: 24px; bottom: 24px`
- 樣式：`w-12 h-12 rounded-full bg-brand-600 text-white shadow-shell`
- Hover：`bg-brand-700 shadow-lg`
- 面板開啟時隱藏觸發按鈕

### AI 對話訊息渲染設計

每則 AI 回應 (`AiChatMessage.vue`) 的渲染結構：

```
┌────────────────────────────────────┐
│ 🤖 AI 助手                        │
│                                    │
│ "WB 線最近 7 天不良率最高的原因..." │  ← explanation 文字
│                                    │
│ 使用了：不良原因排行               │  ← query_used 標籤（StatusBadge tone-neutral）
│                                    │
│ ┌────────────────────────────────┐ │
│ │    ████                        │ │  ← 內嵌 ECharts 圖表
│ │  ████████                      │ │    （Pareto / 趨勢 / KPI 卡片）
│ │ ██████████  ----累計%          │ │    高度: 200px (compact mode)
│ │  Reason A  B  C  D  E         │ │
│ └────────────────────────────────┘ │
│                                    │
│ [查看 Reason A 的 Lot 清單]        │  ← drill-down suggestion chips
│ [比較前 7 天的趨勢]               │    （clickable, 點擊 = 新問題提交）
│ [查看哪些材料相關]                 │
└────────────────────────────────────┘
```

**圖表渲染策略 (`AiChartRenderer.vue`)：**

| `query_used` | 圖表類型 | ECharts 元件 | 高度 |
|---|---|---|---|
| `*_pareto` | Bar + Line（雙Y軸 Pareto） | BarChart + LineChart | 200px |
| `*_trend` | Line（時間序列） | LineChart | 180px |
| `*_summary`, `wip_summary` | KPI 卡片（非 ECharts） | 自定義 flexbox | auto |
| `*_matrix` | Mini heatmap | HeatmapChart | 160px |
| `*_list`, `hold_list` | Compact 表格 | HTML table | max 10 rows, scrollable |

圖表使用 compact 模式：
- 隱藏 legend（空間有限）
- 簡化 tooltip（只顯示值）
- `autoresize: { throttle: 100 }` 跟隨面板大小
- 遵循現有 `ParetoSection.vue` 的 VChart import 模式

### useAiChat composable 設計

```javascript
// frontend/src/shared-composables/useAiChat.js
export function useAiChat() {
  // ── 狀態 ──
  const messages = ref([]);         // [{ role: 'user'|'ai'|'error', content, chartData?, querUsed?, suggestions? }]
  const isOpen = ref(false);        // 面板開關
  const isLoading = ref(false);     // 等待 LLM 回應
  const isRateLimited = ref(false); // 429 鎖定狀態
  const context = computed(/* 最近 3 輪的 intent + params + summary */);

  // ── 方法 ──
  async function submitQuestion(question) { /* POST /api/ai/query, 管理 loading/error */ }
  function submitSuggestion(suggestion) { /* 將 suggestion 作為新問題提交 */ }
  function resetConversation() { /* 清空 messages + context */ }
  function togglePanel() { /* isOpen toggle */ }

  // ── 生命週期 ──
  // 使用 useRequestGuard 防止 race condition
  // Rate limit 鎖定 20 秒後自動解除（setTimeout）
  // AbortController 在新請求時取消舊請求

  return { messages, isOpen, isLoading, isRateLimited, context,
           submitQuestion, submitSuggestion, resetConversation, togglePanel };
}
```

**與 portal-shell 整合：**
```vue
<!-- portal-shell/App.vue -->
<script setup>
import { useAiChat } from '../shared-composables/useAiChat.js';
const aiChat = useAiChat();
</script>

<template>
  <div class="shell" :class="{ 'ai-panel-open': aiChat.isOpen.value }">
    <!-- 既有 sidebar + content -->
    <AiChatTrigger v-if="!aiChat.isOpen.value" @click="aiChat.togglePanel" />
    <AiChatPanel v-if="aiChat.isOpen.value" v-bind="aiChat" />
  </div>
</template>
```

### AnomalyBadge 設計

```
┌─── 頁面 header ──────────────────────────────────────┐
│ Yield Alert Center  [⚠ 3 項異常]  ← AnomalyBadge   │
│                          │                            │
│                          ▼ (click 展開 popover)       │
│                     ┌──────────────────────────┐      │
│                     │ 🔴 WB/FBGA: Z=-3.2       │      │
│                     │ 🔴 DB/QFP:  Z=-2.8       │      │
│                     │ 🟡 SOLDER/BGA: Z=-2.1    │      │
│                     │ ──────────────────────── │      │
│                     │ 查看全部異常 →            │      │
│                     └──────────────────────────┘      │
└───────────────────────────────────────────────────────┘
```

**AnomalyBadge Props:**
```javascript
{
  count: Number,       // 異常數量
  items: Array,        // top-3 異常項目 [{ label, value, severity }]
  type: String,        // 'yield' | 'reject' | 'hold' | 'equipment'
  loading: Boolean,    // 載入中狀態
}
```

**樣式：**
- 正常：`bg-state-warning/10 text-state-warning border border-state-warning/20 rounded-full px-3 py-1`
- 危急（count > 5）：`bg-state-danger/10 text-state-danger border-state-danger/20`
- Popover：`bg-surface-card shadow-panel rounded-card p-3`，絕對定位於 badge 下方
- 動畫：badge 出現時 `scale-in`（`--motion-fast`），popover 用 `fade-in`

**各頁面整合模式：**
```vue
<!-- yield-alert-center/App.vue -->
<header class="header">
  <h1>Yield Alert Center</h1>
  <AnomalyBadge
    v-if="anomalyFeatureEnabled"
    :count="yieldAnomalies.length"
    :items="topAnomalies"
    :loading="anomalyLoading"
    type="yield"
  />
</header>
```

API 呼叫在頁面 `onMounted` 時 parallel 發起（與既有資料載入共用 `Promise.all`），不阻塞主頁面渲染。

### 樣式規範

**新增 CSS 檔案：**
- `frontend/src/portal-shell/ai-chat.css` — Chat panel 樣式，scoped under `.theme-portal-shell`（須在 `portal-shell/App.vue` 的 `.shell` 根 div 加入此 class）
- AnomalyBadge 使用 `<style scoped>` + Tailwind utilities，不需獨立 CSS 檔

**遵循合約：**
- 所有顏色使用 `tailwind.config.js` 的 semantic tokens（`state.warning`、`state.danger`、`surface.card`）
- 不使用 hard-coded hex（ECharts 圖表內的顏色例外，但須集中在 AiChartRenderer 內）
- Feature-scoped：chat 樣式在 `.theme-portal-shell` 下，badge 在各頁面 theme class 下
- 新增 CSS 檔案須更新 `contract/css_inventory.md`

### 響應式設計

| 斷點 | Chat Panel | AnomalyBadge | 觸發按鈕 |
|------|-----------|--------------|---------|
| ≥ 769px | 右側 380px 面板，不影響 main content | 行內顯示於 header | 右下角 FAB |
| ≤ 768px | 全螢幕覆蓋 + backdrop overlay | 收縮為純 icon（tooltip 顯示數量） | 右下角 FAB（縮小為 40px） |

## Token 用量與成本試算

### 單次查詢 Token 模型

| 組件 | Input tokens | Output tokens | 說明 |
|------|-------------|--------------|------|
| System prompt | 2,500 | — | 固定，含 ~20 個函式描述 + 參數 + 工作站代碼 |
| 使用者問題 | 75 | — | 中文問句中位數 |
| 每輪上下文增量 | 300 | — | user 150 + assistant intent 150 |
| Intent JSON 回應 | — | 150 | Haiku 結構化輸出 |
| Level 1 摘要 prompt | 1,715 | — | Sonnet: 精簡 prompt 1,500 + 壓縮摘要 140 + 問題 75 |
| Level 1 分析回應 | — | 300 | Sonnet 中文分析文字 |

### 定價基準（Claude 2025）

| 模型 | Input ($/M tokens) | Output ($/M tokens) |
|------|-------------------|-------------------|
| Claude Haiku 4.5 | $0.80 | $4.00 |
| Claude Sonnet 4/4.5 | $3.00 | $15.00 |

### 四種使用情境試算

#### 每日 Token 用量

| 情境 | 查詢/日 | L0:L1 比 | 平均輪數 | Haiku Input | Haiku Output | Sonnet Input | Sonnet Output | 總 Tokens |
|------|--------|---------|---------|-------------|-------------|-------------|-------------|-----------|
| 1 輕度（試用） | 30 | 80:20 | 1.5 | 120,375 | 6,750 | 15,435 | 2,700 | 145,260 |
| 2 中度（單線） | 100 | 70:30 | 2.0 | 545,000 | 30,000 | 102,900 | 18,000 | 695,900 |
| 3 重度（全廠） | 500 | 60:40 | 2.5 | 3,518,750 | 187,500 | 857,500 | 150,000 | 4,713,750 |
| 4 極端（壓測） | 1,000 | 50:50 | 3.0 | 8,625,000 | 450,000 | 2,572,500 | 450,000 | 12,097,500 |

#### 成本總覽

| 情境 | 每日成本 | 每月成本 | 每次查詢成本 | 全 Sonnet 月成本 | 雙模型節省 |
|------|---------|---------|------------|----------------|-----------|
| 1 輕度 | $0.21 | **$6.30** | $0.007 | $16.48 | 62% |
| 2 中度 | $1.13 | **$34.04** | $0.011 | $79.91 | 57% |
| 3 重度 | $8.39 | **$251.63** | $0.017 | $545.74 | 54% |
| 4 極端 | $23.17 | **$695.03** | $0.023 | $1,412.78 | 51% |

#### 計算範例（情境 2 詳細拆解）

```
100 次/日，70% L0 (70次)，30% L1 (30次)，全部 2 輪

── Level 0 Haiku（70 次 × 2 輪）──
每次 input: 第1輪 2,575 + 第2輪 2,875 = 5,450
每次 output: 150 × 2 = 300
日 input: 70 × 5,450 = 381,500
日 output: 70 × 300 = 21,000

── Level 1 Haiku 部分（30 次 × 2 輪）──
日 input: 30 × 5,450 = 163,500
日 output: 30 × 300 = 9,000

── Level 1 Sonnet 部分（30 次 × 2 輪）──
每次 input: 1,715 × 2 = 3,430
每次 output: 300 × 2 = 600
日 input: 30 × 3,430 = 102,900
日 output: 30 × 600 = 18,000

── 每日成本 ──
Haiku:  (545,000/1M) × $0.80 + (30,000/1M) × $4.00 = $0.436 + $0.120 = $0.556
Sonnet: (102,900/1M) × $3.00 + (18,000/1M) × $15.00 = $0.309 + $0.270 = $0.579
合計: $1.135/日 → $34.04/月
```

### 成本敏感度分析

| 調整項 | 影響 |
|-------|------|
| **全改 Sonnet（不用 Haiku）** | 月成本增加 2.0x ~ 2.6x |
| **Level 1 比例每增 10%** | 月成本約增 15-20%（Sonnet output $15/M 是主要驅動） |
| **對話輪數每增 1 輪** | token 約增 40%（因上下文累積） |
| **加入 prompt caching** | System prompt 2,500 tokens 可快取，預估省 5-10% |

### 關鍵洞察

- **成本主要驅動因子**：Level 1 的 Sonnet output tokens（$15/M）佔比最高
- **雙模型策略效益顯著**：相比全 Sonnet 節省 51%-62%
- **中度使用（單線上線）月成本 ~$34** — 遠低於一台設備的維護成本
- **建議初期**：以 Level 0 為主（>80%），僅在使用者主動要求分析時啟用 Level 1

## Risks / Trade-offs

### Phase 1 風險

**[Z-score 對非常態分佈資料失準]** → 對每個指標先做分佈檢查，偏態嚴重時改用 percentile-based 偵測。初期以 percentile 為主、Z-score 為輔。

**[異常過多導致警報疲勞]** → 提供靈敏度調節（2σ/3σ 切換）；前端只顯示 top-N 異常；Feature flag 控制漸進開放。

### Phase 2 風險

**[LLM 意圖解析錯誤]** → 參數 schema validation 攔截不合法值；intent 白名單阻擋未知函式；前端顯示「AI 理解為：XXX」讓使用者確認。

**[資料隱私 — 結果摘要含敏感資訊]** → Level 0 模式完全不送結果；Level 1 的摘要內容（reason 名稱等）需資安政策明確核准後才啟用。

**[LLM API 不可用]** → AI 查詢失敗不影響現有功能；前端顯示降級提示「AI 助手暫時不可用，請使用一般查詢」。

**[外部 API 延遲]** → LLM 回應通常 1-3 秒；設置 10 秒 timeout；前端顯示 loading 狀態。

**[成本失控]** → Rate limit 3 req/min/user；每日 token 用量監控；Redis 記錄每次查詢的 token 數。

### 共通風險

**[Oracle 連線池壓力]** → AI 觸發的查詢走 slow-query pool（size=2）；不增加主連線池負擔。

**[操作員不信任 AI]** → AI 結果旁邊始終顯示原始數據和鑽研連結；異常標記可點擊查看計算依據。

## Migration Plan

### Phase 1 部署
1. Feature flag `ANALYTICS_ANOMALY_DETECTION_ENABLED=false` 部署全部程式碼
2. 內部測試：用已知歷史異常資料回測 Z-score/percentile 準確度
3. 開放 flag 給 QA 環境
4. 調整靈敏度閾值
5. 正式環境 flag 開放

### Phase 2 部署
1. 通過企業資安審查（外部 API 連線許可）
2. Feature flag `AI_QUERY_ENABLED=false` 部署
3. 內部測試：10 個常見查詢意圖解析正確率 > 90%
4. Beta 用戶群開放
5. 監控 token 用量和 API 成本
6. 全面開放

### Rollback
- 關閉 feature flag 即可完全停用，不影響任何現有功能
- 無 schema migration、無資料結構變更、無破壞性改動

## Open Questions

1. **資安審查時程**：Phase 2 的外部 LLM API 連線需要多久的審查流程？是否有可能部署內網 LLM？
2. **Level 1 摘要的隱私邊界**：reject reason 名稱、workcenter group 名稱是否允許送至外部 API？
3. **異常偵測閾值**：初始 Z-score 閾值設為 2σ 是否合適？需要產線工程師校準。
4. **AI 查詢的使用者範圍**：是否所有使用者都能使用 AI 查詢，還是限定角色？
