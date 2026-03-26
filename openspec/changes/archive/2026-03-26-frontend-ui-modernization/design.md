## Context

MES Dashboard 前端已完成 SPA shell 遷移，現行 19 條 in-scope native route 透過 `nativeModuleRegistry.js` 動態載入。設計系統基礎已建立：`tailwind.config.js` 定義 brand/surface/state/text tokens，`styles/tailwind.css` 提供 `.ui-btn`/`.ui-card`/`.ui-section-card` 等全域元件 class，`shared-ui/components/` 已有多個可重用元件。

**現狀問題：**
- 各 feature 自建 table markup（排序指示器、分頁、loading 各異）
- Summary card 在 wip/hold/resource 三系列各有不同 HTML 結構與 CSS class
- Card 樣式三套並存（`.ui-card` / `.section-card` CSS / `SectionCard.vue`）
- Icon 全部 inline SVG 散落各處，無統一管理
- Shell 視覺功能完整但缺乏現代層次感

**現有依賴：** Vue 3.5, Vue Router 4.6, ECharts 6, DuckDB WASM, Vite 6, Tailwind 3.4

**約束：**
- 不破壞主色系（brand blue `#0080C8` gradient + surface/state tokens）
- 遵守 CSS contract（theme scoping, inventory sync）
- 漸進式改造，不需一次全改

---

## Goals / Non-Goals

**Goals:**
- 建立統一的 DataTable 元件，覆蓋 sortable/pagination/loading/empty 四大需求
- 建立統一的 SummaryCard 元件，支援 KPI 展示/clickable filter/status coloring
- 引入 Lucide icon library 取代散落的 inline SVG
- 引入 @vueuse/core 減少自建 utility composable
- 擴展 Tailwind tokens（shadow 5 級、Latin 字體、半透明色彩）
- 升級 Shell 視覺（header blur、sidebar accent、page transition）
- 6 批次漸進統一 19 條 in-scope native route 對應頁面

**Non-Goals:**
- 不重寫 echarts 圖表元件（保持 vue-echarts 整合）
- 不改變 API 層或後端邏輯
- 不改變路由架構或 nativeModuleRegistry 動態載入機制
- 不引入 CSS-in-JS 或 Styled Components（維持 Tailwind + CSS 架構）
- 不改造已 deprecated 的 direct-entry admin 頁面（`/admin/performance`, `/admin/user-usage-kpi`）——僅驗證 redirect 行為不受影響
- 不引入 component library（如 PrimeVue, Naive UI）——自建元件以保持一致性與輕量

---

## Decisions

### Decision 1: 引入 Lucide Vue Next 作為 icon 系統

**選擇：** `lucide-vue-next`

**理由：**
- Tree-shakeable：只打包使用的 icon，不影響 bundle size
- 與現有 inline SVG 風格一致（stroke-based, 24x24 viewBox）
- 400+ icon 覆蓋 MES 所需（refresh, filter, chevron, alert, chart 等）
- Vue 3 原生支持，SSR-safe

**替代方案考量：**
- **Heroicons** — 品質好但 icon 數量較少（~300），且 outline/solid 混用需額外管理
- **Phosphor Icons** — icon 數量最多但 Vue 3 package 維護不穩定
- **繼續 inline SVG** — 已證明不可維護，icon 散落 15+ 檔案無法統一管理

**遷移策略：** 新元件直接使用 Lucide；現有 inline SVG 在 feature page 批次改造時逐步替換。

### Decision 2: 引入 @vueuse/core

**選擇：** `@vueuse/core`

**理由：**
- 提供 `onClickOutside`（取代 MultiSelect/Tooltip 自建 click-outside 邏輯）
- 提供 `useResizeObserver`（取代手動 resize listener）
- 提供 `useIntersectionObserver`（DataTable sticky header 偵測）
- 提供 `useMediaQuery`（取代 `isMobileViewport()` 手動偵測）
- Tree-shakeable，只打包使用的 composable

**替代方案考量：**
- **繼續自建** — 增加維護負擔，且自建版本缺乏 edge case 處理
- **整個替換為 VueUse** — 過度，只使用需要的 composable

### Decision 3: Inter 字體作為 Latin/數字補充

**選擇：** Inter（Variable font, woff2 local hosting）

**理由：**
- Tabular numbers（`font-variant-numeric: tabular-nums`）讓數據對齊
- 與 Noto Sans TC 視覺重心匹配（x-height 相近）
- Variable font 單檔涵蓋 400-700 weight
- Local hosting 避免 Google Fonts GDPR/效能問題

**Font stack 調整：**
```
fontFamily: {
  sans: ['Inter', 'Noto Sans TC', 'Microsoft JhengHei', 'system-ui', 'sans-serif']
}
```

