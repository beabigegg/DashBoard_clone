## Context

工程師需要查詢 LOT/工單對應的原物料消耗記錄，以及反向從原物料批號追溯使用該批料的所有 LOT。目前原物料資訊只能在 Query Tool 的 LotDetail "原物料" tab 逐筆查看（透過 `/api/trace/events?domains=["materials"]`），不支援批量輸入或反向查詢。

資料來源 `DWH.DW_MES_LOTMATERIALSHISTORY` 有 1800 萬筆記錄，已建立四個索引：
- IDX1: `CONTAINERID`（正向 LOT 查詢）
- IDX2: `PJ_WORKORDER`（正向工單查詢）
- IDX3: `MATERIALPARTNAME`（料號，本次不使用）
- IDX4: `MATERIALLOTNAME`（反向原物料批號查詢）

站群組（WORKCENTER_GROUP）對應由 `filter_cache.get_workcenter_mapping()` 提供，從 `DW_MES_SPEC_WORKCENTER_V` 載入，每小時刷新。

## Goals / Non-Goals

**Goals:**

- 提供獨立頁面，支援正向（LOT ID / 工單 → 原物料）和反向（原物料批號 → LOT）雙向查詢
- 正向查詢支援 LOT ID 和工單兩種輸入模式切換
- 支援多筆輸入（換行/逗號分隔）
- 結果含站群組篩選、分頁、CSV 匯出
- 使用既有 Oracle 索引，查詢效率可控

**Non-Goals:**

- 不支援 MATERIALPARTNAME（料號）反向查詢（資料量風險過高，同一料號可能數萬筆）
- 不需日期範圍篩選（以 LOT/工單/原物料批號為查詢條件即可）
- 不做 Redis 快取或 BatchQueryEngine 分片（查詢範圍由輸入筆數控制，非時間範圍）
- 不做 BOM 對照或原物料品質統計

## Decisions

### D1: 使用 `read_sql_df`（pooled connection）而非 `read_sql_df_slow`

**決定**: 查詢使用 pooled connection（`read_sql_df`），不走 slow query path。

**理由**: 此查詢依賴索引命中，預期回應時間 < 5s。不像 reject-history 的全表掃描需要 dedicated connection。正向查詢最多幾千筆結果，反向查詢設結果上限 10,000 筆。

**替代方案**: 使用 `read_sql_df_slow`。
**為何不採用**: 佔用 slow query semaphore 會排擠需要長時間執行的查詢（reject-history、resource-history）。

### D2: 正向查詢先解析 LOT ID → CONTAINERID

**決定**: LOT ID 輸入模式需要先將 CONTAINERNAME 轉換為 CONTAINERID（16-char hex），因為 `LOTMATERIALSHISTORY` 的索引是 CONTAINERID。使用 `DW_MES_CONTAINER` 做 batch lookup。工單模式直接查 `PJ_WORKORDER` 索引，不需轉換。

**理由**: 使用者輸入的是可讀的 LOT 名稱（如 GA25060001-A01），但資料表索引是 CONTAINERID。直接 JOIN 會讓 optimizer 可能選擇低效計畫。先 batch resolve 再用 IN clause 更可預測。

**替代方案**: SQL 內直接 JOIN CONTAINER 表。
**為何不採用**: 對於多筆 LOT 輸入，兩步驟（resolve + query）的執行計畫更穩定，且 resolve 結果可重用於顯示。

### D3: 站群組篩選在後端 enrichment 而非 SQL WHERE

**決定**: SQL 查詢不加 WORKCENTERNAME 過濾。查詢結果回來後，後端用 `get_workcenter_mapping()` 對每列添加 `WORKCENTER_GROUP` 欄位，前端可做篩選。若使用者選了站群組篩選，後端先 resolve 站群組 → WORKCENTERNAME 清單，再在 SQL 加 `AND WORKCENTERNAME IN (...)` 過濾。

**理由**: 如果不篩選，使用者能看到所有站點的資料（含站群組欄位）。如果篩選了，SQL 層就縮減結果集，減少傳輸和分頁壓力。

### D4: 反向查詢結果數上限 10,000 筆

**決定**: 反向查詢（原物料批號 → LOT）加入 `FETCH FIRST 10001 ROWS ONLY` 上限。若回傳超過 10,000 筆，前端顯示警告「結果超過上限，請縮小查詢範圍」。

**理由**: 一批常用原物料可能被上千個 LOT 使用。無上限的反向查詢可能回傳數萬筆，壓垮前端和 Oracle 連線。10,000 筆足以覆蓋絕大多數場景。

### D5: 前端頁面結構沿用 Vite multi-page 模式

**決定**: 新增 `frontend/material-trace.html` + `frontend/src/material-trace/App.vue` 作為獨立 Vite entry point。沿用 reject-history 的單檔 App.vue + 子元件模式。

**理由**: 專案的所有查詢頁面（reject-history、hold-history、resource-history）都是獨立 Vite entry。統一架構。

### D6: 輸入筆數上限

**決定**: 正向查詢（LOT ID / 工單）輸入上限 200 筆，反向查詢（原物料批號）輸入上限 50 筆。

**理由**: 正向查詢每筆 LOT 平均產生 10-50 筆原物料記錄，200 筆 LOT 最多 10,000 筆結果。反向查詢每批原物料可能對應 100-1000 個 LOT，50 批已有碰上 10,000 筆上限的風險。

## Risks / Trade-offs

- **[低] CONTAINERID resolve 多一次 round-trip** — LOT ID 模式需先查 `DW_MES_CONTAINER` 轉換。→ Container 表有 CONTAINERNAME 索引，batch IN query 很快（< 1s）。
- **[低] 站群組 mapping 可能未涵蓋所有 WORKCENTERNAME** — `DW_MES_SPEC_WORKCENTER_V` 可能缺少新站點。→ 未映射的站點在結果中站群組欄位顯示空值，不影響查詢結果。
- **[中] 反向查詢結果截斷** — 10,000 筆上限可能截斷大量使用的原物料批號結果。→ 前端明確顯示截斷警告，引導使用者縮小範圍。
