## Context

WIP 即時概況和 Hold 即時概況共用部分 Hold 資料呈現邏輯，但目前職責劃分不清：Hold 柏拉圖放在 WIP 頁面、Hold 頁面篩選能力薄弱、Lot 明細欄位不一致。兩頁的後端 service 層（`wip_service.py`）已共用 `_select_with_snapshot_indexes()` 作為核心查詢引擎，支援 workorder/lotid/pj_type/firstname/waferdesc 篩選，但 Hold Overview 的 route 層和 service function 簽名尚未穿透這些參數。

**現有架構：**
- `ParetoSection.vue` 位於 `wip-overview/components/`，僅 WIP 使用
- Hold Overview 的 `FilterBar` 僅有 holdType + reason 兩個篩選欄位
- Hold Overview 和 Hold Detail 各有獨立的 `LotTable.vue`，欄位不同（前者有 Hold Reason 無 Spec，後者相反）
- Hold Detail 返回按鈕指向 WIP Overview

## Goals / Non-Goals

**Goals:**
- Hold 相關視覺化（柏拉圖）集中到 Hold 即時概況
- WIP 即時概況的 Hold 卡片改為跳轉入口（而非本地篩選）
- Hold 即時概況具備與 WIP 相同的 6 欄位篩選能力
- 統一 Lot 明細表格為 13 欄（含 Hold Reason + Spec）
- 修正 Hold 即時概況版面窄的問題
- Hold Detail 導航回到 Hold Overview（而非 WIP Overview）

**Non-Goals:**
- 不變更 Hold 柏拉圖的資料來源 API（繼續使用 `/api/wip/overview/hold`）
- 不變更 Hold Detail 的內部功能（AgeDistribution、DistributionTable 等）
- 不重構後端 `wip_service.py` 的核心查詢邏輯
- 不新增 API endpoint（只擴充現有 endpoint 的參數）

## Decisions

### D1. 柏拉圖資料來源：沿用 `/api/wip/overview/hold`

Hold 即時概況的柏拉圖直接呼叫現有 `/api/wip/overview/hold` API，而非新增 Hold Overview 專用 endpoint。

**理由：** 該 API 回傳 `{items: [{reason, lots, qty, holdType}]}`，正好是 `ParetoSection` + `splitHoldByType()` 所需格式。已有的 treemap API 回傳格式不同（workcenter×reason 分組），不適合柏拉圖。

### D2. ParetoSection 搬遷至 `wip-shared/components/`

將 `ParetoSection.vue` 從 `wip-overview/components/` 移至 `wip-shared/components/`，柏拉圖 CSS 抽取為 `wip-shared/pareto-styles.css`。

**理由：** `wip-shared/` 是既有的共用目錄（已有 `styles.css`），符合專案的組件共用慣例。

### D3. 統一 LotTable 為 `wip-shared/components/HoldLotTable.vue`

以 Hold Overview 的 `LotTable.vue` 為基礎，新增 Spec 欄位，形成 13 欄統一表格。兩頁均改用此共用組件。

**理由：** 後端 `get_hold_detail_lots` 已同時回傳 `holdReason` 和 `spec`（wip_service.py:3079-3080），純前端調整。共用組件避免欄位不同步。

### D4. FilterPanel 直接 import WIP Overview 的組件

Hold Overview 的 FilterPanel 直接 `import FilterPanel from '../wip-overview/components/FilterPanel.vue'`，不複製組件。

**理由：** FilterPanel 的 props interface（filters/options/loading + apply/clear/draft-change events）是穩定的，且內部已正確處理 MultiSelect 相對路徑。避免組件重複。

### D5. 柏拉圖根據 holdType 條件顯示

- holdType = 'all'（預設）→ 顯示品質異常 + 非品質異常兩張柏拉圖
- holdType = 'quality' → 僅顯示品質異常柏拉圖
- holdType = 'non-quality' → 僅顯示非品質異常柏拉圖

**理由：** 使用者選擇特定 holdType 後，無關的柏拉圖顯示空資料會造成困惑。

### D6. 後端參數穿透策略

`get_hold_detail_summary` 和 `get_hold_detail_lots` 加入 5 個 Optional[str] 參數，傳遞至 `_select_with_snapshot_indexes()`（cache path）和 Oracle fallback。`get_wip_matrix` 已原生支援，只需在 route 層解析參數。

**理由：** 最小變更量，`_select_with_snapshot_indexes` 已支援全部篩選欄位。

## Risks / Trade-offs

- **[ParetoSection 搬遷路徑斷裂]** → 搬遷後需確認 WIP Overview 不再 import 舊路徑。透過 `npm run build` 驗證。
- **[FilterPanel 跨目錄 import]** → 若 FilterPanel 內部路徑變更會影響 Hold Overview。風險低，該組件穩定。未來可考慮提升至 shared。
- **[Hold Overview API 回應時間增加]** → 新增 FilterPanel 觸發 filter-options API。此 API 已有 debounce（120ms）和 cache，影響可忽略。
- **[WIP Hold 卡片不再 toggle matrix]** → 使用者行為改變。但 Hold 卡片的 toggle 功能使用率低，跳轉到專頁更直觀。RUN/QUEUE 卡片保持原行為。