**替代方案考量：**
- **DM Sans** — 幾何風格，與 Noto Sans TC 視覺衝突
- **IBM Plex Sans** — 優秀但字重檔案較大
- **保持純 Noto Sans TC** — Latin 字元與數字的 kerning 不如 Inter 精緻

### Decision 4: DataTable 元件架構

**選擇：** Compound component 模式（DataTable + DataTableColumn slot-based）

```vue
<DataTable
  :data="sortedData"
  :loading="loading"
  :pagination="pagination"
  sortable
  @sort="handleSort"
  @page-change="handlePageChange"
>
  <DataTableColumn key="LOT_ID" label="Lot" sortable width="180px">
    <template #cell="{ row }">{{ row.LOT_ID }}</template>
  </DataTableColumn>
  <DataTableColumn key="STATUS" label="狀態">
    <template #cell="{ row }">
      <StatusBadge :tone="getStatusTone(row.STATUS)">{{ row.STATUS }}</StatusBadge>
    </template>
  </DataTableColumn>
</DataTable>
```

**理由：**
- Slot-based 讓每個 column 的 cell 可自定義渲染（StatusBadge, link, formatted number 等）
- 內建 `useSortableTable` + `PaginationControl` 整合
- Sticky header、zebra striping、loading overlay、empty state 全部內建
- 向下相容：column 定義可從現有 `<th>`/`<td>` 逐步遷移

**替代方案考量：**
- **Config-based（JSON columns）** — 靈活度不足，cell 自定義需要 render function
- **Headless table（TanStack Table）** — 過度工程，MES 的 table 需求不需要虛擬滾動或複雜 grouping
- **純 composable（無 UI 元件）** — 已有 `useSortableTable`，但 markup 仍需各自重複

### Decision 5: SummaryCard 元件架構

**選擇：** 單一元件 + props 變體

```vue
<SummaryCardGroup :columns="5">
  <SummaryCard
    label="Total Lots"
    :value="summary.totalLots"
    format="number"
    accent="brand"
  />
  <SummaryCard
    label="OU%"
    :value="summary.ou"
    format="percent"
    accent="success"
    clickable
    :active="activeFilter === 'ou'"
    @click="toggleFilter('ou')"
  >
    <template #sub>
      <OuBadge :level="ouLevel" />
    </template>
  </SummaryCard>
</SummaryCardGroup>
```

**理由：**
- 統一三種現有 summary card 模式（wip 2-card / hold 5-card / resource 10-card）
- `accent` prop 取代 status class（`.prd`, `.sby` 等）→ 映射為 top border color
- `clickable` + `active` props 統一互動模式
- `format` prop 處理 `toLocaleString('zh-TW')` / percent / duration
- `SummaryCardGroup` 處理 responsive grid layout

**替代方案考量：**
- **各 feature 保持自建** — 已證明導致不一致
- **CSS-only（無 Vue 元件）** — 無法統一互動邏輯（click, active, hover）

### Decision 6: Page Transition 實作

**選擇：** 在 `NativeRouteView.vue` 以 Vue `<Transition>` 包裹「已解析的 native component」+ CSS-only animation

```vue
<!-- NativeRouteView.vue -->
<Transition name="page-fade" mode="out-in">
  <component
    :is="resolvedComponent"
    v-if="resolvedComponent"
    :key="targetRoute"
  />
</Transition>
```

```css
.page-fade-enter-active { transition: opacity var(--motion-normal) var(--motion-ease), transform var(--motion-normal) var(--motion-ease); }
.page-fade-leave-active { transition: opacity var(--motion-fast) var(--motion-ease); }
.page-fade-enter-from { opacity: 0; transform: translateY(8px); }
.page-fade-leave-to { opacity: 0; }
```

**理由：**
- 純 CSS，不需要額外 library
- `out-in` mode 確保不會同時渲染兩個頁面
- 進場 fade-up（200ms）+ 離場 fade（150ms）= 輕快不拖沓
- 尊重 `prefers-reduced-motion`
- 保持 shell host `App.vue` 的 `<RouterView />` 直出，不干擾現有 chart lifecycle/blank-state guard 測試

### Decision 7: Shell 視覺升級策略

**選擇：** 漸進增強現有 CSS，不重構 HTML 結構

| 項目 | 實作方式 |
|------|----------|
| Header blur | `backdrop-filter: blur(12px); background: rgba(0, 74, 118, 0.92)` |
| Header 底線 | `border-bottom: 1px solid rgba(255,255,255,0.1)` |
| Sidebar accent | `.drawer-link.active::before { width: 3px; background: brand.500 }` |
| Sidebar hover | `transition: background var(--motion-fast), color var(--motion-fast)` |
| Breadcrumb | 加入 Lucide `ChevronRight` icon separator |

