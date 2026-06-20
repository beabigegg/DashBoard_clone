# Change Request

## Original Request

Wire acquire_heavy_query_slot() into all four execute_*_job RQ workers
(execute_query_tool_job, execute_hold_query_job, execute_resource_query_job,
execute_reject_query_job) so concurrent RQ workers cannot exceed MAX_CONCURRENT (3)
simultaneous Oracle connections. Under N=8 concurrent dispatched workers, peak
simultaneous Oracle-phase executions must be ≤ MAX_CONCURRENT; all N jobs complete
without deadlock or slot leak; flag-off paths and existing job output, error
handling, progress_callback behavior must be identical.

## Business / User Goal

## Non-goals

## Constraints

## Known Context

## Open Questions

## Requested Delivery Date / Priority
