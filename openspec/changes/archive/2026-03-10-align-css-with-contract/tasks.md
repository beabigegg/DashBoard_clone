## 1. Baseline & Governance Setup

- [x] 1.1 盤點 `frontend/src/**/*.css` 與 `frontend/src/**/*.vue`，輸出基線統計（`:root`、`var(--*)`、`body/html/*`、靜態 `style="..."`）
- [x] 1.2 建立 route 對應的 theme root class 對照表（含 shell 載入路徑與 root 容器）
- [x] 1.3 建立 migration exception registry（欄位至少含 route、owner、deadline、reason）

## 2. Theme Root Isolation Rollout

- [x] 2.1 在各 route `App.vue` 根容器加上對應 `theme-*` class
- [x] 2.2 針對 route-local CSS 將一般 selector 規則加上對應 theme root scope
- [x] 2.3 確認 `@keyframes`/at-rule 未被錯誤前綴化，必要時改為白名單處理

## 3. Global Base/Reset Consolidation

- [x] 3.1 從 route-local CSS 移除 `body/html/*` 及 reset 規則
- [x] 3.2 將必要全域 base/reset 統一到 `frontend/src/styles/tailwind.css` 的 `@layer base`
- [x] 3.3 驗證除 `tailwind.css` 外，不再有 route-local 全域 selector 規則

## 4. Token Source Unification

- [x] 4.1 將 token 類 CSS 變數映射到 `frontend/tailwind.config.js` `theme.extend`
- [x] 4.2 將 token 類 `var(--*)` 用法改為 `theme('...')`，優先處理 shared 與高流量頁
- [x] 4.3 移除 route-local `:root` token 宣告；僅保留必要且有作用域的區域運算變數

## 5. Shared Semantic Normalization (`ui-*`)

- [x] 5.1 掃描重複出現 >=3 次的共享視覺語意（例如 `.btn`, `.header`, `.panel`, `.summary-card`）
- [x] 5.2 在 `frontend/src/styles/tailwind.css` `@layer components` 新增對應 `ui-*` 類別
- [x] 5.3 逐步替換 route 內重複樣式使用點，減少 duplicated declarations

## 6. Static Inline Style Remediation

- [x] 6.1 清理 `.vue` 模板中的靜態 `style="..."`，改為 class 或 scoped style
- [x] 6.2 保留必要 `:style` 動態綁定，並補註解說明其動態性（僅在非顯而易見時）
- [x] 6.3 針對圖表/高互動元件（例如 lineage/tree）完成靜態樣式外移

## 7. Shell Navigation Regression Checks

- [x] 7.1 驗證 shell route 切換後不存在跨頁樣式污染（含 `resource/wip/query/tables/msd`）
- [x] 7.2 驗證 standalone entry 與 shell entry 視覺關鍵區塊一致（header/card/filter/action）
- [x] 7.3 驗證 deferred/legacy 路由在過渡期間有明確 exception 記錄

## 8. CI Guardrails & Documentation Update

- [x] 8.1 新增自動檢查：禁止 route-local `:root` token、`body/html/*` 與靜態 inline style
- [x] 8.2 將檢查腳本加入前端 CI 流程，設定失敗門檻
- [x] 8.3 更新 `contract/css_refactoring_plan.md` 為實際執行版（含階段門檻與驗收）
