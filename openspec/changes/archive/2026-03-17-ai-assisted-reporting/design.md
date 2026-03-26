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

### LLM API 環境（實測驗證 2026-03-17）

- **API Endpoint**: `https://ollama_pjapi.theaken.com/v1/chat/completions`（公司內網）
- **可用模型**: `gpt-oss:120b`（本地 llama.cpp，唯一穩定可用）
- **API 格式**: OpenAI-compatible（`/v1/chat/completions`）
- **Context Window**: **16,384 tokens**（實測確認，超過回傳 400 `exceed_context_size_error`）
- **認證**: `Authorization: Bearer <API_KEY>`
- **TLS**: 內網 hostname mismatch — `curl` 可正常連線，Python `requests` 需 `verify=False`
- **回應特性**: 思考過程放在 `reasoning_content`，JSON 結構化回答放在 `content`（需 system prompt 明確指定格式）
- **速度**: ~25ms/token，單輪意圖解析約 2.5-4 秒
- **Stateless API**: 伺服器端不保留對話記憶，每次請求需傳完整 messages 陣列
- **零 API 費用**: 內網自建模型，無 token 計費

## Goals / Non-Goals

**Goals:**
- 提供系統化的統計異常偵測，取代人工看圖判斷（Phase 1）✅ 已完成
- 提供自然語言查詢介面，降低跨頁面鑽研的操作門檻（Phase 2）
- 零新 Python 依賴（Phase 2 使用 `requests` 呼叫 OpenAI-compatible API）
- 製造資料不離開內網 — LLM 僅做意圖解析，查詢結果不傳給 LLM
- 支援 5 輪多輪對話，含 context 上限偵測

**Non-Goals:**
- 不建置本地 ML 模型訓練/推論基礎設施（Phase 3 保留評估，不在此次範圍）
- 不讓 LLM 生成或接觸 SQL — 只呼叫已驗證的 service 函式
- 不做預測性分析（良率預測、設備故障預測）
- 不取代現有頁面 — AI 是輔助入口，不是替代品
- 不處理自然語言寫入操作（Hold/Release 等）
- 不做 LLM 結果摘要分析 — 僅做意圖解析，結果由前端直接渲染

## Decisions

### Decision 1: Phase 1 使用 DuckDB 窗口函數而非 ML 模型 ✅ 已實作

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
- **實測驗證**：gpt-oss:120b 能正確從函式目錄中選擇函式並填入參數（5/5 正確率，含上下文推斷）

### Decision 3: 純意圖解析模式（取代原三級 Token 策略）

**選擇**：僅做意圖解析（LLM → JSON intent → 後端調度 → 前端渲染），不做 LLM 結果摘要

**原設計**：三級策略（L0 純意圖 / L1 壓縮摘要 / L2 完整回傳）

**調整理由**：
- gpt-oss:120b 回應速度 ~3-4 秒/次，若加 L1 摘要需兩次 LLM call（6-8 秒），UX 太差
- 內網自建模型零費用，成本控制不再是分級的驅動因素
- 隱私最優 — 查詢結果完全不傳給 LLM
- 前端直接渲染圖表/表格比 LLM 文字摘要更直觀
- 後續如需摘要能力，可在此架構上擴展（加一個 `ai_result_summarizer.py`），不影響現有流程

### Decision 4: 後端代理模式呼叫 LLM API

**選擇**：Flask 後端代理 LLM API 請求

**替代方案**：前端直接呼叫 LLM API

**理由**：
- API key 不上前端 — 避免 key 洩漏
- 無需 CSP 變更 — 不需在 `connect-src` 加外部域名
- 集中審計 — 所有 AI 查詢在後端記錄
- Rate limit 在後端統一控制

### Decision 5: 單模型策略（取代原雙模型 Haiku + Sonnet）

**選擇**：所有 LLM 呼叫統一使用 `gpt-oss:120b`

**原設計**：意圖解析用 Claude Haiku，摘要分析用 Claude Sonnet

