# Change Request

## Original Request

新增「生產達成率」看板頁面，放在「生產輔助」抽屜之下（目前該抽屜只有 /db-scheduling）。此為一般可篩選查詢的報表頁（篩選 + 表格/圖表），非即時自動刷新大螢幕看板。

### 業務邏輯（資料來源：Oracle DW_MES_LOTWIPHISTORY，別名 weh）

**1. 班別(SHIFT_CODE)計算** — 新業務規則，原本由 Oracle function `PJ_GET_CLASSCODE_F(P_TIMESTAMP)` 提供，本程式庫內尚未實作，需要在 Python/SQL 端重新實作等價邏輯：

```
CASE WHEN TO_CHAR(P_TIMESTAMP,'YYYYMMDD') <= '20191231' OR TO_CHAR(P_TIMESTAMP,'YYYYMMDD') >= '20200330' THEN
  -- 兩班制（目前現行制度）
  CASE WHEN HH24:MI:SS BETWEEN 00:00:00 AND 07:29:59 THEN 'N'
       WHEN HH24:MI:SS BETWEEN 07:30:00 AND 19:29:59 THEN 'D'
       WHEN HH24:MI:SS BETWEEN 19:30:00 AND 23:59:59 THEN 'N'
  END
ELSE
  -- 三班制（僅 2020/01/01–2020/03/29 歷史區間，目前已不使用，僅為歷史資料查詢正確性保留）
  CASE WHEN HH24:MI:SS BETWEEN 08:00:00 AND 15:59:59 THEN 'A'
       WHEN HH24:MI:SS BETWEEN 16:00:00 AND 23:59:59 THEN 'B'
       WHEN HH24:MI:SS BETWEEN 00:00:00 AND 07:59:59 THEN 'C'
  END
END
```

**2. 產出日期(output_date)計算** — 對應原本 Oracle function `PJ_GET_OUTPUTDATE_F(TRACKOUTTIMESTAMP)`，需重新實作：
- 基本規則：`output_date = TRUNC(TRACKOUTTIMESTAMP)`（日曆日期）
- 例外（跨夜班別歸屬前一天）：凌晨到早班開始前的時段要歸屬到「前一個日曆日」，因為這段時間仍屬於前一天晚上開始的夜班：
  - 兩班制：`00:00:00–07:29:59`（N 班的後半段）→ `output_date = TRUNC(timestamp) - 1`
  - 三班制（歷史區間，同樣模式類推，未經使用者最終確認，需在文件中註記為假設）：`00:00:00–07:59:59`（C 班）→ `output_date = TRUNC(timestamp) - 1`
  - 其餘時段 `output_date = TRUNC(timestamp)`

使用者確認案例：4/26 07:30–19:29 屬於 4/26 D 班；4/26 19:30–4/27 07:29 屬於 4/26 N 班（即便 4/27 00:00–07:29 這段時間的日曆日期是 4/27，仍歸屬 output_date=4/26）。

請將這兩項規則明確寫入 `contracts/business/business-rules.md` 作為新的業務規則條目。

**3. 哪些站點/工序要計入產出**（需在新的 service 查詢中原樣保留判斷條件）：

```sql
WHERE (C.CONTAINERNAME LIKE &P_ContainerName ||'%' Or &P_ContainerName is null)
  AND ((Case When(WB.WORKFLOWNAME Like '%雙晶%' Or WB.WORKFLOWNAME Like '%三晶%') Then 1 Else 0 End =0 AND
        WC.SPECNAME IN ('Epoxy D/B','Eutectic D/B','Solder Paste D/B','Solder D/B+E-Clip+固化','Solder D/B+E-Clip+固化-DW','Solder Paste D/B+E-Clip','Solder Paste D/B+E-Clip-DW'))
      OR WC.SPECNAME IN ('金線製程','銀線製程','銅線製程','手工跳線','雷射焊接','Eutectic D/B+Ag Wire','Eutectic D/B+Au Wire','Eutectic D/B+Cu Wire','E-Clip+固化','包膠-WB')
      OR (WC.SPECNAME IN ('2DB2WB','1DB2WB') AND weh.processtypename IN ('DWB_WB2'))
      OR (WC.SPECNAME IN ('2DB1WB','1DB1WB') AND weh.processtypename IN ('DWB_WB'))
      OR (WB.WORKFLOWNAME Like '%雙晶%' AND WC.SPECNAME IN ('Epoxy D/B-2','Eutectic D/B-2','Eutectic D/B-雙晶'))
      OR (WB.WORKFLOWNAME Like '%三晶%' AND WC.SPECNAME IN ('Epoxy D/B-3','Eutectic D/B-3'))
      OR (WC.SPECNAME IN ('2DB') AND weh.processtypename IN ('2DB_DB2'))
      OR (WC.SPECNAME IN ('1DB') AND weh.processtypename IN ('2DB_DB'))
      OR (WC.SPECNAME IN ('DBCB') AND weh.processtypename IN ('DBCB_CB'))
      OR (WC.SPECNAME IN ('2DBCBRO','1DBCBRO','CBRO') AND weh.processtypename IN ('CBA_RO')))
```

這段邏輯決定哪些 lot trackout 事件才算作「有效產出」，需要在新的 service 層查詢 `DW_MES_LOTWIPHISTORY` 時完整保留。

**4. 產出數量欄位**：直接使用 `weh.TRACKOUTQTY`（因為資料源已是 DWDB 表，已經整併過，不需要再疊加 `TRACKINPROCESSSPLITQTY` 做補償——使用者已確認）。

