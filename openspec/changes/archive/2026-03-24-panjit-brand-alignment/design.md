# Design: panjit-brand-alignment

## Decision 1: PANJIT 企業藍取代紫色漸層

將 `tailwind.config.js` 的 `brand` 色彩從紫藍系改為 PANJIT 企業藍。

### 色彩對照表

| Token | 現有值 | 新值 | 來源 |
|-------|--------|------|------|
| `brand.50` | `#eef2ff` (紫調) | `#e6f4fb` (藍調) | 品牌藍 50 |
| `brand.100` | `#e0e7ff` (紫調) | `#b3dbf2` (藍調) | 品牌藍 100 |
| `brand.500` | `#667eea` (紫藍) | `#0080C8` (PANJIT 藍) | Logo 藍色方塊 |
| `brand.600` | `#5a67d8` | `#006BA8` | hover 態 |
| `brand.700` | `#4c51bf` | `#005A8F` | active 態 |
| `brand.800` | `#4338ca` | `#004A76` | 深色背景 |
| `accent.500` | `#764ba2` (紫色) | `#00A3E0` (亮科技藍) | 漸層輔色 |

### 連帶更新

| 項目 | 現有值 | 新值 |
|------|--------|------|
| `surface.active` | `#eef2ff` | `#e6f4fb` |
| `boxShadow.shell` | `rgba(102, 126, 234, 0.3)` | `rgba(0, 128, 200, 0.25)` |
| `:root` → `--portal-brand-start` | `theme('colors.token.h667eea')` | `theme('colors.brand.500')` |
| `:root` → `--portal-brand-end` | `theme('colors.token.h764ba2')` | `theme('colors.accent.500')` |

理由：
- PANJIT Logo 核心視覺為藍色方塊 + 深炭灰文字
- 年報使用深藍/灰色調，偏專業半導體風格
- 修改 tailwind.config.js 的 token，所有透過 `theme('colors.brand.*')` / `theme('colors.accent.*')` 引用的 CSS 自動跟著變（約 27 處引用）

## Decision 2: Header 漸層方案 — 深藍→品牌藍

採用深色起點的單色系漸層：

```css
.ui-page-header, .shell-header {
  background: linear-gradient(135deg, theme('colors.brand.800') 0%, theme('colors.brand.500') 100%);
}
```

不採用雙色漸層（brand + accent），理由：
- 半導體產業偏好沈穩、專業的單色調
- 單色系漸層更耐看，不會隨流行褪色
- accent 藍保留給圖表強調、hover 反饋等次要場景

`.ui-btn--primary` 同樣改為單色系：
```css
.ui-btn--primary {
  background: theme('colors.brand.500');  /* 純色取代漸層 */
}
.ui-btn--primary:hover {
  background: theme('colors.brand.600');
  box-shadow: 0 4px 12px rgba(0, 128, 200, 0.35);
}
```

## Decision 3: 排版層級 — 覆蓋 Tailwind 預設 fontSize

```js
fontSize: {
  '2xs': ['11px', { lineHeight: '1rem' }],      // 輔助、badge
  'xs':  ['12px', { lineHeight: '1.125rem' }],   // 標籤、filter label
  'sm':  ['13px', { lineHeight: '1.25rem' }],    // body small（合法化 13px）
  'base':['14px', { lineHeight: '1.375rem' }],   // body default
  'lg':  ['16px', { lineHeight: '1.5rem' }],     // section title
  'xl':  ['20px', { lineHeight: '1.75rem' }],    // page subtitle
  '2xl': ['24px', { lineHeight: '2rem' }],       // page title (h1)
}
```

理由：覆蓋 `text-sm` 為 13px 後，現有大量 `font-size: 13px` 的規則可逐步改用 `text-sm` utility。

## Decision 4: 按鈕系統擴展

在 `styles/tailwind.css` 的 `@layer components` 新增變體，保持 `ui-btn` BEM 命名：

