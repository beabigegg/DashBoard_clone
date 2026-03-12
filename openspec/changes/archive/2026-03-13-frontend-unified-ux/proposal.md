## Why

MES Dashboard 前端由 12+ 個獨立頁面組成，各頁面在篩選器行為、動畫回饋、按鈕命名、空狀態處理、Loading 樣式上各自為政。使用者在不同頁面間切換時操作體驗不一致——搜尋觸發方式不同、hover 回饋不同、spinner 尺寸不同、過渡時間隨機。這導致產品缺乏統一的互動語言，增加維護成本（如 MultiSelect 有兩份重複實作）。本變更建立統一的 UX 基礎設施，讓所有頁面「感覺像同一個產品」。

## What Changes

- **統一 Motion Design Tokens**：在 `:root` 定義 `--motion-fast/normal/slow`、`--motion-ease`、`--hover-lift`、`--overlay-bg` CSS 變數，取代各頁面散落的硬編碼 transition 時間（0.12s~0.3s）和 hover 位移（-1px~-2px）
- **統一按鈕系統**：合併 `.btn-primary` / `.ui-btn-primary` / `.btn` 三套為 `ui-` 前綴 BEM 系統（`.ui-btn`、`.ui-btn--primary`、`.ui-btn--ghost`、`.ui-btn--sm`、`.ui-btn.is-loading`），**BREAKING** 移除舊 class
- **三級 Loading 系統**：新增 `LoadingOverlay`（page/section 兩級）和 `LoadingSpinner`（inline），取代各頁面自行實作的 overlay 和 spinner
- **統一空狀態元件**：新增 `EmptyState` 元件，標準化中文文案（"目前沒有資料"、"找不到符合條件的資料"、"資料載入失敗，請稍後再試"）
- **合併 MultiSelect**：將 `resource-shared` 和 `mid-section-defect` 兩份實作合併為 `shared-ui/MultiSelect.vue`，**BREAKING** 刪除 `mid-section-defect/components/MultiSelect.vue`
- **統一篩選器狀態管理**：新增 `useFilterOrchestrator` composable，配置驅動處理四種篩選模式（Draft→Apply / 兩階段 / 級聯即時 / 互斥切換）+ 交叉依賴
- **提取共用 composables**：新增 `useRequestGuard`（requestId 防抖）和 `useUrlSync`（URL 序列化）
- **統一搜尋觸發動畫**：套用/查詢後的統一視覺回饋（按鈕 spinner + 表格 opacity 降低 + 完成 fade-in）
- **全部頁面同步遷移**：所有 10+ 個頁面一次性替換為新元件、新 class、新 composable

## Capabilities

### New Capabilities
- `motion-design-tokens`: CSS 變數定義統一動畫時間、easing、hover 位移、overlay 背景，以及 Tailwind config 對應的 extend
- `unified-button-system`: `ui-` 前綴 BEM 按鈕 class 系統，含 primary/ghost/sm 變體和 loading 狀態
- `loading-system`: 三級 Loading 元件（LoadingOverlay page/section + LoadingSpinner sm/md/lg）
- `empty-state`: 統一空狀態元件，支援無資料/篩選空/錯誤/載入中四種情境的中文文案
- `unified-multiselect`: 合併兩份 MultiSelect 為單一可配置元件，支援 searchable、selectAll scope 等 props
- `filter-orchestrator`: 配置驅動的篩選器狀態管理 composable，處理四種模式 + 交叉依賴 + 分頁重置 + URL 同步
- `search-trigger-animation`: 套用/查詢觸發後的統一視覺回饋（按鈕 spinner + 表格 dimming + 完成 fade-in）
- `page-migration`: 所有頁面同步遷移至新元件/class/composable，移除舊定義

### Modified Capabilities
_(無既有 spec 的 requirement 層級變更)_

## Impact

- **前端全域樣式**：`frontend/src/styles/tailwind.css` 重寫按鈕、新增 motion tokens
- **Tailwind 配置**：`frontend/tailwind.config.js` 新增 motion extend
- **共用元件**：`frontend/src/shared-ui/components/` 新增 4 個元件
- **共用 composables**：`frontend/src/shared-composables/` 新增 3 個 composable
- **所有頁面**：hold-overview、hold-detail、hold-history、wip-overview、wip-detail、reject-history、yield-alert-center、resource-status、resource-history、mid-section-defect 的 `.vue` 和 `.css` 檔案
- **刪除檔案**：`frontend/src/mid-section-defect/components/MultiSelect.vue`
- **清理檔案**：`wip-shared/styles.css`、`resource-shared/styles.css` 移除重複的 loading/spinner 定義
- **契約更新**：`contract/css_inventory.md` 需同步更新
