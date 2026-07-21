---
contract: api
summary: API behavior, compatibility rules, and endpoint contract requirements.
owner: application-team
surface: api
schema-version: 1.46.0
last-changed: 2026-07-21
breaking-change-policy: deprecate-2-minors
---

# API Contract — MES Dashboard

> 來源：遷移自 `contract/api_development_contract.md` v1.1（2026-05-05）

## 1. API Style

- **Response style:** 所有 API 回應必須使用 `core/response.py` 提供的 `success_response` / `error_response` 輔助函式；禁止手動 `jsonify`。
- **Error style:** 見 `contracts/api/error-format.md`；`error.code` 必須使用預定義的標準錯誤碼常數。
- **Auth style:** Session cookie（Flask-Session）；需要認證的端點使用 `login_required` 裝飾器；Admin 端點額外驗證 `is_admin` flag。
- **Pagination style:** 以 `page` / `per_page` 查詢參數控制；回應在 `meta` 物件中附帶分頁資訊。
- **Date/time style:** ISO 8601 UTC（`meta.timestamp`）；查詢參數日期格式為 `YYYY-MM-DD`。

## 2. Response Envelope

### 2.1 成功回應 (2xx)

```json
{
  "success": true,
  "data": "<Payload>",
  "meta": {
    "timestamp": "<ISO 8601 UTC>",
    "app_version": "<string>",
    "...": "其他可選 meta 欄位（cache_state、pagination 等）"
  }
}
```

- `data`：核心 payload，可為物件或陣列。
- `meta.app_version`：每個 `success_response` / `error_response` 自動注入，來源為 `APP_VERSION` env 或 package metadata。

### 2.2 錯誤回應 (4xx / 5xx)

```json
{
  "success": false,
  "error": {
    "code": "<ERROR_CODE_STRING>",
    "message": "<User-friendly message>",
    "details": "<development-only technical details>"
  },
  "meta": {
    "timestamp": "<ISO 8601 UTC>"
  }
}
```

## 3. Error Handling

| 契約 | 規則 |
|---|---|
| 3.1 | `error.code` 必須使用 `core/response.py` 預定義常數（`VALIDATION_ERROR`、`NOT_FOUND`、`DB_QUERY_ERROR` 等） |
| 3.2 | 優先使用便捷函式：`validation_error()`、`not_found_error()`、`internal_error()` 等 |

## 4. Endpoint Requirements

> 雙方法端點（GET+POST 均接受）在下表中各自列出一行；POST body 為 GET query params 的 JSON 等效。

| method | path | auth | request schema | response schema | errors | tests |
|---|---|---|---|---|---|---|
| POST | /api/auth/login | public | JSON {username,password} | AuthSessionResponse | 400/401/429 | route tests |
| POST | /api/auth/logout | public | — | AckResponse | — | route tests |
| GET | /api/auth/me | public | — | AuthMeResponse | — | route tests |
| PATCH | /api/auth/heartbeat | required | — | AckResponse | 401 | route tests |
| GET | /health | none | — | HealthPayload | — | smoke tests |
| GET | /health/deep | none | — | HealthPayload | — | smoke tests |
| GET | /api/job/{job_id} | required | ?prefix= | JobStatusResponse | 400/404 | route tests |
| POST | /api/job/{job_id}/abandon | required | JSON body | AckResponse | 403/404/409 | route tests |
| GET | /api/spool/{namespace}/{query_id}.parquet | required | namespace in {yield_alert_dataset, reject_dataset, resource_dataset, hold_dataset, downtime_analysis_base_events, downtime_analysis_job_bridge, eap_alarm, wip_dataset, production_achievement, uph_performance} | application/octet-stream (parquet) | 400/410 | route tests |
| GET | /api/wip/overview/summary | required | query params | GenericSuccessResponse | 400/500 | route tests |
| POST | /api/wip/overview/summary | required | JSON body | GenericSuccessResponse | 400/500 | route tests |
| POST | /api/wip/overview/matrix | required | JSON body | GenericSuccessResponse | 400/500 | route tests |
| GET | /api/wip/overview/matrix | required | query params | GenericSuccessResponse | 400/500 | route tests |
| GET | /api/wip/overview/hold | required | query params | GenericSuccessResponse | 400/500 | route tests |
| POST | /api/wip/overview/hold | required | JSON body | GenericSuccessResponse | 400/500 | route tests |
| GET | /api/wip/detail/{workcenter} | required | query params | GenericSuccessResponse | 202/400/500 | route tests |
| POST | /api/wip/detail/{workcenter} | required | JSON body | GenericSuccessResponse | 202/400/500 | route tests |
| GET | /api/wip/lot/{lotid} | required | — | GenericSuccessResponse | 404/500 | route tests |
| GET | /api/wip/meta/workcenters | required | — | GenericSuccessResponse | 500 | route tests |
| GET | /api/wip/meta/packages | required | — | GenericSuccessResponse | 500 | route tests |
| GET | /api/wip/meta/filter-options | required | query params | GenericSuccessResponse | 500 | route tests |
| POST | /api/wip/meta/filter-options | required | JSON body | GenericSuccessResponse | 500 | route tests |
| GET | /api/wip/meta/search | required | ?q= | GenericSuccessResponse | 400/500 | route tests |
| GET | /api/hold-overview/summary | required | query params | GenericSuccessResponse | 400/500 | route tests |
| POST | /api/hold-overview/summary | required | JSON body | GenericSuccessResponse | 400/500 | route tests |
| GET | /api/hold-overview/matrix | required | query params | GenericSuccessResponse | 400/500 | route tests |
| POST | /api/hold-overview/matrix | required | JSON body | GenericSuccessResponse | 400/500 | route tests |
| GET | /api/hold-overview/treemap | required | query params | GenericSuccessResponse | 400/500 | route tests |
| POST | /api/hold-overview/treemap | required | JSON body | GenericSuccessResponse | 400/500 | route tests |
| GET | /api/hold-overview/lots | required | query params (optional: export=true) | GenericSuccessResponse | 400/500 | route tests |
| POST | /api/hold-overview/lots | required | JSON body (optional: export: bool) | GenericSuccessResponse | 400/500 | route tests |
| GET | /api/wip/hold-detail/summary | required | query params | GenericSuccessResponse | 400/500 | route tests |
| GET | /api/wip/hold-detail/distribution | required | query params | GenericSuccessResponse | 400/500 | route tests |
| GET | /api/wip/hold-detail/lots | required | query params | GenericSuccessResponse | 400/500 | route tests |
| GET | /api/hold-history/config | required | — | GenericSuccessResponse | 500 | route tests |
| POST | /api/hold-history/query | required | JSON body | GenericSuccessResponse | 202/400/410/500 | route tests |
| POST | /api/hold-history/today-snapshot | required | JSON body | GenericSuccessResponse | 400/503 | e2e tests |
| GET | /api/hold-history/view | required | ?query_id= | GenericSuccessResponse | 400/410 | route tests |
| GET | /api/qc-gate/summary | required | — | GenericSuccessResponse | 500 | route tests |
| GET | /api/resource/by_status | required | — | GenericSuccessResponse | 500 | route tests |
| GET | /api/resource/by_workcenter | required | — | GenericSuccessResponse | 500 | route tests |
| GET | /api/resource/workcenter_status_matrix | required | — | GenericSuccessResponse | 500 | route tests |
| POST | /api/resource/detail | required | JSON body | GenericSuccessResponse | 400/500 | route tests |
| GET | /api/resource/filter_options | required | — | GenericSuccessResponse | 500 | route tests |
| GET | /api/resource/status_values | required | — | GenericSuccessResponse | 500 | route tests |
| GET | /api/resource/status | required | query params (incl. package_groups) | GenericSuccessResponse | 400/500 | route tests |
| GET | /api/resource/status/options | required | — | GenericSuccessResponse | 500 | route tests |
| GET | /api/resource/status/summary | required | query params (incl. package_groups) | GenericSuccessResponse | 400/500 | route tests |
| GET | /api/resource/status/matrix | required | query params (incl. package_groups) | GenericSuccessResponse | 400/500 | route tests |
| GET | /api/resource/history/options | required | — | GenericSuccessResponse | 500 | route tests |
| POST | /api/resource/history/query | required | JSON body | GenericSuccessResponse | 202/400/410/500 | route tests |
| GET | /api/resource/history/view | required | ?query_id= | GenericSuccessResponse | 400/410 | route tests |
| GET | /api/resource/history/page | required | — | GenericSuccessResponse | — | route tests |
| GET | /api/resource/history/export | required | query params | GenericSuccessResponse | 400/410 | e2e tests |
| POST | /api/resource/history/export | required | JSON body | GenericSuccessResponse | 400/410 | e2e tests |
| GET | /api/resource/history/query/progress | required | ?query_id=<uuid> | ProgressResponse | 400/404 | route tests |
| GET | /api/reject-history/options | required | — | GenericSuccessResponse | 500 | route tests |
| GET | /api/reject-history/summary | required | ?query_id= | GenericSuccessResponse | 400/410 | route tests |
| GET | /api/reject-history/trend | required | ?query_id= | GenericSuccessResponse | 400/410 | route tests |
| GET | /api/reject-history/reason-pareto | required | ?query_id= | GenericSuccessResponse | 400/410 | route tests |
| POST | /api/reject-history/batch-pareto | required | JSON body | GenericSuccessResponse | 400/410 | route tests |
| GET | /api/reject-history/batch-pareto | required | ?query_id= | GenericSuccessResponse | 400/410 | route tests |
| GET | /api/reject-history/list | required | ?query_id=&page= | GenericSuccessResponse | 400/410 | route tests |
| GET | /api/reject-history/export | required | ?query_id= | GenericSuccessResponse | 400/410 | e2e tests |
| GET | /api/reject-history/export-cached | required | ?query_id= | GenericSuccessResponse | 400/410 | e2e tests |
| POST | /api/reject-history/export-cached | required | JSON body | GenericSuccessResponse | 400/410 | e2e tests |
| GET | /api/reject-history/analytics | required | ?query_id= | GenericSuccessResponse | 400/410 | route tests |
| POST | /api/reject-history/query | required | JSON body `{start_date, end_date, pj_types?(opt,list), packages?(opt,list), pj_functions?(opt,list), reasons?(opt,list)}` | GenericSuccessResponse | 202/400/500 | route tests |
| GET | /api/reject-history/count | required | ?query_id= | GenericSuccessResponse | 400/410 | route tests |
| GET | /api/reject-history/job/{job_id} | required | — | JobStatusResponse | 404 | route tests |
| GET | /api/reject-history/view | required | ?query_id= | GenericSuccessResponse | 400/410 | route tests |
| POST | /api/reject-history/view | required | JSON body | GenericSuccessResponse | 400/410 | route tests |
| POST | /api/yield-alert/query | required | JSON body `{start_date, end_date, process_type (opt, closed enum: GA%/GC%/GD%/F%/W%/D%, default GA%), lines[], packages[], types[]}` | GenericSuccessResponse | 202/400/500 | route tests |
| GET | /api/yield-alert/job/{job_id} | required | — | JobStatusResponse | 404 | route tests |
| POST | /api/yield-alert/analyze | required | JSON body | GenericSuccessResponse | 400/410 | route tests |
| GET | /api/yield-alert/view | required | ?query_id= | GenericSuccessResponse | 400/410 | route tests |
| GET | /api/yield-alert/summary | required | ?query_id= | GenericSuccessResponse | 400/410 | route tests |
| GET | /api/yield-alert/trend | required | ?query_id= | GenericSuccessResponse | 400/410 | route tests |
| GET | /api/yield-alert/alerts | required | ?query_id= | YieldAlertAlertsResponse | 400/410 | route tests |
| GET | /api/yield-alert/reason-detail | required | ?query_id=&reason= | GenericSuccessResponse | 400/410 | route tests |
| GET | /api/yield-alert/drilldown-context | required | ?query_id= | GenericSuccessResponse | 400/410 | route tests |
| GET | /api/yield-alert/filter-options | required | — | GenericSuccessResponse | 500 | route tests |
| GET | /api/yield-alert/cross-filter-options | required | ?query_id=&lines[]=... | GenericSuccessResponse | 400/410 | route tests |
| GET | /api/production-history/type-options | required | — | GenericSuccessResponse | 500 | route tests |
| GET | /api/production-history/filter-options | required | ?selected=<json> | GenericSuccessResponse | 400/404/500 | route tests |
| POST | /api/production-history/options | required | JSON body | GenericSuccessResponse | 503 | route tests |
| POST | /api/production-history/query | required | JSON body | GenericSuccessResponse | 202/400/503 | route tests |
| GET | /api/production-history/job/{job_id} | required | — | JobStatusResponse | 404 | route tests |
| POST | /api/production-history/page | required | JSON body | GenericSuccessResponse | 400/410 | route tests |
| POST | /api/production-history/matrix | required | JSON body | GenericSuccessResponse | 400/410 | route tests |
| GET | /api/production-history/count | required | ?query_id= | GenericSuccessResponse | 400/410 | route tests |
| GET | /api/production-history/export | required | query params | GenericSuccessResponse | 400/410 | e2e tests |
| POST | /api/production-history/export | required | JSON body | GenericSuccessResponse | 400/410 | e2e tests |
| POST | /api/material-trace/query | required | JSON body | GenericSuccessResponse | 202/400/503 | route tests |
| GET | /api/material-trace/job/{job_id} | required | — | JobStatusResponse | 404 | route tests |
| POST | /api/material-trace/export | required | JSON {query_hash} | GenericSuccessResponse | 400/409 | e2e tests |
| GET | /api/material-trace/filter-options | required | — | GenericSuccessResponse | 500 | route tests |
| POST | /api/trace/seed-resolve | required | JSON body | GenericSuccessResponse | 400/500 | route tests |
| POST | /api/trace/lineage | required | JSON body | GenericSuccessResponse | 202/400/500 | route tests |
| GET | /api/trace/lineage/job/{job_id} | required | — | JobStatusResponse | 404 | route tests |
| GET | /api/trace/lineage/job/{job_id}/result | required | — | GenericSuccessResponse | 404/410 | route tests |
| POST | /api/trace/events | required | JSON body | GenericSuccessResponse | 400/500 | route tests |
| GET | /api/trace/job/{job_id} | required | — | JobStatusResponse | 404 | route tests |
| GET | /api/trace/job/{job_id}/result | required | — | GenericSuccessResponse | 404/410 | route tests |
| GET | /api/trace/job/{job_id}/stream | required | — | GenericSuccessResponse | 404 | e2e tests |
| GET | /api/mid-section-defect/station-options | required | — | GenericSuccessResponse | 500 | route tests |
| GET | /api/mid-section-defect/container-filter-options | required | ?selected=<json> | MsdContainerFilterOptionsResponse | 400/500 | route tests |
| GET | /api/mid-section-defect/analysis | required | query params; optional pj_types[], packages[], direction=forward adds by_detection_loss_reason/crosstab/trend/amplification | MsdForwardAnalysisResponse | 400/500 | route tests |
| GET | /api/mid-section-defect/analysis/detail | required | query params; direction=forward rows gain detection_loss_reason | MsdForwardDetailResponse | 400/500 | route tests |
| GET | /api/mid-section-defect/loss-reasons | required | — | GenericSuccessResponse | 500 | route tests |
| GET | /api/mid-section-defect/export | required | query params | GenericSuccessResponse | 400/500 | e2e tests |
| GET | /api/analytics/anomaly-summary | required | — | AnomalySummaryResponse | 503 | route tests |
| GET | /api/analytics/yield-anomalies | required | — | GenericSuccessResponse | 503 | route tests |
| GET | /api/analytics/reject-spikes | required | — | GenericSuccessResponse | 503 | route tests |
| GET | /api/analytics/hold-outliers | required | — | GenericSuccessResponse | 503 | route tests |
| GET | /api/analytics/equipment-deviation | required | — | GenericSuccessResponse | 503 | route tests |
| GET | /api/analytics/yield-anomalies/drilldown | required | ?query_id= | GenericSuccessResponse | 400/410/503 | route tests |
| GET | /api/analytics/reject-spikes/drilldown | required | ?query_id= | GenericSuccessResponse | 400/410/503 | route tests |
| GET | /api/analytics/hold-outliers/drilldown | required | ?query_id= | GenericSuccessResponse | 400/410/503 | route tests |
| GET | /api/analytics/equipment-deviation/drilldown | required | ?query_id= | GenericSuccessResponse | 400/410/503 | route tests |
| POST | /api/query-tool/resolve | required | JSON body | GenericSuccessResponse | 400/500 | route tests |
| GET | /api/query-tool/lot-history | required | ?lot_id= | GenericSuccessResponse | 400/500 | route tests |
| GET | /api/query-tool/adjacent-lots | required | ?lot_id= | GenericSuccessResponse | 400/500 | route tests |
| GET | /api/query-tool/lot-associations | required | ?lot_id= | GenericSuccessResponse | 400/500 | route tests |
| POST | /api/query-tool/equipment-period | required | JSON body | EquipmentPeriodResponse | 202/400/500 | route tests |
| GET | /api/query-tool/equipment-list | required | — | GenericSuccessResponse | 500 | route tests |
| GET | /api/query-tool/workcenter-groups | required | — | GenericSuccessResponse | 500 | route tests |
| POST | /api/query-tool/lot-equipment-lookup | required | JSON body | LotEquipmentLookupResponse | 400/500 | route tests |
| GET | /api/query-tool/equipment-recent-jobs/{equipment_id} | required | — | GenericSuccessResponse | 404/500 | route tests |
| POST | /api/query-tool/export-csv | required | JSON body | GenericSuccessResponse | 400/500 | e2e tests |
| GET | /api/job-query/resources | required | — | GenericSuccessResponse | 500 | route tests |
| POST | /api/job-query/jobs | required | JSON body | GenericSuccessResponse | 400/500 | route tests |
| GET | /api/job-query/txn/{job_id} | required | — | GenericSuccessResponse | 404/500 | route tests |
| POST | /api/job-query/export | required | JSON body | GenericSuccessResponse | 400/500 | e2e tests |
| POST | /api/dashboard/kpi | required | JSON body | GenericSuccessResponse | 400/500 | route tests |
| POST | /api/dashboard/workcenter_cards | required | JSON body | GenericSuccessResponse | 400/500 | route tests |
| POST | /api/dashboard/detail | required | JSON body | GenericSuccessResponse | 400/500 | route tests |
| POST | /api/dashboard/ou_trend | required | JSON body | GenericSuccessResponse | 400/500 | route tests |
| POST | /api/dashboard/utilization_heatmap | required | JSON body | GenericSuccessResponse | 400/500 | route tests |
| POST | /api/ai/query | required | JSON body | AiQueryResponse | 400/500 | route tests |
| GET | /admin/api/system-status | admin | — | GenericSuccessResponse | 403/500 | route tests |
| GET | /admin/api/metrics | admin | — | GenericSuccessResponse | 403/500 | route tests |
| GET | /admin/api/logs | admin | query params | GenericSuccessResponse | 403/500 | route tests |
| POST | /admin/api/logs/cleanup | admin | — | AckResponse | 403/500 | route tests |
| POST | /admin/api/log-files/cleanup | admin | — | AckResponse | 403/500 | route tests |
| GET | /admin/api/performance-detail | admin | query params | GenericSuccessResponse | 403/500 | route tests |
| GET | /admin/api/performance-history | admin | query params | GenericSuccessResponse | 403/500 | route tests |
| POST | /admin/api/performance-history/purge | admin | — | AckResponse | 403/500 | route tests |
| GET | /admin/api/storage-info | admin | — | GenericSuccessResponse | 403/500 | route tests |
| POST | /admin/api/worker/restart | admin | — | AckResponse | 403/500 | route tests |
| GET | /admin/api/worker/status | admin | — | GenericSuccessResponse | 403/500 | route tests |
| GET | /admin/api/user-usage-kpi | admin | ?start_date=&end_date=&department= | GenericSuccessResponse | 400/403 | route tests |
| GET | /admin/api/pages | admin | — | AdminPagesResponse | 403/500 | route tests |
| PUT | /admin/api/pages/{route} | admin | JSON body {status} | AckResponse | 400/403/404 | route tests |
| POST | /admin/api/analytics/recalculate | admin | — | AckResponse | 403/500 | route tests |
| POST | /api/downtime-analysis/query | required | JSON body | DowntimeQueryResponse | 202/400/500 | route tests |
| GET | /api/downtime-analysis/options | required | — | GenericSuccessResponse | 500 | route tests |
| GET | /api/downtime-analysis/view | required | ?query_id=&granularity=&top_n= (granularity: day only; week/month planned) — **[DEPRECATED: removal target api 1.17.0]** | GenericSuccessResponse | 400/410 | route tests |
| GET | /api/downtime-analysis/equipment-detail | required | ?query_id= &page_size=(opt,max:1000,default:20) &big_category=(opt) &status_types=(opt,CSV:UDT,SDT,EGT) — **[DEPRECATED: removal target api 1.17.0]** | GenericSuccessResponse | 400/410 | route tests |
| GET | /api/downtime-analysis/event-detail | required | ?query_id= &page= &page_size= &big_category=(opt) &status_types=(opt,CSV) &resource_id=(opt) — **[DEPRECATED: removal target api 1.17.0]** | GenericSuccessResponse | 400/410 | route tests |
| GET | /api/downtime-analysis/export-equipment-detail | required | ?query_id= | GenericSuccessResponse | 400/410 | e2e tests |
| GET | /api/downtime-analysis/export-event-detail | required | ?query_id= | GenericSuccessResponse | 400/410 | e2e tests |
| GET | /api/portal/navigation | required | — | PortalNavigationResponse | 500 | route tests |
| GET | /api/trace/seed/job/{job_id} | required | — | JobStatusResponse | 404 | route tests |
| GET | /api/trace/seed/job/{job_id}/result | required | — | GenericSuccessResponse | 404/410 | route tests |
| GET | /api/material-consumption/filter-options | required | — | GenericSuccessResponse | 500 | route tests |
| POST | /api/material-consumption/query | required | JSON body | GenericSuccessResponse | 400/500 | route tests |
| GET | /api/material-consumption/view | required | ?query_id=&granularity= | GenericSuccessResponse | 400/410 | route tests |
| POST | /api/material-consumption/detail | required | JSON body | GenericSuccessResponse | 202/400/500 | route tests |
| GET | /api/material-consumption/detail/page | required | ?query_id=&page= | GenericSuccessResponse | 400/410 | route tests |
| GET | /api/material-consumption/detail/job/{job_id} | required | — | JobStatusResponse | 404 | route tests |
| POST | /api/material-consumption/export | required | JSON body | GenericSuccessResponse | 400/410 | e2e tests |
| GET | /api/get_table_info | required | — | GenericSuccessResponse | 500 | route tests |
| POST | /api/get_table_columns | required | JSON body | GenericSuccessResponse | 400/500 | route tests |
| POST | /api/query_table | required | JSON body | GenericSuccessResponse | 400/500 | route tests |
| POST | /api/eap-alarm/spool | required | JSON body {date_from, date_to, eqp_types[] (opt), lot_ids[] (opt, max 200), pj_types[] (opt), product_lines[] (opt), pj_bops[] (opt); at-least-one-of-three: eqp_types/lot_ids/product_dims} | EapAlarmSpoolJobAccepted | 202/400/500 | route tests |
| GET | /api/eap-alarm/spool/status | required | ?query_id= | GenericSuccessResponse | 400/410 | route tests |
| GET | /api/eap-alarm/filter-options | required | ?query_id= | GenericSuccessResponse | 400/410 | route tests |
| GET | /api/eap-alarm/summary | required | ?query_id=&alarm_text[]=&alarm_category[]=(opt)&equipment_id[]=(opt)&lot_id[]=(opt)&pj_type[]=(opt)&product_line[]=(opt)&pj_bop[]=(opt) | GenericSuccessResponse | 400/410 | route tests |
| GET | /api/eap-alarm/pareto | required | ?query_id=&dim=(alarm_text/eqp_id/eqp_type/lot_id/pj_type/product_line/pj_bop, default alarm_text; 400 on unknown)&alarm_text[]=&alarm_category[]=(opt)&equipment_id[]=(opt)&lot_id[]=(opt)&pj_type[]=(opt)&product_line[]=(opt)&pj_bop[]=(opt) | GenericSuccessResponse | 400/410 | route tests |
| GET | /api/eap-alarm/trend | required | ?query_id=&granularity=(day or hour, default day)&group_by=(same enum as pareto dim, default alarm_text; 400 on unknown)&alarm_text[]=&alarm_category[]=(opt)&equipment_id[]=(opt)&lot_id[]=(opt)&pj_type[]=(opt)&product_line[]=(opt)&pj_bop[]=(opt) | GenericSuccessResponse | 400/410 | route tests |
| GET | /api/eap-alarm/detail | required | ?query_id=&page=&per_page=(max 200)&alarm_text[]=&alarm_category[]=(opt)&equipment_id[]=(opt)&lot_id[]=(opt)&pj_type[]=(opt)&product_line[]=(opt)&pj_bop[]=(opt) | GenericSuccessResponse | 400/410 | route tests |
| GET | /api/downtime-analysis/meta | required | - | GenericSuccessResponse | 500 | route tests |
| GET | /api/db-scheduling/queue | required | - | DbSchedulingQueueResponse | 400/500 | route tests |
| GET | /api/db-scheduling/equipment-detail | required | - | EquipmentDetailResponse | 400/500 | route tests |
| GET | /api/production-achievement/report | required | ?start_date=&end_date=&shift_code=(opt)&workcenter_group=(opt)&source=(opt,output/moveout,default output)&force_refresh=(opt,bool,clears+re-enqueues the actual-output spool)&refresh_plan=(opt,bool,bypasses the Oracle plan/target cache independently; implied by force_refresh=true) | ProductionAchievementReportResponse | 202/400/500/503 | route tests |
| GET | /api/production-achievement/report/meta | required | ?start_date=&end_date=&source=(opt,output/moveout,default output) | ProductionAchievementReportMetaResponse | 400/500 | route tests |
| GET | /api/production-achievement/filter-options | required | - | GenericSuccessResponse | 500 | route tests |
| GET | /api/production-achievement/targets | required | ?shift_code=(opt)&workcenter_group=(opt) | ProductionAchievementTargetsResponse | 500 | route tests |
| PUT | /api/production-achievement/targets | required | body {shift_code, workcenter_group, target_qty}; also gated by can_edit_targets permission (403 if not whitelisted) | AckResponse | 400/403/500/503 | route tests |
| GET | /admin/api/production-achievement/permissions | admin | - | ProductionAchievementPermissionsResponse | 403/500/503 | route tests |
| PUT | /admin/api/production-achievement/permissions/{user_identifier} | admin | body {can_edit_targets} | AckResponse | 400/403/500/503 | route tests |
| GET | /api/job/{job_id}/result | required | ?prefix= | GenericSuccessResponse | 400/404 | route tests |
| GET | /api/eap-alarm/product-filter-options | required | - | EapAlarmProductFilterOptionsResponse | 500 | route tests |
| POST | /api/query-tool/lot-history | required | JSON body | GenericSuccessResponse | 400/500 | route tests |
| POST | /api/query-tool/lot-associations | required | JSON body | GenericSuccessResponse | 400/500 | route tests |
| POST | /api/uph-performance/spool | required | JSON body {date_from, date_to (both required, 730-day cap SYS-04), families[] (opt, DB/WB category, closed enum GDBA/GWBA; empty/absent = both), models[] (opt, RESOURCEFAMILYNAME machine model e.g. DBA_AD832UR — the real 機型 filter, UPH-06), workcenter_names[] (opt), packages[] (opt), pj_types[] (opt), equipment_ids[] (opt, max 200)} | UphPerformanceSpoolJobAccepted | 202/400/500/503 | route tests |
| GET | /api/uph-performance/spool/status | required | ?query_id= | UphPerformanceSpoolStatusResponse | 400/410 | route tests |
| GET | /api/uph-performance/filter-options | required | ?query_id= | UphPerformanceFilterOptionsResponse | 400/410 | route tests |
| GET | /api/uph-performance/product-filter-options | required | - | UphPerformanceProductFilterOptionsResponse | 500 | route tests |
| GET | /api/uph-performance/trend | required | ?query_id=&group_by=(equipment_id/family/model/package/die_count/wire_count, default family; 400 on unknown)&equipment_id[]=(opt)&workcenter_name[]=(opt)&package[]=(opt)&pj_type[]=(opt)&die_count[]=(opt)&wire_count[]=(opt) | UphPerformanceTrendResponse | 400/410 | route tests |
| GET | /api/uph-performance/ranking | required | ?query_id=&pj_type[]=(opt, own filter axis independent of global filters) | UphPerformanceRankingResponse | 400/410 | route tests |
| GET | /api/uph-performance/detail | required | ?query_id=&page=&per_page=(max 200)&equipment_id[]=(opt)&workcenter_name[]=(opt)&package[]=(opt)&pj_type[]=(opt)&die_count[]=(opt)&wire_count[]=(opt) | UphPerformanceDetailResponse | 400/410 | route tests |
| GET | /api/production-achievement/package-lf-map | required | - | ProductionAchievementPackageLfMapResponse | 500 | route tests |
| PUT | /api/production-achievement/package-lf-map | required | body {raw_package_lf, merged_group}; gated by can_edit_targets permission (403 if not whitelisted) | AckResponse | 400/403/500/503 | route tests |
| DELETE | /api/production-achievement/package-lf-map/{raw} | required | path segment {raw} URL-encoded; gated by can_edit_targets permission (403 if not whitelisted) | AckResponse | 400/403/404/500/503 | route tests |
| GET | /api/production-achievement/workcenter-merge-map | required | - | ProductionAchievementWorkcenterMergeMapResponse | 500 | route tests |
| PUT | /api/production-achievement/workcenter-merge-map | required | body {raw_workcenter_group, merged_workcenter_group, parent_group(opt), plan_source_side(required, input/output)}; gated by can_edit_targets permission (403 if not whitelisted) | AckResponse | 400/403/500/503 | route tests |
| DELETE | /api/production-achievement/workcenter-merge-map/{raw} | required | path segment {raw} URL-encoded; gated by can_edit_targets permission (403 if not whitelisted) | AckResponse | 400/403/404/500/503 | route tests |
| GET | /api/production-achievement/known-package-lf-values | required | - | ProductionAchievementKnownPackageLfValuesResponse | 500 | route tests |
| GET | /api/production-achievement/known-workcenter-groups | required | - | ProductionAchievementKnownWorkcenterGroupsResponse | 500 | route tests |
| GET | /api/production-achievement/permissions/me | required | - | ProductionAchievementOwnPermissionResponse | 500 | route tests |
| GET | /api/uph-performance/machine-options | required | - | UphPerformanceMachineOptionsResponse | 500 | route tests |
| GET | /api/equipment-lookup/options | required | - | EquipmentLookupOptionsResponse | 500 | route tests |
| GET | /api/equipment-lookup/list | required | ?locations=&families=&resource_names= (each repeatable/comma-separated, exact-match)&page=(default 1)&page_size=(default 20, max 10000)&sort_by=(RESOURCENAME/LOCATIONNAME/RESOURCEFAMILYNAME, default RESOURCENAME)&sort_dir=(asc/desc, default asc) | EquipmentLookupListResponse | 400/500 | route tests |

