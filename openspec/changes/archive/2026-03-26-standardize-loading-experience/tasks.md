## 1. 全域等待必用元件與動畫

- [x] 1.1 盤點並移除頁面級自定義 full-page loading 實作，改用 `LoadingOverlay tier="page"` + `LoadingSpinner`
- [x] 1.2 在 `shared-ui/components/LoadingSpinner.vue` 明確化共享動畫 baseline 與 reduced-motion 行為
- [x] 1.3 遷移高優先頁面的全域等待（anomaly-overview、qc-gate、legacy job/excel 入口）到 shared overlay 模式
- [x] 1.4 清理全域等待遺留 keyframes/class（限 page-level），避免與 shared loading 並存

## 2. 小組件等待一致化

- [x] 2.1 建立或固化 `ui-btn` loading pattern（`is-loading` + `LoadingSpinner size="sm"` + disabled + loading copy）
- [x] 2.2 將查詢/匯出/上傳等按鈕 busy 狀態遷移到共享 pattern，替換頁面內自定義 btn-spinner
- [x] 2.3 對齊 `MultiSelect` loading 指示器動畫節奏到共享 motion baseline
- [x] 2.4 修復遺漏或不完整的小 spinner 實作（例如只有 class 無對應樣式）並改為 shared spinner

## 3. 區塊等待一致化

- [x] 3.1 對使用 `DataTable` 的區塊統一採用 `:loading` 規範，移除同狀態下重複 placeholder/loading UI
- [x] 3.2 為非 `DataTable` 區塊建立共用 `BlockLoadingState`（或等價封裝）並替換 ad hoc 文字 loading 區塊
- [x] 3.3 將主要頁面的區塊 loading 遷移到共用模式（query-tool、tables、admin-* 高使用區）
- [x] 3.4 對齊區塊 loading 與 `EmptyState(type="loading")` 使用邏輯，避免同區塊多種等待表現

## 4. 治理與驗收

- [x] 4.1 新增/更新 loading 一致化檢查規則（禁止 page-level 自定義 spinner；允許 tier 化的 component/block 模式）
- [x] 4.2 補充元件與頁面測試：全域等待、按鈕 busy、DataTable loading、MultiSelect loading、reduced-motion
- [x] 4.3 執行前端 build 與測試，確認遷移後無樣式與互動回歸
- [x] 4.4 更新文件（開發規範/遷移說明）並附上三層 loading 使用準則
