# Design: brand-alignment-residual

## Decision 1: Hex Token → 語意 Token 對照表

機械式替換，每個 hex token 對應一個語意 brand token：

| Hex Token | 舊色值 | 語意對應 | 理由 |
|-----------|--------|---------|------|
| `token.h2563eb` | `#2563eb` (blue-600) | `brand.600` | 最接近的品牌色階，用於 hover/active 態 |
| `token.h4f46e5` | `#4f46e5` (indigo-600) | `brand.700` | 用於 primary-dark、spinner、active 色 |
| `token.h6366f1` | `#6366f1` (indigo-500) | `brand.500` | 用於漸層、primary var |
| `token.h5568d3` | `#5568d3` (indigo) | `brand.700` | 用於 primary-dark CSS var |
| `token.h8b5cf6` | `#8b5cf6` (purple-400) | `accent.500` | 漸層終點色（admin header）；`resource-shared` 的 `--status-egt` 保留不動 |
| `token.hc7d2fe` | `#c7d2fe` (light indigo) | `brand.100` | 邊框高亮色 |

### 例外不處理

| Token | 用途 | 理由 |
|-------|------|------|
| `resource-shared:22` `--status-egt: token.h8b5cf6` | 設備狀態色 (EGT) | 非品牌色，屬功能語意，需獨立命名（未來 `state.egt`） |

## Decision 2: Admin Header Gradient — 統一為品牌藍單色系

**Before（三套不同的 indigo 漸層）：**
```css
/* admin-dashboard */
background: linear-gradient(135deg, token.h2563eb 0%, token.h6366f1 45%, token.h8b5cf6 100%);
/* admin-performance */
background: linear-gradient(135deg, token.h6366f1 0%, token.h8b5cf6 100%);
/* admin-user-usage-kpi */
background: linear-gradient(135deg, token.h2563eb 0%, token.h6366f1 100%);
```

**After（統一）：**
```css
background: linear-gradient(135deg, theme('colors.brand.800') 0%, theme('colors.brand.500') 100%);
```

理由：與 `panjit-brand-alignment` 確立的 header gradient 標準一致（Decision 2）。

## Decision 3: portal-shell 全域樣式遷移

**Before（`portal-shell/style.css` 第 1-14 行）：**
```css
:root { color-scheme: light; }
* { box-sizing: border-box; }
body {
  margin: 0;
  font-family: "Noto Sans TC", "Microsoft JhengHei", sans-serif;
  background: theme('colors.token.hf5f7fa');
  color: theme('colors.token.h1f2937');
}
```

**After：**
- 將 `:root { color-scheme: light; }` 移至 `tailwind.css` 的 `@layer base`
- 刪除 `* { box-sizing }` — Tailwind preflight 已設定 `*, *::before, *::after { box-sizing: border-box; }`
- 將 `body` 規則移至 `tailwind.css` 的 `@layer base`，並改用語意 token：
  ```css
  body {
    margin: 0;
    font-family: theme('fontFamily.sans');
    background: theme('colors.surface.app');
    color: theme('colors.text.primary');
  }
  ```

理由：
- CSS 契約 2.1 禁止在非 `tailwind.css` 的檔案中定義 `:root` 規則
- CSS 契約 5.2 要求 base style resets 在 `@layer base` 中定義
- `token.hf5f7fa` = `surface.app`，`token.h1f2937` = `text.primary`（已有語意對應）

## Decision 4: Vue/JS hex token var 遷移 + tailwind.css CSS var 清理

Vue/JS 中有 8 處透過 `var(--color-token-hXXXXXX)` 直接引用 hex token CSS var（圖表色、KPI 卡片色）。需先建立語意 CSS var，再遷移引用，最後移除無引用的 hex token var。

**Step 1 — 新增語意 CSS var（`tailwind.css :root`）：**
```css
--color-brand-500: theme('colors.brand.500');
--color-brand-600: theme('colors.brand.600');
--color-accent-500: theme('colors.accent.500');
```

**Step 2 — 遷移 Vue/JS 引用：**

