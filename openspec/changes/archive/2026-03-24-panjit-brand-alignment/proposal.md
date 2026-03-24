# Proposal: panjit-brand-alignment

## Problem

MES Dashboard 的品牌色彩使用泛用紫色漸層（`#667eea` → `#764ba2`），與 PANJIT 的企業識別完全脫鉤。PANJIT Logo 的核心視覺元素是**企業藍色方塊**（約 `#0080C8`）搭配**深炭灰文字**，年報與官網也一致使用深藍/灰色調的專業半導體風格。

目前的問題：
1. **品牌失焦**：紫色漸層偏向 2020 泛用 SaaS 風格，無 PANJIT 企業辨識度
2. **排版碎片化**：大量使用 `13px` 不在 Tailwind scale 中，字級混用 12-16px 多種尺寸無統一層級
3. **按鈕系統碎片化**：至少 3-4 套按鈕定義分散在不同 CSS 檔案
4. **表格偏舊**：全邊框 + `border-collapse` 風格偏工程感，缺乏現代 dashboard 體驗
5. **載入體驗**：僅有 spinner 和 opacity 淡化，缺少 skeleton loading
6. **Token 命名混亂**：約 130 個 `token.hXXXXXX` 以 hex 值命名，完全喪失語意

## Appetite

Medium — 分 3 個 Phase 依優先級推進，高優先級項目（品牌色、排版、按鈕）可在一個迭代內完成，中/低優先級項目可後續跟進。

## Solution

### Phase 1: 品牌基礎對齊（高優先級）

1. **品牌色彩對齊 PANJIT 企業藍**
   - `tailwind.config.js` 的 `brand` 系列從紫色改為 PANJIT 藍（`#0080C8` 為主色）
   - `accent` 從紫色改為亮科技藍（`#00A3E0`）
   - 連帶更新 `boxShadow.shell`、`surface.active`
   - 所有透過 `theme()` 引用的 CSS 自動跟著變

2. **Header 漸層改為品牌藍風格**
   - `.ui-page-header` 從紫色漸層改為深藍→品牌藍漸層
   - 符合半導體產業的沈穩科技感

3. **建立完整排版層級**
   - 在 `tailwind.config.js` 定義 `2xs`~`2xl` 完整 fontSize scale
   - 覆蓋 `text-sm` 為 `13px`，合法化現有用法

### Phase 2: 元件統一與現代化（中優先級）

4. **統一按鈕系統**
   - 確保 `ui-btn--primary` 使用新品牌藍
   - 新增 `ui-btn--secondary`、`ui-btn--danger` 變體
   - 清除各 feature CSS 殘留的重複按鈕定義

5. **現代化表格樣式**
   - 移除全邊框改為行分隔線
   - 表頭使用 `brand.50` 淺藍底
   - 統一 hover 行色、加入 sticky header

6. **新增 Skeleton Loading 元件**
   - `shared-ui/components/SkeletonLoader.vue`（`<style scoped>`）
   - 提供 text、card、table 三種 skeleton 變體

### Phase 3: 技術債清理（低優先級）

7. **Token 色彩漸進式語意化**
   - 高頻 `token.hXXXXXX` 重新命名為語意化名稱
   - 已被 brand/accent/surface/text 覆蓋的 token 標記 deprecated 並逐步移除

## Non-goals

- 不重寫現有 Vue 元件的 `<template>` 結構
- 不修改後端 API
- 不變更路由架構
- 不修改 ECharts 圖表配色（屬 CSS 契約 6.1 的例外治理範疇）
- 不引入新的 CSS 框架或 UI 函式庫

## Constraints

- **CSS 契約 2.2**：所有設計規範只改 `tailwind.config.js` 的 `theme.extend`
- **CSS 契約 3.2.2**：全域元件類別在 `styles/tailwind.css` 的 `@layer components` 用 `ui-` 前綴
- **CSS 契約 4.2/4.3**：Feature 樣式保持 `.theme-xxx` 作用域
- **CSS 契約 7.2**：新增 CSS 檔案需同步更新 `contract/css_inventory.md`
- **CSS 契約 2.1**：禁止在 `:root` 手動定義色彩
