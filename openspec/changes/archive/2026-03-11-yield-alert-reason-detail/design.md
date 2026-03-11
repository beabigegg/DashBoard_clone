## Context

Yield Alert Center 目前的告警清單提供「查看追溯」按鈕，但其行為是呼叫 `/api/yield-alert/drilldown-context` 組裝 URL 後跳轉至 reject-history 頁面。由於 linkage analyze（`POST /api/yield-alert/analyze`）從未被前端觸發，`linkage_df` 永遠是空的 DataFrame，所有告警列的 `match_status` 均為 `none`，使用者無法得到有效的追溯資訊。

`DWH.DW_MES_LOTREJECTHISTORY` 有 `PJ_WORKORDER` 欄位可直接對應 ERP 的 `WIP_ENTITY_NAME`（`_compute_reject_linkage` 已驗證此映射可行）。以 workorder + 日期為鍵的查詢結果集極小（單一工單單一天），適合 on-demand 直查，不需要 dataset cache。

## Goals / Non-Goals

**Goals:**
- 點擊「查看原因」後 inline 顯示 MES `DW_MES_LOTREJECTHISTORY` 的 LOT 級別報廢明細（不跳轉頁面）
- 移除無實際功能的「映射狀態」欄位（match_status）
- 清理前端已死的 drilldown / linkageWarning 邏輯
- 新增最小化後端 endpoint，直查 Oracle，不依賴 dataset cache

**Non-Goals:**
- 不刪除既有 `/api/yield-alert/drilldown-context`、`/api/yield-alert/analyze` endpoints（留給未來或外部消費）
- 不修改 reject-history 頁面本身
- 不重構 dataset cache / linkage 計算邏輯

## Decisions

### 1. On-demand 直查 Oracle，不走 dataset cache

**決策**：`reason-detail` endpoint 以 `workorder + date_bucket` 直查 `DW_MES_LOTREJECTHISTORY`，不嘗試從 `detail_df` 或 `linkage_df` 拼湊。

**理由**：
- 查詢極窄（單一 workorder + 日期），Oracle 走 index scan，預期 < 1s
- dataset cache 存的是 ERP 資料（`ERP_WIP_MOVETXN_DETAIL`），MES 資料不在其中
- 無需增加 cache 複雜度；使用者點擊頻率低，不需要特殊快取策略

**替代方案考慮**：先把 MES 資料也批量拉進 dataset cache → 增加初始查詢時間與記憶體佔用，不值得。

### 2. Inline 展開行（expandable row），不用 modal

**決策**：點擊「查看原因」在該告警列下方 inline 展開子表格，再次點擊收合。同一時間只允許一列展開。

**理由**：
- 告警表格本身已有多欄，modal 會蓋住 context；展開列讓使用者可以同時看到告警數值與原因明細
- 實作簡單，不需要 portal/teleport，Vue 一個 `v-if` 控制 `<tr class="reason-detail-row">` 即可
- 同一時間一列展開夠用（點擊另一列自動切換），降低狀態管理複雜度

**替代方案考慮**：側邊抽屜 → 需要 drawer 整合，過度工程；modal → 蓋住 context。

### 3. SQL 設計：`reason_detail.sql` 直接查 `DW_MES_LOTREJECTHISTORY`

**決策**：不沿用 `reject_history/primary.sql`（需 `BASE_WITH_CTE` macro）。新寫一支輕量 SQL，只撈所需欄位。

**欄位**：`TRUNC(TXNDATE)`, `CONTAINERNAME`, `WORKCENTERNAME`, `LOSSREASONNAME`, `LOSSREASON_CODE`, `REJECTCOMMENT`, `REJECTQTY`, `REJECT_TOTAL_QTY`（REJECTQTY + STANDBYQTY + QTYTOPROCESS + INPROCESSQTY + PROCESSEDQTY）

**安全邊界**：`FETCH FIRST 200 ROWS ONLY`，避免異常工單拉出大量資料。

### 4. 前端狀態管理

**決策**：以 `expandedRowKey = ref('')` 記錄目前展開的列（格式 `date_bucket|workorder`）；`reasonDetailRows = ref([])`、`reasonDetailLoading = ref(false)` 記錄明細資料與載入狀態。

**切換邏輯**：
```
click(row) →
  if expandedRowKey == rowKey: 收合（清空 expandedRowKey）
  else: 設定 expandedRowKey，fetch reason-detail API，存入 reasonDetailRows
```

### 5. 保留 `navigateToRuntimeRoute` import 與 drilldown 相關後端

**決策**：`navigateToRuntimeRoute` 從 import 移除（確認只有 `openDrilldown` 在用）；後端 drilldown/analyze endpoints 繼續存在但前端不呼叫。

## Risks / Trade-offs

- **[風險] Oracle 直查延遲**：極端情況下 MES 表 index miss → Mitigation: SQL 加 `FETCH FIRST 200 ROWS ONLY`；前端顯示 loading 狀態；API timeout 設 30s（低於 `API_TIMEOUT = 90s`）
- **[風險] workorder 大小寫不一致**：ERP 存的是大寫，MES `PJ_WORKORDER` 可能混合 → Mitigation: SQL 兩側加 `UPPER(TRIM(...))`，與 `_compute_reject_linkage` 保持一致
- **[Trade-off] match_status 移除**：若未來需要 linkage 功能，需重新加回欄位 → 可接受，當前 linkage 邏輯無效，移除比留著更清晰
