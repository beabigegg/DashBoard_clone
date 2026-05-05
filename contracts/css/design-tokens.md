---
contract: design-tokens
summary: Canonical design token inventory for colors, spacing, typography, and layering.
owner: design-system
surface: ui
schema-version: 1.0.0
last-changed: 2026-05-05
---

# Design Tokens

> 唯一真實來源：`frontend/tailwind.config.js` → `theme.extend`  
> 此文件是說明性索引；以 tailwind.config.js 的實際內容為準。

## Colors

所有顏色定義在 `tailwind.config.js` 的 `theme.extend.colors`：

| token key | usage |
|---|---|
| `brand.*` | 主色系（按鈕、連結、highlight） |
| `accent.*` | 輔助色（互補、強調） |
| `stroke.panel` | 卡片邊框色 |
| `danger` / `warning` / `success` | 語意狀態色（用於 Chip `tone` 系統、ErrorBanner） |
| `seriesA`...`seriesN` | 圖表序列色（ECharts palette 集中引用點） |

**引用方式（CSS 中）：** `theme('colors.brand.500')`  
**引用方式（JS/Vue 圖表）：** 從集中 palette 物件取得，禁止散落硬編碼相同色碼。

## Spacing

沿用 Tailwind 預設間距尺度；自訂間距定義在 `theme.extend.spacing`。

## Typography

字體大小、行高、字重在 `theme.extend.fontSize` / `theme.extend.fontWeight` 定義。

## Radius / Shadow

| token | 用途 |
|---|---|
| `boxShadow.panel` | SummaryCard、SectionCard 陰影 |
| `borderRadius.*` | 通用圓角（通常從 Tailwind 預設） |

## Z-index

z-index 值不應硬編碼；若需新 layer 必須先在 `tailwind.config.js` 定義並 PR review。

## Token Addition Policy

1. 新增 token 必須修改 `frontend/tailwind.config.js`，並在同一 PR 補充此文件的索引。
2. 禁止在 `.css` 的 `:root` 中手動定義 CSS 變數作為替代（違反 CSS Contract §2.1）。
3. 新 token 需語意化命名（不用 `color-1`, `spacing-42`）。
4. 圖表色碼例外：若第三方圖表函式庫必須用 HEX，需集中定義為 palette 物件，不得散落各 component。
