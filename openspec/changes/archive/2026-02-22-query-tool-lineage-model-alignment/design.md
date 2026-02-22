## Context

「批次追蹤工具」目前已拆成三個頁籤（正向/反向/設備），但 lineage 核心仍以 `SPLITFROMID` 與 `DW_MES_PJ_COMBINEDASSYLOTS` 為主，資料語意不足以完整表達現場流程：

- GC 並非 GA 的必經節點，且非 1:1；部分批次只有 GC 抽點，部分完全不經 GC。
- Wafer LOT（`DW_MES_CONTAINER.FIRSTNAME`）是 GA/GC 共同上游錨點，應獨立建模。
- GD 重工追溯主鏈在 `DW_MES_CONTAINER`：`ORIGINALCONTAINERID` + `FIRSTNAME` + `SPLITFROMID`，僅靠 COMBINED 表無法表達完整重工來源。

已驗證資料特徵（實查）：

- GD lot 可由 `DW_MES_PJ_COMBINEDASSYLOTS.FINISHEDNAME` 反解至 `GDxxxx-Axx`。
- 該 GD lot 在 `DW_MES_CONTAINER` 中可取得 `MFGORDERNAME=GD...` 與 `ORIGINALCONTAINERID`、`FIRSTNAME`。
- `ORIGINALCONTAINERID` 對應來源 lot 可回接 Wafer LOT（`FIRSTNAME`）。

約束條件：

- 需沿用現有 `/api/query-tool/*`、`/api/trace/*` 路由，不做破壞式移除。
- 需保留 staged trace 的快取與 rate limit 行為。
- 需維持查詢效能，避免以 Wafer LOT 為起點時產生不可控 fan-out。

## Goals / Non-Goals

**Goals:**

- 以「語意化節點/邊」重建 query-tool 的追溯模型，明確區分 split、merge、wafer-origin、gd-rework。
- 明確支持兩種入口集合：
  - 正向：Wafer LOT / GA-GC 工單 / GA-GC LOT
  - 反向：成品流水號 / GD 工單 / GD LOT ID
- 前端樹圖可視化要能辨識「GA 無 GC」與「GD 重工分支」。
- 將 GD 追溯落在 lot/workorder 層級保證可追，並保留 serial 層級可得資訊。

**Non-Goals:**

- 不承諾舊成品流水號與新成品流水號 1:1 映射。
- 不調整設備頁籤功能。
- 不在本變更導入新資料來源（僅使用既有 DWH 表）。

## Decisions

### D1. 建立 Typed Lineage Graph（節點/邊雙語意）

後端 lineage 輸出新增語意欄位，與現有欄位並存（過渡期兼容）：

- `nodes`: 依 `container_id` 聚合節點屬性（`node_type`, `container_name`, `mfgorder_name`, `wafer_lot`）
- `edges`: 邊列表（`from_cid`, `to_cid`, `edge_type`）
- `edge_type` 固定枚舉：
  - `split_from`
  - `merge_source`
  - `wafer_origin`
  - `gd_rework_source`

`node_type` 判定優先順序：

1. `MFGORDERNAME LIKE 'GD%'` 或 `CONTAINERNAME LIKE 'GD%'` → `GD`
2. `MFGORDERNAME LIKE 'GC%'` 或 `CONTAINERNAME LIKE 'GC%'` → `GC`
3. `MFGORDERNAME LIKE 'GA%'` 或 `CONTAINERNAME LIKE 'GA%'` → `GA`
4. `OBJECTTYPE='LOT'` 且為 Wafer 錨點節點 → `WAFER`
5. COMBINED `FINISHEDNAME` 的虛擬節點 → `SERIAL`

保留現有 `children_map` / `parent_map` 等欄位，前端逐步切換到 typed graph。

### D2. 以 Profile 區分 seed-resolve 輸入語意

`/api/trace/seed-resolve` 改為 profile-aware 的 resolve type 規則：

- `query_tool`（正向）允許：`wafer_lot`, `lot_id`, `work_order`
- `query_tool_reverse`（反向）允許：`serial_number`, `gd_work_order`, `gd_lot_id`

其中：

- `wafer_lot`: 以 `DW_MES_CONTAINER.FIRSTNAME` 解析種子 lot 集合
- `gd_work_order`: 僅允許 `GD%` 前綴，對 `DW_MES_CONTAINER.MFGORDERNAME` 解析
- `gd_lot_id`: 以 `DW_MES_CONTAINER.CONTAINERNAME` 解析，且需同時符合 GD 規則（`CONTAINERNAME LIKE 'GD%'` 或 `MFGORDERNAME LIKE 'GD%'`）
- `work_order`（正向）限定 GA/GC（非 GD）

