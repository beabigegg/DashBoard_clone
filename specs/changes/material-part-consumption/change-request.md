# Change Request

## Original Request

料號用量報表：以 MATERIALPARTNAME 為主鍵，查詢 DW_MES_LOTMATERIALSHISTORY 的扣料量/趨勢（週/月/季），多料號比較，依產品 TYPE 分組（JOIN DW_MES_CONTAINER），Redis+Parquet spool+DuckDB 兩層快取，粒度切換不重查 Oracle

補充澄清（互動確認）：
- 支援多料號同時查詢，趨勢圖每條線對應一個 MATERIALPARTNAME
- 分組維度：依多選料號比較，並用 BY TYPE（JOIN DW_MES_CONTAINER 取產品類型欄位）
- 新頁面放在 drawer-2（歷史報表）

## Business / User Goal

工程師想查「某料號在某段時間用了多少、趨勢如何、用在哪類產品上」，現行必須靠 query-tool 手動組合，沒有專屬報表。

## Non-goals

- 不取代現有 material-trace（LOT/批號追溯）功能
- MVP 不實作日期範圍分段平行查詢（aggregate SQL 預期 < 5s）
- 不實作 DuckDB prewarm（消耗數據異動頻繁）

## Constraints

- MATERIALPARTNAME 上限建議 20 個（趨勢圖系列數限制）
- Oracle 欄位：MATERIALPARTNAME、QTYCONSUMED、QTYREQUIRED、TXNDATE（非 TXNDATETIME）
- TYPE 欄位名需先 DESCRIBE DWH.DW_MES_CONTAINER 確認（候選：DEVICENAME、PACKAGETYPENAME）
- Admin Dashboard rq_monitor_service._QUEUE_NAMES 為硬編碼，需同步新增新佇列

## Known Context

已完成規劃（/home/egg/.claude/plans/by-wobbly-crown.md）：
- Summary spool：day-level 彙整 Parquet，粒度在 DuckDB 重新 GROUP BY
- Detail spool：raw rows，同 material-trace spool+DuckDB runtime 模式
- 粒度切換：GET /view?query_id=X&granularity=week，不查 Oracle

## Open Questions

- DW_MES_CONTAINER 的 TYPE 欄位確切名稱（實作前需 DESCRIBE）

## Requested Delivery Date / Priority

無硬性截止日，優先實作 Summary（KPI+趨勢）再做 Detail（分頁+匯出）
