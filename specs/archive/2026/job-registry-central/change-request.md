# Change Request

## Original Request

Job Registry 中央化：新增 job_registry.py（JobTypeConfig dataclass + _REGISTRY dict + register/get/list functions）、在 async_query_job_service.py 加入 enqueue_job_dynamic() dispatcher、並在現有 8 個 job service 末端加上宣告式 register_job_type()。不改路由 dispatch 邏輯，完全向後相容。驗收：test_job_registry.py 5 個測試全通過、test_async_query_job_service.py 無 regression、cdd-kit validate 通過。

Context: Phase 2 of docs/dynamic-rq-migration-plan.md. Phase 1 (AsyncQueryProgress UI) is complete and merged.

## Business / User Goal

## Non-goals

## Constraints

## Known Context

## Open Questions

## Requested Delivery Date / Priority
