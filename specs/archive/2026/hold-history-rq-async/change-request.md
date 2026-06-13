# Change Request

## Original Request

將 POST /api/hold-history/query 加入 RQ async 執行路徑。查詢日期範圍 ≥ HOLD_ASYNC_DAY_THRESHOLD（預設 90 天）時返回 HTTP 202 async job；短範圍繼續 HTTP 200 同步。新增 hold_query_job_service.py worker fn，包裝現有 execute_primary_query()，pct milestones 5→15→60→90→100。前端 hold-history App.vue 整合既有 AsyncQueryProgress。成功標準：長範圍查詢顯示進度條且結果正確；短範圍 UX 不變；cdd-kit validate 通過。

## Business / User Goal

## Non-goals

## Constraints

## Known Context

## Open Questions

## Requested Delivery Date / Priority
