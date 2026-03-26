## Context

MES Dashboard 前端架構審查揭露系統性 UX 缺陷：無障礙基礎設施不完整（無焦點環、無 landmark、無 reduced-motion）、圖表缺乏統一的 resize 節流與語義標籤、血緣樹全展開導致大量節點效能差、資料表格無排序功能、篩選器在行動裝置溢出。

**現有架構約束：**
- CSS 開發契約要求：全域元件類別放 `tailwind.css` @layer components 並使用 `ui-` 前綴；feature CSS 必須 scope 在 theme root class 下；色值必須用 `theme()` 引用
- 14 個微應用模組，各有獨立 `style.css` 與 theme root class
- ECharts 6 + vue-echarts 8 為圖表基礎，使用 CanvasRenderer
- 既有 shared-ui 元件庫（LoadingOverlay、LoadingSpinner、PaginationControl、MultiSelect、SectionCard、EmptyState）

## Goals / Non-Goals

**Goals:**
- 建立跨所有頁面的無障礙基礎設施（WCAG AA 級別）
- 改善圖表互動一致性與效能
- 解決血緣樹大資料量效能與操控性問題
- 強化資料表格排序與分頁功能
- 改善篩選器行動裝置支援
- 統一重複的元件樣式定義

**Non-Goals:**
- Heatmap 色盲友善調色盤（暫不考慮）
- Skeleton loading 全面導入
- 日期選擇器統一元件
- Sidebar icon-rail 中間寬度模式
- 血緣樹 Web Worker 匯出
- MultiSelect 語義重構為 listbox/option

## Decisions

### Decision 1: Focus Ring 實作於全域 @layer components

**選擇**: 在 `tailwind.css` 的 `@layer components` 統一定義 `:focus-visible` 規則，而非在各 feature CSS 中分別定義。

**理由**: 焦點環是跨所有頁面的一致性需求，符合 CSS 契約 3.2.2（全域複用元件類別定義於 tailwind.css）。在各 feature CSS 重複定義會違反 DRY 原則且增加維護成本。

**替代方案**: 在各 feature `style.css` 中 scope 定義 — 拒絕，因為焦點環行為應全域一致。

### Decision 2: useSortableTable 為純前端排序

**選擇**: `useSortableTable` composable 在前端對已載入的資料進行排序，不發送排序參數至後端 API。

**理由**: 現有表格資料量通常在分頁範圍內（≤100 筆/頁），前端排序足夠高效。後端排序需修改所有相關 API 端點，工作量遠超本次範圍。

**替代方案**: 後端排序 — 拒絕，因為需要修改後端 API 契約，不在本次範圍。

### Decision 3: 血緣樹使用 ECharts 原生 roam 而非自建縮放

**選擇**: 使用 ECharts 內建 `roam: true` 啟用平移 + 滾輪縮放，搭配「重置視圖」按鈕呼叫 `dispatchAction({ type: 'restore' })`。

**理由**: ECharts 原生 roam 支援已足夠成熟，且零額外依賴。自建縮放需處理 canvas 座標轉換、觸控手勢等複雜問題。

**替代方案**: D3-zoom 疊加 — 拒絕，因為引入新依賴且與 ECharts 事件系統衝突。

### Decision 4: ErrorBanner 使用 slot 模式而非 prop 模式

**選擇**: `ErrorBanner` 元件提供 `action` slot 供消費者自定義重試按鈕，而非透過 `onRetry` prop 回調。

**理由**: Slot 模式更靈活 — 部分頁面需要「重試」、部分需要「重新載入」、部分不需要任何動作。Prop 模式會導致元件 API 膨脹。

### Decision 5: Reduced Motion 使用 :is() 群組選擇器

**選擇**: 在 feature CSS 的 `@media (prefers-reduced-motion: reduce)` 區塊中，使用 `:is(.theme-wip-overview, .theme-wip-detail)` 群組選擇器覆蓋多個 theme scope。

**理由**: 減少重複的 @media 區塊數量，同時維持 CSS 契約 4.3 的 theme scope 要求。

### Decision 6: 分頁元件強化採用漸進式修改而非重寫

**選擇**: 在現有 `PaginationControl.vue` 上新增 props（`showPageNumbers`、`showPageSize`、`pageSizeOptions`），預設值保持向後相容。

**理由**: 避免破壞現有消費者。新 props 預設為 `false` / `undefined` 時行為與現有完全一致。

## Risks / Trade-offs

**[Risk] text.muted 色值全域變更影響視覺** → 影響所有使用 `text-text-muted` 的元素。色值從 `#94a3b8` 加深為 `#64748b`（即現有 `text.secondary`），視覺差異為文字略深。建議先在 staging 環境逐頁檢視。

**[Risk] initialTreeDepth 限制可能影響使用者習慣** → 習慣全展開的使用者需額外點擊「全部展開」。透過按鈕放置在顯眼位置（toolbar 區域）降低學習成本。

**[Risk] 前端排序在極端資料量下效能** → 當單頁 >1000 筆時排序可能有感延遲。現有分頁機制（每頁 ≤100）可控制此風險。

**[Risk] Phase 6 元件樣式統一影響範圍大** → 涉及多個 feature CSS 的刪除與修改。建議逐模組執行並獨立驗證，不一次全改。
