# Change Request

## Original Request

Downtime Analysis 遷移至 RQ 非同步查詢（Phase 3-A）。受影響 surface：POST /api/downtime-analysis/query 路由、新增 downtime_query_job_service.py、前端 downtime-analysis/App.vue 加入 AsyncQueryProgress。目標行為：查詢天數 ≥ DOWNTIME_ASYNC_DAY_THRESHOLD（預設 30）時回傳 202 + job_id，前端輪詢進度條；短查詢維持同步路徑不變。成功標準：(1) 長範圍查詢顯示進度 bar、資料正確呈現；(2) 短查詢仍走同步回傳 200；(3) parity 測試確認 RQ 路徑與同步路徑產生完全相同 downtime base_events 與 job_bridge 資料；(4) env-contract 新增 4 個 DOWNTIME_* 環境變數通過 cdd-kit validate。

## Business / User Goal

## Non-goals

## Constraints

## Known Context

## Open Questions

## Requested Delivery Date / Priority
