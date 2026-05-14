---
change-id: prod-history-first-tier-cache-filters
schema-version: 0.1.0
last-changed: 2026-05-14
risk: high
tier: 1
---

# Test Plan: prod-history-first-tier-cache-filters

## Acceptance Criteria → Test Mapping

| criterion id | test family | test file path | test name (one line) | tier |
|---|---|---|---|---|
| AC-1 | unit | tests/test_container_filter_cache.py | test_4tuple_payload_v2_round_trip — empty selection returns full distinct sets from cache | 1 |
| AC-2 | unit+property | tests/test_container_filter_cache.py + tests/property/test_cross_filter.py | test_cross_filter_narrows_by_selected_package; test_cross_filter_symmetric_across_fields; test_selection_order_independence | 1 |
| AC-3 | unit | tests/test_production_history_service.py | test_main_query_accepts_new_filter_params + test_backward_compat_type_only_flow_unchanged | 1 |
| AC-4 | unit+fuzz | tests/test_common_filters.py + tests/routes/test_fuzz_routes.py | test_parse_wildcard_tokens_rejects_sql_meta_chars; test_main_query_wildcard_param_meta_char_rejection | 1 |
| AC-5 | unit+property | tests/test_common_filters.py + tests/property/test_wildcard_parser.py | test_parse_wildcard_tokens_idempotent; test_parser_idempotence | 1 |
| AC-6 | integration | tests/integration/test_multi_worker_concurrency.py + tests/integration/test_real_multi_worker.py | test_container_filter_cache_lock_under_4_workers; test_lock_holder_crash_releases_lock; test_container_filter_cache_real_oracle | 1 (mock) / 3 (real) |
| AC-7 | e2e | frontend/tests/playwright/production-history-cross-filter.spec.ts | renders 4 MultiSelect rows + 3 textareas; second-tier MFGORDERNAME/CONTAINERNAME/FIRSTNAME chips suppressed | 1 |
| AC-8 | unit+data-boundary | tests/test_container_filter_cache.py + tests/test_production_history_service.py | test_schema_version_mismatch_triggers_rebuild; test_stale_schema_v1_payload_ignored | 1 |

## Test Families Required

unit / contract / integration / e2e / visual / data-boundary / resilience / monkey / stress / property

### Test Layer Plan

| layer | path | covers | tier | status |
|---|---|---|---|---|
| unit-backend-cache | tests/test_container_filter_cache.py | 4-tuple payload v2, cross-filter narrow/symmetry, schema version, lock | 1 | extend |
| unit-backend-service | tests/test_production_history_service.py | main-query param plumbing, wildcard→LIKE bind, back-compat, boundary cases | 1 | extend |
| unit-backend-sql | tests/test_production_history_sql_runtime.py | EXTRA_FILTERS emit for wildcard fields (test_extra_filters_wildcard_emit) | 1 | extend |
| unit-backend-parser | tests/test_common_filters.py | wildcard grammar (single `*` any pos; rejects pure `*`, multi-`*`, short prefix, SQL meta, control/NUL); dedup+cap=100; idempotence | 1 | new |
| contract | tests/test_production_history_routes.py | test_filter_options_endpoint_empty_selection / _with_selected_package / _rejects_unknown_keys (fail-open); test_filter_options_response_shape_matches_data_2_7; test_main_query_envelope_unchanged | 1 | extend |
| route-fuzz | tests/routes/test_fuzz_routes.py | test_filter_options_wildcard_meta_char_rejection; test_main_query_wildcard_param_meta_char_rejection; test_main_query_oversized_wildcard_input | 1 | extend |
| integration-cache | tests/integration/test_multi_worker_concurrency.py | test_container_filter_cache_lock_under_4_workers; test_lock_holder_crash_releases_lock | 1 | extend |
| integration-real | tests/integration/test_real_multi_worker.py | test_container_filter_cache_real_oracle (Oracle XE) | 3 (nightly) | extend |
| integration-resilience | tests/integration/test_redis_chaos.py, tests/integration/test_redis_timeout_fallback.py | test_filter_options_falls_back_when_redis_down; test_filter_options_l1_fallback | 1 | extend |
| data-boundary | tests/test_production_history_service.py | test_empty_cache_rebuild_under_load; test_stale_schema_v1_payload_ignored; test_pj_function_null_handled | 1 | extend |
| property | tests/property/test_wildcard_parser.py, tests/property/test_cross_filter.py | parser idempotence, selection-order independence | 1 | new |
| frontend-unit | frontend/tests/validation/useProductionHistory.validation.test.js, frontend/tests/legacy/production-history.test.js | test_multi_line_input_parser; test_cross_filter_loader_composable | 1 | extend |
| e2e | frontend/tests/playwright/production-history-cross-filter.spec.ts; -wildcard-paste.spec.ts; -multi-line-input.spec.ts | AC-7 UX flows; wildcard query; multi-line paste | 1 | new |
| visual | frontend/tests/playwright/production-history-cross-filter.spec.ts | DOM-level chip-suppression + 4 MultiSelect + 3 textarea rows snapshot | 1 | new |
| stress | tests/stress/test_production_history_stress.py | test_cache_rebuild_thundering_herd; test_high_cardinality_lot_in_list (1000 LOTs) | 1 (lightweight) | new |

## Out of Scope

- Soak (24h+) — short TTL window, classifier flagged as not-required.
- ROWNUM cap on non-anchored `%X%` — D7 deferred; no contract yet.
- Pixel-diff visual regression — DOM-level Playwright assertion is sufficient for chip suppression.
- Historical L2 entry migration — schema-version bump invalidates by design.
- Multi-`*` wildcard execution — D2 rejects in v1; only rejection assertion is in scope.

## Fuzz Payload Strategy

Extend `tests/routes/_fuzz_payloads.py` with a `WILDCARD_HOSTILE` group keyed on the 3 wildcard fields (`mfg_orders`, `lot_ids`, `wafer_lots`) and the 4 MultiSelect arrays. Cases: SQL meta (`'`, `;`, `--`, `/*`, `*/`); control chars `\x00`–`\x1f` (incl. NUL embedded mid-token); unicode RTL (`‮`) and full-width digits; 10KB single token; multi-`*` (`***`, `MA**`, `*A*B*`); pure `*`; single-char `X` below min-prefix=2; non-anchored `%X%` triggers (`*A*`); oversized list (>100 → cap); mixed-separator dump (CRLF + comma + tab). All must yield 400 with stable error code per PHF-04/PHF-05, never reach Oracle bind, and leave cache untouched.

## Property Tests

- `tests/property/test_wildcard_parser.py::test_parser_idempotence` — Hypothesis strategy over valid+invalid tokens; asserts `parse(parse(x)) == parse(x)` (AC-5, PHF-05).
- `tests/property/test_cross_filter.py::test_selection_order_independence` — for any 2-field selection `{A,B}` over the cached 4-tuple corpus, narrow-by-A-then-B equals narrow-by-B-then-A (AC-2 symmetry, PHF-02).

## Notes

All test names referenced verbatim from the work packet. Tier 1 = pre-merge; tier 3 = nightly real-Oracle.