| 變體 | 用途 | 樣式 |
|------|------|------|
| `ui-btn--primary` | 主要動作 | `brand.500` 純色底 + 白字 |
| `ui-btn--secondary` | 次要動作 | `brand.50` 底 + `brand.600` 字 + `brand.500` 邊框 |
| `ui-btn--danger` | 破壞性動作 | `state.danger` 底 + 白字 |
| `ui-btn--ghost` | (現有) | 維持不變 |
| `ui-btn--sm` | (現有) | 維持不變 |

清除範圍（殘留的非 `ui-btn` 按鈕定義）：

| 檔案 | 規則 | 處理 |
|------|------|------|
| `portal-shell/style.css:305` | `.btn-link` | 清除（原誤標為 `.btn-primary`，實際不存在） |
| `query-tool/style.css:71-112` | `.btn`, `.btn-primary`, `.btn-export` | 改用 `ui-btn` 系列 |
| `admin-dashboard/style.css:80-99` | `.btn` | 改用 `ui-btn` 系列 |
| `admin-performance/style.css:51-70` | `.btn` | 改用 `ui-btn` 系列 |
| `admin-user-usage-kpi/style.css:63-82` | `.btn` | 改用 `ui-btn` 系列 |
| `material-trace/style.css:289-299` | `.btn-export` | 改用 `ui-btn` 系列 |

## Decision 5: 表格現代化 — 漸進式修改

在各 feature `style.css` 中修改 `.matrix-table` 相關樣式（保持 `.theme-xxx` 作用域）：

**Before:**
```css
.theme-xxx .matrix-table { border-collapse: collapse; }
.theme-xxx .matrix-table th, td { border: 1px solid ...; }
```

**After:**
```css
.theme-xxx .matrix-table { border-collapse: separate; border-spacing: 0; }
.theme-xxx .matrix-table th {
  background: theme('colors.brand.50');
  border-bottom: 2px solid theme('colors.stroke.panel');
  position: sticky; top: 0; z-index: 1;
}
.theme-xxx .matrix-table td {
  border-bottom: 1px solid theme('colors.stroke.soft');
}
.theme-xxx .matrix-table tbody tr:hover { background: theme('colors.surface.hover'); }
```

影響檔案（4 個含 matrix-table 的 CSS + 3 個 Vue 檔案）：在 `wip-shared/styles.css` 和 `resource-shared/styles.css` 兩個共用層修改，`hold-overview/style.css` 和 `wip-overview/style.css` 有 route-local 覆蓋需同步調整。

## Decision 6: Skeleton Loading — Vue scoped 元件

新增 `frontend/src/shared-ui/components/SkeletonLoader.vue`：
- Props: `type` (`text` | `card` | `table`)、`rows`（行數）
- 使用 `<style scoped>` — 不新增獨立 CSS 檔案
- 動畫 `@keyframes shimmer` 定義在 scoped style 內
- 需更新 `contract/css_inventory.md` 的 Shared UI Component Styles 表格

## Decision 7: Token 語意化 — 分批漸進

**第一批**（本次變更處理）：移除已被語意 token 完全覆蓋的重複項 + 遷移品牌相關 hex token：

| 現有 token | 已被覆蓋為 | 處理 |
|-----------|-----------|------|
| `token.h667eea` | `brand.500`（舊值，本次改為 `#0080C8`） | 移除（config 層） |
| `token.h764ba2` | `accent.500`（舊值，本次改為 `#00A3E0`） | 移除（config 層） |
| `token.heef2ff` | `brand.50`（舊值 `#eef2ff`） | 引用遷移至 `brand.50`（7 處） |
| `token.h4338ca` | `brand.800`（舊值 `#4338ca`） | 引用遷移至 `brand.800`（5 處） |
| `token.h4c51bf` | `brand.700`（舊值 `#4c51bf`） | 引用遷移至 `brand.700`（2 處） |
| `token.hc7d2fe` | `brand.100`（舊值 `#c7d2fe`） | 引用遷移至 `brand.100`（5 處） |
| `token.h6366f1` | `brand.500`（舊值 `#6366f1`） | 部分遷移（job-query 1 處）；admin 系列保留 |
| `token.h1e3a8a` | `brand.800` | 引用遷移至 `brand.800`（2 處） |
| `token.h1f2937` | `text.primary` | 保留（仍有 CSS var 引用） |
| `token.h64748b` | `text.secondary` / `text.muted` | 保留（仍有 CSS var 引用） |
| `token.hf5f7fa` | `surface.app` | 保留（仍有 CSS var 引用） |
| `token.hffffff` | `surface.card` | 保留（仍有 CSS var 引用） |