此設計避免正反向模式語意混用，且可在 API 層即早回饋錯誤。

### D3. GD 反向追溯採「Container 主鏈 + Combined 輔鏈」

GD 反向演算法（三種起點共用）：

1. 種子為 serial 時，先由 `DW_MES_PJ_COMBINEDASSYLOTS.FINISHEDNAME` 找到 lot（常為 `GDxxxx-Axx`）；種子為 `gd_lot_id` 時直接命中該 lot；種子為 `gd_work_order` 時直接展開該工單 lot 群。
2. 對 serial 或 `gd_lot_id` 起點，讀取 lot 的 `MFGORDERNAME` 以展開同 GD 工單 lot 群。
3. 對每個 GD lot 取來源：
   - 主來源：`ORIGINALCONTAINERID`
   - 回退來源：`SPLITFROMID`（當 ORIGINAL 為空或無效）
4. 來源 lot 再透過 `FIRSTNAME` 接回 Wafer LOT 錨點。
5. COMBINED 僅負責「lot -> 成品流水號」映射，不作為 GD 來源主依據。

這可涵蓋「成品流水號 -> GD -> 來源 lot -> wafer」與「GD 工單 -> lot 群 -> 來源 lot」兩條路徑。

### D4. 前端改為語意化樹圖且保持明細過濾邊界

`LineageTreeChart` 調整為語意視覺：

- 節點顏色/形狀區分 `WAFER/GC/GA/GD/SERIAL`
- 邊樣式區分 `split/merge/wafer-origin/gd-rework`
- 無 GC 時強制顯示 `WAFER -> GA` 直接鏈路，不用「缺失」呈現

互動邊界：

- 點擊節點僅更新 detail panel 的 container scope
- 不重新過濾/改寫樹本身（避免「點樹即變樹」）

### D5. 效能策略：分段查詢 + 批次 + 快取

- lineage 查詢維持分段與批次（IN clause batching）策略。
- Wafer LOT 展開加入結果上限與分頁/裁切策略（避免單一查詢過大）。
- GD 關係查詢以 Redis/L2 做短期快取（可由 env 配置 TTL）。
- 監控新增 typed-edge 命中統計，觀察 `wafer_origin` 與 `gd_rework_source` 的覆蓋率。

### D6. 向後相容與漸進切換

- API contract 採「新增欄位」方式，不先移除舊欄位。
- 前端先讀新欄位，保留舊欄位 fallback 一個版本週期。
- 若生產異常，可切回舊渲染路徑（feature flag 或 runtime config）。

## Risks / Trade-offs

- [Risk] Wafer LOT fan-out 過大導致查詢壓力  
  Mitigation: 設定種子展開上限、分段查詢、UI 提示「僅顯示前 N 筆」。

- [Risk] `FIRSTNAME` 同名造成跨流程誤連  
  Mitigation: 邊生成時加上 `OBJECTTYPE='LOT'` 與工單/時間窗交叉約束；疑似多義連線以低信任度標記。

- [Risk] GD 舊/新 serial 無法 1:1 對映引發期待落差  
  Mitigation: 在規格與 UI 說明明確宣告 serial 層級的限制，保證 lot/workorder 層級完整可追。

- [Risk] 新舊欄位並存造成前後端邏輯複雜  
  Mitigation: 設定移除時程，待新前端穩定後再移除舊欄位讀取。

## Migration Plan

1. 後端先落地 typed lineage（不改前端），確認 API 回傳兼容。  
2. 前端切換至 typed graph 視覺與新 resolve 類型。  
3. 啟用 GD reverse 路徑與 GC-optional 顯示規則。  
4. 以實例資料驗證三種主流程：
   - WAFER -> GA（無 GC）
   - WAFER -> GC -> GA
   - SERIAL -> GD -> SOURCE LOT -> WAFER
5. 穩定後移除舊渲染相依欄位（若決議移除）。

Rollback：

- 關閉 typed graph 功能開關，前端退回舊欄位渲染。
- 保留新 SQL/欄位但不被前端使用，避免熱修回滾需 DB 變更。

## Open Questions

- Wafer LOT 輸入值格式是否需要強制前綴或正則，以降低同名誤連？
- 正向 `work_order` 是否嚴格限制 GA/GC，或允許 GD 但提示「請用反向頁籤」？
- `WAFER -> GA` 直接鏈路在視覺上要以虛線還是實線呈現（避免與 split 混淆）？