## 5. Routing & Naming

- **4.1 Blueprint：** 所有 API 路由必須按功能模組劃分為獨立 Flask Blueprint 檔案。
- **4.2 URL Prefix：** 所有 API 路由 URL 必須以 `/api/` 作為根路徑。
- **4.3 Naming：** 資源端點用名詞+HTTP method（RESTful）；操作端點可用動詞（RPC 風格）；保持風格一致性。

## 6. Separation of Concerns

- **5.1 Thin Controller：** 路由 handler 只負責：解析請求、基礎驗證、呼叫 service、格式化回應。
- **5.2：** 禁止在路由 handler 中撰寫業務邏輯或直接操作 DB。

## 7. Async Job Pattern

**Type A — 同步 re-query on 410：** view miss → 410 `cache_expired` → client 同步重新觸發 `execute_primary_query()`。適用：`hold_history_routes.py`、`resource_history_routes.py`。

**Type B — async 202 polling：** query miss + RQ available → 202 `{async: true, job_id, status_url}` → client polling `GET /api/job/<job_id>?prefix=<p>`。RQ 不可用時 fallback sync 200。適用：`reject_history_routes.py`、`yield_alert_routes.py`、`production_history_routes.py`、`trace_routes.py`、`material_trace_routes.py`、`downtime_analysis_routes.py`（date range ≥ CostPolicy.day_threshold=30 when `DOWNTIME_ASYNC_ENABLED=true`）、`hold_history_routes.py`（date range ≥ CostPolicy.day_threshold=30 when `HOLD_ASYNC_ENABLED=true`）、`resource_history_routes.py`（date range ≥ CostPolicy.day_threshold=30 when `RESOURCE_ASYNC_ENABLED=true`）、`eap_alarm_routes.py`（all date ranges; always async when worker available; no threshold — Type B only, no sync fallback path）、`query_tool_routes.py`（`POST /api/query-tool/equipment-period`; when `QUERY_TOOL_USE_RQ=on` + date range ≥ CostPolicy.day_threshold + worker available → 202+job_id; else sync 200; query-path-c-elimination-cleanup AC-1）、`production_achievement_routes.py`（`GET /api/production-achievement/report`；all date ranges；spool miss + worker available → always async，no day-range threshold；worker unavailable → 503，no sync fallback path；canonical spool key is date-range only（`shift_code`/`workcenter_group` do not affect routing or the spool key）；gated by `PRODUCTION_ACHIEVEMENT_USE_UNIFIED_JOB`；production-achievement-async-spool）。

## 8. API Inventory Governance

- **6.1：** `contracts/api/api-inventory.md` 為 API 契約治理盤點清單，記錄端點分類與例外邊界。
- **6.2：** 新增/刪除/重新命名/搬移任何 API 端點，必須在同一個變更同步更新盤點清單。
- **6.3：** 每個端點必須被分類為 `standard-json`、`health-exception`、`stream-download-exception` 或 `legacy-transition`。
- **6.4：** 例外端點更新時必須補上原因、影響範圍與對應驗證說明。

## 9. Test Tier Positioning

- **Resilience**（`frontend/tests/playwright/resilience/`，pre-merge CI）：API failure 注入（500/503/abort）、慢網路 overlay 行為、按鈕連點防重複、瀏覽器歷史 URL state 回復。
- **Data Boundary**（`frontend/tests/playwright/data-boundary/`，pre-merge CI）：惡意輸入（SQL、100k 字串、Unicode、倒置日期）、empty-state 顯示、export 按鈕 disabled。
- **Fault Integration**（`tests/integration/test_oracle_error_codes.py` 等，nightly）：ORA-* 錯誤碼對應、Redis timeout fallback、race condition 並發競態。

規則：
- **7.1：** Happy path 契約驗證不得混入 resilience/fault 情境；新增測試必須放在對應子目錄以獨立 spec/file 呈現。
- **7.2：** 每個 resilience/fault test 必須執行 mutation check（移除對應 handler → spec 應 FAIL）；PR 描述附 mutation check 紀錄。
- **7.3：** Route fuzz 測試（`tests/routes/test_fuzz_routes.py`）使用 `MALICIOUS_INPUTS`（定義於 `tests/routes/_fuzz_payloads.py`），惡意 payload 必須以 `VALIDATION_ERROR` 回應而非 500。

## 10. Compatibility Notes