同步修正硬編碼的 `rgba(102, 126, 234, ...)` 和 `rgba(99, 102, 241, ...)` 為品牌藍 `rgba(0, 128, 200, ...)`（10 處）。

**後續批次**：
- `token.h6366f1` 在 admin-dashboard、admin-performance、admin-user-usage-kpi、mid-section-defect 的漸層引用（獨立變更）
- `token.h5568d3` 在 wip-shared、yield-alert-center 的 CSS var 引用
- 其餘非品牌相關 hex token 的語意化遷移

## Architecture

```
tailwind.config.js  ←── 1. 修改品牌色 + 排版層級（所有下游自動生效）
       │
       ├── styles/tailwind.css  ←── 2. 更新 :root vars, ui-btn 擴展, ui-page-header
       │
       ├── portal-shell/style.css  ←── 3. shell-header 漸層 + token 遷移 + 清除 .btn-link
       │
       ├── wip-shared/styles.css  ←── 4. 表格現代化 + rgba 修正
       ├── resource-shared/styles.css  ←── 4. 表格現代化 + header gradient 修正
       │
       ├── resource-history/style.css  ←── 4a. header gradient 修正
       ├── hold-history/style.css  ←── 4a. header gradient 修正
       ├── yield-alert-center/style.css  ←── 4a. header gradient + rgba 修正
       ├── reject-history/style.css  ←── 4a. header gradient 修正
       │
       ├── query-tool/style.css  ←── 5. 按鈕清除 + token 遷移 + rgba 修正
       ├── admin-dashboard/style.css  ←── 5. 按鈕清除
       ├── admin-performance/style.css  ←── 5. 按鈕清除
       ├── admin-user-usage-kpi/style.css  ←── 5. 按鈕清除
       ├── material-trace/style.css  ←── 5. 按鈕清除
       │
       ├── anomaly-overview/style.css  ←── 5a. token 遷移
       ├── hold-overview/style.css  ←── 5a. token 遷移 + rgba 修正
       ├── wip-detail/style.css  ←── 5a. rgba 修正
       ├── qc-gate/style.css  ←── 5a. token 遷移 + rgba 修正
       ├── job-query/style.css  ←── 5a. token 遷移
       │
       ├── shared-ui/components/AiChartRenderer.vue  ←── 5b. 圖表調色盤對齊
       ├── query-tool/components/LineageTreeChart.vue  ←── 5b. token 遷移
       │
       ├── shared-ui/components/SkeletonLoader.vue  ←── 6. 新增元件
       │
       └── contract/css_inventory.md  ←── 7. 同步更新
```

## Risk & Mitigation

| 風險 | 影響 | 緩解策略 |
|------|------|---------|
| 漸層色變更後 LoginPage 視覺落差 | LoginPage 的 glassmorphism 效果依賴品牌色 | 需微調 LoginPage 的光球和按鈕色彩 |
| 移除 `.btn-primary` 等舊類別導致 Vue template 壞掉 | 按鈕失去樣式 | 同步更新 Vue template 的 class 名稱 |
| 表格改為無邊框後在資料密集場景可讀性下降 | 用戶難以區分欄位 | 保留 `td` 的 `border-bottom`，配合 zebra stripes |
| `resource-shared` header gradient 影響 7 個 theme 作用域 | 若遺漏則 hold/resource/yield 等頁面顯示不一致漸層 | 已納入 Task 1.8 統一處理 |
| 硬編碼 rgba 紫色值未被 token 變更觸及 | shadow/focus ring 仍呈現舊紫色調 | 已納入 Task 1.10 全面替換為品牌藍 rgba |
| admin 系列漸層使用 `h6366f1`/`h8b5cf6` 不在本次範圍 | admin 頁面仍保留 indigo 風格 | 標記為後續獨立變更（不影響主要使用者流程） |