**調整理由**：
- 實際可用 API 只有 `gpt-oss:120b` 一個模型穩定可用
- 該模型為公司內網自建（llama.cpp），零 API 費用
- 取消 L1 摘要後不需要雙模型策略
- 環境變數簡化為 `AI_MODEL`（單一設定）

### Decision 6: 5 輪多輪對話 + Context 上限偵測 + Redis 儲存

**選擇**：後端管理對話狀態，存在 Redis，最多 5 輪，含 context token 上限偵測

**替代方案 A**：前端管理對話上下文（原設計 useAiChat composable 的 `context` computed）
**替代方案 B**：Python memory dict 存對話

**理由**：
- **後端管理** — LLM API 是 stateless，每次需重組完整 messages 陣列，由後端統一管理更可靠
- **Redis 儲存** — Gunicorn 多 worker（PRD: 4），memory dict 是 per-process 的，跨 worker 會遺失對話；Redis 跨 worker 安全
- **5 輪限制** — 實測 5 輪僅佔 ~954 tokens（16K context 的 6%），token 預算充裕
- **Context 上限偵測** — 雖然 5 輪不太可能超限，但加入 12,000 token 硬上限作為安全閥，超過則回傳 `CONTEXT_LIMIT_REACHED`，前端提示「對話已達上限，請開啟新對話」
- **TTL 自動過期** — Redis key 設 30 分鐘 TTL，閒置對話自動清理

**對話 Redis 結構**：
```
Key:    ai_chat:{user_id}:{conversation_id}
Value:  JSON { "messages": [...], "round_count": N }
TTL:    1800 秒（30 分鐘）
```

**Token 預算實測數據（gpt-oss:120b）**：

| 項目 | Tokens |
|------|--------|
| System prompt（15 個函式目錄） | ~676 |
| 第 1 輪（system + user） | 704 |
| 第 2 輪（累計） | 766 |
| 第 3 輪（累計） | 834 |
| 第 4 輪（累計） | 895 |
| 第 5 輪（累計） | 954 |
| max_tokens 回覆預留 | 500 |
| **5 輪後總佔用** | **~1,454** |
| **剩餘 context** | **~14,930** |
| Context 硬上限 | 12,000 |

### Decision 7: AI Chat Panel 採用右側滑出面板而非 Modal/內嵌區塊

**選擇**：固定位置右側滑出面板（類似 customer support chat widget）

**替代方案 A**：Modal 彈窗
**替代方案 B**：頁面內嵌聊天區塊

**理由**：
- Portal shell 現有架構是「左側 sidebar + 右側 main content」— 右側面板自然對稱
- 滑出面板不遮擋主頁面內容 — 操作員可同時看圖表和 AI 回應
- Modal 會完全中斷操作流，且無法同時參照頁面數據
- 內嵌區塊需修改每個頁面的 layout，影響範圍過大
- 面板關閉後對話保留，隨時可重開 — 符合多輪鑽研的工作流

### Decision 8: AnomalyBadge 基於既有 StatusBadge tone 模式擴展 ✅ 已實作

**選擇**：新建 `AnomalyBadge.vue`，參考 `StatusBadge.vue` 的 tone 系統（neutral/success/warning/danger），增加 popover 展開

**替代方案**：直接修改 StatusBadge 加入 popover

**理由**：
- StatusBadge 是純展示元件（無互動），加入 popover 會改變其職責
- AnomalyBadge 需要額外的 props（items、type）和點擊互動
- 分離保持 StatusBadge 的簡單性，避免影響 100+ 處既有引用

## Backend Architecture — Phase 2

### 後端新增模組

```
src/mes_dashboard/
├── services/
│   ├── ai_function_registry.py     # [新增] 函式目錄 + system prompt 生成
│   └── ai_query_service.py         # [新增] LLM 呼叫 + intent 驗證 + service 調度 + 對話管理
├── routes/
│   └── ai_routes.py                # [新增] POST /api/ai/query
├── core/
│   └── response.py                 # [修改] 新增 error codes
└── config/
    └── settings.py                 # [修改] AI 相關配置
```

