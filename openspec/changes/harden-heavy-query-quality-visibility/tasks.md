## 1. Query-tool Completeness Contract Parity

- [x] 1.1 Update query-tool single-item detail service functions (`history/materials/rejects/holds`) to return `quality_meta` from EventFetcher payloads.
- [x] 1.2 Keep batch detail payload schema unchanged and align single-item payload keys to match batch semantics.
- [x] 1.3 Verify route handlers continue to use existing `success_response`/`validation_error` contracts while exposing the new metadata fields.

## 2. Query-tool UI Non-Complete Warning Parity

- [x] 2.1 Update LOT detail composable/state mapping so single-item and batch-item modes both store active sub-tab `quality_meta`.
- [x] 2.2 Ensure warning rendering logic in LOT detail component is driven by `quality_meta.status` for all paged sub-tabs.
- [x] 2.3 Ensure warning clears when refreshed payload status returns to `complete`.

## 3. MSD Staged Completeness Visibility

- [x] 3.1 Wire MSD page warning state to staged events aggregation `quality_meta` and show explicit warning for `partial`/`truncated`/`failed`.
- [x] 3.2 Keep genealogy warning behavior and render completeness warning independently when both conditions are present.
- [x] 3.3 Document and enforce active UI reliance on staged trace completeness semantics while keeping legacy analysis endpoints compatibility-only.

## 4. Fallback and Replay Completeness Preservation

- [x] 4.1 Audit normalization/replay paths for trace events and query-tool detail payload shaping to ensure non-complete statuses are not dropped.
- [x] 4.2 Add guard assertions/logging where metadata could be silently downgraded during fallback/cache-hit handling.
- [x] 4.3 Validate that runtime fallback paths preserve equivalent completeness semantics versus preferred runtime paths.

## 5. Regression Test Coverage

- [x] 5.1 Add backend tests for query-tool single vs batch completeness parity (`quality_meta` presence and status equivalence).
- [x] 5.2 Extend frontend query-tool composable tests to cover single-item non-complete warning visibility.
- [x] 5.3 Add MSD frontend tests for staged completeness warning rendering and coexistence with genealogy warning.
- [x] 5.4 Add/extend API tests to verify trace events cached replay keeps normalized `quality_meta` and `domain_quality_meta`.

## 6. Verification and Release Gates

- [x] 6.1 Run targeted backend + frontend test suites for query-tool, trace staged API, and MSD flows.
- [x] 6.2 Add a release checklist item confirming route-mode parity (single/batch and staged/compatibility) for completeness visibility.
- [x] 6.3 Capture before/after evidence in change notes to prove non-complete states are no longer silent in active heavy-query UX paths.