**理由：** HTML 結構不動 = 不影響功能邏輯，純視覺增強。

### Decision 8: Shadow 系統擴展

**選擇：** 5 級語意化 shadow

```js
boxShadow: {
  xs:    '0 1px 2px rgba(0, 0, 0, 0.04)',
  sm:    '0 1px 4px rgba(0, 0, 0, 0.06)',     // 現有 soft
  md:    '0 4px 12px rgba(0, 0, 0, 0.08)',     // 現有 panel
  lg:    '0 8px 24px rgba(0, 0, 0, 0.12)',
  xl:    '0 16px 48px rgba(0, 0, 0, 0.16)',
}
```

**理由：** 現有 3 級（soft/panel/shell）命名不語意化，擴展為業界標準 5 級。保留 `soft`/`panel` 作為 alias 向下相容（`soft→sm`、`panel→md`）。`shell` 保持原 brand-blue 值 (`rgba(0, 128, 200, 0.25)`) 不納入中性高度 alias，因其攜帶品牌色彩語意（chrome 互動元素聚焦陰影），與中性高度陰影性質不同。

---

## Risks / Trade-offs

| Risk | Impact | Mitigation |
|------|--------|------------|
| DataTable 無法覆蓋所有現有 table 的特殊需求（expandable rows, matrix layout） | 部分 feature 需保留自建 table | DataTable 提供 `#expand` slot；Matrix table 保持獨立元件，不強制遷移 |
| Inter 字體增加首次載入大小 | ~100KB (variable woff2) | `font-display: swap` + preload；中文頁面 Noto Sans TC 已是主要瓶頸，Inter 影響可忽略 |
| 新增 2 個 npm 依賴增加 bundle | lucide ~3KB/icon, vueuse ~5KB/composable (tree-shaken) | 兩者都 tree-shakeable；實測後若超出預算可 lazy import |
| Feature page 批次改造可能引入 regression | 功能行為變更 | 每批次改造後 visual snapshot 驗證 + 手動 smoke test |
| Shell 視覺變更影響所有頁面 | 全域影響 | Shell 變更作為獨立 PR，全頁面驗收後再進行 feature 批次 |
| 向下相容 alias 造成 CSS 膨脹 | 雙重 class 定義 | Phase 5 CSS 瘦身時移除 alias |

---

## Migration Plan

### Phase 順序與交付節奏

```
Phase 1: Design Token 擴展 + 字體引入
  ├── PR-1a: tailwind.config.js token 擴展 + Inter font
  └── PR-1b: styles/tailwind.css CSS variables + shadow alias

Phase 2: 核心元件
  ├── PR-2a: npm install lucide-vue-next @vueuse/core
  ├── PR-2b: DataTable + DataTableColumn 元件
  ├── PR-2c: SummaryCard + SummaryCardGroup 元件
  ├── PR-2d: Chip 元件
  └── PR-2e: 現有元件升級（SectionCard, PageHeader, FilterToolbar, EmptyState, StatusBadge）

Phase 3: Shell 視覺
  └── PR-3: Shell header/sidebar/breadcrumb/page-transition

Phase 4: Feature Pages（6 批次，每批次 1 PR）
  ├── PR-4a: wip-overview, hold-overview, resource-status
  ├── PR-4b: hold-detail, wip-detail, reject-history
  ├── PR-4c: resource-history, hold-history, qc-gate
  ├── PR-4d: query-tool, material-trace, yield-alert-center
  ├── PR-4e: job-query, tables, excel-query, mid-section-defect
  └── PR-4f: admin-dashboard, anomaly-overview, production-history

Phase 5: CSS 瘦身
  └── PR-5: 移除重複 class、shadow alias、更新 css_inventory.md
```

### Rollback 策略

- 每個 PR 獨立可 revert
- Phase 1-2 是 additive（新增 token/元件），不影響現有功能
- Phase 3 Shell 變更若需 rollback，revert single PR 即可
- Phase 4 各批次獨立，單一 feature regression 只需 revert 該批次

---

## Finalized Decisions (Apply-ready)

1. **Matrix table 不遷移為 DataTable**：`wip-overview` / `hold-overview` 維持獨立 Matrix 元件；僅對齊 loading/empty interaction pattern。
2. **Inter 一律 local woff2**：不使用 CDN，確保可控性與部署一致性。
3. **Batch 順序固定為 PR-4a ~ PR-4f**：除非業務緊急升級優先級，否則按既定順序執行以降低交付風險。
4. **不引入 Storybook**：本變更以 shared-ui 元件檔內說明 + OpenSpec artifacts 作為文件化載體，避免新增維運成本。