### ai_function_registry.py 設計

負責：
1. 定義所有 LLM 可呼叫的函式清單（name, description, params schema, service path, drill_down）
2. 生成 system prompt（函式目錄 + 回覆格式 + 參數說明 + 規則）
3. 提供 intent validation（檢查函式是否存在、參數是否合法）

```python
REGISTRY = {
    "reject_reason_pareto": {
        "description": "不良原因排行（Pareto）",
        "service": "reject_history_service.get_reason_pareto",
        "params": {
            "workcenter_group": {"type": "string", "required": True, "enum": [...]},
            "package": {"type": "string", "required": False},
            "days": {"type": "int", "required": False, "default": 7},
        },
        "drill_down": ["reject_trend", "lot_query"],
    },
    # ... ~15 個函式
}

def build_system_prompt() -> str:
    """從 REGISTRY 動態生成 system prompt（~676 tokens）"""

def validate_intent(function_name: str, params: dict) -> tuple[bool, str]:
    """驗證 intent 是否合法：函式存在 + 參數 schema 通過"""
```

### ai_query_service.py 設計

負責：
1. 管理 Redis 對話歷史（建立/讀取/追加/清理）
2. 組裝 LLM messages（system + history + new user message）
3. Context token 上限偵測
4. 呼叫 LLM API（`requests.post`，`verify=False`）
5. 解析回應（`content` 優先，fallback `reasoning_content`，提取 JSON）
6. Intent validation → service 函式動態調度
7. 組裝前端回應（answer, chart_data, query_used, params_used, suggestions）

```python
def process_query(user_id: str, question: str, conversation_id: str | None) -> dict:
    """
    主入口。
    1. 從 Redis 取回對話歷史（或建立新對話）
    2. 組裝 messages，檢查 token 上限
    3. 呼叫 LLM → 取得 intent JSON
    4. validate_intent → 調度 service 函式
    5. 將本輪 user+assistant 追加至 Redis
    6. 回傳 { answer, chart_data, query_used, params_used, suggestions, conversation_id, round, max_rounds }
    """
```

**對話流程**：
```
前端 POST /api/ai/query { question, conversation_id? }
  │
  ├─ conversation_id 為空 → 建立新對話，生成 UUID
  ├─ conversation_id 存在 → 從 Redis 取回 messages
  │                         → 驗證 user_id ownership
  │                         → 檢查 round_count ≤ 5
  │
  ├─ 組裝 [system_prompt, ...history_messages, new_user_message]
  ├─ 估算 prompt tokens → 超過 12,000 則回傳 CONTEXT_LIMIT_REACHED
  │
  ├─ POST https://ollama_pjapi.theaken.com/v1/chat/completions
  │   { model: "gpt-oss:120b", messages, stream: false, max_tokens: 500 }
  │   timeout: 30s, verify: configurable
  │
  ├─ 解析 response.choices[0].message
  │   content = msg.content || msg.reasoning_content
  │   提取 JSON（正則 or json.loads）
  │
  ├─ validate_intent(function_name, params)
  │   → 失敗：回傳 explanation + 可用函式建議
  │   → 成功：動態呼叫 service 函式
  │
  ├─ 將 user + assistant messages 追加至 Redis（TTL refresh）
  │
  └─ 回傳 { answer, chart_data, query_used, params_used, suggestions,
            conversation_id, round, max_rounds: 5 }
```

### 環境變數

```env
# AI-Assisted Reporting — Phase 2
AI_QUERY_ENABLED=false
AI_API_URL=https://ollama_pjapi.theaken.com
AI_API_KEY=<your-api-key>
AI_MODEL=gpt-oss:120b
AI_REQUEST_TIMEOUT=30
AI_VERIFY_TLS=false
AI_MAX_ROUNDS=5
AI_CONTEXT_TOKEN_LIMIT=12000
AI_MAX_TOKENS=500
AI_CONVERSATION_TTL=1800
AI_RATE_LIMIT_MAX_REQUESTS=3
AI_RATE_LIMIT_WINDOW_SECONDS=60
```

