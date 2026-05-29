---
change-id: ai-pipeline-upgrade
schema-version: 0.1.0
last-changed: 2026-05-29
risk: medium
tier: 1
---

# Test Plan: ai-pipeline-upgrade

## Acceptance Criteria → Test Mapping

| criterion id | test family | test file path | test name | tier |
|---|---|---|---|---|
| AC-1 | unit | tests/test_ai_query_service.py | TestCombinedCallOneCallOnly | 0 |
| AC-1 | unit | tests/test_ai_query_service.py | TestCombinedCallOutputSchema | 0 |
| AC-1 | unit | tests/test_ai_query_service.py | TestCombinedCallNullIntent | 0 |
| AC-2 | unit | tests/test_ai_function_registry.py | TestCombinedPromptContainsAll41Functions | 0 |
| AC-2 | unit | tests/test_ai_function_registry.py | TestCombinedPromptTokenBudget | 0 |
| AC-3 | integration | tests/test_ai_query_service.py | TestHistoryInjectedIntoCombinedCall | 1 |
| AC-3 | integration | tests/test_ai_query_understanding.py | TestHistorySurvivesAdvanceQueryStatePop | 1 |
| AC-4 | unit | tests/test_ai_query_understanding.py | TestChatHistoryAppendOnSuccess | 0 |
| AC-4 | unit | tests/test_ai_query_understanding.py | TestChatHistoryNoAppendOnFailure | 0 |
| AC-4 | unit | tests/test_ai_query_understanding.py | TestChatHistoryAppendOnEmptyResult | 0 |
| AC-5 | unit | tests/test_ai_query_understanding.py | TestChatHistoryCapEnforcement | 0 |
| AC-5 | unit | tests/test_ai_query_understanding.py | TestChatHistoryCapExactBoundary | 0 |
| AC-6 | contract | tests/test_ai_function_registry.py | TestProductionHistoryQueryFunctionEntry | 1 |
| AC-6 | contract | tests/test_ai_function_registry.py | TestResourceHistorySummaryFunctionEntry | 1 |
| AC-6 | contract | tests/test_ai_function_registry.py | TestQcGateStatusFunctionEntry | 1 |
| AC-6 | unit | tests/test_ai_query_service.py | TestProductionHistoryQueryDispatchAdapter | 0 |
| AC-6 | unit | tests/test_ai_query_service.py | TestNormalizeChartDataNewFunctions | 0 |
| AC-7 | resilience | tests/test_ai_query_service.py | TestCombinedCallMalformedJson | 1 |
| AC-7 | resilience | tests/test_ai_query_service.py | TestCombinedCallPartialJson | 1 |
| AC-7 | data-boundary | tests/test_ai_function_registry.py | TestQcGateStatusNoParams | 1 |
| AC-7 | data-boundary | tests/test_ai_function_registry.py | TestProductionHistoryQueryParamSchema | 1 |
| AC-7 | data-boundary | tests/test_ai_function_registry.py | TestResourceHistorySummaryParamSchema | 1 |

## Test Families Required

| family | tier | notes |
|---|---|---|
| unit | 0 | Combined prompt structure, chat_history append/cap/eviction, dispatch adapter, `normalize_chart_data` new branches — all provable without I/O |
| contract | 1 | Three new YAML entries resolve to correct callables and param schemas; extends existing `TestYamlLoading` + `TestAllServicesImportable` |
| integration | 1 | End-to-end `process_query_function()` single-call path (mock LLM); two-turn session verifying history survives `advance_query_state` pop (R3) |
| data-boundary | 1 | `qc_gate_status` with empty/no params; param validation for `production_history_query` and `resource_history_summary` against YAML schema |
| resilience | 1 | Malformed JSON, partial JSON, null `function` key from combined call — each must return defined fallback, no unhandled exception |

## Out of Scope

- E2E against live LLM API (Tier 3 nightly; no live network in pre-merge gates)
- Stress / soak for `chat_history` memory growth (promote to `stress-soak-report.md` only if nightly surfaces unbounded growth — see change-classification.md §Required Tests soak note)
- Frontend rendering of `production_history_query` / `resource_history_summary` / `qc_gate_status` chart output
- Oracle query latency for `production_history_query` (R2 risk; covered by AI-09 contract clause, not a pre-merge gate)
- Concurrent RLock contention under thread load (covered by code review; thread-safety of `_SESSION_STORE` is unchanged)

## Notes

- Extend `TestYamlLoading.test_all_known_functions_present` to include the 3 new names (41 total) rather than creating a duplicate registry test.
- `TestCombinedPromptTokenBudget` should assert character or estimated-token count stays within a safe margin of the 131K window — not an exact token call.
- `TestHistorySurvivesAdvanceQueryStatePop` is the pinned guard for Open Risk R3: the test must call `advance_query_state` to `ready_to_search` and then verify `get_chat_history()` still returns the prior turn.
- `TestCombinedCallMalformedJson` is the most critical new test: supply raw LLM output that is not valid JSON and assert the pipeline returns a defined error response without raising.
- `TestProductionHistoryQueryDispatchAdapter` must supply `params` as a flat dict and assert the callable receives them as a single positional dict argument (`raw_params`), not as kwargs.