| 檔案 | 舊值 | 新值 |
|------|------|------|
| `OverviewTab.vue:99` | `var(--color-token-h2563eb)` | `var(--color-brand-600)` |
| `EquipmentTimeline.vue:64` | `var(--color-token-h2563eb)` | `var(--color-brand-600)` |
| `KpiCards.vue:34,80` | `var(--color-token-h6366f1)` | `var(--color-brand-500)` |
| `OverviewTab.vue:103` | `var(--color-token-h8b5cf6)` | `var(--color-accent-500)` |
| `KpiCards.vue:52,86` | `var(--color-token-h8b5cf6)` | `var(--color-accent-500)` |

例外：`constants.js:27` `EGT: 'var(--color-token-h8b5cf6)'` — 設備狀態色，非品牌色，保留不動（同 Decision 1 例外）。

**Step 3 — 移除已無引用的 hex token var：**
- 移除：`--color-token-h2563eb`、`--color-token-h6366f1`（引用歸零）
- 保留：`--color-token-h8b5cf6`（`constants.js` EGT 仍引用）

## Decision 5: admin-performance 作用域修復

`admin-performance/style.css` 的 `.perf-header` 未在 `.theme-admin-performance` 作用域下。由於該檔案僅由 admin-performance 路由載入（route-local CSS），CSS 契約 4.3 允許 route-local CSS 可不加 theme 作用域。但為一致性，建議保持現狀不動（風險低於修改）。

## Architecture

```
tailwind.css @layer base  ←── 1. 接收 portal-shell 遷移的全域規則 + 清理 CSS var
       │
       ├── portal-shell/style.css  ←── 2. 移除 :root/*/body 全域規則
       │
       ├── admin-dashboard/style.css  ←── 3. header gradient → brand.800→brand.500
       ├── admin-performance/style.css  ←── 3. header gradient → brand.800→brand.500
       ├── admin-user-usage-kpi/style.css  ←── 3. header gradient + token 遷移
       ├── mid-section-defect/style.css  ←── 3. --msd-primary + token 遷移
       │
       ├── wip-shared/styles.css  ←── 4. --primary-dark token 遷移
       ├── yield-alert-center/style.css  ←── 4. --ya-primary-hover token 遷移
       │
       ├── resource-shared/styles.css  ←── 5. --resource-primary token 遷移
       ├── resource-history/style.css  ←── 5. accent-color token 遷移
       ├── reject-history/style.css  ←── 5. accent-color + 背景 token 遷移
       ├── query-tool/style.css  ←── 5. accent-color token 遷移
       │
       ├── anomaly-overview/style.css  ←── 6. spinner/active token 遷移
       ├── tables/style.css  ←── 6. --primary token 遷移
       ├── excel-query/style.css  ←── 6. btn 背景 token 遷移
       ├── job-query/style.css  ←── 6. btn 背景 token 遷移
       ├── portal/portal.css  ←── 6. border-color token 遷移
       ├── shared-composables/TraceProgressBar.vue  ←── 6. color token 遷移
       │
       └── portal-shell/style.css  ←── 6. .btn-link token 遷移
```

## Risk & Mitigation

| 風險 | 影響 | 緩解策略 |
|------|------|---------|
| `token.h2563eb` 散佈廣泛（17 處），替換為 `brand.600` 後色差明顯 | `#2563eb` (鮮藍) vs `#006BA8` (深企業藍) 色差較大 | 視覺走查重點檢查 resource 模組的 accent-color 和互動色 |
| `--status-egt` 保留 `token.h8b5cf6` 但 admin 漸層遷移後該 token 仍需存在 | 無法移除 config 中的 token | 可接受，後續以 `state.egt` 獨立語意化 |
| portal-shell body 規則遷移後 CSS 載入順序變化 | `@layer base` 權重低於非 layer CSS，可能被覆蓋 | 驗證：portal-shell 載入後 body 樣式是否正確套用 |
| `token.h4f46e5` 用於 spinner 動畫 border-top-color | 色彩改變可能影響 loading 感知 | brand.700 仍為深藍色，spinner 視覺影響小 |