- `meta.app_version`（2026-04-15）：所有 `success_response` / `error_response` 自動注入，backward-compatible。
- `analytics-summary` 額外注入 `meta.cache_state ∈ {warm, cold, stale}`。
- `/health` / `/health/deep`（2026-03-11）：additive `system_memory` + `async_workers` blocks，backward-compatible。
- **resource-history progress endpoint（2026-05-13，resource-history-perf）**：新增 `GET /api/resource/history/query/progress?query_id=<uuid>`；auth required；response shape: `{ query_id, total_chunks, completed_chunks, percent, status }`；`status` 為 closed enum `running | done | error`；400 on missing `query_id`，404 on unknown `query_id`；additive，不影響既有端點。
- **Production-History first-tier cache filters（2026-05-14，prod-history-first-tier-cache-filters）**：以下為 additive，backward-compatible：
  - 新增端點：`GET /api/production-history/filter-options?selected=<json>`；auth required；response `success_response`；errors 400/404/500。
  - `selected` 為 URL-encoded JSON：`{"pj_types":[],"packages":[],"bops":[],"pj_functions":[]}`；空物件或省略 → 回傳完整四欄 distinct 集合（empty-selection 場景，AC-1）。
  - Response payload：`data: {pj_types[], packages[], bops[], pj_functions[]}` + `meta: {updated_at, schema_version: 2}`。
  - 主查詢端點 `POST /api/production-history/query` 新增六個可選 JSON body 欄位（全部 additive，缺省時與舊行為一致）：
    - `pj_packages[]`（string 陣列，cached MultiSelect，plain `IN`）
    - `pj_bops[]`（string 陣列，cached MultiSelect，plain `IN`）
    - `pj_functions[]`（string 陣列，cached MultiSelect，plain `IN`）
    - `mfg_orders[]`（string 陣列，支援 `*` 萬用字元，依 PHF-02/PHF-03 規則 bind `LIKE ESCAPE '\'`）
    - `lot_ids[]`（string 陣列，支援 `*` 萬用字元；上游既有 `IN` 行為升級為 wildcard-aware）
    - `wafer_lots[]`（string 陣列，支援 `*` 萬用字元，新欄位）
  - 萬用字元語法見 business-rules.md PHF-02；server-side validation 拒絕 SQL meta-char（PHF-06），最多 100 patterns/field。
  - Type-only flow 不變（其他欄位皆 optional，省略時即既有行為）。
- **Production-History query-mode tabs（2026-05-14，prod-history-query-mode-tabs）**：以下為 additive，backward-compatible：
  - `POST /api/production-history/query` 的 `start_date` / `end_date` 由「無條件必填」放寬為「條件必填」：
    - **Classification mode**（request body 不含任何 identifier wildcard token — `mfg_orders` / `lot_ids` / `wafer_lots` 皆空或缺省）：`start_date` / `end_date` 仍為必填，缺少時 → 400 `VALIDATION_ERROR`（行為與舊版完全一致）。
    - **Identifier mode**（request body 含至少一個 `mfg_orders` / `lot_ids` / `wafer_lots` token）：`start_date` / `end_date` 為可選；兩者皆缺省時執行 wide / all-time 查詢，不再回傳 dates-required 錯誤。
  - 當 identifier token 存在「且」日期亦有提供時，日期上限規則（730d，VAL-03 / SYS-04）仍適用。
  - 既有 callers（classification 流程、現有測試）一律持續送出 `start_date` / `end_date`，行為不變；此變更不影響 first-tier cache filter 機制、wildcard 文法、second-tier 過濾或 matrix/detail 渲染。
  - Per-mode 驗證語意見 business-rules.md PHF-07 / PHF-08。
- **WIP new filter params（2026-05-13，wip-hold-drilldown-filters）**：以下四個端點新增三個可選查詢參數，全部為 additive，不影響既有呼叫方：
  - 端點：`GET/POST /api/wip/detail/<workcenter>`、`GET/POST /api/wip/overview/summary`、`GET/POST /api/wip/overview/matrix`、`GET/POST /api/wip/meta/filter-options`
  - 新增參數：
    - `workflow`（string，optional）：WORKFLOWNAME 精確比對過濾
    - `bop`（string，optional）：BOP 精確比對過濾
    - `pj_function`（string，optional）：PJ_FUNCTION 精確比對過濾
  - `GET/POST /api/wip/detail/<workcenter>` lot 列新增 `pjType` 欄位（來源：DB `PJ_TYPE` 欄）；null 值以 `null` 回傳。
  - `GET/POST /api/wip/meta/filter-options` response 新增三個 string array：`workflows`、`bops`、`pjFunctions`，與既有 `workorders` / `lotids` / `packages` / `types` / `firstnames` / `waferdescs` 並列。
- **Production-History detail partial-trackout aggregation (2026-05-15, prod-history-detail-partial-merge)**：以下為 additive，backward-compatible：
  - `POST /api/production-history/page` response：`data.rows` 每筆 row 新增 `partial_count: integer (≥ 1)`。`1` 表示未合併列；`≥ 2` 表示這列聚合了多筆 partial track-out（同一上機 session，4 鍵 `lot_id + spec + equipment_id + trackin_time`）。當 `partial_count ≥ 2` 時 `trackin_qty` 為原始上機量（`MAX(...)`，因 MES `TRACKINQTY` 隨 partial 遞減），`trackout_time = MAX(...)`，`trackout_qty = SUM(...)`。Additive；既有忽略未知欄位的 consumer 不受影響。
  - `GET /api/production-history/export` CSV：在原最後一欄 `TrackOutQty` 之後新增一欄 `PartialCount`。完整欄位順序：`LotID, Type, Package, BOP, Function, WorkOrder, WaferLot, WorkCenter, Spec, EquipmentID, EquipmentName, TrackInTime, TrackOutTime, TrackInQty, TrackOutQty, PartialCount`。以位置解析 CSV 的 consumer 需處理新尾欄；視為 additive（沿用 Breaking Change Policy）。
  - `pagination.total_rows`（`POST /api/production-history/page`）語意更新：反映聚合後的列數，而非 raw spool 列數。當查詢無 partial trackout 時兩者相同；當有合併群組時 `total_rows` 小於原 LOTWIPHISTORY 列數。
  - 三條後端路徑（DuckDB SQL 主路徑、pandas fallback、CSV 匯出）一致套用相同聚合邏輯。
  - 嚴格守門：群組內非鍵欄位若有差異則該群組退回 raw rows（不合併），對 API consumer 透明 — 無新錯誤碼。詳見 business-rules.md PH-06 / PH-07。
- **Admin dashboard fixes（2026-05-19，fix-admin-dashboard）**：以下為 additive，backward-compatible：
  - `GET /admin/api/performance-detail` `data.redis` 子物件新增四個 key：`evicted_keys`（integer），`expired_keys`（integer），`mem_fragmentation_ratio`（float），`slowlog`（array of top-5 entries：`{id, duration_us, command}`）。Redis 不可達時整個 `data.redis` 維持 `null` 或 `{"error": "..."}` 行為不變。
  - `GET /admin/api/performance-detail` 新增頂層 `data.duckdb` 子物件：`{temp_dir_bytes: integer|null, memory_limit_state: string|null}`。DuckDB telemetry 不可用時 `data.duckdb` 為 `null`。
  - `GET /admin/api/logs` 查詢範圍從「僅未同步記錄（synced=0）」擴大為「全部記錄（含已同步）」；pagination 修正為在 merge sort 後正確套用 offset/limit；response schema 不變。
  - 無端點新增/刪除/重新命名；無現有 key 移除或更名；所有改動為 additive。
- **Query-Tool partial-trackout aggregation (2026-05-15, query-tool-partial-trackout)**：以下為 additive，backward-compatible：
  - `GET /api/query-tool/lot-history` 與 `POST /api/query-tool/equipment-period`（`query_type=lots`）response rows 新增 `partial_count: integer (≥ 1)`。`TRACKINQTY` 改為 `MAX(TRACKINQTY)`（原始上機量，因 MES `TRACKINQTY` 隨 partial 遞減）；`TRACKOUTQTY` 改為 `SUM(TRACKOUTQTY)`（累計下機量）；`TRACKOUTTIMESTAMP` 改為 `MAX(TRACKOUTTIMESTAMP)`。舊行為為 `ROW_NUMBER() ... WHERE rn=1` 取最後一筆 partial —— 為靜默的數據準確性 bug。
  - `GET /api/query-tool/adjacent-lots` response rows 同樣新增 `partial_count: integer (≥ 1)`，使用 3-tuple `(CONTAINERID, EQUIPMENTID, TRACKINTIMESTAMP)` 聚合語意。
  - `partial_count` 為 additive 新欄位；既有忽略未知欄位的 consumer 不受影響。
  - 無端點移除、無欄位移除、無錯誤碼變更。
  - 嚴格守門：群組內非鍵欄位差異 → raw rows 各帶 `partial_count = 1`，對 API consumer 透明。詳見 business-rules.md QT-05 / QT-06。
  - `POST /api/query-tool/export-csv`（`export_type=lot_history` 與 `export_type=equipment_lots`）CSV 新增 `partial_count` 為傳遞欄位；以位置解析 CSV 的 consumer 需處理新尾欄。
- **Query-Tool equipment-rejects detail rewrite (2026-05-18, `equipment-rejects-by-lots`)**: `POST /api/query-tool/equipment-period` (`query_type='rejects'`) and `POST /api/query-tool/export-csv` (`export_type='equipment_rejects'`) response shape changed from aggregate (EQUIPMENTNAME, LOSSREASONNAME, TOTAL_REJECT_QTY, TOTAL_DEFECT_QTY, AFFECTED_LOT_COUNT) to per-reject-event detail rows (see data-shape-contract.md §3.7). Data source changed from LOTREJECTHISTORY filtered by EQUIPMENTNAME to LOTWIPHISTORY→LOTREJECTHISTORY via CONTAINERID (fixes cross-station reject omission). Service parameter renamed `equipment_names → equipment_ids`. Hard cutover — both EquipmentView and LotEquipmentView consumers ship in the same PR. Deprecate-2-minors policy bypassed because all consumers are in the same monorepo and shipped atomically.

- **Package / PRODUCTLINENAME additive field（2026-05-22，add-package-detail-tables）**：以下為 additive，backward-compatible：
  - `GET /api/hold-history/detail/page`（DuckDB spool 路徑）detail list 每筆明細列新增 `package: string | null`（來源：`list.sql` 中 `c.PRODUCTLINENAME AS package`；service 以 `row.get('PACKAGE')` → camelCase `package` 映射；LEFT JOIN 無比對時為 `null`；Oracle CHAR trailing-space 以 `_clean_text()` 消除）。
  - `GET /api/query-tool/lot-history` response rows 新增 `PRODUCTLINENAME: string | null`（來源：`lot_history.sql` 新增 `c.PRODUCTLINENAME`；`_df_to_records()` pass-through；LEFT JOIN 無比對時為 `null`）。
  - `POST /api/query-tool/equipment-period`（`query_type=lots`）response rows 新增 `PRODUCTLINENAME: string | null`（來源：`equipment_lots.sql` 新增 `c.PRODUCTLINENAME`；同上）。
  - `POST /api/query-tool/equipment-period`（`query_type=rejects`）：`PRODUCTLINENAME` 已在 `equipment_lot_rejects.sql` line 52 存在；本次僅確認 API response 已包含此欄及前端補顯示；無 SQL 或 service 變更。
  - `GET /api/material-consumption/detail/page` response rows 新增 `PRODUCTLINENAME: string | null`（來源：`detail_rows.sql` 新增 `c.PRODUCTLINENAME`；detail spool parquet 新增欄位；spool schema breaking-change — 需 `rm -f tmp/query_spool/material_consumption/detail-*.parquet` upon deploy/rollback，見 ci-gates.md §Rollback Policy）。
  - CSV/Excel export 對應更新：hold-history、query-tool equipment lots、query-tool equipment rejects（已含）、material-consumption 匯出檔案均新增 Package / PRODUCTLINENAME 欄。query-tool Lot History tab 無 export，不適用。
  - `_PARTIAL_NONKEY_COLS_LOT`（`query_tool_sql_runtime.py`）須加入 `"PRODUCTLINENAME"`，確保 QT-06 strict guard 將其視為 non-key column（divergence → raw rows with `partial_count=1`）。
  - 無端點移除、無欄位移除、無 error code 變更；所有改動為 additive。
  - Consumers：`frontend/src/hold-history/` (DetailTable)、`frontend/src/query-tool/` (LotHistoryTable, EquipmentLotsTable, EquipmentRejectsTable)、`frontend/src/material-consumption/` (DetailTable + export)。

- **Resource-Status Package Group（2026-05-21，resource-status-package-group）**：以下為 additive，backward-compatible：
  - `GET /api/resource/status`：新增可選查詢參數 `package_groups`（逗號分隔字串，optional）；回應每筆 record 新增 `PACKAGEGROUPNAME: string | null`（來源：`DW_MES_RESOURCE_PACKAGEGROUP` 46-row in-process lookup dict，`PACKAGEGROUPID` 為 null 時回傳 `null`；約佔所有設備的 91%）。
  - `GET /api/resource/status/summary`：新增可選查詢參數 `package_groups`；不影響 OU%/AVAIL% 計算。
  - `GET /api/resource/status/matrix`：新增可選查詢參數 `package_groups`；Package 為新增可展開維度，不改變現有 workcenter/family 維度行為。
  - `GET /api/resource/status/options`：回應 `data` 物件新增 `package_groups: string[]`（distinct 排序字串陣列）。
  - `package_groups` 篩選器在 warm-cache 路徑與 Oracle fallback 路徑均套用。
  - Lookup dict（`DW_MES_RESOURCE_PACKAGEGROUP`，46 筆）為 in-process dict，TTL = 7 天，獨立於 `resource_cache` 的 24h 週期；不新增 Redis key，不需 DB migration。
  - PACKAGEGROUPID 為 Oracle CHAR 型別；join key 比對使用 `str(...).strip()` 兩側正規化，確保型別一致。
  - 無端點移除、無欄位移除、無錯誤碼變更；所有改動為 additive。
  - Consumers：`frontend/src/resource-status/`（FilterBar、EquipmentCard、MatrixSection）。

- **[api-pipeline-upgrade] AI function-mode combined call（2026-05-29）**：以下為 additive，不影響既有端點：
  - `process_query_function()` 改為單一 combined LLM call（原 R1+R2 → combined），輸出 schema `{"function","params","explanation"}`；malformed JSON 安全降級為 null-intent 回應（不拋出例外）。
  - `_SESSION_STORE` 新增 `chat_history` 鍵（list of `{"role","content"}` pairs，cap 8 對/16 訊息，FIFO eviction）；history 注入 combined call 與 text2sql Stage 1；成功後 append；例外時不 append。
  - 新增三個 AI 函式：`production_history_query`（raw_params 派遣）、`resource_history_summary`、`qc_gate_status`。
  - Route surface、response envelope、TTL、error codes 均不變；無欄位移除；全部 additive。

- **Material-Consumption endpoints（2026-05-20，material-part-consumption）**：以下為 additive，新頁面，不影響既有端點：
  - 新增 7 個端點：`GET /api/material-consumption/filter-options` → `{workcenter_groups, primary_categories, pj_types}`；`POST /api/material-consumption/query`（summary sync，body: `{material_parts[1..20], start_date, end_date, granularity: week|month|quarter, workcenter_groups?, primary_categories?, pj_types?}`，response: `{query_id, kpi: {total_consumed, total_required, efficiency_pct, lot_count, workorder_count}, trend[], type_breakdown[]}`）；`GET /api/material-consumption/view?query_id=X&granularity=Y`（DuckDB regroup，no Oracle，410 on spool miss）；`POST /api/material-consumption/detail`（sync 200 when rows ≤ SYNC_ROW_LIMIT，else 202 async；response: `{query_id, rows[], pagination: {page, total_pages, total_rows, per_page}}`）；`GET /api/material-consumption/detail/page?query_id=X&page=N`；`GET /api/material-consumption/detail/job/<job_id>` → `{status: pending|running|done|failed, query_id?}`；`POST /api/material-consumption/export`（csv-stream，text/csv，DuckDB chunked，no full-memory load）。
  - Summary query always synchronous. Detail query sync ≤ `SYNC_ROW_LIMIT` (env default 30000); async Type B (RQ queue `material-consumption`) for larger sets.
  - `GET /view` summary spool cache key EXCLUDES granularity — one spool serves all three granularity views; DuckDB re-groups in milliseconds.
  - `material_parts` cap: 20 values; `*` wildcard → `LIKE %`; SQL meta-chars → 400 VALIDATION_ERROR (business-rules.md MC-02).
  - Parquet spool schema is breaking-change surface: column rename/add/remove → `rm -f tmp/query_spool/material_consumption/*.parquet` on deploy and rollback.
  - Consumers: `frontend/src/material-consumption/` (new, no existing consumer); Admin Dashboard `rq_monitor_service` updated with new queue name (additive).

- **downtime-analysis-page (2026-05-29)**: New endpoint family `/api/downtime-analysis/*` (5 endpoints). All auth required; Type A spool pattern.
  - `GET /api/downtime-analysis/options` → `{workcenter_groups[], families[], resources[], package_groups[], big_categories[], reasons[]}`. 500 on cache unavailable.
  - `POST /api/downtime-analysis/query` — body: `{start_date, end_date, workcenter_groups?, families?, resource_ids?, package_groups?, big_categories?, status_types?}`; date range cap 730d (SYS-04); response: `{query_id, summary: DowntimeKpiShape, daily_trend: DailyTrendRow[], big_category: BigCategoryRow[], top_reasons: TopReasonRow[]}` (see data-shape-contract.md §3.12). 400 on invalid/missing dates; 500 on Oracle error.
  - `GET /api/downtime-analysis/view?query_id=&granularity=&top_n=` — granularity: `day` only (`week`/`month` planned; 400 on invalid value); `top_n` default 10; DuckDB regroup from spool; no Oracle re-query; 410 on spool miss.
  - `GET /api/downtime-analysis/equipment-detail?query_id=&big_category=(opt)&status_types=(opt,CSV)` → `{equipment_detail: EquipmentDetailRow[]}`; response wrapper key is `equipment_detail`; optional filter params apply pandas `.isin()` narrow on in-memory `events_df` (no Oracle re-query); omitting all three returns pre-existing unfiltered response; 410 on spool miss.
  - `GET /api/downtime-analysis/event-detail?query_id=&page=&page_size=&big_category=(opt)&status_types=(opt,CSV)&resource_id=(opt)` → `{events: paginated EventDetailRow[]}` with nullable `JobEnrichment` (null when `match_source='none'`); response wrapper key is `events`; page default 1, page_size default 50 max 200; `resource_id` enables Tier 3 lazy-load scoping; omitting all three filter params returns pre-existing unfiltered response; 410 on spool miss.
