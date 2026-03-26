## Why

目前已 release 的報表頁面中，篩選行為有明顯差異：有些頁面具備互相影響的動態選項，有些僅做查詢後過濾或單向收斂。這會造成使用者在跨報表分析時的操作落差與誤解，並增加「無結果查詢」與重複嘗試成本，因此需要補強並統一篩選策略。

## What Changes

- 建立跨報表的篩選策略分級與適用準則，明確區分：
  - 探索型報表：需支援多欄位互相影響篩選
  - 監控/鑽取型報表：保留輕量篩選與 drilldown 為主
- 針對探索型頁面補強互相篩選：
  - `reject-history`：選項 API 支援依目前草稿條件回傳受限選項，降低無效組合
  - `resource-history`：將現有 machine 單向收斂擴展為上游條件一致收斂並自動剔除失效選取值
- 統一前端互篩行為細節：debounce、請求去重/過期保護、無效選取值 prune、apply/clear 一致語意
- 補上互篩策略的驗證與回歸測試（前端互動與後端 option API 行為）

## Capabilities

### New Capabilities
- `report-filter-strategy`: 定義報表篩選策略分級、互篩行為基線與一致性驗證規範

### Modified Capabilities
- `reject-history-page`: 篩選選項改為可依草稿條件動態收斂，並維持既有政策旗標語意
- `resource-history-page`: 篩選聯動由部分收斂提升為完整上游影響與失效值自動清理

## Impact

- **Frontend**
  - `frontend/src/reject-history/App.vue`
  - `frontend/src/reject-history/components/FilterPanel.vue`
  - `frontend/src/resource-history/App.vue`
  - `frontend/src/resource-history/components/FilterBar.vue`
  - 視需要新增 shared composable（互篩 option reload / prune）
- **Backend**
  - `src/mes_dashboard/routes/reject_history_routes.py`
  - `src/mes_dashboard/services/reject_history_service.py`
  - 視需要新增/擴充 `resource-history` option API 參數解析與服務層
- **Tests**
  - `tests/` 中 reject-history / resource-history 相關 route & service 測試
  - `frontend/tests/` 補互篩行為測試
- **Non-goals**
  - 本次不要求所有 released 頁面全面改為完整互篩；僅先補強探索型頁面，監控/鑽取型頁面維持現有互動模型
