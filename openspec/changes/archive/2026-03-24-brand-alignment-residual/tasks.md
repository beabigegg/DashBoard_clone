# Tasks: brand-alignment-residual

## Phase 1: Admin 漸層 + CSS var 對齊（高優先級）

- [x] 1.1 修改 `admin-dashboard/style.css:10` header gradient
  - `linear-gradient(135deg, token.h2563eb 0%, token.h6366f1 45%, token.h8b5cf6 100%)` → `linear-gradient(135deg, theme('colors.brand.800') 0%, theme('colors.brand.500') 100%)`

- [x] 1.2 修改 `admin-performance/style.css:11` header gradient
  - `linear-gradient(135deg, token.h6366f1 0%, token.h8b5cf6 100%)` → `linear-gradient(135deg, theme('colors.brand.800') 0%, theme('colors.brand.500') 100%)`

- [x] 1.3 修改 `admin-user-usage-kpi/style.css:11` header gradient
  - `linear-gradient(135deg, token.h2563eb 0%, token.h6366f1 100%)` → `linear-gradient(135deg, theme('colors.brand.800') 0%, theme('colors.brand.500') 100%)`

- [x] 1.4 修改 `mid-section-defect/style.css` CSS var 和 border
  - `:9` `--msd-primary: token.h6366f1` → `brand.500`
  - `:10` `--msd-primary-dark: token.h4f46e5` → `brand.700`
  - `:371` `border-top: 3px solid token.h6366f1` → `brand.500`

- [x] 1.5 修改 `wip-shared/styles.css:16` CSS var
  - `--primary-dark: token.h5568d3` → `brand.700`

- [x] 1.6 修改 `yield-alert-center/style.css:8` CSS var
  - `--ya-primary-hover: token.h5568d3` → `brand.700`

## Phase 2: 高頻 hex token 語意化（高優先級）

### token.h2563eb → brand.600（17 處）

- [x] 2.1 `resource-shared/styles.css`
  - `:15` `--resource-primary: token.h2563eb` → `brand.600`
  - `:366` `color: token.h2563eb` → `brand.600`
  - `:580` `accent-color: token.h2563eb` → `brand.600`

- [x] 2.2 `admin-dashboard/style.css:606`
  - `color: token.h2563eb` → `brand.600`

- [x] 2.3 `admin-user-usage-kpi/style.css:102`
  - `color: token.h2563eb` → `brand.600`

- [x] 2.4 `reject-history/style.css`
  - `:30` `background: token.h2563eb` → `brand.600`
  - `:252` `accent-color: token.h2563eb` → `brand.600`
  - `:465` `border-top-color: token.h2563eb` → `brand.600`
  - `:622` `accent-color: token.h2563eb` → `brand.600`

- [x] 2.5 `resource-history/style.css:81`
  - `accent-color: token.h2563eb` → `brand.600`

- [x] 2.6 `query-tool/style.css:495`
  - `accent-color: token.h2563eb` → `brand.600`

- [x] 2.7 `shared-composables/TraceProgressBar.vue:124`
  - `color: token.h2563eb` → `brand.600`

### token.h4f46e5 → brand.700（9 處）

- [x] 2.8 `tables/style.css:8`
  - `--primary: token.h4f46e5` → `brand.700`

- [x] 2.9 `anomaly-overview/style.css`
  - `:156` `color: token.h4f46e5` → `brand.700`
  - `:258` `border-top-color: token.h4f46e5` → `brand.700`
  - `:279` `border-top: 2px solid token.h4f46e5` → `brand.700`
  - `:299` `background: token.h4f46e5` → `brand.700`

- [x] 2.10 `excel-query/style.css:60`
  - `background: token.h4f46e5` → `brand.700`

- [x] 2.11 `job-query/style.css:74`
  - `background: token.h4f46e5` → `brand.700`

- [x] 2.12 `portal-shell/style.css:290`
  - `.btn-link` `color: token.h4f46e5` → `brand.700`

### 其他 token

- [x] 2.13 `portal/portal.css:65`
  - `border-color: token.hc7d2fe` → `brand.100`

## Phase 3: portal-shell 契約違規修復（中優先級）

- [x] 3.1 將 `portal-shell/style.css` 的 `:root { color-scheme: light; }` 遷移至 `tailwind.css` 的 `@layer base`

- [x] 3.2 移除 `portal-shell/style.css` 的 `* { box-sizing: border-box; }` — Tailwind preflight 已處理

- [x] 3.3 將 `portal-shell/style.css` 的 `body { ... }` 遷移至 `tailwind.css` 的 `@layer base`
  - `font-family` 改為 `theme('fontFamily.sans')`
  - `background: token.hf5f7fa` 改為 `surface.app`
  - `color: token.h1f2937` 改為 `text.primary`

- [x] 3.4 遷移 Vue/JS 中殘留的 `var(--color-token-hXXXXXX)` 引用
  - `admin-dashboard/tabs/OverviewTab.vue:99` `var(--color-token-h2563eb)` → `var(--color-brand-600)`
  - `query-tool/components/EquipmentTimeline.vue:64` `var(--color-token-h2563eb)` → `var(--color-brand-600)`
  - `mid-section-defect/components/KpiCards.vue:34,80` `var(--color-token-h6366f1)` → `var(--color-brand-500)`
  - `admin-dashboard/tabs/OverviewTab.vue:103` `var(--color-token-h8b5cf6)` → `var(--color-accent-500)`
  - `mid-section-defect/components/KpiCards.vue:52,86` `var(--color-token-h8b5cf6)` → `var(--color-accent-500)`
  - 例外：`resource-shared/constants.js:27` EGT 設備狀態色 — 保留不動（同 `--status-egt` 例外）

- [x] 3.5 在 `tailwind.css` `:root` 新增語意 CSS var 並移除已無引用的 hex token var
  - 新增：`--color-brand-500`, `--color-brand-600`, `--color-accent-500`（指向 `theme('colors.brand.*')` / `theme('colors.accent.*')`）
  - 移除：`--color-token-h2563eb`、`--color-token-h6366f1`（引用歸零後）
  - 保留：`--color-token-h8b5cf6`（`constants.js` EGT 仍引用）

## Phase 4: 收尾驗證

- [x] 4.1 Vite production build — 確認無編譯錯誤
- [x] 4.2 視覺走查 — 重點頁面：admin-dashboard, admin-performance, resource-status, wip-overview, anomaly-overview, portal-shell sidebar