- **downtime-analysis-page-redesign（2026-06-03）**: Additive optional filter params on two existing endpoints. No Oracle re-query; filtering in in-memory parquet spool. Response wrapper keys (`equipment_detail`, `events`) and per-row schemas unchanged.
  - `GET /api/downtime-analysis/equipment-detail` gains `big_category` (string, opt) and `status_types` (string, opt, CSV e.g. `UDT,SDT`; parsed by `_csv_param()`).
  - `GET /api/downtime-analysis/event-detail` gains `big_category`, `status_types`, and `resource_id` (string, opt; Tier 3 lazy-load scoping).
  - Backward-compatible: omitting all params returns byte-for-byte identical unfiltered response.
  - Consumers: `frontend/src/downtime-analysis/` only (StatusMachineJobTable.vue, MachineEventRows.vue).
  - Spool namespace `downtime_analysis_*`, cache key includes `DOWNTIME_BRIDGE_VERSION`. Additive; no existing endpoints changed.

- **downtime-browser-duckdb (2026-06-12)**: `POST /api/downtime-analysis/query` response shape changed when `DOWNTIME_BROWSER_DUCKDB=true` (default: false at initial ship). All pre-aggregated keys (`summary`, `daily_trend`, `big_category`, `top_reasons`) removed from primary path; moved to browser DuckDB-WASM. Three endpoints deprecated for removal at api 1.17.0.
  - `POST /api/downtime-analysis/query` (flag ON): returns `{base_spool_url: string, jobs_spool_url: string, query_id: string, taxonomy: TaxonomyShape}`. `base_spool_url = /api/spool/downtime_analysis_base_events/<query_id>.parquet`; `jobs_spool_url = /api/spool/downtime_analysis_job_bridge/<query_id>.parquet`. `taxonomy = {map: [[reason, category], …], prefixes: [[prefix, category], …], egt_category: "工程", fallback: "其他/未分類"}`. 90-day Oracle-path guard removed (`_MAX_ORACLE_DAYS`); 730-day SYS-04 hard cap retained. 400 on invalid/missing dates or >730d range; 500 on Oracle error.
  - `POST /api/downtime-analysis/query` (flag OFF): returns prior `{query_id, summary, daily_trend, big_category, top_reasons}` shape unchanged (rollback target).
  - `GET /api/downtime-analysis/view` — **DEPRECATED** (removal target api 1.17.0); kept alive for flag-off fallback. No behavior change.
  - `GET /api/downtime-analysis/equipment-detail` — **DEPRECATED** (removal target api 1.17.0); kept alive for flag-off fallback. No behavior change.
  - `GET /api/downtime-analysis/event-detail` — **DEPRECATED** (removal target api 1.17.0); kept alive for flag-off fallback. No behavior change.
  - Feature flag: `DOWNTIME_BROWSER_DUCKDB` env var (default false); module-level `_BROWSER_DUCKDB_ENABLED` in routes module; toggle without redeploy via gunicorn env reload.
  - Two-parquet atomicity: server writes both spools or neither; base hit with missing job spool → 500, never silent empty join.
  - CSV export for new shape: browser-blob from DuckDB-WASM result; server `export_*_csv` streamers kept as flag-off fallback only.
  - Raw spool schema: `downtime_analysis_base_events` (7 cols) and `downtime_analysis_job_bridge` (16 cols); see data-shape-contract.md §3.13. `SCHEMA_VERSION` constant participates in cache key; bumping orphans stale raw parquets without manual `rm`. Post-deploy `rm -f tmp/query_spool/downtime_analysis_base_events/*.parquet tmp/query_spool/downtime_analysis_job_bridge/*.parquet` required on schema-breaking rollback.
  - Consumers: `frontend/src/downtime-analysis/useDowntimeDuckDB.ts` (new composable; flag ON path only).
  - **Spool namespace whitelist**: `GET /api/spool/<namespace>/…` validates namespace against `_ALLOWED_NAMESPACES` in `spool_routes.py`. Any new spool-using feature MUST add its namespace to that frozenset AND to the parametrize list in `tests/test_spool_routes.py`; omitting either causes HTTP 400 for all parquet downloads from that feature. Contract: namespaces are `downtime_analysis_base_events` and `downtime_analysis_job_bridge` (added 2026-06-13; omission caused post-deploy HTTP 400 regression).

- **async-progress-ui (2026-06-13)**: `GET /api/job/<job_id>?prefix=<p>` response `data` object gains two optional fields: `pct` (float 0.0–100.0) and `stage` (string). Present only when the job service explicitly calls `update_job_progress(pct=..., stage=...)`. Consumers that poll only `status`/`result`/`error` are unaffected. Additive; no existing fields removed. See data-shape-contract.md §1.4.

- **downtime-rq-async (2026-06-13)**: `POST /api/downtime-analysis/query` gains async 202 path (additive, env-gated):
  - date range ≥ `DOWNTIME_ASYNC_DAY_THRESHOLD` (default 30) + `DOWNTIME_ASYNC_ENABLED=true` + worker available → HTTP 202 `{async: true, job_id, status_url}` where `status_url = /api/job/<job_id>?prefix=downtime`.
  - Short range (< threshold), disabled flag, or unavailable worker → HTTP 200 sync (unchanged, AC-2).
  - After job `status=finished`: `result.query_id` loads both parquet spools atomically (DA-11; data-shape-contract.md §3.14).
  - New env vars: `DOWNTIME_ASYNC_ENABLED`, `DOWNTIME_ASYNC_DAY_THRESHOLD` (30), `DOWNTIME_WORKER_QUEUE` (`downtime-query`), `DOWNTIME_JOB_TIMEOUT_SECONDS` (1800) — env-contract.md §Async Worker — Downtime Query.
  - Rollback: `DOWNTIME_ASYNC_ENABLED=false` restores pure-sync; no parquet cleanup required.
  - **Prerequisite**: async path requires `DOWNTIME_BROWSER_DUCKDB=true` (module-level `_BROWSER_DUCKDB_ENABLED`). When `DOWNTIME_BROWSER_DUCKDB=false`, all downtime queries fall through to the flag-OFF aggregated-response sync path regardless of `DOWNTIME_ASYNC_ENABLED`.

- **hold-history-rq-async (2026-06-13)**: `POST /api/hold-history/query` gains async 202 path (additive, env-gated):
  - date range ≥ `HOLD_ASYNC_DAY_THRESHOLD` (default 90) + `HOLD_ASYNC_ENABLED=true` + worker available → HTTP 202 `{async: true, job_id, status_url}` where `status_url = /api/job/<job_id>?prefix=hold-history`.
  - Short range (< threshold), disabled flag, or unavailable worker → HTTP 200 sync (unchanged).
  - After job `status=finished`: `result.query_id` loads the hold_dataset spool (existing Type A pattern for `/view` unchanged).
  - New env vars: `HOLD_ASYNC_ENABLED`, `HOLD_ASYNC_DAY_THRESHOLD` (90), `HOLD_WORKER_QUEUE` (`hold-history-query`), `HOLD_JOB_TIMEOUT_SECONDS` (1800) — env-contract.md §Async Worker — Hold History Query.
  - Rollback: `HOLD_ASYNC_ENABLED=false` restores pure-sync; no spool cleanup required.

- **resource-history-rq-async (2026-06-15)**: `POST /api/resource/history/query` gains async 202 path (additive, env-gated):
  - date range ≥ `RESOURCE_ASYNC_DAY_THRESHOLD` (default 90) + `RESOURCE_ASYNC_ENABLED=true` + worker available → HTTP 202 `{async: true, job_id, status_url}` where `status_url = /api/job/<job_id>?prefix=resource-history`.
  - Short range (< threshold), disabled flag, or unavailable worker → HTTP 200 sync (unchanged).
  - After job `status=finished`: `result.query_id` loads the resource_dataset spool (existing Type A pattern for `/view` unchanged).
  - New env vars: `RESOURCE_ASYNC_ENABLED`, `RESOURCE_ASYNC_DAY_THRESHOLD` (90), `RESOURCE_WORKER_QUEUE` (`resource-history-query`), `RESOURCE_JOB_TIMEOUT_SECONDS` (1800) — env-contract.md §Async Worker — Resource History Query.
  - Rollback: `RESOURCE_ASYNC_ENABLED=false` restores pure-sync; no spool cleanup required.

- **yield-alert-spool-refactor (2026-06-16)**: The following changes to yield-alert endpoints are additive except where noted:
  - `POST /api/yield-alert/query` body gains optional `process_type` field: closed enum `"GA%"` (packaging/assembly, default) or `"GC%"` (wafer-sort/point-test). Omitting `process_type` defaults to `"GA%"` (backward-compatible). All four downstream views (trend, summary, heatmap, alerts) scope to the same process type from the spool.
  - `GET /api/yield-alert/alerts` response rows gain `source_code: string | null` — the LOT ID from `ERP_WIP_MOVETXN_DETAIL.SOURCE_CODE`. `null` for workorder-level rows. Non-null SOURCE_CODE rows always carry TX=0 (scrap-only; do NOT inflate the TX numerator). Additive.
  - Data source for trend/summary changed from `ERP_WIP_MOVETXN` to `ERP_WIP_MOVETXN_DETAIL` (totals verified identical for GA% — TX=70,494,377, SCRAP=81,972). No change to response values.
  - `PACKAGE IS NOT NULL` filter removed from GA% queries. Verified 0 GA% rows have PACKAGE=NA; filter was redundant. No change to response values.
  - Reject linkage now computed in the single initial spool pull; the separate `_compute_reject_linkage` Oracle query is retired.
  - All four views now served exclusively from DuckDB spool. Live Oracle trend.sql/summary.sql query paths retired. 410 `CACHE_EXPIRED` behavior for spool miss is unchanged.
  - `yield_alert_dataset` parquet spool gains `process_type`, `SOURCE_CODE`, `REJECT_LINKED` columns; `_SCHEMA_VERSION` must be bumped. Rollback: `rm -f tmp/query_spool/yield_alert_dataset/*.parquet`.
  - Sole consumer: `frontend/src/yield-alert-center/`. No external partners or mobile consumers known.
- **hold-overview-export-csv (2026-06-16)**: `GET/POST /api/hold-overview/lots` gains optional export/full-data mode (additive):
  - New optional request param: `export` (boolean; GET: `?export=true`, POST body: `"export": true`). Default false/absent (omitting it preserves existing paginated behavior exactly).
  - Export mode: pagination cap (`per_page` max 200) is bypassed; all matching rows up to `HOLD_OVERVIEW_EXPORT_MAX_ROWS` are returned. Response `data.lots` array shape is unchanged (same 13-column lot row). Response `data.summary`, `data.specs`, `data.sys_date` are still present; `meta.pagination` is set to `{page: 1, per_page: <total>, total_count: <n>, total_pages: 1}` for consistency with existing consumers.
  - Additive; existing paginated callers that do not send `export` receive identical responses. No existing fields removed or renamed. No new error codes.
  - Sole consumer: `frontend/src/hold-overview/`. No external partners or mobile consumers known.

- **eap-alarm-analysis (2026-06-18)**: New endpoint family `/api/eap-alarm/*` (7 endpoints). All auth required; Type B async (POST /spool → 202 → poll /api/job/<id>?prefix=eap-alarm). Spool key: `eap_alarm:{date_from}:{date_to}:{sorted_eqp_types_hash}`; namespace `eap_alarm` added to `_ALLOWED_NAMESPACES`. Fine-filter options (alarm_text, alarm_category, equipment_id) derived from DuckDB spool only — no Oracle re-query (EA-02). AlarmCategory decoded server-side per EA-05 decode table. Navigation: new "EAP" top-level category in portal shell. Additive; no existing endpoints changed.
- **yield-alert-filter-expansion (2026-07-01):** `POST /api/yield-alert/query` `process_type` accepted-value enum expands from `{GA%, GC%}` to `{GA%, GC%, GD%, F%, W%, D%}` (additive for existing callers sending GA%/GC%; new values unlock previously-invisible ~1.65% of `ERP_WIP_MOVETXN_DETAIL` transactions). `process_type` remains a `query_id` hash input, so each of the 6 values produces its own spool file — GA/GC spool behavior is unchanged. BREAKING (shape semantics, not JSON key): `GET /api/yield-alert/view` (`data.filter_options.workcenter_groups`) and `GET /api/yield-alert/cross-filter-options` (`data.workcenter_groups`) now compute `workcenter_groups` as `SELECT DISTINCT DEPARTMENT_NAME` (raw spool column) against the query_id spool — same mechanism as `lines`/`packages`/`types`/`functions` — instead of the global, query-independent `filter_cache.get_workcenter_groups()` (`DWH.DW_MES_SPEC_WORKCENTER_V`) with `_YIELD_WORKCENTER_GROUP_ORDER`/`_DEPT_SEQ_MAP` grouping. Values now vary by query_id/process_type and are no longer grouped/ordered display names. `GET /api/yield-alert/filter-options` (separate endpoint, initial dropdown seed) and the shared `filter_cache` path used by other pages are unchanged. See data-shape-contract.md §3.16.4/§3.16.5 and business-rules.md YA-01/YA-02/YA-10/YA-11. Sole consumer: `frontend/src/yield-alert-center/`. No external partners or mobile consumers known.

## Breaking Change Policy

Breaking changes（移除欄位、改變 error code、改變 URL）需走 deprecate-2-minors 流程：先標記 deprecated，保留一個 minor 版本，再移除。

## Compatibility Notes

- **equipment-lookup-page (2026-07-21):** New endpoint family `/api/equipment-lookup/*` (2 endpoints: `GET /options`, `GET /list`) — 機台查詢 quick-lookup page under the 查詢工具 drawer. New schemas `EquipmentLookupOptionsResponse` (`{locations[], families[], resource_names[]}`) and `EquipmentLookupListResponse` (`{rows: [{RESOURCENAME, LOCATIONNAME, RESOURCEFAMILYNAME, VENDORNAME, VENDORMODEL, WORKCENTERNAME}], pagination: {page, page_size, total, total_pages}}`). Both endpoints are sync-only and read entirely from the existing `resource_cache` in-memory equipment snapshot (`get_distinct_values()` / `get_resources_by_filter()`) — no new Oracle queries, no spool, no RQ worker. `locations`/`families`/`resource_names` are independent, non-narrowing, exact-match multi-value filters (repeatable or comma-separated); `resource_names` is applied as a Python membership filter on top of `get_resources_by_filter()` since that shared function intentionally has no RESOURCENAME parameter (near-1:1 cardinality, unsuited to its bucketed index). `page_size` accepts up to 10000 so the frontend can fetch all matching rows in one call for CSV export; there is deliberately no separate export endpoint. Additive; no existing endpoints changed.
- **production-achievement-oracle-plan-source (2026-07-16):** `GET /api/production-achievement/report` `ProductionAchievementReportResponse` redefined in place again (third breaking redefinition of the same schema name). BREAKING response-shape change under the same endpoint/schema name — no deprecate-2-minors window (same exception precedent as every prior `production-achievement-*` breaking change: sole consumer `frontend/src/production-achievement/` ships in the same atomic PR):
  - Targets are now sourced from Oracle `DWH.MES_WIP_OUTPUTPLAN`/`MES_WIP_OUTPUTPLAN_DETAIL` (business-rules.md PA-11), replacing the Excel-imported `production_achievement_daily_plans` MySQL table (§3.32, deprecated not dropped — existing rollback policy).
  - **Removed endpoints**: `GET/PUT /api/production-achievement/daily-plans`, `POST /api/production-achievement/daily-plans/import/preview`, `POST /api/production-achievement/daily-plans/import/confirm` (4 method+path rows) — all return 404. Removed schemas: `ProductionAchievementDailyPlanRow`/`Response`, `ProductionAchievementDailyPlanMapEntry`, `ProductionAchievementDailyPlanImportRow`/`MissingRow`/`Summary`/`PreviewData`/`PreviewResponse`/`ConfirmData`/`ConfirmResponse`.
  - **Spool-hit (HTTP 200)**: `data.daily_plan_map` renamed to `data.plan_map`, shape changed from static `(workcenter_group, package_lf_group) -> daily_plan_qty` to date-indexed `(output_date, plan_package_group) -> {planqty_input, planqty_output}` (new schema `ProductionAchievementPlanMapEntry`, data-shape-contract.md §3.34) — no station dimension at all (the Oracle source broadcasts the same target to every station for a package/day). `data.workcenter_merge_map` entries gain `parent_group`/`plan_source_side` fields (business-rules.md PA-19/PA-20; `ProductionAchievementWorkcenterMergeMapRow`/`Entry` updated in place).
  - **Changed endpoint**: `PUT /api/production-achievement/workcenter-merge-map` body gains a REQUIRED `plan_source_side` field (`input`\|`output`, PA-20) — always submitted together with `parent_group`, never independently.
  - `GET /filter-options`, `GET/PUT /targets` (shift-based), the admin permission endpoints, `package-lf-map[/{raw}]`, `known-package-lf-values`, `known-workcenter-groups` are unchanged.
  - Sole consumer: `frontend/src/production-achievement/` + `frontend/src/production-achievement-settings/` (Excel-import UI/`DailyPlanPanel`/`DailyPlanImportDialog` removed). No external partners or mobile consumers known.
- **fix-equipment-lots-trim (2026-07-09):** Two changes, both backward-compatible:
  - Bug fix: `equipment_lots.sql` now selects `TRIM(c.CONTAINERNAME) AS CONTAINERNAME` (previously untrimmed Oracle CHAR-padded value), matching the sibling `TRIM(c.PRODUCTLINENAME)` treatment already present. Value-only fix — no column added/removed, no row-shape change (data-shape-contract.md §3.6 unaffected). Fixes a client-side exact-match filter defect that silently zeroed out the 生產紀錄 sub-tab.
  - Additive: `POST /api/query-tool/equipment-period` (`query_type=lots`) gains an optional JSON body field `container_names: string[]`. When provided, narrows results server-side via `UPPER(TRIM(c.CONTAINERNAME)) IN (...)` before the `QUERY_TOOL_DETAIL_MAX_PER_PAGE` (500) pagination clamp, applied identically on the sync route and the async RQ job path. Absent/empty array → unchanged behavior (existing callers unaffected). No new error codes.
  - Consumer: `frontend/src/query-tool/composables/useLotEquipmentQuery.ts` (`queryLots()`/`queryRejects()`) — also gains a defensive `.trim()` before `.toUpperCase()` in its own exact-match filter; no other known consumers (internal jobs/mobile/partners).
