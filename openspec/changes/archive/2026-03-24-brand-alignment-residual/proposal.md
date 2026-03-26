# Proposal: brand-alignment-residual

## Problem

`panjit-brand-alignment` 變更將核心 `brand.*` / `accent.*` token 從紫色系改為 PANJIT 企業藍，並處理了直接引用 `brand.*` 的 CSS 和高可見度的 hex token。然而，審核發現以下殘留問題：

1. **Admin 系列 indigo 漸層未對齊**：`admin-dashboard`、`admin-performance`、`admin-user-usage-kpi` 的 header gradient 仍使用 `token.h2563eb→h6366f1→h8b5cf6`（indigo/紫色漸層），與已對齊的主站品牌藍不一致
2. **CSS var 中的舊紫色 token**：`wip-shared` 的 `--primary-dark` 和 `yield-alert-center` 的 `--ya-primary-hover` 仍指向 `token.h5568d3`
3. **portal-shell 全域樣式違反 CSS 契約 2.1/5.2**：`:root`、`*`、`body` 規則應在 `tailwind.css` 的 `@layer base` 中定義
4. **大量 hex token 引用未語意化**：`token.h2563eb`（17 處）、`token.h4f46e5`（9 處）、`token.h6366f1`（6 處）等仍以 hex 命名引用，語意不清

## Appetite

Medium — 變更範圍橫跨約 15 個 CSS/Vue 檔案，但每個檔案的改動是機械式的 token 替換，風險可控。

## Solution

### Phase 1: Admin 漸層 + CSS var 對齊（高優先級）

- Admin 系列 header gradient 統一改為 `brand.800 → brand.500` 單色系漸層
- `mid-section-defect` 的 `--msd-primary` 改為 `brand.500`
- `wip-shared` 的 `--primary-dark` 和 `yield-alert-center` 的 `--ya-primary-hover` 改為 `brand.700`

### Phase 2: 高頻 hex token 語意化遷移（高優先級）

- `token.h2563eb`（#2563eb, blue-600）→ `brand.600`（17 處跨 10 個檔案）
- `token.h4f46e5`（#4f46e5, indigo-600）→ `brand.700`（9 處跨 7 個檔案）
- `token.h6366f1`（#6366f1, indigo-500）→ `brand.500`（6 處跨 5 個檔案）
- `token.h5568d3`（#5568d3, indigo）→ `brand.700`（2 處）
- `token.hc7d2fe`（#c7d2fe, light indigo）→ `brand.100`（1 處）

### Phase 3: portal-shell 契約違規修復（中優先級）

- 將 `:root { color-scheme }` 遷移至 `tailwind.css` 的 `@layer base`
- 移除 `* { box-sizing }` (Tailwind preflight 已處理)
- 將 `body` 規則遷移至 `tailwind.css` 的 `@layer base`
- 清理 `tailwind.css` 中已無引用的 CSS var（`--color-token-h6366f1` 等）

### Phase 4: 收尾

- Vite build 驗證
- 視覺走查

## Non-goals

- 不修改 `token.h8b5cf6` 在 `resource-shared` 的 `--status-egt` 用途（這是設備狀態語意色，非品牌色）
- 不處理非紫色/indigo 系的 hex token（如 `token.hf5f7fa`、`token.h1f2937` 等灰色系 token）
- 不修改 Vue template 結構
- 不修改後端 API

## Constraints

- **CSS 契約 2.1**：禁止在 `:root` 手動定義色彩
- **CSS 契約 2.2**：所有設計 token 只改 `tailwind.config.js` 的 `theme.extend`
- **CSS 契約 4.2/4.3**：Feature 樣式保持 `.theme-xxx` 作用域
- **CSS 契約 5.2**：base style resets 只能在 `tailwind.css` 的 `@layer base`
