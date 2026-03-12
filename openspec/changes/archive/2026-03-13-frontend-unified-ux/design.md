## Context

MES Dashboard 前端有 12+ 個獨立頁面，各自實作篩選器行為、動畫回饋、按鈕樣式、空狀態、Loading 等 UI 模式。具體問題：

- **按鈕**：`.btn-primary` / `.ui-btn-primary` / `.btn` 三套 class 並存於 `tailwind.css`、`wip-shared/styles.css`、各頁面 `style.css`
- **Motion**：transition 時間散布 0.12s~0.3s，hover translateY 有 -1px 和 -2px 兩種
- **Spinner**：42px/4px 和 14px/2px 兩種尺寸，各頁面自行定義
- **MultiSelect**：`resource-shared/components/MultiSelect.vue` 和 `mid-section-defect/components/MultiSelect.vue` 兩份實作
- **篩選器**：四種模式（Draft→Apply、兩階段、級聯即時、互斥切換）各頁面獨立實作，requestId 防抖、URL 同步等邏輯重複散落
- **空狀態**：中英混用（"無資料"/"No data"/"無符合項目"）

現有 shared-ui 元件：SectionCard、StatusBadge、TimelineChart、PaginationControl、FilterToolbar。
現有 shared-composables：useAsyncJobPolling、useAutocomplete、useAutoRefresh、usePaginationState、useQueryState、useTraceProgress。

## Goals / Non-Goals

**Goals:**
- 建立統一的 motion design tokens（CSS 變數），所有動畫效果引用同一組變數
- 合併三套按鈕為 `ui-` 前綴 BEM 系統
- 提供三級 Loading 元件（page / section / inline），取代各頁面自訂 overlay/spinner
- 標準化空狀態元件和中文文案
- 合併兩份 MultiSelect 為單一共用元件
- 建立 `useFilterOrchestrator` composable 統一四種篩選模式的狀態管理
- 所有頁面一次性遷移，不留舊 class / 舊元件

**Non-Goals:**
- 不改變任何頁面的業務邏輯或 API 呼叫行為
- 不引入新的 UI 框架或元件庫
- 不重構後端 API
- 不改變篩選器的功能行為（僅統一狀態管理方式）
- 不處理 portal-shell 或導航相關的 UX

## Decisions

### D1: Motion Tokens 放在 `:root` CSS 變數而非 Tailwind theme

**決定**：在 `tailwind.css` 的 `@layer base` 中定義 `:root` CSS 變數，同時在 `tailwind.config.js` extend 中引用這些變數。

**理由**：CSS 變數可在 `transition` shorthand 中直接使用（如 `transition: opacity var(--motion-normal) var(--motion-ease)`），Tailwind 的 `transitionDuration` utility 無法涵蓋 easing 組合。同時透過 Tailwind extend 讓 `duration-normal` 等 utility class 也可用。

**替代方案**：純 Tailwind theme extend —— 但無法在 `@apply` 或手寫 CSS 中方便組合 duration + easing。

### D2: 按鈕系統採 `ui-` 前綴 BEM

**決定**：`.ui-btn` 基礎 + `.ui-btn--primary` / `.ui-btn--ghost` / `.ui-btn--sm` 修飾符 + `.is-loading` 狀態。直接移除舊 `.btn-primary` / `.btn` / `.btn-secondary`。

**理由**：`ui-` 前綴避免與第三方衝突；BEM 命名語義清晰；`.is-loading` 狀態 class 可搭配 `LoadingSpinner` 元件使用。

**替代方案**：保留舊 class 作為 alias —— 增加維護負擔，且無法強制遷移。

### D3: Loading 分三級

**決定**：
- `LoadingOverlay` 元件：`tier="page"` 全頁覆蓋（白色半透明背景 + 大 spinner），`tier="section"` 區塊覆蓋（同背景 + 中 spinner）
- `LoadingSpinner` 元件：純 spinner 動畫，`size="sm|md|lg"`，用於按鈕內或行內

**理由**：三級對應實際使用場景——首次載入、區塊重載、按鈕內微互動。統一 spinner 尺寸（sm=14px, md=24px, lg=42px）和 border-width。

### D4: MultiSelect 合併策略

**決定**：以 `resource-shared` 版本為基礎（有 `requestAnimationFrame` focus、selectAll 尊重搜尋過濾），補入 `mid-section-defect` 版本的 label+value 搜尋功能。新元件放 `shared-ui/components/MultiSelect.vue`。

**理由**：resource-shared 版本功能更完整；mid-section-defect 版本的搜尋邏輯是純增量。

**替代方案**：重寫 —— 風險更高，兩份現有實作已經過生產驗證。

### D5: useFilterOrchestrator 配置驅動設計

**決定**：單一 composable 接受配置物件，描述欄位定義、觸發方式、交叉依賴、分頁規則。各頁面用不同配置呼叫同一個 composable。

**配置結構**：
```js
{
  fields: { [name]: { trigger: 'immediate' | 'draft-apply', initial, options } },
  dependencies: [{ when, then, action: 'reload-options' | 'clear' | 'reset', debounce? }],
  pagination: { resetOn: ['*'] | string[] },
  urlSync: { enabled: boolean },
}
```

**理由**：配置驅動讓四種模式統一為同一套邏輯，差異由配置表達。各頁面的交叉影響矩陣轉為 `dependencies` 陣列，明確且可測試。

**替代方案**：
- 各模式各自一個 composable —— 無法共用分頁重置、URL 同步等橫切邏輯。
- 狀態管理庫（Pinia） —— 過度引入，當前 composable 模式已足夠。

### D6: useRequestGuard 提取

**決定**：提取 `nextRequestId()` + `isStaleRequest(id)` 模式為獨立 composable，供 `useFilterOrchestrator` 內部使用，也可獨立使用。

**理由**：至少 6 個頁面有相同的 requestId 防抖 pattern，提取後消除重複。

### D7: 全面替換策略（Big Bang）

**決定**：所有頁面同步遷移，不保留舊 class / 舊元件的向後相容 alias。

**理由**：
- 頁面間無運行時依賴，可安全同步替換
- 保留 alias 會導致新舊混用，永遠清不乾淨
- 專案是單一部署，無需漸進式遷移

**風險緩解**：一個 feature branch 完成所有變更，整體測試後合併。

## Risks / Trade-offs

- **[大範圍變更導致回歸]** → 每頁遷移後逐一驗證篩選器交叉影響矩陣（見 proposal），比對 Network tab API 呼叫
- **[useFilterOrchestrator 配置不夠彈性]** → 預留 `onFetch` / `onPrimaryQuery` callback 讓頁面注入自訂邏輯；如有極端邊界情況可在頁面層 override
- **[MultiSelect 合併遺漏行為差異]** → 合併前列出兩版差異清單，確保全部 props/events 都有對應
- **[Motion tokens 不被採用]** → grep 驗證無硬編碼 transition 時間殘留
- **[Big Bang 合併衝突]** → 盡量縮短 branch 存活時間；基礎層先合併，頁面遷移跟進
