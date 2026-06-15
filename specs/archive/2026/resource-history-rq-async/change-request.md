# Change Request

## Original Request

將設備歷史（resource-history）查詢接入 RQ async worker，對應長區間（超過閾值天數）的 POST /query 走 202 async 路徑，由獨立 worker 執行 Oracle 查詢與 Parquet spool，前端輪詢 job status 後呼叫 /view 取得資料；短區間維持現有同步路徑不變。

參考實作：hold-history-rq-async（已完成），本次採用相同架構模式。

## Business / User Goal

## Non-goals

## Constraints

## Known Context

## Open Questions

## Requested Delivery Date / Priority
