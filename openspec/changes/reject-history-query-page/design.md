## Context

目前 `query-tool` 僅提供單點查詢 reject 資訊，沒有針對歷史趨勢、原因分布與績效指標的完整頁面。`DW_MES_LOTREJECTHISTORY` 存在同一 `HISTORYMAINLINEID` 對應多筆原因紀錄的特性，直接彙總 `MOVEINQTY` 會造成分母膨脹，讓報廢率失真。另一方面，現有語意中「reject 五欄合計」與 `DEFECTQTY` 曾被混用，導致跨頁面解讀不一致。

此變更需要跨越前端（新報表頁）、後端（新 API + service + SQL）、與治理層（route contract、drawer/page registry、coverage test），屬於跨模組整合型設計。

## Goals / Non-Goals

**Goals:**
- 建立 `/reject-history` 專用報表頁，提供篩選、KPI、趨勢、Pareto、明細與匯出。
- 固化兩條指標語義並列：
  - 扣帳報廢 `REJECT_TOTAL_QTY`
  - 不扣帳報廢 `DEFECT_QTY`
- 以事件層級去重 `MOVEIN_QTY`，避免因 `HISTORYMAINLINEID` 多筆造成比率失真。
- 完整納入現有 pure Vite + portal-shell + route contract 治理流程。
- 在視覺上清楚區分 reject 與 defect，避免操作端誤判。

**Non-Goals:**
- 不改寫既有 `query-tool` 與其 API 欄位契約。
- 不新增第三方套件（沿用 Vue 3、ECharts、Flask、SQLLoader）。
- 不在此變更內建立新的資料倉儲實體表（先以查詢層與 service 聚合實作）。
- 不重構非 reject-history 相關頁面的 UI 風格。

## Decisions

### D1: 以單一「日粒度基底查詢」作為 API 共同資料來源

**Decision:** 以 `src/mes_dashboard/sql/reject_history/performance_daily.sql` 作為基底查詢，summary/trend/pareto/list/export 都由 service 在同一語義上二次聚合。

**Why:**
- 可避免各 endpoint 重複實作計算邏輯造成語意漂移。
- 已在 SQL 中明確定義五欄合計與 `DEFECTQTY` 分離，符合業務規則。
- 可先解決語義一致性，再視流量評估是否做 materialization。

**Alternatives considered:**
- 各 API 各自寫 SQL：開發快但長期高風險，易出現欄位定義不一致。
- 先建資料表再查詢：效能可控但前置成本高，超出本次提案節奏。

### D2: `MOVEIN_QTY` 以事件去重策略統一計算

**Decision:** 以 `HISTORYMAINLINEID` 為首選去重鍵；若缺值，退回 `CONTAINERID + TXNDATE(second) + SPECID` 組合鍵；只對事件首筆計入 `MOVEIN_QTY`。

**Why:**
- 原始資料存在一對多原因拆分，若不去重分母會被重複計算。
- 去重規則集中在基底 SQL，前後端不用再各自補丁。

**Alternatives considered:**
- 以 `CONTAINERID` 去重：會誤合併同 lot 不同事件。
- 不去重：報表比率不可用。

### D3: API 採「頁面導向」端點設計

**Decision:** 提供 `summary`、`trend`、`reason-pareto`、`list`、`export` 五個端點，參數模型一致（日期 + 維度過濾），由 route 層統一做驗證與邊界控制。

**Why:**
- 前端可平行載入、獨立重刷局部區塊。
- 可針對高成本端點（list/export）單獨做 rate limit。
- 與 `hold-history`/`resource-history` 現有模式一致。

### D4: 前端視覺採「雙軸語義敘事」布局

**Decision:** 在單頁內明確分離「扣帳報廢」與「不扣帳報廢」兩條視覺敘事線，避免混讀。

**Visual structure:**
- Header：漸層標題區，顯示頁名、資料更新時間、語義說明 badge（扣帳/不扣帳）。
- Filter Card：日期區間 + 維度篩選（站群/站點/產品線/原因），含查詢與清除。
- KPI Row（8 卡）：`MOVEIN_QTY`、`REJECT_TOTAL_QTY`、`DEFECT_QTY`、兩種 rate、`REJECT_SHARE_PCT`、受影響 lot/workorder。
- Trend Row：
  - 左圖：`REJECT_TOTAL_QTY` vs `DEFECT_QTY`（量）
  - 右圖：`REJECT_RATE_PCT` vs `DEFECT_RATE_PCT`（率）
- Pareto + Detail：原因 Pareto（支援 metric mode 切換）與可分頁明細表。

**Visual semantics:**
- Reject（扣帳）使用暖色語義（紅/橘系）
- Defect（不扣帳）使用冷色語義（藍/青系）
- `MOVEIN_QTY`、總計與背景採中性灰藍語義
- 互動態（hover/active/filter chip）沿用既有 shared style token，確保與現有報表視覺一致

**Alternatives considered:**
- 只保留單圖單指標：無法傳達兩種語義並列。
- 新建完全獨立視覺主題：與既有 portal 風格落差大、維運成本高。

### D5: 新頁採 pure Vite entry + Flask static route + shell native loader

**Decision:** `frontend/src/reject-history/index.html` 作為 entry，build 後由 Flask `send_from_directory` 提供 `/reject-history`，並註冊到 `routeContracts` 與 `nativeModuleRegistry`。

**Why:**
- 與既有 in-scope page 架構一致，降低整合風險。
- 保留 shell canonical route 與 direct-entry 相容策略。

### D6: 匯出欄位以「語義明示」優先於歷史相容命名

**Decision:** CSV 欄位明確輸出 `REJECT_TOTAL_QTY` 與 `DEFECT_QTY`，並可附五個 reject 組成欄位；不使用易混淆別名。

**Why:**
- 報表是對外分析依據，語義清晰優先於短期縮寫便利。
- 與 field-name-consistency 治理要求一致。

## Risks / Trade-offs

- **[基底 SQL 單一來源造成查詢負載偏高]** → 先以日期與維度條件收斂、list/export 加 rate limit，必要時再追加快取或物化。
- **[使用者沿用舊語意理解 defect]** → UI 顯示語義說明 badge + tooltip，匯出欄位採顯式命名。
- **[Pareto 指標切換造成理解成本]** → 預設以 `REJECT_TOTAL_QTY` 顯示，並保留清楚的 toggle label。
- **[路由治理漏登記導致 shell 無法導航]** → contract parity test + page_status 驗證列為必做任務。
- **[明細資料量大造成前端卡頓]** → 後端分頁、預設 `per_page=50`，並避免一次性全量載入。

## Migration Plan

1. 建立後端 SQL/service/routes（先讓 API 可單獨驗證）。
2. 建立前端 reject-history 頁面與元件（先接 summary/trend，再接 pareto/list/export）。
3. 整合 shell 治理資產：`routeContracts`、`nativeModuleRegistry`、`page_status`、Flask page route。
4. 補齊測試：service、routes、route-contract parity、前端 smoke。
5. 先以 `dev` 狀態上線到抽屜，完成 UAT 後調整為 `released`。

**Rollback strategy:**
- 將 `/reject-history` 從 page registry 標記為隱藏或 `dev` 並停用導航入口。
- 保留已上線的既有頁面與 API，不影響既有報表路徑。

## Open Questions

- 趨勢圖預設粒度是否固定「日」，或需同頁支援週/月切換？
- Pareto 預設排序基準是否固定 `REJECT_TOTAL_QTY`，是否要允許切換為 `DEFECT_QTY`？
- 匯出是否要同時提供「彙總版」與「明細版」兩種檔案型態，或先只提供明細版？
