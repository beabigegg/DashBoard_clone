## ADDED Requirements

### Requirement: Async query job service supports production-history consumer
The `async_query_job_service` SHALL be used by `production_history_job_service` as a consumer without any code changes to the core module. The `enqueue_job` function already accepts arbitrary `queue_name`, `worker_fn`, and `kwargs`.

#### Scenario: Production history job enqueues via shared service
- **WHEN** `production_history_job_service.enqueue_production_history_query()` is called
- **THEN** it SHALL delegate to `async_query_job_service.enqueue_job()` with `queue_name="production-history-query"`

### Requirement: Async query job service supports yield-alert consumer
The `async_query_job_service` SHALL be used by `yield_alert_job_service` as a consumer without any code changes to the core module.

#### Scenario: Yield alert job enqueues via shared service
- **WHEN** `yield_alert_job_service.enqueue_yield_alert_query()` is called
- **THEN** it SHALL delegate to `async_query_job_service.enqueue_job()` with `queue_name="yield-alert-query"`

### Requirement: RQ monitor includes all active queues
The `rq_monitor_service` `_QUEUE_NAMES` list SHALL include all 5 active queue names: `trace-events`, `reject-query`, `msd-analysis`, `production-history-query`, `yield-alert-query`. The existing list is missing `msd-analysis` — this change SHALL fix that omission alongside adding the two new queues.

#### Scenario: All queues appear in monitored queue list
- **WHEN** the RQ monitor scans active queues
- **THEN** `trace-events`, `reject-query`, `msd-analysis`, `production-history-query`, and `yield-alert-query` SHALL all be included in the monitored set

#### Scenario: Admin dashboard displays new workers and queues
- **WHEN** the admin dashboard WorkerTab loads RQ status
- **THEN** the new workers and queues SHALL appear in the Workers table and Queue list (WorkerTab renders dynamically from API data, no frontend code change needed)