- **query-tool-url-timeout (2026-07-09, PR #32):** Additive — `POST /api/query-tool/lot-history` and `POST /api/query-tool/lot-associations` added alongside the existing `GET` routes. The frontend batch path (`useLotDetail.ts`) now sends `container_ids`/`workcenter_groups` as a JSON body instead of a comma-joined query-string param, so a large batch (up to `QUERY_TOOL_MAX_CONTAINER_IDS`) can no longer produce a request line long enough to be rejected by gunicorn's `limit_request_line` before the app's own 413 batch-size guard runs. `GET` remains supported (same params, query string) for single-CID reads and external callers. Request/response shapes and error codes are otherwise unchanged.
- **move-target-permissions-panel (2026-07-08):** UI-only relocation, no endpoint/schema/auth change. `GET /admin/api/production-achievement/permissions` and `PUT /admin/api/production-achievement/permissions/{user_identifier}` are unchanged (still `admin_required`, same request/response shapes). The consumer of these two endpoints moves from `frontend/src/admin-pages/` (permission block, removed) to `frontend/src/admin-dashboard/` (new tab) — this supersedes the consumer note in the `production-achievement-kanban (2026-07-02)` entry below, which is left as historical record and not edited in place.
- **production-achievement-overhaul (2026-07-14):** `GET /api/production-achievement/report` `ProductionAchievementReportResponse` is redefined in place again (second breaking redefinition of the same schema name — first was `production-achievement-async-spool`). BREAKING response-shape change under the same endpoint/schema name — no deprecate-2-minors window (same exception precedent: sole consumer `frontend/src/production-achievement/` ships in the same atomic PR):
  - Oracle SQL and worker now group by 4 dimensions (`output_date, shift_code, SPECNAME, PACKAGE_LF` — business-rules.md PA-09); `start_date`/`end_date` unchanged (both required, 730-day cap SYS-04); `shift_code`/`workcenter_group` request query params remain accepted-but-inert (unchanged from `production-achievement-async-spool` — still do not affect the canonical spool key or the server response).
  - **Spool-hit (HTTP 200)**: `data` grows from 2 to 5 inline arrays: `{query_id, spool_download_url, spec_workcenter_map, targets_map, package_lf_map, workcenter_merge_map, daily_plan_map}` (data-shape-contract.md §3.28.4). Three new arrays: `package_lf_map` (§3.33, D1 sparse/fallback-to-self), `workcenter_merge_map` (§3.33, D2 explicit-inclusion/exclude-by-absence), `daily_plan_map` (§3.34). `spool_download_url` parquet gains a 5th nullable column `PACKAGE_LF` (§3.28.1); `_PA_SPOOL_SCHEMA_VERSION` bumps 1→2 (breaking parquet-schema change — stale v1 parquets self-heal by key mismatch; optional `rm -f tmp/query_spool/production_achievement/*.parquet` fast-forward, see ci-gates.md §Rollback Policy).
  - **Spool-miss (HTTP 202)** / **Worker-unavailable (HTTP 503)**: unchanged from `production-achievement-async-spool` (`ProductionAchievementJobAccepted`, `always_async=True`, `sync_fallback_allowed=False`).
  - **New env vars**: none — reuses `PRODUCTION_ACHIEVEMENT_USE_UNIFIED_JOB` and the shared `WARMUP_INTERVAL_SECONDS`/`WARMUP_SCHEDULER_ENABLED` verbatim (business-rules.md PA-14).
  - **New endpoints** (additive) for the 3 new MySQL-backed CRUD tables plus 2 read-only "known values" helper endpoints: `GET/PUT/DELETE /api/production-achievement/package-lf-map[/{raw}]`, `GET/PUT/DELETE /api/production-achievement/workcenter-merge-map[/{raw}]`, `GET/PUT /api/production-achievement/daily-plans`, `GET /api/production-achievement/known-package-lf-values`, `GET /api/production-achievement/known-workcenter-groups` (10 distinct method+path rows) — all gated by the existing `can_edit_targets` permission verbatim (widened scope, no new permission system; business-rules.md PA-09/PA-10/PA-11); 403 on write when not whitelisted. New schemas: `ProductionAchievementPackageLfMapRow`/`Response`, `ProductionAchievementWorkcenterMergeMapRow`/`Response`, `ProductionAchievementDailyPlanRow`/`Response`, `ProductionAchievementKnownPackageLfValuesResponse`, `ProductionAchievementKnownWorkcenterGroupsResponse`. The `known-workcenter-groups` endpoint was added after initial review, per interaction-design.md OD-8, to let `WorkcenterMergeMappingPanel` enumerate the full raw `WORK_CENTER_GROUP` universe (including currently-excluded groups) for admin include/exclude toggling — mirrors `known-package-lf-values` exactly.
  - `GET /filter-options`, the admin permission endpoints, and `GET/PUT /targets` (shift-based) are unchanged — coexist independently (business-rules.md PA-11).
  - Sole consumer: `frontend/src/production-achievement/` + new `frontend/src/production-achievement-settings/`. No external partners or mobile consumers known.
- **production-achievement-async-spool (2026-07-08):** `GET /api/production-achievement/report` changes from a synchronous Oracle-backed aggregate-row response to the async RQ → DuckDB parquet spool pattern (mirrors `resource-history-rq-async`; ADR-0016). BREAKING response-shape change under the same endpoint/schema name — no deprecate-2-minors window (feature is pre-launch, sole consumer `frontend/src/production-achievement/` ships in the same atomic PR; same precedent as `equipment-rejects-by-lots`/`nav-config-to-code`):
  - Request params unchanged: `start_date`, `end_date` (both required, 730-day cap SYS-04), `shift_code` (opt), `workcenter_group` (opt). **Behavior change**: `shift_code`/`workcenter_group` no longer affect the server-side response or the canonical spool key — the canonical spool key is `(start_date, end_date, _PA_SPOOL_SCHEMA_VERSION)` only (date-range only, ADR-0016). The unfiltered SPECNAME-grain dataset for the full date range is always spooled; `shift_code`/`workcenter_group` filtering (PA-06/PA-07) is now applied client-side in DuckDB-WASM, not server-side.
  - **Spool-hit (HTTP 200)**: `data = {query_id, spool_download_url, spec_workcenter_map, targets_map}` (data-shape-contract.md §3.28). `spool_download_url = /api/spool/production_achievement/<query_id>.parquet` — namespace added to `spool_routes._ALLOWED_NAMESPACES` (AC-3). Injection is unconditional (Q1 resolved: local-compute activation threshold overridden to 0 for this page — no `total_row_count` gate, unlike `resource_history`'s `>= threshold` gate).
  - **Spool-miss (HTTP 202)**: `data = {async: true, job_id, status_url}`, `status_url = /api/job/<job_id>?prefix=production-achievement` — REUSES the generic job-status endpoint (§7 Type B), the same mechanism as `resource-history-rq-async`/`downtime-rq-async`/`hold-history-rq-async`, NOT a new domain-specific `/api/production-achievement/job/{job_id}` route (unlike the older `production-history`/`reject-history`/`material-trace`/`yield-alert`/`trace` per-domain job routes). New schema `ProductionAchievementJobAccepted`.
  - **Poll-completion flow**: the job `result` payload is `{query_id}` only (mirrors data-shape-contract.md §3.14.2's downtime pattern) — it does NOT itself carry `spool_download_url`/`spec_workcenter_map`/`targets_map`. After `status=finished`, the frontend re-issues the identical `GET /api/production-achievement/report` request; the canonical spool now exists, so this second call takes the 200 spool-hit path above at zero Oracle cost. **Confirm this against the actual `useProductionAchievementDuckDB.ts` completion handler during implementation** — if the job result instead carries the injected fields directly, update this note and data-shape-contract.md §3.28.4 to match.
  - **Worker-unavailable (HTTP 503)**: `always_async=True`, `sync_fallback_allowed=False` — spool-miss + no RQ worker → 503 `SERVICE_UNAVAILABLE` (no silent sync fallback; same decision tree as `eap-alarm`/`material-trace`/`downtime`).
  - New env vars: `PRODUCTION_ACHIEVEMENT_USE_UNIFIED_JOB` (env-contract.md §Worker Feature-Flag Env-Var Parity), `PRODUCTION_ACHIEVEMENT_WORKER_QUEUE`/`PRODUCTION_ACHIEVEMENT_JOB_TIMEOUT_SECONDS` (§Async Worker — Production Achievement Query).
  - `GET /filter-options`, `GET`/`PUT /targets`, and the admin permission endpoints are unchanged (non-goal, change-request.md).
  - New schemas: `ProductionAchievementJobAccepted` (202). `ProductionAchievementReportResponse` (existing schema, same name) is REWRITTEN in place to describe the new 200 spool-hit shape — see data-shape-contract.md §3.28.
  - Sole consumer: `frontend/src/production-achievement/`. No external partners or mobile consumers known.
- **production-achievement-kanban (2026-07-02):** New endpoint family `/api/production-achievement/*` (4 endpoints) + `/admin/api/production-achievement/permissions*` (2 endpoints), all additive — new page, no existing endpoints changed.
  - `GET /api/production-achievement/report` — filters: `start_date`, `end_date` (both required, 730-day cap per SYS-04), `shift_code` (opt, enum `N|D|A|B|C`), `workcenter_group` (opt). Response: array of rows per data-shape-contract.md §3.25. Reuses `filter_cache.get_spec_workcenter_mapping()` for station grouping (business-rules.md PA-06) — no new SPECNAME→station mapping.
  - `GET /api/production-achievement/filter-options` — returns available `shift_code` and `workcenter_group` values for the FilterBar; sourced from `filter_cache` + the shift-code enum, not a new cache namespace.
  - `GET /api/production-achievement/targets` — read current target values, no permission gate (view-only for any authenticated user).
  - `PUT /api/production-achievement/targets` — permission-gated write (new `can_edit_targets` check, independent of `admin_required`); reads/writes the new MySQL table `production_achievement_targets` directly via `core/mysql_client.py` (data-shape-contract.md §3.26), NOT via `core/sync_worker.py`. Requires `MYSQL_OPS_ENABLED=true` in production (env-contract.md). 403 `FORBIDDEN` when caller is not whitelisted; 503 `SERVICE_UNAVAILABLE` when MySQL OPS is disabled.
  - `GET /admin/api/production-achievement/permissions` / `PUT /admin/api/production-achievement/permissions/{user_identifier}` — admin-only whitelist management for the new MySQL table `production_achievement_edit_permissions` (data-shape-contract.md §3.27), also direct mysql_client read/write.
  - New nav entry under existing 生產輔助 drawer (alongside `/db-scheduling`); `navigationManifest.js` + `nativeModuleRegistry.js` + migration manifests updated in the same change.
  - Sole consumer: `frontend/src/production-achievement/` (new) + `frontend/src/admin-pages/` (permission block). No external partners.

- **add-db-scheduling-page (2026-06-26):** 新增 `GET /api/db-scheduling/queue`（auth required；sync；read-only）。返回 D/B-START lot 的推薦設備清單；資料來源 `DWH.DW_MES_LOT_V` 5-min WIP cache。結果按 PACKAGE_LEF → PJ_TYPE → WAFERLOT → UTS 排序。一個 lot 可對應多筆 row（一筆設備一行）。matchSource 閉合 enum：workflow / bop-fallback / none。Additive；無現有端點變更。

- **nav-config-to-code (2026-06-24):** BREAKING — 4 drawer endpoints removed (all return **404**): `GET /admin/api/drawers`, `POST /admin/api/drawers`, `PUT /admin/api/drawers/{drawer_id}`, `DELETE /admin/api/drawers/{drawer_id}`. `PUT /admin/api/pages/{route}` body narrows to `{status}` — `name`, `drawer_id`, `order` silently ignored, MUST NOT persist. `GET /admin/api/pages` response narrows to `{pages:[{route,status}]}` — `name`, `drawer_id`, `order` absent. `GET /api/portal/navigation` drops `drawers`, adds `statuses` (route → status map; absent route = released). Sole consumers `frontend/src/admin-pages/` + `portal-shell/` — monorepo atomic cutover, no deprecation window.

- **rh-primary-prefilter (2026-06-25):** `POST /api/reject-history/query` body gains three new optional fields (additive, backward-compatible when absent): `pj_types[]`, `packages[]`, `pj_functions[]` (all string arrays). Injected into `{{ BASE_WHERE }}` of `reject_raw` CTE (Oracle-layer, before GROUP BY) via `NVL(TRIM(c.col), '(NA)') IN (...)` — NULL container values map to sentinel `(NA)`, not silently dropped. Empty list or field absent = no restriction. `PJ_BOP` not included. Options from shared `container_filter_cache`. Parity: same fields in both sync+async/RQ paths and spool/cache keys. Sole consumer: `frontend/src/reject-history/`.

- **rh-remove-supplementary-filter (2026-06-25):** `POST /api/reject-history/query` body gains `reasons[]` optional string array (additive; absent/empty = no restriction). Injected into `{{ BASE_WHERE }}` of `reject_raw` CTE via `NVL(TRIM(r.LOSSREASONNAME), '(未填寫)') IN (:reason_0, ...)` with `reason_`-prefixed bind params. Sentinel `(未填寫)` for null/blank LOSSREASONNAME is distinct from the `(NA)` sentinel used for container-level fields. `workcenter_groups[]` param removed — supplementary `{{ WHERE_CLAUSE }}` filter section (workcenter_groups, packages, reasons, types) fully removed. Breaking for callers sending `workcenter_groups`; sole consumer is monorepo frontend, atomic cutover, no deprecation window (same precedent as [api 1.27.0]).

## CHANGELOG

- **[api 1.46.0] — 2026-07-21 (equipment-lookup-page):** New endpoint family `/api/equipment-lookup/*` (2 endpoints: `GET /options`, `GET /list`). New schemas `EquipmentLookupOptionsResponse`, `EquipmentLookupListResponse`. Sync-only, served entirely from the existing `resource_cache` in-memory equipment snapshot — no new Oracle queries, no spool, no RQ worker. Additive; no existing endpoints changed.
- **[api 1.39.0] — 2026-07-21 (production-achievement-metadata-gated-refresh):** New `GET /api/production-achievement/report/meta` — cheap freshness-only probe (`sync_time`/`latest_data_timestamp` via a direct Redis spool-metadata read, no MySQL/Oracle round-trips, never enqueues). New schema `ProductionAchievementReportMetaResponse`. Additive; no existing endpoint changed. Frontend: `production-achievement` gains metadata-gated auto-refresh (polls this endpoint; only re-fetches `GET /report` when `sync_time` changes), scoped to 今日/前日 modes to match the hourly warmup scheduler's coverage.
- **[api 1.38.1] — 2026-07-08 (move-target-permissions-panel):** No endpoint/schema/auth change. Consumer-only note: the two admin permission endpoints' frontend consumer moves from `admin-pages` to `admin-dashboard` (see Compatibility Notes above).
- **[api 1.38.0] — 2026-07-08 (production-achievement-async-spool):** `GET /api/production-achievement/report` migrated from a synchronous Oracle-aggregated-row response to the async RQ → DuckDB parquet spool pattern (ADR-0016). Spool-hit → HTTP 200 `{query_id, spool_download_url, spec_workcenter_map, targets_map}` (`ProductionAchievementReportResponse` redefined in place); spool-miss + worker available → HTTP 202 (new `ProductionAchievementJobAccepted`, reuses generic `/api/job/<id>?prefix=production-achievement`); spool-miss + worker unavailable → HTTP 503. `shift_code`/`workcenter_group` no longer affect the server response or spool key. `production_achievement` added to the spool-namespace enum. No deprecation window (pre-launch, atomic-PR consumer). Other 5 endpoints in this family unchanged.
- **[api 1.36.0] — 2026-07-02 (production-achievement-kanban):** New endpoint family `/api/production-achievement/*` (4 endpoints: report, filter-options, targets GET/PUT) + `/admin/api/production-achievement/permissions*` (2 endpoints). New schemas: `ProductionAchievementReportResponse`, `ProductionAchievementTargetsResponse`, `ProductionAchievementPermissionsResponse`. `PUT /api/production-achievement/targets` is permission-gated by a new independent `can_edit_targets` check (not `admin_required`); 403 on unauthorized write. All additive; no existing endpoints changed.
- **[api 1.35.0] — 2026-07-01 (yield-alert-filter-expansion):** `POST /api/yield-alert/query` `process_type` enum expands `{GA%,GC%}` → `{GA%,GC%,GD%,F%,W%,D%}`. `GET /api/yield-alert/view` + `GET /api/yield-alert/cross-filter-options` `workcenter_groups` value source changes from global `filter_cache`/`DW_MES_SPEC_WORKCENTER_V` to per-query_id spool `SELECT DISTINCT DEPARTMENT_NAME` (breaking shape semantics; JSON key unchanged). `GET /api/yield-alert/filter-options` unchanged.
- **[api 1.34.0] — 2026-06-30 (eap-alarm-coarse-filter):** `POST /api/eap-alarm/spool` gains `lot_ids[]`, `pj_types[]`, `product_lines[]`, `pj_bops[]` (all optional); `eqp_types[]` now optional; at-least-one-of-three validation (EA-08). New `GET /api/eap-alarm/product-filter-options` — reads `container_filter_cache`, maps `packages→product_lines` and `bops→pj_bops`; cold-cache = empty arrays (not 500). Spool key hash extended to all 5 dims; `_SCHEMA_VERSION` 2→3. New schema `EapAlarmProductFilterOptionsResponse`. Additive for clients that always supply `eqp_types`.
- **[api 1.33.0] — 2026-06-30 (msd-forward-cause-effect):** `GET /api/mid-section-defect/analysis?direction=forward` gains `by_detection_loss_reason[]`, `loss_reason_workcenter_crosstab`, `downstream_trend[]`, `amplification`; schema `MsdForwardAnalysisResponse`. Detail gains `DETECTION_LOSS_REASON`; schema `MsdForwardDetailResponse`. Additive.
- **[api 1.32.0] — 2026-06-29 (msd-type-package-filter):** New `GET /api/mid-section-defect/container-filter-options?selected=<json>` — cross-filter cached options for Type/Package FilterBar MultiSelects; reuses shared `container_filter_cache`; no Oracle at request time; 400 on malformed `selected` JSON; 500 on Oracle build error; response schema `MsdContainerFilterOptionsResponse`. `GET /api/mid-section-defect/analysis` gains optional `pj_types[]` and `packages[]` multi-value query params (absent/empty = no restriction; AND-semantics when both present; post-query filter on detection_df BEFORE spool derivation). Both params added to analysis result cache key to prevent collision. Additive; no existing fields removed or renamed.
- **[api 1.31.0] — 2026-06-27 (fix-ci-conformance):** `GET /api/job/{job_id}/result` (auth required; ?prefix= query param; returns stored job result payload; 400/404). Endpoint existed in `job_routes.py` but was missing from the API contract.
- **[api 1.29.0] — 2026-06-25 (rh-remove-supplementary-filter):** `POST /api/reject-history/query` gains `reasons[]` optional string array (additive; absent/empty = no restriction). `NVL(TRIM(r.LOSSREASONNAME), '(未填寫)') IN (...)` at `{{ BASE_WHERE }}` layer; sentinel `(未填寫)` distinct from container-level `(NA)`. `workcenter_groups[]` param removed; supplementary `{{ WHERE_CLAUSE }}` layer removed entirely. Sole consumer `frontend/src/reject-history/`; monorepo atomic cutover (same precedent as [api 1.27.0]).
- **[api 1.28.0] — 2026-06-25 (rh-primary-prefilter):** `POST /api/reject-history/query` body gains three new optional fields: `pj_types[]`, `packages[]`, `pj_functions[]` (string arrays; absent or empty = no restriction). Injected into `{{ BASE_WHERE }}` of `reject_raw` CTE (Oracle-layer, before GROUP BY). SQL form: `NVL(TRIM(c.col), '(NA)') IN (...)` — NULL container values map to `(NA)` sentinel, not silently dropped. `PJ_BOP` explicitly excluded. Options from shared `container_filter_cache`. Both sync (200) and async/RQ (202) paths carry new fields identically. Additive; no existing fields removed or renamed.
- **[api 1.27.0] — 2026-06-24 (nav-config-to-code):** Removed BREAKING: `GET /admin/api/drawers`, `POST /admin/api/drawers`, `PUT /admin/api/drawers/{drawer_id}`, `DELETE /admin/api/drawers/{drawer_id}` all return **404**. `name`/`drawer_id`/`order` removed from `GET /admin/api/pages` response body and `PUT /admin/api/pages` accepted body. Changed: `GET /api/portal/navigation` response drops `drawers`, adds `statuses` map; response schema renamed `GenericSuccessResponse` → `PortalNavigationResponse`. Added: `AdminPagesResponse` schema; `PUT /admin/api/pages/{route}` row. No deprecation window — monorepo atomic cutover.
- **WIP detail async 202 routing (2026-06-20, wip-rq-worker-chunks-cleanup)**: `GET/POST /api/wip/detail/<workcenter>` now returns HTTP 202 + `{async: true, job_id, status_url}` when row count ≥ L3 (200,000) and RQ worker available. Sync 200 path is unchanged when row count < L3 or worker unavailable (fail-open). New spool namespace `wip_dataset` added to `/api/spool` whitelist. New schema `WipDetailJobAccepted`. Type B async; `prefix=wip-detail` for job status polling. Additive; no existing fields removed or renamed. Worker ships inert until `stress-soak-report.md` sign-off (see ci-gates.md §Promotion Policy).
## [api 1.25.0] — 2026-06-18
### Added
- eap-alarm-analysis: 7 new endpoints under `/api/eap-alarm/*` (POST /spool 202 async, GET /spool/status, GET /filter-options, GET /summary, GET /pareto, GET /trend, GET /detail). Spool namespace `eap_alarm` added to `/api/spool` whitelist. Type B async; fine-filter views DuckDB-only (no Oracle re-query post-spool). New schema `EapAlarmSpoolJobAccepted`. Additive; no existing endpoints changed.

## [api 1.24.0] — 2026-06-16
### Added
- yield-alert-spool-refactor: `POST /api/yield-alert/query` body gains optional `process_type` field (enum: `"GA%"` default / `"GC%"`; backward-compatible when omitted). `GET /api/yield-alert/alerts` response rows gain `source_code: string | null` (LOT ID from ERP_WIP_MOVETXN_DETAIL; null for workorder-level rows; non-null always TX=0). All four views now served from DuckDB spool only; live Oracle trend/summary paths retired. `yield_alert_dataset` spool gains `process_type`, `SOURCE_CODE`, `REJECT_LINKED` columns (schema-version bump + parquet cleanup on deploy/rollback). `PACKAGE IS NOT NULL` filter removed from GA% queries (0 affected rows). Reject linkage folded into initial spool pull. Data source changed from ERP_WIP_MOVETXN to ERP_WIP_MOVETXN_DETAIL (totals identical for GA%). Sole consumer: `frontend/src/yield-alert-center/`. Additive; no existing response fields removed or renamed.

## [api 1.23.0] — 2026-06-16
### Added
- hold-overview-export-csv: `GET /api/hold-overview/lots` and `POST /api/hold-overview/lots` gain optional `export` boolean parameter (GET: `?export=true`, POST body: `"export": true`). Export mode bypasses per_page cap (200) and returns all matching rows up to `HOLD_OVERVIEW_EXPORT_MAX_ROWS`. Paginated behavior is unchanged when `export` is absent or false. Additive; no existing fields removed or renamed.

## [api 1.22.0] — 2026-06-16
### Added
- response-shape-adr0007: Added `## Schema Authoring Rules` section documenting cdd-kit response schema cell format, Tier-A table header requirements, dataPath semantics, and openapi.json regeneration obligation. Additive; no API surface changed.

## [api 1.19.0] — 2026-06-15
### Added
- resource-history-rq-async: `POST /api/resource/history/query` gains async 202 path when `RESOURCE_ASYNC_ENABLED=true` and date range ≥ `RESOURCE_ASYNC_DAY_THRESHOLD` (default 90 days). Short-range, flag-off, or unavailable worker → HTTP 200 sync unchanged. Type B §7 extended to include `resource_history_routes.py`. §10 compatibility note added. New `resource-history-query` RQ queue. Additive; no existing fields removed.

## [api 1.18.0] — 2026-06-13
### Added
- hold-history-rq-async: `POST /api/hold-history/query` gains async 202 path when `HOLD_ASYNC_ENABLED=true` and date range ≥ `HOLD_ASYNC_DAY_THRESHOLD` (default 90 days). Short-range, flag-off, or unavailable worker → HTTP 200 sync unchanged. Type B §7 extended to include `hold_history_routes.py`. §10 compatibility note added. New `hold-history-query` RQ queue. Additive; no existing fields removed.

## [api 1.16.0]
- async-progress-ui (2026-06-13): `GET /api/job/<job_id>` response `data` gains optional `pct: float` (0.0–100.0) and `stage: string` fields. Emitted by yield-alert-job-service and production-history-job-service progress milestones. Additive; no existing fields removed or renamed.

## [api 1.12.0]
- ai-pipeline-upgrade (2026-05-29): [api-pipeline-upgrade] Internal function-mode pipeline collapsed from two LLM calls (R1 intent + R2 params) to one combined call returning `{"function","params","explanation"}`. `_SESSION_STORE` extended with `chat_history` key (list of role/content pairs, cap 8 pairs); history injected into combined call and text2sql Stage 1 only. Three new AI functions registered (`production_history_query`, `resource_history_summary`, `qc_gate_status`). Route surface (`/api/ai/query`), response envelope keys, TTL, and error codes are unchanged. No fields removed; all changes internal to the AI service layer. Backward-compatible.

## [api 1.11.0]
- add-package-detail-tables (2026-05-22): Added `package: string | null` to hold-history detail rows; added `PRODUCTLINENAME: string | null` to query-tool lot-history and equipment-lots rows; confirmed equipment-rejects already had PRODUCTLINENAME; added `PRODUCTLINENAME: string | null` to material-consumption detail rows (detail spool schema updated — parquet cleanup required on deploy/rollback). All additive; no existing fields removed.

## [api 1.10.0]
- resource-status-package-group (2026-05-21): Added optional `package_groups` query param to `/api/resource/status`, `/api/resource/status/summary`, `/api/resource/status/matrix`; added `package_groups[]` to `/api/resource/status/options` response; added `PACKAGEGROUPNAME: string | null` to each `/api/resource/status` record. All additive; no existing endpoints changed.

## [api 1.9.0]
- material-part-consumption (2026-05-20): Added 7 endpoints under `/api/material-consumption` (filter-options, query, view, detail, detail/page, detail/job, export). New additive surface; no existing endpoints changed.

## Schema Authoring Rules

- **Response schema cell format:** `response schema` cells must contain a bare identifier matching `/^[A-Za-z][A-Za-z0-9_]*/` (optionally with `[]` suffix for arrays). Any prefix such as `→ SchemaName` is treated as prose — no `$ref` is generated and `cdd-kit validate --contracts` reports "checked 0 sampled endpoint(s)" (vacuous pass, silently non-enforcing).
- **Tier-A field table headers:** A named schema component is compiled only when the table uses exactly `| field | type | required |` as column headers. Any other header set (e.g., `| name | type | description |`) causes the table to be silently skipped. Use Tier-B `json-schema` blocks when in doubt.
- **`dataPath` in `response-samples.json`:** Set `dataPath` only when the declared schema describes the *inner* payload (not the envelope). Schemas that describe the full `{success, data, meta}` envelope must omit `dataPath`; using it on an envelope schema causes type-mismatch failures on error responses (no `data` key).
- **`contracts/openapi.json` must be regenerated after every edit** to the endpoint table or `## Schemas` section: run `cdd-kit openapi export --out contracts/openapi.json` and commit the result. The `openapi-sync` CI gate (`cdd-kit openapi export --check`) detects drift and blocks merge.

## Schemas

> Typed response schemas for all 155 contract endpoints (158 minus 4 drawer endpoints + 1 PUT /admin/api/pages/{route} = 155). Tier A = field table; Tier B = json-schema block. Referenced by `response schema` column above and resolved by `cdd-kit openapi export → contracts/openapi.json`.

### AckResponse

Tier-B — minimal acknowledgement; body carries no domain payload.

```json-schema
{
  "type": "object",
  "required": ["success", "meta"],
  "properties": {
    "success": { "type": "boolean" },
    "data": { "type": ["object", "null"] },
    "meta": { "type": "object", "required": ["timestamp"], "properties": { "timestamp": { "type": "string" }, "app_version": { "type": "string" } } }
  }
}
```

### GenericSuccessResponse

Tier-B — wraps any domain payload returned by `success_response(data)`. Used for endpoints whose payload shape is feature-specific or deeply nested. Offline test-client captures may return error envelopes (`success:false`) when Oracle/Redis is unavailable, or raw objects for legacy endpoints — the schema accepts all valid JSON objects.

```json-schema
{
  "type": ["object", "null"],
  "properties": {
    "success": { "type": "boolean" },
    "data": {},
    "error": {},
    "meta": {
      "type": "object",
      "properties": {
        "timestamp":   { "type": "string" },
        "app_version": { "type": "string" }
      }
    }
  }
}
```

### HealthPayload

Tier-B — top-level health envelope (no `success`/`data` wrapper; health-exception endpoints).

```json-schema
{
  "type": "object",
  "required": ["status"],
  "properties": {
    "status": { "type": "string", "enum": ["ok", "error", "healthy", "degraded"] },
    "version": { "type": "string" },
    "checks": { "type": "object" }
  }
}
```

### AuthSessionResponse

Tier-B — successful login response containing user session info.

```json-schema
{
  "type": "object",
  "required": ["success"],
  "properties": {
    "success": { "type": "boolean" },
    "data": {
      "type": "object",
      "properties": {
        "username":    { "type": "string" },
        "displayName": { "type": "string" },
        "isAdmin":     { "type": "boolean" }
      }
    },
    "error": {},
    "meta": {
      "type": "object",
      "properties": {
        "timestamp":   { "type": "string" },
        "app_version": { "type": "string" }
      }
    }
  }
}
```

### AuthMeResponse

Tier-B — `GET /api/auth/me`; returns current user or null data when not logged in.

```json-schema
{
  "type": "object",
  "required": ["success", "meta"],
  "properties": {
    "success": { "type": "boolean", "enum": [true] },
    "data": {},
    "meta": {
      "type": "object",
      "required": ["timestamp"],
      "properties": {
        "timestamp":   { "type": "string" },
        "app_version": { "type": "string" }
      }
    }
  }
}
```

### JobStatusResponse

Tier-B — async job polling response (`GET /api/job/<job_id>`).

```json-schema
{
  "type": "object",
  "required": ["success"],
  "properties": {
    "success": { "type": "boolean" },
    "data": {
      "type": ["object", "null"],
      "properties": {
        "status":    { "type": "string", "enum": ["pending", "running", "done", "failed"] },
        "query_id":  { "type": "string" },
        "result":    {},
        "error":     { "type": "string" },
        "pct":       { "type": "number", "minimum": 0, "maximum": 100 },
        "stage":     { "type": "string" }
      }
    },
    "meta": {
      "type": "object",
      "required": ["timestamp"],
      "properties": {
        "timestamp":   { "type": "string" },
        "app_version": { "type": "string" }
      }
    }
  }
}
```

### ProgressResponse

Tier-B — batch query progress (`GET /api/resource/history/query/progress`).

```json-schema
{
  "type": "object",
  "required": ["success"],
  "properties": {
    "success": { "type": "boolean" },
    "data": { "type": "object", "properties": { "query_id": { "type": "string" }, "total_chunks": { "type": "integer" }, "completed_chunks": { "type": "integer" }, "percent": { "type": "number" }, "status": { "type": "string" } } },
    "meta": { "type": "object", "required": ["timestamp"], "properties": { "timestamp": { "type": "string" }, "app_version": { "type": "string" } } }
  }
}
```

### HoldHistoryJobAccepted

Tier-B — 202 async branch for `POST /api/hold-history/query`.

```json-schema
{
  "type": "object",
  "required": ["success", "data", "meta"],
  "properties": {
    "success": { "type": "boolean", "enum": [true] },
    "data": { "type": "object", "required": ["async", "job_id", "status_url"], "properties": { "async": { "type": "boolean", "enum": [true] }, "job_id": { "type": "string" }, "status_url": { "type": "string" }, "status": { "type": "string" } } },
    "meta": { "type": "object", "required": ["timestamp"], "properties": { "timestamp": { "type": "string" }, "app_version": { "type": "string" } } }
  }
}
```

### ResourceHistoryJobAccepted

Tier-B — 202 async branch for `POST /api/resource/history/query`.

```json-schema
{
  "type": "object",
  "required": ["success", "data", "meta"],
  "properties": {
    "success": { "type": "boolean", "enum": [true] },
    "data": { "type": "object", "required": ["async", "job_id", "status_url"], "properties": { "async": { "type": "boolean", "enum": [true] }, "job_id": { "type": "string" }, "status_url": { "type": "string" }, "status": { "type": "string" } } },
    "meta": { "type": "object", "required": ["timestamp"], "properties": { "timestamp": { "type": "string" }, "app_version": { "type": "string" } } }
  }
}
```

### RejectHistoryJobAccepted

Tier-B — 202 async branch for `POST /api/reject-history/query`.

```json-schema
{
  "type": "object",
  "required": ["success", "data", "meta"],
  "properties": {
    "success": { "type": "boolean", "enum": [true] },
    "data": { "type": "object", "required": ["async", "job_id", "status_url"], "properties": { "async": { "type": "boolean", "enum": [true] }, "job_id": { "type": "string" }, "status_url": { "type": "string" }, "status": { "type": "string" } } },
    "meta": { "type": "object", "required": ["timestamp"], "properties": { "timestamp": { "type": "string" }, "app_version": { "type": "string" } } }
  }
}
```

### YieldAlertJobAccepted

Tier-B — 202 async branch for `POST /api/yield-alert/query`.

```json-schema
{
  "type": "object",
  "required": ["success", "data", "meta"],
  "properties": {
    "success": { "type": "boolean", "enum": [true] },
    "data": { "type": "object", "required": ["async", "job_id", "status_url"], "properties": { "async": { "type": "boolean", "enum": [true] }, "job_id": { "type": "string" }, "status_url": { "type": "string" }, "status": { "type": "string" } } },
    "meta": { "type": "object", "required": ["timestamp"], "properties": { "timestamp": { "type": "string" }, "app_version": { "type": "string" } } }
  }
}
```

### YieldAlertAlertsResponse

Tier-B — `GET /api/yield-alert/alerts`; alert list rows including LOT dimension.

```json-schema
{
  "type": "object",
  "required": ["success"],
  "properties": {
    "success": { "type": "boolean" },
    "data": {
      "type": "object",
      "properties": {
        "query_id": { "type": "string" },
        "alerts": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "line":        { "type": "string" },
              "type":        { "type": "string" },
              "package":     { "type": ["string", "null"] },
              "tx_qty":      { "type": "integer" },
              "scrap_qty":   { "type": "integer" },
              "yield_pct":   { "type": "number" },
              "alert_level": { "type": "string" },
              "source_code": { "type": ["string", "null"] }
            }
          }
        }
      }
    },
    "meta": {
      "type": "object",
      "required": ["timestamp"],
      "properties": {
        "timestamp":   { "type": "string" },
        "app_version": { "type": "string" }
      }
    }
  }
}
```

### ProductionHistoryJobAccepted

Tier-B — 202 async branch for `POST /api/production-history/query`.

```json-schema
{
  "type": "object",
  "required": ["success", "data", "meta"],
  "properties": {
    "success": { "type": "boolean", "enum": [true] },
    "data": { "type": "object", "required": ["async", "job_id", "status_url"], "properties": { "async": { "type": "boolean", "enum": [true] }, "job_id": { "type": "string" }, "status_url": { "type": "string" }, "status": { "type": "string" } } },
    "meta": { "type": "object", "required": ["timestamp"], "properties": { "timestamp": { "type": "string" }, "app_version": { "type": "string" } } }
  }
}
```

### MaterialTraceJobAccepted

Tier-B — 202 async branch for `POST /api/material-trace/query`.

```json-schema
{
  "type": "object",
  "required": ["success", "data", "meta"],
  "properties": {
    "success": { "type": "boolean", "enum": [true] },
    "data": { "type": "object", "required": ["async", "job_id", "status_url"], "properties": { "async": { "type": "boolean", "enum": [true] }, "job_id": { "type": "string" }, "status_url": { "type": "string" }, "status": { "type": "string" } } },
    "meta": { "type": "object", "required": ["timestamp"], "properties": { "timestamp": { "type": "string" }, "app_version": { "type": "string" } } }
  }
}
```

### TraceJobAccepted

Tier-B — 202 async branch for `POST /api/trace/lineage`.

```json-schema
{
  "type": "object",
  "required": ["success", "data", "meta"],
  "properties": {
    "success": { "type": "boolean", "enum": [true] },
    "data": { "type": "object", "required": ["async", "job_id", "status_url"], "properties": { "async": { "type": "boolean", "enum": [true] }, "job_id": { "type": "string" }, "status_url": { "type": "string" }, "status": { "type": "string" } } },
    "meta": { "type": "object", "required": ["timestamp"], "properties": { "timestamp": { "type": "string" }, "app_version": { "type": "string" } } }
  }
}
```

### MaterialConsumptionJobAccepted

Tier-B — 202 async branch for `POST /api/material-consumption/detail`.

```json-schema
{
  "type": "object",
  "required": ["success", "data", "meta"],
  "properties": {
    "success": { "type": "boolean", "enum": [true] },
    "data": { "type": "object", "required": ["async", "job_id", "status_url"], "properties": { "async": { "type": "boolean", "enum": [true] }, "job_id": { "type": "string" }, "status_url": { "type": "string" }, "status": { "type": "string" } } },
    "meta": { "type": "object", "required": ["timestamp"], "properties": { "timestamp": { "type": "string" }, "app_version": { "type": "string" } } }
  }
}
```

### DowntimeJobAccepted

Tier-B — 202 async branch for `POST /api/downtime-analysis/query`.

```json-schema
{
  "type": "object",
  "required": ["success", "data", "meta"],
  "properties": {
    "success": { "type": "boolean", "enum": [true] },
    "data": { "type": "object", "required": ["async", "job_id", "status_url"], "properties": { "async": { "type": "boolean", "enum": [true] }, "job_id": { "type": "string" }, "status_url": { "type": "string" }, "status": { "type": "string" } } },
    "meta": { "type": "object", "required": ["timestamp"], "properties": { "timestamp": { "type": "string" }, "app_version": { "type": "string" } } }
  }
}
```

### DowntimeQueryResponse

Tier-B — 200 sync branch for `POST /api/downtime-analysis/query`. Shape varies by `DOWNTIME_BROWSER_DUCKDB` flag.

```json-schema
{
  "type": "object",
  "required": ["success"],
  "properties": {
    "success": { "type": "boolean" },
    "error": {},
    "data": {
      "type": "object",
      "properties": {
        "query_id":       { "type": "string" },
        "base_spool_url": { "type": "string" },
        "jobs_spool_url": { "type": "string" },
        "taxonomy":       { "type": "object" },
        "summary":        {},
        "daily_trend":    { "type": "array" },
        "big_category":   { "type": "array" },
        "top_reasons":    { "type": "array" }
      }
    },
    "meta": {
      "type": "object",
      "required": ["timestamp"],
      "properties": {
        "timestamp":   { "type": "string" },
        "app_version": { "type": "string" }
      }
    }
  }
}
```

### AnomalySummaryResponse

Tier-B — `GET /api/analytics/anomaly-summary`; injects `meta.cache_state`.

```json-schema
{
  "type": "object",
  "required": ["success"],
  "properties": {
    "success": { "type": "boolean" },
    "data":    {},
    "error":   {},
    "meta": {
      "type": "object",
      "properties": {
        "timestamp":   { "type": "string" },
        "app_version": { "type": "string" },
        "cache_state": { "type": "string", "enum": ["warm", "cold", "stale"] }
      }
    }
  }
}
```

### AiQueryResponse

Tier-B — `POST /api/ai/query`; NL query result.

```json-schema
{
  "type": "object",
  "required": ["success"],
  "properties": {
    "success": { "type": "boolean" },
    "error": {},
    "data": {
      "type": "object",
      "properties": {
        "answer":              { "type": "string" },
        "chart_data":          {},
        "query_used":          { "type": "string" },
        "params_used":         {},
        "suggestions":         { "type": "array" },
        "sql_used":            { "type": "string" },
        "tool_trace":          {},
        "needs_clarification": { "type": "boolean" }
      }
    },
    "meta": {
      "type": "object",
      "required": ["timestamp"],
      "properties": {
        "timestamp":   { "type": "string" },
        "app_version": { "type": "string" }
      }
    }
  }
}
```

### StandardErrorResponse

Tier-B — every `4xx`/`5xx` error envelope; see `contracts/api/error-format.md ## Schemas` for the canonical block.

```json-schema
{
  "type": "object",
  "required": ["success", "error", "meta"],
  "properties": {
    "success": { "type": "boolean", "enum": [false] },
    "error": { "type": "object", "required": ["code", "message"], "properties": { "code": { "type": "string" }, "message": { "type": "string" }, "details": {} } },
    "meta": { "type": "object", "required": ["timestamp"], "properties": { "timestamp": { "type": "string" }, "app_version": { "type": "string" } } }
  }
}
```

### EapAlarmSpoolJobAccepted
| field | type | required | format | notes |
|---|---|---|---|---|
| async | boolean | yes |  | 202 async branch indicator |
| job_id | string | yes |  | RQ job identifier |
| status_url | string | yes |  | polling URL |
| query_id | string | no |  | spool key |

### QueryToolJobAccepted
| field | type | required | format | notes |
|---|---|---|---|---|
| async | boolean | yes |  | 202 async branch indicator |
| job_id | string | yes |  | RQ job identifier |
| status_url | string | yes |  | polling URL |
| status | string | no |  | job status hint |

### EquipmentPeriodResponse

Tier-B — `POST /api/query-tool/equipment-period`. Sync 200 branch populates
`data.data`/`data.total`/`data.date_range`/`data.pagination`; async 202
branch (wide date range + RQ worker available) populates
`data.async`/`data.job_id`/`data.status_url`/`data.result_url` instead
(mirrors `QueryToolJobAccepted`, plus `result_url`). `data.data[]` row shape
varies by `query_type` (lots/jobs/rejects/status_hours) — see
`contracts/data/data-shape-contract.md` §3.6/§3.7 for the per-`query_type`
column set; left as a generic object here since this citation resolver
cannot express per-array-item fields (see interaction-design.md notes on
Presented Information for `query-tool-subtab-cache`/
`fix-equipment-lots-trim`, which cite `data.data` itself, not row columns).

```json-schema
{
  "type": "object",
  "properties": {
    "success": {"type": "boolean"},
    "data": {
      "type": "object",
      "properties": {
        "data": {"type": "array", "items": {"type": "object"}},
        "total": {"type": "integer"},
        "date_range": {
          "type": ["object", "null"],
          "properties": {
            "start": {"type": "string"},
            "end": {"type": "string"}
          }
        },
        "pagination": {
          "type": "object",
          "properties": {
            "page": {"type": "integer"},
            "per_page": {"type": "integer"},
            "total": {"type": "integer"},
            "total_pages": {"type": "integer"}
          }
        },
        "async": {"type": "boolean"},
        "job_id": {"type": "string"},
        "status_url": {"type": "string"},
        "result_url": {"type": "string"}
      }
    },
    "error": {},
    "meta": {"type": "object"}
  },
  "required": ["success"]
}
```

### LotEquipmentLookupResponse

Tier-B — `POST /api/query-tool/lot-equipment-lookup`. `date_range` is
`null` when no records matched (`not_found_hint` populated instead, and
`trace_map` may hold parent-lot trace results).

```json-schema
{
  "type": "object",
  "properties": {
    "success": {"type": "boolean"},
    "data": {
      "type": "object",
      "properties": {
        "equipment_ids": {"type": "array", "items": {"type": "string"}},
        "equipment_names": {"type": "array", "items": {"type": "string"}},
        "date_range": {
          "type": ["object", "null"],
          "properties": {
            "start": {"type": "string"},
            "end": {"type": "string"}
          }
        },
        "trace_map": {"type": "object"},
        "lot_names": {"type": "array", "items": {"type": "string"}},
        "not_found_hint": {"type": "string"}
      }
    },
    "error": {},
    "meta": {"type": "object"}
  },
  "required": ["success"]
}
```

### WipDetailJobAccepted
| field | type | required | format | notes |
|---|---|---|---|---|
| async | boolean | yes |  | 202 async branch indicator |
| job_id | string | yes |  | RQ job identifier |
| status_url | string | yes |  | polling URL; prefix=wip-detail |

### AdminPagesResponse

Tier-B — slim page-status list returned by `GET /admin/api/pages`.

```json-schema
{
  "type": "object",
  "properties": {
    "success": {"type": "boolean"},
    "data": {
      "type": "object",
      "properties": {
        "pages": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "route":  {"type": "string"},
              "status": {"type": "string", "enum": ["released", "dev"]}
            },
            "required": ["route", "status"]
          }
        }
      },
      "required": ["pages"]
    },
    "meta": {"type": "object"}
  },
  "required": ["success", "data"]
}
```

### PortalNavigationResponse

Tier-B — status feed returned by `GET /api/portal/navigation` (no drawers; structure lives in the frontend manifest).

```json-schema
{
  "type": "object",
  "properties": {
    "statuses": {
      "type": "object",
      "additionalProperties": {"type": "string", "enum": ["released", "dev"]},
      "description": "Map of route → status; absent route defaults to released"
    },
    "is_admin":    {"type": "boolean"},
    "admin_user":  {"oneOf": [{"type": "object"}, {"type": "null"}]},
    "admin_links": {"type": "object"},
    "features":    {"type": "object"},
    "diagnostics": {"type": "object"}
  },
  "required": ["statuses", "is_admin", "admin_links", "features", "diagnostics"]
}
```

### DbSchedulingQueueResponse

Tier-B — response for `GET /api/db-scheduling/queue`. Array of lot-equipment recommendation rows, each representing one equipment option for a D/B-START lot. One lot can have multiple rows (one per equipment).

```json-schema
{
  "type": "object",
  "required": ["success", "data"],
  "properties": {
    "success": {"type": "boolean"},
    "data": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["lotId", "workflowName", "qty", "targetSpec", "equipment", "matchSource"],
        "properties": {
          "lotId": {"type": "string"},
          "workflowName": {"type": "string"},
          "packageLef": {"type": "string"},
          "pjType": {"type": "string"},
          "waferLot": {"type": "string"},
          "uts": {"type": "string", "description": "date string YYYY/MM/DD"},
          "qty": {"type": "integer"},
          "bop": {"type": "string"},
          "eqpPackageLef": {"type": "string", "description": "running lot Package LEF on equipment (priority-column key, primary)"},
          "eqpPjType": {"type": "string", "description": "running lot PJ Type on equipment (priority-column key, secondary)"},
          "eqpWaferLot": {"type": "string", "description": "running lot Wafer Lot on equipment (priority-column key, tertiary)"},
          "eqpUts": {"type": "string", "description": "running lot UTS on equipment (priority-column key, quaternary)"},
          "targetSpec": {"type": "string", "description": "DB process SPEC name"},
          "equipment": {"type": "string", "description": "single equipment ID; one row per equipment"},
          "matchSource": {"type": "string", "enum": ["workflow", "bop-fallback", "none"]}
        }
      }
    },
    "meta": {"type": "object"}
  }
}
```

### EquipmentDetailResponse
| field | type | required | format | notes |
|---|---|---|---|---|
| success | boolean | yes |  |  |
| equipment | string | yes |  | equipment ID |
| e10Status | string | no |  | E10 asset status code (PRD/SBY/UDT/SDT/NST) |
| e10Reason | string | no |  | E10 status reason code |
| jobOrder | string | no |  | maintenance job order number |
| jobModel | string | no |  | maintenance job model |
| jobStage | string | no |  | maintenance job stage |
| jobId | string | no |  | maintenance job ID |
| jobStatus | string | no |  | maintenance job status |
| lotId | string | no |  | running lot ID on the equipment |
| workorder | string | no |  | running lot work order |
| wipStatus | string | no |  | WIP status (Active/Hold) |
| runcardStatus | string | no |  | runcard status |
| qty | integer | no |  | lot quantity (pcs) |
| waferLotQty | integer | no |  | wafer lot quantity |
| ageByDays | number | no |  | lot age in days |
| priorityCodeName | string | no |  | work order priority code name |
| productName | string | no |  | product P/N (PRODUCT column) |
| package | string | no |  | package type (PRODUCTLINENAME) |
| packageLef | string | no |  | Package+LeadFrame (PACKAGE_LEF) |
| pjType | string | no |  | PJ TYPE classification |
| pjFunction | string | no |  | PJ FUNCTION classification |
| bop | string | no |  | Bill of Process |
| dateCodeReq | string | no |  | date code requirement (DATECODE) |
| produceRegion | string | no |  | produce region (PJ_PRODUCEREGION) |
| specName | string | no |  | spec name |
| workflowName | string | no |  | workflow name |

### ProductionAchievementReportRow
| field | type | required |
|---|---|---|
| output_date | string | yes |
| shift_code | string | yes |
| workcenter_group | string | yes |
| actual_output_qty | integer | yes |
| target_qty | integer | yes |
| achievement_rate | number | yes |

See data-shape-contract.md §3.25 for field semantics (nullable `target_qty`/`achievement_rate`, PA-01..PA-07 business rules). **As of `production-achievement-async-spool`, this row shape is no longer the server response** — it is (a) the shape the frontend computes client-side in DuckDB-WASM from the §3.28 spool + maps, and (b) the test-only golden-reference shape from `build_achievement_rows()` for the dual-tier parity gate.

### ProductionAchievementReportResponse

Tier-B — `GET /api/production-achievement/report`. Redefined by `production-achievement-async-spool`, extended in place by `production-achievement-overhaul` (2-array → 5-array spool-hit envelope), and revised again in place by `production-achievement-oracle-plan-source` (`daily_plan_map` → `plan_map`, Oracle-sourced date-indexed shape replacing the old static per-workcenter shape; `workcenter_merge_map` entries gain `parent_group`/`plan_source_side` — see data-shape-contract.md §3.28/§3.34). Describes the HTTP 200 spool-hit shape only; the HTTP 202 spool-miss shape is `ProductionAchievementJobAccepted`. Only `success` is required (matching `ProductionAchievementPermissionsResponse`'s pattern) — contract error codes 400/500/503 mean an error-envelope capture (`success:false`, no `data`) is a valid sample.

```json-schema
{
  "type": "object",
  "required": ["success"],
  "properties": {
    "success": { "type": "boolean" },
    "data": {
      "type": ["object", "null"],
      "properties": {
        "query_id": { "type": "string" },
        "spool_download_url": { "type": "string" },
        "spec_workcenter_map": {
          "type": "array",
          "items": {
            "type": "object",
            "required": ["SPECNAME", "workcenter_group"],
            "properties": {
              "SPECNAME": { "type": "string" },
              "workcenter_group": { "type": "string" }
            }
          }
        },
        "targets_map": {
          "type": "array",
          "items": {
            "type": "object",
            "required": ["shift_code", "workcenter_group", "target_qty"],
            "properties": {
              "shift_code": { "type": "string" },
              "workcenter_group": { "type": "string" },
              "target_qty": { "type": ["integer", "null"] }
            }
          }
        },
        "package_lf_map": {
          "type": "array",
          "items": {
            "type": "object",
            "required": ["raw_package_lf", "merged_group"],
            "properties": {
              "raw_package_lf": { "type": "string" },
              "merged_group": { "type": "string" }
            }
          }
        },
        "workcenter_merge_map": {
          "type": "array",
          "items": {
            "type": "object",
            "required": ["raw_workcenter_group", "merged_workcenter_group", "parent_group", "plan_source_side"],
            "properties": {
              "raw_workcenter_group": { "type": "string" },
              "merged_workcenter_group": { "type": "string" },
              "parent_group": { "type": "string" },
              "plan_source_side": { "type": "string", "enum": ["input", "output"] }
            }
          }
        },
        "plan_map": {
          "type": "array",
          "items": {
            "type": "object",
            "required": ["output_date", "plan_package_group", "planqty_input", "planqty_output"],
            "properties": {
              "output_date": { "type": "string" },
              "plan_package_group": { "type": "string" },
              "planqty_input": { "type": "integer" },
              "planqty_output": { "type": "integer" }
            }
          }
        }
      }
    },
    "error": {},
    "meta": {
      "type": "object",
      "properties": {
        "timestamp":   { "type": "string" },
        "app_version": { "type": "string" }
      }
    }
  }
}
```

### ProductionAchievementReportMetaResponse

Tier-C — `GET /api/production-achievement/report/meta`. Cheap freshness-only probe added by `production-achievement-metadata-gated-refresh`: reads the same Redis spool metadata pointer `GET /report`'s spool-hit branch uses for `sync_time`/`latest_data_timestamp`, but skips `get_targets_map()`/`get_workcenter_merge_entries()` (uncached MySQL round-trips) and `get_oracle_plan_rows()` (Oracle-backed) entirely — safe for frequent polling. Always HTTP 200; a spool miss returns `sync_time`/`latest_data_timestamp` as `null` (never 202/503 — this endpoint never enqueues a background job). 400 on missing/invalid `start_date`/`end_date` (same `_validate_date_range` as `GET /report`).

```json-schema
{
  "type": "object",
  "required": ["success"],
  "properties": {
    "success": { "type": "boolean" },
    "data": {
      "type": ["object", "null"],
      "properties": {
        "query_id": { "type": "string" },
        "source": { "type": "string", "enum": ["output", "moveout"] },
        "sync_time": { "type": ["integer", "null"] },
        "latest_data_timestamp": { "type": ["string", "null"] }
      }
    },
    "error": {},
    "meta": {
      "type": "object",
      "properties": {
        "timestamp":   { "type": "string" },
        "app_version": { "type": "string" }
      }
    }
  }
}
```

### ProductionAchievementJobAccepted

Tier-B — 202 async branch for `GET /api/production-achievement/report` (spool miss). `always_async=True`; worker unavailable → HTTP 503 (no sync fallback) rather than this shape.

```json-schema
{
  "type": "object",
  "required": ["success", "data", "meta"],
  "properties": {
    "success": { "type": "boolean", "enum": [true] },
    "data": { "type": "object", "required": ["async", "job_id", "status_url"], "properties": { "async": { "type": "boolean", "enum": [true] }, "job_id": { "type": "string" }, "status_url": { "type": "string" } } },
    "meta": { "type": "object", "required": ["timestamp"], "properties": { "timestamp": { "type": "string" }, "app_version": { "type": "string" } } }
  }
}
```

### ProductionAchievementTargetRow
| field | type | required |
|---|---|---|
| shift_code | string | yes |
| workcenter_group | string | yes |
| target_qty | integer | yes |
| updated_at | string | yes |
| updated_by | string | yes |

See data-shape-contract.md §3.26 for field semantics.

### ProductionAchievementTargetsResponse

Row shape per `ProductionAchievementTargetRow` above (`data` is an array of that row shape).

```json-schema
{
  "type": "object",
  "required": ["success", "data"],
  "properties": {
    "success": { "type": "boolean" },
    "data":    { "type": "array" },
    "meta": {
      "type": "object",
      "properties": {
        "timestamp":   { "type": "string" },
        "app_version": { "type": "string" }
      }
    }
  }
}
```

### ProductionAchievementPermissionRow
| field | type | required |
|---|---|---|
| user_identifier | string | yes |
| can_edit_targets | boolean | yes |
| granted_at | string | yes |
| granted_by | string | yes |

See data-shape-contract.md §3.27 for field semantics.

### ProductionAchievementPermissionsResponse

Tier-B — `GET /admin/api/production-achievement/permissions`; row shape per `ProductionAchievementPermissionRow` above. Contract error codes `403/500/503` mean an error-envelope capture (`success:false`, no `data`) is a valid sample — only `success` is required, matching `AnomalySummaryResponse`'s pattern (this endpoint returns 503 when `MYSQL_OPS_ENABLED=false`, per design.md's per-endpoint MySQL-failure behavior).

```json-schema
{
  "type": "object",
  "required": ["success"],
  "properties": {
    "success": { "type": "boolean" },
    "data":    {},
    "error":   {},
    "meta": {
      "type": "object",
      "properties": {
        "timestamp":   { "type": "string" },
        "app_version": { "type": "string" }
      }
    }
  }
}
```

### MsdContainerFilterOptionsResponse

Tier-B — cross-filter cached options returned by `GET /api/mid-section-defect/container-filter-options` (data-shape §2.13). Reuses `container_filter_cache`; no Oracle at request time. 400 on malformed `selected` JSON; 500 on Oracle build error.

```json-schema
{
  "type": "object",
  "required": ["success", "data"],
  "properties": {
    "success": {"type": "boolean"},
    "data": {
      "type": "object",
      "required": ["pj_types", "packages", "bops", "pj_functions"],
      "properties": {
        "pj_types":     {"type": "array", "items": {"type": "string"}},
        "packages":     {"type": "array", "items": {"type": "string"}},
        "bops":         {"type": "array", "items": {"type": "string"}},
        "pj_functions": {"type": "array", "items": {"type": "string"}}
      }
    },
    "meta": {"type": "object"}
  }
}
```

### MsdForwardAnalysisResponse

Tier-B — response for `GET /api/mid-section-defect/analysis?direction=forward`. Extends the generic analysis response with forward cause-effect aggregation fields.

```json-schema
{
  "type": "object",
  "required": ["success", "data"],
  "properties": {
    "success": {"type": "boolean"},
    "data": {
      "type": "object",
      "required": ["kpi", "charts", "daily_trend", "available_loss_reasons", "genealogy_status"],
      "properties": {
        "kpi": {"type": "object"},
        "charts": {"type": "object"},
        "daily_trend": {"type": "array"},
        "available_loss_reasons": {"type": "array", "items": {"type": "string"}},
        "genealogy_status": {"type": "string"},
        "trace_query_id": {"type": ["string", "null"]},
        "detail_total_count": {"type": "integer"},
        "by_detection_loss_reason": {
          "type": "array",
          "items": {
            "type": "object",
            "required": ["loss_reason", "reject_qty", "reject_rate"],
            "properties": {
              "loss_reason": {"type": "string"},
              "reject_qty": {"type": "integer"},
              "reject_rate": {"type": "number", "minimum": 0, "maximum": 1}
            }
          }
        },
        "loss_reason_workcenter_crosstab": {
          "type": "object",
          "properties": {
            "loss_reasons": {"type": "array", "items": {"type": "string"}},
            "workcenter_groups": {"type": "array", "items": {"type": "string"}},
            "cells": {
              "type": "array",
              "items": {
                "type": "object",
                "required": ["loss_reason", "workcenter_group", "reject_qty", "reject_rate"],
                "properties": {
                  "loss_reason": {"type": "string"},
                  "workcenter_group": {"type": "string"},
                  "reject_qty": {"type": "integer"},
                  "reject_rate": {"type": "number", "minimum": 0}
                }
              }
            }
          }
        },
        "downstream_trend": {
          "type": "array",
          "items": {
            "type": "object",
            "required": ["date", "reject_qty", "reject_rate"],
            "properties": {
              "date": {"type": "string", "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$"},
              "reject_qty": {"type": "integer"},
              "reject_rate": {"type": "number", "minimum": 0}
            }
          }
        },
        "amplification": {
          "type": ["number", "null"],
          "description": "downstream_reject_rate / detection_reject_rate. null when detection_rate=0 (display dash); 0.0 when downstream=0 and detection>0."
        }
      }
    },
    "meta": {"type": "object"}
  }
}
```

### MsdForwardDetailResponse

Tier-B — response for `GET /api/mid-section-defect/analysis/detail?direction=forward`. Detail rows gain `detection_loss_reason` (primary detection loss reason for the lot; null if no rejects).

```json-schema
{
  "type": "object",
  "required": ["success", "data"],
  "properties": {
    "success": {"type": "boolean"},
    "data": {
      "type": "object",
      "required": ["detail", "pagination"],
      "properties": {
        "detail": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "CONTAINERNAME": {"type": "string"},
              "PJ_TYPE": {"type": "string"},
              "PRODUCTLINENAME": {"type": "string"},
              "WORKFLOW": {"type": "string"},
              "DETECTION_EQUIPMENTNAME": {"type": "string"},
              "INPUT_QTY": {"type": "integer"},
              "DEFECT_QTY": {"type": "integer"},
              "DOWNSTREAM_STATIONS": {"type": "integer"},
              "DOWNSTREAM_REJECTS": {"type": "integer"},
              "DOWNSTREAM_REJECT_RATE": {"type": "number"},
              "WORST_DOWNSTREAM": {"type": "string"},
              "DETECTION_LOSS_REASON": {"type": ["string", "null"]}
            }
          }
        },
        "pagination": {"type": "object"},
        "trace_query_id": {"type": ["string", "null"]}
      }
    },
    "meta": {"type": "object"}
  }
}
```

### EapAlarmProductFilterOptionsResponse
| field | type | required | format | notes |
|---|---|---|---|---|
| pj_types | string[] | yes | List of PJ_TYPE values from container_filter_cache |  |
| product_lines | string[] | yes | List of PRODUCTLINENAME values (mapped from packages in cache) |  |
| pj_bops | string[] | yes | List of PJ_BOP values (mapped from bops in cache) |  |
| updated_at | string | no | ISO-8601 cache refresh timestamp; null if cache never populated |  |

### UphPerformanceSpoolJobAccepted
| field | type | required | format | notes |
|---|---|---|---|---|
| async | boolean | yes |  | false on spool-hit, true on spool-miss |
| query_id | string | yes |  | canonical coarse-filter spool key |
| job_id | string | no |  | present only when async=true; RQ job identifier |
| status_url | string | no |  | present only when async=true; polling URL |

### UphPerformanceSpoolStatusResponse
| field | type | required | format | notes |
|---|---|---|---|---|
| query_id | string | no |  | spool key, present when known |
| status | enum(queued,running,finished,failed) | yes |  | async job status, or a plain spool-hit indicator when the key was already resolved |

### UphPerformanceFilterOptionsResponse
| field | type | required | format | notes |
|---|---|---|---|---|
| equipment_id_options | string[] | yes |  | distinct EQUIPMENT_ID values present in the built spool |
| workcenter_name_options | string[] | yes |  | distinct WORKCENTERNAME values present in the built spool |
| package_options | string[] | yes |  | distinct PRODUCTLINENAME (Package) values present in the built spool |
| pj_type_options | string[] | yes |  | distinct PJ_TYPE (Type) values present in the built spool |
| die_count_options | string[] | yes |  | distinct DIE_COUNT (MES_PRODUCT.NUMBEROFROWS) values present in the built spool |
| wire_count_options | string[] | yes |  | distinct WIRE_COUNT (MES_PRODUCT.NUMBEROFCOLS) values present in the built spool |

### UphPerformanceProductFilterOptionsResponse
| field | type | required | format | notes |
|---|---|---|---|---|
| pj_types | string[] | yes |  | Oracle-free Type options from container_filter_cache, available before any query runs |
| product_lines | string[] | yes |  | Oracle-free Package options from container_filter_cache, available before any query runs |

### UphPerformanceTrendSeriesItem
| field | type | required | format | notes |
|---|---|---|---|---|
| name | string | yes |  | group label — equipment_id, family (DB/WB category), model (機型), or package value depending on group_by |
| data | number[] | yes |  | one value per label bucket; null entries mean a missing hour, never a zero |

### UphPerformanceRankingItem
| field | type | required | format | notes |
|---|---|---|---|---|
| equipment_id | string | yes |  |  |
| avg_uph | number | no |  | null when zero rows carry a non-null UPH_VALUE for this equipment |
| sample_count | integer | yes |  |  |

### UphPerformanceDetailRow
| field | type | required | format | notes |
|---|---|---|---|---|
| lot_id | string | yes |  |  |
| equipment_id | string | yes |  |  |
| model | string | no |  | machine model (RESOURCEFAMILYNAME); null when equipment has no DW_MES_RESOURCE match |
| uph_value | number | no |  | raw PARAMETER_VALUE, no scale conversion (UPH-04) |

### UphPerformanceTrendResponse
| field | type | required | format | notes |
|---|---|---|---|---|
| labels | string[] | yes |  | hourly time-bucket labels (native M[60] granularity) |
| series | UphPerformanceTrendSeriesItem[] | yes |  | see data-shape-contract.md §3.29 Trend for the full per-item shape |
| group_by | string | yes |  | closed enum: equipment_id, family, model, package, die_count, or wire_count (default family) |

### UphPerformanceRankingResponse
| field | type | required | format | notes |
|---|---|---|---|---|
| items | UphPerformanceRankingItem[] | yes |  | ranked ascending by avg_uph; see data-shape-contract.md §3.29 Ranking for the full per-row shape |
| pj_types | string[] | yes |  | available Type values for this block's own independent filter |

### UphPerformanceDetailMeta
| field | type | required | format | notes |
|---|---|---|---|---|
| page | integer | yes |  |  |
| per_page | integer | yes |  | default 50, contract cap 200 |
| total_count | integer | yes |  |  |
| total_pages | integer | yes |  |  |

### UphPerformanceDetailResponse
| field | type | required | format | notes |
|---|---|---|---|---|
| rows | UphPerformanceDetailRow[] | yes |  | see data-shape-contract.md §3.29 Detail for the full per-row shape |
| meta | UphPerformanceDetailMeta | yes |  | pagination |

### ProductionAchievementPackageLfMapRow
| field | type | required | format | notes |
|---|---|---|---|---|
| raw_package_lf | string | yes |  |  |
| merged_group | string | yes |  |  |
| updated_at | string | yes |  |  |
| updated_by | string | yes |  |  |

### ProductionAchievementWorkcenterMergeMapRow
| field | type | required | format | notes |
|---|---|---|---|---|
| raw_workcenter_group | string | yes |  |  |
| merged_workcenter_group | string | yes |  |  |
| parent_group | string | yes |  |  |
| plan_source_side | string | yes |  |  |
| updated_at | string | yes |  |  |
| updated_by | string | yes |  |  |

### ProductionAchievementKnownPackageLfValuesResponse
| field | type | required | format | notes |
|---|---|---|---|---|
| success | boolean | yes |  |  |
| data | ProductionAchievementKnownPackageLfValuesData | yes |  |  |
| meta | ProductionAchievementResponseMeta | no |  |  |

### ProductionAchievementSpecWorkcenterMapRow
| field | type | required | format | notes |
|---|---|---|---|---|
| SPECNAME | string | yes |  |  |
| workcenter_group | string | yes |  |  |

### ProductionAchievementTargetsMapEntry
| field | type | required | format | notes |
|---|---|---|---|---|
| shift_code | string | yes |  |  |
| workcenter_group | string | yes |  |  |
| target_qty | integer | yes |  |  |

### ProductionAchievementPackageLfMapEntry
| field | type | required | format | notes |
|---|---|---|---|---|
| raw_package_lf | string | yes |  |  |
| merged_group | string | yes |  |  |

### ProductionAchievementWorkcenterMergeMapEntry
| field | type | required | format | notes |
|---|---|---|---|---|
| raw_workcenter_group | string | yes |  |  |
| merged_workcenter_group | string | yes |  |  |
| parent_group | string | yes |  |  |
| plan_source_side | string | yes |  |  |

### ProductionAchievementKnownWorkcenterGroupsResponse
| field | type | required | format | notes |
|---|---|---|---|---|
| success | boolean | yes |  |  |
| data | ProductionAchievementKnownWorkcenterGroupsData | yes |  |  |
| meta | ProductionAchievementResponseMeta | no |  |  |

### ProductionAchievementPackageLfMapResponse
| field | type | required | format | notes |
|---|---|---|---|---|
| success | boolean | yes |  |  |
| data | ProductionAchievementPackageLfMapRow[] | yes |  |  |
| meta | ProductionAchievementResponseMeta | no |  |  |

### ProductionAchievementWorkcenterMergeMapResponse
| field | type | required | format | notes |
|---|---|---|---|---|
| success | boolean | yes |  |  |
| data | ProductionAchievementWorkcenterMergeMapRow[] | yes |  |  |
| meta | ProductionAchievementResponseMeta | no |  |  |

### ProductionAchievementKnownPackageLfValuesData
| field | type | required | format | notes |
|---|---|---|---|---|
| package_lf_values | string[] | yes |  |  |

### ProductionAchievementKnownWorkcenterGroupsData
| field | type | required | format | notes |
|---|---|---|---|---|
| raw_workcenter_groups | string[] | yes |  |  |

### ProductionAchievementResponseMeta
| field | type | required | format | notes |
|---|---|---|---|---|
| timestamp | string | no |  |  |
| app_version | string | no |  |  |

### ProductionAchievementOwnPermissionResponse
| field | type | required | format | notes |
|---|---|---|---|---|
| success | boolean | yes |  |  |
| data | ProductionAchievementOwnPermissionData | yes |  |  |
| meta | ProductionAchievementResponseMeta | no |  |  |

### ProductionAchievementOwnPermissionData
| field | type | required | format | notes |
|---|---|---|---|---|
| can_edit_targets | boolean | yes |  | Whether the current session user is whitelisted to edit production-achievement targets/settings. |

### ProductionAchievementPlanMapEntry
| field | type | required | format | notes |
|---|---|---|---|---|
| output_date | string | yes |  |  |
| plan_package_group | string | yes |  |  |
| planqty_input | integer | yes |  |  |
| planqty_output | integer | yes |  |  |

### UphPerformanceMachineFamily
| field | type | required | format | notes |
|---|---|---|---|---|
| code | string | yes |  | GDBA or GWBA |
| label | string | yes |  | Die-Bond or Wire-Bond |

### UphPerformanceMachineModel
| field | type | required | format | notes |
|---|---|---|---|---|
| family | string | yes |  | GDBA/GWBA the model belongs to |
| model | string | yes |  | RESOURCEFAMILYNAME (e.g. DBA_AD832UR) — the real 機型 |

### UphPerformanceMachineEquipment
| field | type | required | format | notes |
|---|---|---|---|---|
| equipment_id | string | yes |  | RESOURCENAME (e.g. GDBA-0131) |
| family | string | yes |  | GDBA/GWBA |
| model | string | no |  | RESOURCEFAMILYNAME; null when unmapped |
| workcenter | string | no |  | WORKCENTERNAME; null when unmapped |

### UphPerformanceMachineOptionsResponse
| field | type | required | format | notes |
|---|---|---|---|---|
| families | UphPerformanceMachineFamily[] | yes |  | DB/WB category options |
| models | UphPerformanceMachineModel[] | yes |  | cascade source (family→model) |
| workcenters | string[] | yes |  | distinct WORKCENTERNAME (工作站) |
| equipment | UphPerformanceMachineEquipment[] | yes |  | full per-equipment map for client-side cascade |

### EquipmentLookupOptionsResponse
| field | type | required | format | notes |
|---|---|---|---|---|
| locations | string[] | yes |  | Distinct LOCATIONNAME (機台位置) values; full universe, no cross-filter narrowing |
| families | string[] | yes |  | Distinct RESOURCEFAMILYNAME (機型) values; full universe, no cross-filter narrowing |
| resource_names | string[] | yes |  | Distinct RESOURCENAME (編號) values; full universe, no cross-filter narrowing |

### EquipmentLookupListResponse
| field | type | required | format | notes |
|---|---|---|---|---|
| rows | EquipmentLookupRow[] | yes |  | Filtered/sorted/paginated equipment rows |
| pagination | EquipmentLookupPagination | yes |  |  |

### EquipmentLookupRow
| field | type | required | format | notes |
|---|---|---|---|---|
| RESOURCENAME | string | no |  | 編號 |
| LOCATIONNAME | string | no |  | 機台位置 |
| RESOURCEFAMILYNAME | string | no |  | 機型 |
| VENDORNAME | string | no |  | display-only |
| VENDORMODEL | string | no |  | display-only |
| WORKCENTERNAME | string | no |  | display-only |

### EquipmentLookupPagination
| field | type | required | format | notes |
|---|---|---|---|---|
| page | integer | yes |  | 1-based current page |
| page_size | integer | yes |  | rows per page (max 10000) |
| total | integer | yes |  | total matching rows across all pages |
| total_pages | integer | yes |  | max(1, ceil(total / page_size)) |
