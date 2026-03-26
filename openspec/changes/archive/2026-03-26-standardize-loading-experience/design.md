## Context

目前 Loading 體驗存在跨頁分歧：部分頁面使用全域 overlay，部分以自定 spinner 或純文字「載入中」呈現，且動畫速度與互動行為不一致。這個變更是跨 `shared-ui`、多個 feature 頁面與既有樣式規範的橫向治理，必須在不改動後端 API 的前提下，建立可落地且可驗證的三層 Loading 架構。

此設計直接對應提案的優先順序：
1. 全域等待必用元件與動畫
2. 小組件等待一致化
3. 區塊等待一致化

## Goals / Non-Goals

**Goals:**
- 建立明確的三層 Loading 分類（全域/小組件/區塊）與使用邊界。
- 收斂全域等待到 `LoadingOverlay + LoadingSpinner`，避免頁面自定義全屏等待。
- 將按鈕 busy、inline spinner、MultiSelect loading 動畫對齊共享規格。
- 讓 `DataTable` 與非表格區塊有一致的 block-level loading 呈現規則。
- 形成可驗證的治理方式（lint/checklist/test case）。

**Non-Goals:**
- 不新增或修改任何後端 API。
- 不改動業務查詢邏輯與資料契約。
- 不做全面視覺重設計（僅針對 loading 相關交互與動畫一致化）。

## Decisions

### D1. 採用三層 Loading 架構作為唯一分類標準
- 定義：
  - 全域等待：阻斷頁面主要操作的查詢與初始化。
  - 小組件等待：按鈕、下拉、微互動中的局部等待。
  - 區塊等待：卡片、表格、區域內容刷新。
- 替代方案：單一 spinner 套所有場景。
- 為何不選：會犧牲場景語意，導致 UX 過度僵化（例如區塊更新不需要全頁遮罩）。

### D2. 全域等待強制統一為 LoadingOverlay + LoadingSpinner
- `tier="page"` 作為全域等待標準實作，動畫基準統一為 shared spinner。
- 禁止頁面自定義 full-screen spinner（包含 legacy style 片段）。
- 替代方案：允許各頁自定樣式但要求「近似」。
- 為何不選：近似無法驗收，會持續出現速度與外觀漂移。

### D3. 小組件等待以共享 spinner + 按鈕 busy 模式收斂
- 引入/強化 `LoadingButton` 模式（可由 `ui-btn.is-loading` + `LoadingSpinner size="sm"` 實作）。
- Busy 狀態必須同時包含：`disabled`、視覺狀態、可存取文案切換。
- `MultiSelect` loading 指示器保留在元件內，但動畫節奏對齊共享 motion token。
- 替代方案：保留每頁按鈕文字切換自行實作。
- 為何不選：重複邏輯多、易漏掉 disabled 與 aria 行為。

### D4. 區塊等待採雙軌：DataTable 原生規範 + 通用 BlockLoadingState
- 表格優先走 `DataTable :loading`（opacity + pointer-events + transition 規則）。
- 非 `DataTable` 區塊使用共用 `BlockLoadingState`（或 `EmptyState type="loading"` 的一致封裝）取代散落 placeholder。
- 替代方案：所有區塊都改成 overlay。
- 為何不選：過度遮罩會破壞局部更新可讀性，且實作成本較高。

### D5. 依風險採分批遷移
- 批次 1（全域）：先收斂 page-level，立即消除最大不一致。
- 批次 2（小組件）：替換按鈕 busy 與自定小 spinner。
- 批次 3（區塊）：逐頁把 placeholder loading 遷移到共用模式。
- 替代方案：一次性全量替換。
- 為何不選：回歸面太大，難快速定位視覺與互動回歸。

### D6. 驗收以「規範 + 掃描 + 主要頁面測試」三層保證
- 規範：spec requirements 作為唯一標準。
- 掃描：檢查自定 full-page spinner、重複 loading class、非共用 busy 寫法。
- 測試：針對高頻頁面驗證三層 loading 行為與 reduced-motion。

## Risks / Trade-offs

- [全域與區塊邊界誤用] → 以 capability 規範與 code review checklist 強制區分場景。
- [舊頁面混合 legacy 與新元件，遷移中出現雙重 loading] → 分批替換時加入「單一來源」檢查（同區塊不可同時 overlay+placeholder）。
- [按鈕 busy 一致化造成既有文案差異] → 保留文案可配置，但強制行為一致（disabled/spinner/aria）。
- [區塊 loading 元件化初期增加少量重構成本] → 優先改高流量頁面，低風險頁面延後。

## Migration Plan

1. 建立/更新 shared 規範元件：`LoadingSpinner`、`LoadingOverlay`、`LoadingButton`（或等價模式）、`BlockLoadingState`。
2. 批次 1：替換全域等待（頁面級）。
3. 批次 2：替換小組件等待（按鈕、inline spinner、MultiSelect motion 對齊）。
4. 批次 3：替換區塊等待（表格/卡片 placeholder 收斂）。
5. 清理遺留 CSS 與重複 keyframes，補齊測試與治理檢查。

Rollback strategy:
- 每批次以獨立提交/PR 進行；若出現回歸，回退該批次變更，不影響其他批次。

## Open Questions

- `BlockLoadingState` 是否先以最小 API（`text`, `size`）落地，或一次納入 skeleton 變體？
- 對於 login 頁等品牌導向場景，是否允許保留視覺差異但強制動畫 token 一致？
