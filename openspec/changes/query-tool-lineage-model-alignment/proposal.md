## Why

目前「批次追蹤工具」雖已拆成正向/反向/設備三個頁籤，但追溯模型仍以 `SPLITFROMID + COMBINEDASSYLOTS` 為主，與實際 GA/GC/GD/WAFER LOT 關係不完全一致。已完成的資料探索也顯示：GC→GA 常透過共同 `FIRSTNAME`（Wafer LOT）而非 split 直接可見，GD 重工鏈也主要落在 `DW_MES_CONTAINER`（`ORIGINALCONTAINERID` / `FIRSTNAME` / `SPLITFROMID`），若不補齊模型，前端樹圖會持續出現「可顯示但語意不正確」的問題。

## What Changes

- 釐清並統一「批次追蹤」資料語意，將追溯關係分成可辨識的邊類型，而不只是一般 parent/child：
  - `split_from`（拆批）
  - `merge_source`（併批）
  - `wafer_origin`（`FIRSTNAME` 對應 Wafer LOT）
  - `gd_rework_source`（GD 重工來源，依 `ORIGINALCONTAINERID`/`FIRSTNAME`）
- 明確納入 GC 非必經站規則：
  - GC 與 GA 非 1:1，也不是必經關係（可能僅抽點，也可能完全不經 GC）
  - 追溯主錨點改為 Wafer LOT；GC 視為「可選節點」，不存在時不視為斷鏈
  - 前端需顯示 `WAFER -> GA` 直接鏈路（無 GC 時），讓使用者可視覺辨識「跳過 GC」情境
- 調整查詢入口，對齊你定義的使用情境：
  - 正向頁籤支援：Wafer LOT、GA/GC 工單、GA/GC LOT 作為起點
  - 反向頁籤支援：成品流水號、GD 工單、GD LOT ID 作為起點
- 讓正反向追溯輸出採同一份「語意化關係圖」資料結構，只在起點與展開方向不同，避免結果解讀不一致。
- 補齊 GA 無 GC 時的可視化語意：若無 GC 節點，仍須明確顯示 Wafer LOT 補充鏈路，不可隱性省略。
- 前端樹圖改為「節點類型 + 關係類型」雙重視覺表達（非僅 root/branch/leaf）：
  - 節點至少區分：WAFER、GC、GA、GD、SERIAL
  - 關係邊樣式區分：split、merge、wafer-origin、gd-rework
  - 保留點選節點只過濾下方明細，不回頭過濾樹本身。
- 增加查詢效能與風險控制策略：
  - 先做 seed resolve，再按需分段展開關係，避免一次全量 fan-out
  - 對 GD 關係查詢加入快取策略（可配置 TTL，預設使用既有 Redis 快取層）
  - 補上追溯鏈路命中統計與慢查監控欄位，便於驗證模型是否正確覆蓋。

### GD 追溯策略（補充）

- 反向起點為「成品流水號」時：
  1. 先用 `DW_MES_PJ_COMBINEDASSYLOTS.FINISHEDNAME` 解析到 GD lot（例如 `GDxxxx-A01`）
  2. 取得 GD lot 對應 `MFGORDERNAME=GD...`
  3. 以 `DW_MES_CONTAINER` 展開同 GD 工單全部 lot
  4. 每一個 GD lot 以 `ORIGINALCONTAINERID`（主）與 `FIRSTNAME`（輔）回溯來源 lot
  5. 來源 lot 再透過 `FIRSTNAME` 連到 Wafer LOT 錨點
- 反向起點為「GD 工單」時：
  - 直接從 `DW_MES_CONTAINER` 取 GD lot 群，後續同上回溯來源 lot 與 Wafer LOT
- 反向起點為「GD LOT ID」時：
  - 以 `DW_MES_CONTAINER.CONTAINERNAME` 精準命中 GD lot（需符合 GD 規則），再沿用同一條回溯鏈
  - 適用「已知單顆/單批 GD lot，未知整張 GD 工單」的快速反查情境
- 正向時，若查到來源 lot 存在 GD 再製分支，需額外顯示 `gd_rework_source` 邊，形成「原 lot -> GD lot -> 新成品」分支。
- 限制聲明：
  - 目前資料可穩定追出「來源 lot 與 GD lot 關係」；
  - 舊成品流水號與新成品流水號不保證存在 1:1 可直接映射，提案先保證 lot/workorder 層級完整可追。

### 現況/需求/整合比較

| 面向 | 目前實作 | 新需求 | 本提案整合方向 |
|---|---|---|---|
| 正向入口 | `lot_id` / `work_order` | Wafer LOT + GA/GC 工單 + GA/GC LOT | 擴充 resolve type 與正向查詢入口 |
| 反向入口 | 僅成品流水號 | 成品流水號 + GD 工單 + GD LOT ID | 反向 QueryBar 增加 GD 工單/GD LOT 模式 |
| GD 關聯 | 主要倚賴 COMBINED 映射 | 需追出重工來源與重測後新結果 | 改以 `DW_MES_CONTAINER` 欄位為 GD 主鏈，COMBINED 僅作輔助 |
| GC 缺失情境 | 樹上不易看出補線來源 | GA 無 GC 時仍要看見 WAFER LOT | 新增 `wafer_origin` 邊與視覺標示 |
| 前端語意 | 泛化 root/branch/leaf | 要看得出流程語意 | 改成節點/邊語意化圖例與樣式 |

## Capabilities

### New Capabilities

- _(none)_

### Modified Capabilities

- `query-tool-lot-trace`: 查詢入口、正反向頁籤語意、樹圖互動與可視化規則更新。
- `lineage-engine-core`: 從單一 split/merge 模型擴充為可輸出 wafer/GD 關係的語意化關係圖。
- `trace-staged-api`: seed resolve 與 lineage response contract 擴充（新 resolve type、typed edges、節點分類欄位）。
- `progressive-trace-ux`: 正反向追溯在同一 UX 規則下顯示，並保持分段載入與快取策略一致。

## Impact

- **前端**：`frontend/src/query-tool/App.vue`、`frontend/src/query-tool/components/QueryBar.vue`、`frontend/src/query-tool/components/LineageTreeChart.vue`、相關 composables（`useLotResolve.js`、`useLotLineage.js`、`useReverseLineage.js`）
- **後端 API**：`src/mes_dashboard/routes/query_tool_routes.py`、`src/mes_dashboard/routes/trace_routes.py`
- **服務層**：`src/mes_dashboard/services/query_tool_service.py`、`src/mes_dashboard/services/lineage_engine.py`
- **SQL/資料來源**：`src/mes_dashboard/sql/lineage/*.sql`、`src/mes_dashboard/sql/query_tool/*resolve*.sql`（含 `DW_MES_CONTAINER` 欄位關聯補強）
- **快取/監控**：沿用既有 Redis/L2 cache 與 slow-query logger，新增追溯關係命中統計欄位