### Error Codes 新增

```python
# core/response.py 新增
EXTERNAL_SERVICE_TIMEOUT = "EXTERNAL_SERVICE_TIMEOUT"
EXTERNAL_SERVICE_ERROR = "EXTERNAL_SERVICE_ERROR"
CONTEXT_LIMIT_REACHED = "CONTEXT_LIMIT_REACHED"
```

## Frontend Architecture

### 元件層級與歸屬

```
frontend/src/
├── portal-shell/
│   ├── App.vue                          # [修改] 整合 AiChatTrigger + AiChatPanel
│   └── ai-chat.css                      # [新增] Chat panel 樣式（scoped .theme-portal-shell）
│
├── shared-ui/components/
│   ├── AiChatTrigger.vue               # [新增] 固定位置觸發按鈕（右下角 FAB）
│   ├── AiChatPanel.vue                 # [新增] 右側滑出對話面板
│   ├── AiChatMessage.vue               # [新增] 單則訊息渲染（問題/回應/錯誤）
│   └── AiChartRenderer.vue             # [新增] 根據 query_used 自動選擇圖表類型
│
├── shared-composables/
│   └── useAiChat.js                    # [新增] AI 對話狀態管理
│
# Phase 1 已完成的元件（不在此次範圍）
```

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
│ │          │                           │ │ ┌──────────┐ │ │ │
│ │          │                           │ │ │ 輪次 3/5  │ │ │ │
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
  const messages = ref([]);         // [{ role: 'user'|'ai'|'error', content, chartData?, queryUsed?, suggestions? }]
  const conversationId = ref(null); // 後端管理的對話 ID（UUID）
  const currentRound = ref(0);      // 目前輪次
  const maxRounds = ref(5);         // 最大輪次（從後端回應取得）
  const isOpen = ref(false);        // 面板開關
  const isLoading = ref(false);     // 等待 LLM 回應
  const isRateLimited = ref(false); // 429 鎖定狀態
  const isContextFull = ref(false); // context 上限已達

  // ── 方法 ──
  async function submitQuestion(question) {
    // POST /api/ai/query { question, conversation_id }
    // → 更新 conversationId, currentRound, maxRounds
    // → 處理 CONTEXT_LIMIT_REACHED → isContextFull = true
  }
  function submitSuggestion(suggestion) { /* 將 suggestion 作為新問題提交 */ }
  function resetConversation() {
    // 清空 messages, conversationId, currentRound
    // isContextFull = false
  }
  function togglePanel() { /* isOpen toggle */ }

  // ── 生命週期 ──
  // 使用 useRequestGuard 防止 race condition
  // Rate limit 鎖定 20 秒後自動解除（setTimeout）
  // AbortController 在新請求時取消舊請求

  return { messages, conversationId, currentRound, maxRounds,
           isOpen, isLoading, isRateLimited, isContextFull,
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
  <div class="shell theme-portal-shell" :class="{ 'ai-panel-open': aiChat.isOpen.value }">
    <!-- 既有 sidebar + content -->
    <AiChatTrigger v-if="!aiChat.isOpen.value" @click="aiChat.togglePanel" />
    <AiChatPanel v-if="aiChat.isOpen.value" v-bind="aiChat" />
  </div>
</template>
```

**前端對話狀態 UX：**
- 面板 header 顯示「輪次 N/5」
- 第 5 輪後，輸入框 disabled + 提示「已達對話上限，請點擊「新對話」繼續」
- 收到 `CONTEXT_LIMIT_REACHED` 時同上處理
- 「新對話」按鈕清空本地 messages + 重置 conversationId

### 樣式規範

**新增 CSS 檔案：**
- `frontend/src/portal-shell/ai-chat.css` — Chat panel 樣式，scoped under `.theme-portal-shell`（須在 `portal-shell/App.vue` 的 `.shell` 根 div 加入此 class）

**遵循合約：**
- 所有顏色使用 `tailwind.config.js` 的 semantic tokens（`state.warning`、`state.danger`、`surface.card`）
- 不使用 hard-coded hex（ECharts 圖表內的顏色例外，但須集中在 AiChartRenderer 內）
- Feature-scoped：chat 樣式在 `.theme-portal-shell` 下
- 新增 CSS 檔案須更新 `contract/css_inventory.md`

### 響應式設計

| 斷點 | Chat Panel | 觸發按鈕 |
|------|-----------|---------|
| ≥ 769px | 右側 380px 面板，不影響 main content | 右下角 FAB |
| ≤ 768px | 全螢幕覆蓋 + backdrop overlay | 右下角 FAB（縮小為 40px） |

## Risks / Trade-offs

### Phase 1 風險 ✅ 已處理

### Phase 2 風險

**[LLM 意圖解析錯誤]** → 參數 schema validation 攔截不合法值；intent 白名單阻擋未知函式；前端顯示「AI 理解為：XXX」讓使用者確認。

**[gpt-oss:120b 回應速度慢]** → 實測 ~3-4 秒/次，前端需明確 loading 狀態（typing indicator）；timeout 設 30 秒；前端提示使用者耐心等待。

**[TLS 憑證 hostname mismatch]** → Python requests 需 `verify=False`；環境變數 `AI_VERIFY_TLS` 控制，正式環境修正憑證後可改為 `true`。

**[LLM API 不可用]** → AI 查詢失敗不影響現有功能；前端顯示降級提示「AI 助手暫時不可用，請使用一般查詢」。

**[多 worker 對話遺失]** → 使用 Redis 存對話歷史（非 memory dict），跨 worker 安全。TTL 30 分鐘自動過期。

**[Context window 超限]** → 5 輪限制 + 12,000 token 硬上限偵測；超過時前端提示開新對話。實測 5 輪僅佔 ~954 tokens，極不易觸發。

**[model 回應格式不穩定]** → content/reasoning_content 雙路徑讀取；JSON 提取用正則 fallback；system prompt 明確要求「只回覆 JSON」。

### 共通風險

**[Oracle 連線池壓力]** → AI 觸發的查詢走既有 service 函式（已有 rate limit 和 pool 隔離），不增加額外連線池負擔。

**[操作員不信任 AI]** → AI 結果旁邊始終顯示原始數據和鑽研連結。

## Migration Plan

### Phase 1 部署 ✅ 已完成
- `ANALYTICS_ANOMALY_DETECTION_ENABLED=true` 已上線

### Phase 2 部署
1. Feature flag `AI_QUERY_ENABLED=false` 部署全部程式碼
2. 設定 `.env` 中的 `AI_API_KEY` 和 `AI_API_URL`
3. 內部測試：10 個常見查詢意圖解析正確率 > 90%
4. 測試 5 輪多輪對話流暢度和 context 上限偵測
5. 開放 flag 給少數使用者
6. 觀察 LLM 回應速度和穩定性
7. 全面開放

### Rollback
- 關閉 feature flag 即可完全停用，不影響任何現有功能
- 無 schema migration、無資料結構變更、無破壞性改動
- Redis 對話 key 30 分鐘自動過期，無需手動清理

## Resolved Questions

1. ~~**資安審查時程**~~ → 使用公司內網自建模型 `gpt-oss:120b`，無需外部 API 連線審查
2. ~~**Level 1 摘要的隱私邊界**~~ → 不做 L1 摘要，查詢結果不傳給 LLM
3. ~~**異常偵測閾值**~~ → Phase 1 已上線，閾值已調校
4. **AI 查詢的使用者範圍**：目前設計為所有登入使用者可用（受 rate limit 控制），如需限定角色可在 `ai_routes.py` 加 role check