**5. 大站點/PACKAGE 分組維度**：看板以「大站點/PACKAGE」為分組維度（不是設備、不是日期+班別為主）。這個分組不需要另外手動維護 SPECNAME 對照表——專案內已有現成機制可重用：`src/mes_dashboard/services/filter_cache.py` 的 `get_spec_workcenter_mapping()`，從 Oracle view `DW_MES_SPEC_WORKCENTER_V`（環境變數 `FILTER_CACHE_SPEC_WORKCENTER_VIEW`）快取出 `{SPEC → {workcenter, group, sequence}}`，其中 `WORK_CENTER_GROUP` 即為「大站點/PACKAGE」欄位，應直接複用此既有 cache 服務做 SPECNAME → 大站點的對照，勿重新硬寫一份對照表。

### 達成率計算與呈現

- 達成率 = 實際產出（依 output_date + shift_code + 大站點/PACKAGE 分組後 `SUM(TRACKOUTQTY)`）÷ 目標值。
- 呈現/分組維度：以「大站點/PACKAGE」為主要維度（非設備、非明細）。

### 目標值管理（新功能，達成率的分母來源）

- 需要一個畫面區域，讓「被授權的使用者」可以輸入/編輯每班的目標值。
- 目標值輸入粒度：班別(SHIFT_CODE) + 大站點/PACKAGE（固定值，重複使用於每天，不含日期維度；沒有異動就不需要每天重新輸入）。
- 目標值資料表：新建一張獨立的表，直接寫入/讀取 MySQL（透過現有 `core/mysql_client.py` 的 MySQL OPS 連線），不要透過現有 SQLite dual-layer sync_worker 機制（因為那是設計給 log/metrics 這種單向、最多 10 分鐘延遲同步的場景，不適合需要立即一致性的目標值讀寫）。注意 `MYSQL_OPS_ENABLED` 預設為 false，需確認部署環境已啟用。

### 權限管理（新功能，最小範圍）

- 在既有 Admin 頁面新增一個「權限管理」區塊。此次僅需最小範圍：單一旗標型權限——「是否可編輯達成率目標值」，可指派給特定使用者/帳號（白名單形式），不需要做成通用多權限框架。
- 這個新權限表同樣獨立建一張表，直接寫入/讀取 MySQL（不透過 SQLite sync_worker），確保多 worker/多主機讀到的權限狀態即時一致。
- 現有 `core/permissions.py` 只有 `is_admin` 這種二元判斷，此次是在此之外新增一個獨立的權限判斷（不是取代 `admin_required`，是新增一個新的裝飾器/檢查函式，給「可編輯達成率目標值」這個動作用）。

### 前端整合要求

- 新增頁面路由需同時更新：`frontend/src/portal-shell/navigationManifest.js`（生產輔助 drawer 底下新增分頁）、`frontend/src/portal-shell/nativeModuleRegistry.js`（掛載閘門）、`docs/migration/full-modernization-architecture-blueprint/asset_readiness_manifest.json`、`docs/migration/full-modernization-architecture-blueprint/route_scope_matrix.json`、`data/page_status.json`。
- 前端頁面型態：篩選（日期範圍、班別、大站點/PACKAGE）+ 表格/圖表呈現達成率，可參考 production-history 或其他既有報表頁的架構模式（filter orchestration + DataTable/圖表）。

### 範圍拆分

此次合併成一個 CDD change 一次完成（權限管理最小範圍 + 生產達成率頁面），不拆成兩個 change。

## Business / User Goal

工程師/主管需要在單一報表頁查詢「大站點/PACKAGE」層級的生產達成率（實際產出 ÷ 目標值），依日期範圍、班別、大站點篩選；被授權人員可維護每班/每大站點的目標值。

## Non-goals

- 不做即時自動刷新的大螢幕看板（一般報表頁即可）。
- 不做通用多權限框架，僅新增單一「可編輯達成率目標值」旗標權限。
- 不需重建 SPECNAME→大站點對照表（複用既有 `filter_cache.get_spec_workcenter_mapping()`）。
- 三班制(A/B/C)歷史區間的 output_date 跨日規則為推論假設，非本次驗收重點，僅需文件註記。

## Constraints

- 目標值與新權限表須直接讀寫 MySQL（`core/mysql_client.py`），不得經由現有 SQLite→MySQL `sync_worker` 單向同步機制（該機制專為 log/metrics 設計，有最多 10 分鐘延遲且無回寫，不符合權限/目標值即時一致性需求）。
- `MYSQL_OPS_ENABLED` 預設為 `false`，此功能上線需確認部署環境已啟用該旗標。
- 第 3 段 WHERE 子句的站點篩選條件需完整保留（含 SPECNAME + processtypename/WORKFLOWNAME 組合判斷），不可簡化。

## Known Context

- 「生產輔助」drawer 已存在（`frontend/src/portal-shell/navigationManifest.js`），目前僅有 `/db-scheduling`。
- 專案內已有 `filter_cache.get_spec_workcenter_mapping()`（來源 `DW_MES_SPEC_WORKCENTER_V`）可直接複用做大站點分組，不需新建對照表。
- 現有 `core/permissions.py` 僅有二元 `is_admin` 判斷，需新增獨立的細粒度權限檢查（非取代 admin_required）。
- 現有 dual-layer SQLite→MySQL 架構（`core/mysql_client.py` + `core/sync_worker.py`）是為 log/metrics 設計的單向、最終一致同步，不適用於本次目標值/權限表的即時一致需求。

## Open Questions

- 三班制(A/B/C)歷史區間 C 班（00:00–07:59:59）是否確實比照 N/D 兩班制的跨日規則歸屬前一天——使用者僅確認目前現行為兩班制，此假設未經最終驗證，待未來如需查詢該歷史區間資料時再確認。

## Requested Delivery Date / Priority

未特別指定。
