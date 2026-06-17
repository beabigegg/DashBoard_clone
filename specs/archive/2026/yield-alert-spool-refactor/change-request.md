# Change Request

## Original Request

yield-alert-center 架構重構：(1) 主查詢新增點測/封裝類型切換（GA%/GC%），(2) 所有視圖（趨勢、Summary卡片、熱圖、告警清單）統一從 DuckDB spool 快取計算，移除 trend.sql/summary.sql 的即時 Oracle 查詢，(3) 告警清單新增 LOT 維度（SOURCE_CODE），(4) reject linkage 一併拉入初始 spool

## Business / User Goal

工廠工程師需要能區分查詢「點測（GC%，wafer sort）」與「封裝（GA%，assembly）」的良率，目前兩種製程混用同一套查詢邏輯，且 trend/summary 視圖與 alerts 使用不同資料來源（MOVETXN 彙總表 vs DETAIL 明細表），造成過濾條件（PACKAGE/LINE/TYPE）對分子/分母作用不一致。

## Non-goals

- 不修改良率計算公式（SCRAP_QTY / TRANSACTION_QTY）
- 不改動 WIP / Hold / reject-history 等其他報表頁面
- 告警清單 LOT 維度僅增加顯示，不改變良率計算的工單粒度

## Constraints

- ERP_WIP_MOVETXN_DETAIL 每月 GA% 約 417,928 筆，加入 SOURCE_CODE 後約 1,001,283 筆（2.4x），spool 需能承載
- SOURCE_CODE = LOT ID（格式 GA26020192-A00-003-01），SOURCE_CODE NOT NULL 的列 TX=0（報廢專屬），不影響 TX 分子計算
- PACKAGE=NA 在 GA% 工單中有 0 筆，PACKAGE IS NOT NULL 篩選對 GA% 完全冗餘，可安全移除
- GC%（點測）與 GA%（封裝）在同一個資料庫表，用 WIP_ENTITY_NAME LIKE 'GC%' 或 'GA%' 區分

## Known Context

已在本對話完成的小型前置修改（尚未 commit）：
- frontend/src/yield-alert-center/App.vue：移除 PageHeader，onSort() 改呼叫 runQuery(1)
- src/mes_dashboard/sql/yield_alert/trend.sql：移除 SCRAP_QTY / YIELD_PCT 列（Python 不使用）
- src/mes_dashboard/sql/yield_alert/summary.sql：同上

資料驗證結論（直接 Oracle 查詢確認）：
- MOVETXN 與 DETAIL 彙總結果完全一致（TX=70,494,377，SCRAP=81,972）
- GA% 工單中 PACKAGE=NA 有 0 筆，PACKAGE IS NOT NULL 篩選冗餘
- SOURCE_CODE NOT NULL 的列 100% 為 SCRAP ONLY（TX=0）
- SOURCE_CODE 格式對應 DW_MES_WIP.CONTAINERNAME（LOT ID）

## Open Questions

無 — 所有技術決策已在前對話確認。

## Requested Delivery Date / Priority

高優先。
