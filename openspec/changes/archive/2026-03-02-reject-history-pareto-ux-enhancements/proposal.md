## Why

目前 Reject History 柏拉圖在 `TYPE`、`WORKFLOW`、`機台` 維度上，僅靠累計 80% 顯示時仍可能出現過多項目，影響閱讀與分析效率；同時圖表點選與明細匯出尚未完整對齊，造成追查流程不連續。需要補強互動式篩選與匯出一致性，讓使用者可直接從柏拉圖一路鑽取到可交付的明細結果。

## What Changes

- 在柏拉圖 `TYPE`、`WORKFLOW`、`機台` 三個維度新增顯示範圍選項：`全部顯示`、`只顯示 TOP 20`。
- 將「Pareto 僅顯示累計前 80%」移入「補充篩選」區域，並維持預設啟用。
- 柏拉圖支援點選項目多選（bar/table），並同步套用到下方明系列表。
- 明系列表新增 `匯出 CSV`，匯出內容必須與當前明細可見結果完全一致（套用主篩選、補充篩選、Pareto 點選篩選、排序/分頁語意）。
- 匯出 CSV 強化字元編碼與欄位轉義處理，避免中文亂碼與欄位錯位。

## Capabilities

### New Capabilities
- `reject-history-detail-export-parity`: 明細匯出與畫面篩選完全一致的 CSV 匯出能力

### Modified Capabilities
- `reject-history-page`: 擴充柏拉圖顯示範圍控制、補充篩選位置調整、Pareto 多選聯動明細
- `reject-history-api`: 匯出端點需保證套用所有有效篩選（含 Pareto 衍生篩選），並提供穩定 CSV 編碼輸出

## Impact

- Frontend: `src/pages/reject-history`（FilterPanel、ParetoSection、DetailTable、頁面狀態管理與查詢參數組裝）
- Backend/API: reject-history list/export 查詢參數解析與 CSV 產生流程
- Tests: 補齊 page 互動測試（多選/聯動/顯示範圍）與 API 匯出一致性測試（filter parity、encoding）
