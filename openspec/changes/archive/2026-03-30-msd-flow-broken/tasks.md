## 1. Frontend Fix

- [x] 1.1 Add `trace_query_id` to `buildDetailParams()` in `frontend/src/mid-section-defect/App.vue` — include `currentTraceQueryId.value` when non-null, matching the existing `exportCsv()` pattern at line 503

## 2. Verification

- [x] 2.1 Verify the detail endpoint returns data (not 410) when `trace_query_id` is passed with a valid spool
