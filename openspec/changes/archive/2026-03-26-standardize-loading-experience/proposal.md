## Why

目前前端等待體驗混用了多套 spinner、不同動畫速度、純文字等待與局部自定義樣式，導致使用者在不同頁面對「查詢中/載入中」的感知不一致，也提高了維護與回歸驗證成本。隨著前端頁面已完成 Vite/Vue 模組化，現在是建立統一 Loading 分層規範並完成收斂的最佳時機。

## What Changes

- 建立三層 Loading 規範並明確分責：
  - 全域等待（Page-level blocking）
  - 小組件等待（Inline/component-level）
  - 區塊等待（Block/section-level）
- 全域等待強制使用 `LoadingOverlay + LoadingSpinner`，禁止頁面自定義全屏等待動畫。
- 小組件等待統一為共享 spinner 與一致的按鈕 busy 狀態（含查詢/匯出/上傳）。
- 區塊等待統一為可重用的區塊 loading 呈現模式，並與 `DataTable` loading/empty 行為對齊。
- 針對既有重複與分歧實作建立遷移路徑（先高頻頁面，再其餘頁面）與驗收準則。

## Capabilities

### New Capabilities
- `loading-tier-policy`: 定義全域、小組件、區塊三層 loading 適用場景、必用元件與禁用模式。

### Modified Capabilities
- `loading-system`: 強化全域等待必用元件與統一動畫規範，補上淘汰自定義全域 spinner 的要求。
- `unified-button-system`: 補齊按鈕 busy/loading 狀態一致化要求（含 inline spinner 呈現與文案切換準則）。
- `data-table-component`: 明確區塊級 loading 呈現規範，避免同時出現不一致的表格 placeholder/loading 實作。
- `unified-multiselect`: 明確 MultiSelect loading 指示器與共享動畫 token 對齊規範。

## Impact

- Affected code:
  - `frontend/src/shared-ui/components/*`（LoadingOverlay/LoadingSpinner/DataTable/MultiSelect 與新增或擴充共用元件）
  - 多個 feature 頁面的 `App.vue` 與 `style.css`（替換自定義 spinner、純文字 loading、區塊 placeholder）
- APIs: 無後端 API 變更。
- Dependencies: 無新增第三方依賴。
- Governance/Test:
  - 更新前端 loading 一致化的驗收清單與測試覆蓋（元件測試與主要頁面行為檢查）。
