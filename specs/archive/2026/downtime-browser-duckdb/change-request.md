# Change Request

## Original Request

Downtime Analysis 改用 Browser-side DuckDB-WASM 處理：Server 只負責 Oracle 抓取 + 輸出原始 parquet spool，不再做 Python pandas 彙整；瀏覽器端用 DuckDB-WASM 執行 cross-shift merge、job overlap join、以及所有視圖查詢（BigCategory / DailyTrend / EquipmentDetail / EventDetail）。目標：消除 gunicorn worker OOM 問題、讓 filter 切換即時（本地 SQL）。同時移除 90 天 Oracle fallback 日期限制（改架構後不再需要）。

做 使用新的cdd-new提案進行, 並且取消查詢90天的日期限制

## Business / User Goal

## Non-goals

## Constraints

## Known Context

## Open Questions

## Requested Delivery Date / Priority
