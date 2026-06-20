# Change Request

## Original Request

Proposal B+C: wip-rq-worker-and-merge-chunks-cleanup

Implement `execute_wip_detail_job` RQ worker and register the "wip-detail" job type so that WIP detail queries above L3 threshold are routed to RQ async path and complete successfully (currently `enqueue_job_dynamic("wip-detail")` returns `(None, "Unknown job type")` and always falls through to synchronous path).

Additionally, remove `merge_chunks` dead code entirely — it has zero callers since the previous change that fully removed the old chunked path. No dual-path E2E needed since the old path is completely gone.

Success criterion:
- WIP detail queries above L3 return 202, job completes, results retrievable by frontend
- WIP detail queries below L3 continue using the sync path unchanged
- `merge_chunks` function is fully deleted with no callers remaining (`grep merge_chunks` → no hits)

## Business / User Goal

## Non-goals

## Constraints

## Known Context

## Open Questions

## Requested Delivery Date / Priority
