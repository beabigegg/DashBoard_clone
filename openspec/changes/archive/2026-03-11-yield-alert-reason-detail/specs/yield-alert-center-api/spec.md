## ADDED Requirements

### Requirement: Yield Alert Center API SHALL expose a reason-detail endpoint
The API SHALL provide `GET /api/yield-alert/reason-detail` as a direct-query endpoint that does not depend on an existing `query_id` or dataset cache.

#### Scenario: Endpoint availability
- **WHEN** the yield alert feature flag is enabled
- **THEN** `GET /api/yield-alert/reason-detail` SHALL be accessible and rate-limited by `_QUERY_RATE_LIMIT`
- **WHEN** the yield alert feature flag is disabled
- **THEN** the endpoint SHALL return HTTP 404 with `{ success: false, error: "yield_alert_disabled" }`

#### Scenario: Delegated query execution
- **WHEN** the endpoint receives valid `workorder` and `date_bucket` parameters
- **THEN** it SHALL delegate to `query_reason_detail(workorder=..., date_bucket=...)` in `yield_alert_service.py`
- **THEN** it SHALL return the result as `{ success: true, data: { items: [...], workorder: "...", date_bucket: "..." } }`

## REMOVED Requirements

### Requirement: Yield Alert Center API drilldown-context endpoint is the primary drill path
**Reason**: 「查看追溯」跳轉行為被 inline reason-detail 取代，drilldown-context 不再是使用者互動的主要入口。
**Migration**: 前端改呼叫 `GET /api/yield-alert/reason-detail`；`/api/yield-alert/drilldown-context` endpoint 仍保留在後端（不刪除）供未來使用，但前端不再觸發。
