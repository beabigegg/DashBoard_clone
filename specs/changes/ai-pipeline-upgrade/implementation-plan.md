---
change-id: ai-pipeline-upgrade
schema-version: 0.1.0
last-changed: 2026-05-29
---

# Implementation Plan: ai-pipeline-upgrade

## Objective

Collapse the AI function-mode pipeline's two sequential LLM calls (R1 intent select +
R2 param fill) into one combined call returning `{"function","params","explanation"}`;
add a bounded per-conversation `chat_history` to the existing `_SESSION_STORE` and inject
it into the combined call and text2sql Stage 1; register three new functions
(`production_history_query`, `resource_history_summary`, `qc_gate_status`) in
`ai_functions.yaml` with correct dispatch and `normalize_chart_data` handling; and bump
the four affected contracts. Route surface, response envelope, TTL, RLock, and the 131K
context window are unchanged. Implement TDD per `test-plan.md` (22 tests).

## Execution Scope

### In Scope
- D1 combined-prompt merge in `process_query_function()` (single combined call; R3 unchanged).
- D2 `chat_history` session-state extension + injection (combined call + text2sql Stage 1 only).
- D3 three new YAML function entries + dispatch adapter + `normalize_chart_data` branch.
- Contract bumps: api-contract, api-inventory, business-rules, data-shape (see Contract Updates).
- All 22 tests in `test-plan.md` across the three test files.

### Out of Scope (Non-goals — backend-engineer must NOT do these)
- Do NOT delete `build_round1_prompt()` / `build_round2_prompt()` (retained for agent mode + tests; mark `# deprecated` only).
- Do NOT edit the three callee services (`production_history_service.py`, `resource_history_service.py`, `qc_gate_service.py`) — invoked read-only.
- Do NOT change `ai_routes.py` route surface or the response envelope keys.
- Do NOT inject `chat_history` into text2sql Stage 2 (SQL generation) or Round 3 (summarize).
- Do NOT introduce a new env var (cap is a code constant; TTL/context window unchanged).
- Do NOT refactor `_call_llm`, `_extract_json_from_text`, `normalize_chart_data` existing branches, or text2sql retry loop beyond the additive changes named below.
- Do NOT change the RLock object or TTL semantics in `ai_query_understanding.py`.
- Out of scope per `test-plan.md` §Out of Scope: live-LLM E2E, soak, frontend rendering, Oracle latency benchmarking, RLock contention load tests.

## Required Changes

| id | area | required action | owner agent |
|---|---|---|---|
| IP-1 | `ai_function_registry.py` | Add `build_combined_prompt()` per design.md D1 (all 41 names+descriptions + instruction to emit `params`; output `{"function","params","explanation"}`). Mark `build_round1_prompt`/`build_round2_prompt` with `# deprecated`; keep them. | backend-engineer |
| IP-2 | `ai_query_service.py` | Rewrite `process_query_function()` to issue ONE combined call via `build_combined_prompt()`; map malformed/null `function` to existing null-intent path (D1 fallback, AC-7); emit single `combined_select_fill` tool_trace entry; keep R3. | backend-engineer |
| IP-3 | `ai_query_understanding.py` | Add `get_chat_history()`, `append_to_chat_history()`, `_evict_if_needed()` under `_SESSION_LOCK` per D2; cap 8 pairs / 16 messages FIFO; preserve `chat_history` across the `ready_to_search` pop (R3 fix). | backend-engineer |
| IP-4 | `ai_query_service.py` | Inject `chat_history` between system and user turn in combined call AND text2sql Stage 1 only; append `(question, answer)` on success incl. empty-result, NOT on Timeout/Connection/Value errors (D2). | backend-engineer |
| IP-5 | `ai_functions.yaml` + `ai_function_registry.py` | Add 3 entries (41 total). `production_history_query` gets `dispatch: raw_params`; `get_service_function`/dispatch must call `service_fn(params)` when flagged (D3). | backend-engineer |
| IP-6 | `ai_query_service.py` | Add `normalize_chart_data` branch: `if fn == "qc_gate_status": return raw.get("stations", []) if isinstance(raw, dict) else raw` (D3). | backend-engineer |
| IP-7 | contracts (4 files) | Version bumps + new rules per Contract Updates section. | backend-engineer |
| IP-8 | tests (3 files) | Author/extend 22 tests per `test-plan.md`, TDD order. | backend-engineer |

## Source Artifact Pointers

| source | relevant pointer | used for |
|---|---|---|
| design.md | D1 (Combined-prompt structure + Fallback + tool_trace) | IP-1, IP-2 implementation constraints |
| design.md | D2 (chat_history: format, placement, cap, append policy, text2sql scope, R3 persistence interaction) | IP-3, IP-4 |
| design.md | D3 (three new functions; raw_params adapter; granularity enum; qc_gate normalize branch) | IP-5, IP-6 |
| design.md | Open Risks R1/R2/R3 | Known Risks below; R3 pinned by `TestHistorySurvivesAdvanceQueryStatePop` |
| test-plan.md | AC→test mapping table (22 rows) | IP-8; exact test names + files + tiers |
| test-plan.md | §Notes | Extend `TestYamlLoading` to 41; token-budget = char/estimate not live call; R3 guard semantics |
| ci-gates.md | Required Gates table | verification commands (below) |
| change-classification.md | Inferred Acceptance Criteria AC-1..AC-7 | scope completeness check |
| agent-log/contract-reviewer.yml | version-bumps, AI-04..AI-09, §2.9 gaps | Contract Updates section |

## File-Level Plan

| path or glob | action | notes |
|---|---|---|
| `src/mes_dashboard/services/ai_function_registry.py` | add `build_combined_prompt()`; `# deprecated` on R1/R2 builders; dispatch flag handling in `get_service_function` (or a wrapper) for `raw_params` | D1, D3. Reuse existing `REGISTRY` iteration pattern (cf. current `build_round1_prompt` loop lines 324-326). Do not alter `validate_intent` semantics. |
| `src/mes_dashboard/services/ai_functions.yaml` | add `production_history_query`, `resource_history_summary`, `qc_gate_status` (41 total) | D3. `production_history_query`: `service: ...production_history_service.query_production_history`, `dispatch: raw_params`, `chart_type: table`, params `start_date`(req)/`end_date`(req)/`lot_ids`(opt list)/`pj_types`(opt list); 7-day default + cost hint in descriptions. `resource_history_summary`: `service: ...resource_history_service.query_summary`, standard kwargs, `chart_type: kpi`, params `start_date`/`end_date`/`granularity`(enum day/week/month/year default day)/`workcenter_groups`(opt `$WORKCENTER_GROUPS`); do NOT expose families/resource_ids/is_*. `qc_gate_status`: `service: ...qc_gate_service.get_qc_gate_summary`, `params: {}`, `chart_type: table`. |
| `src/mes_dashboard/services/ai_query_service.py` | rewrite `process_query_function()` (IP-2/IP-4); add `qc_gate_status` normalize branch (IP-6); raw_params dispatch at the `service_fn(**params)` site (line ~1373) | Combined call replaces R1+R2 blocks (lines ~1290-1349). Keep default-merge loop, `_auto_resolve_id`, `validate_intent`, R3 block, empty-result handling unchanged. Reuse existing `requests.Timeout/ConnectionError/RuntimeError` → Timeout/Connection mapping. Import `build_combined_prompt`; keep R1/R2 imports for compatibility or drop only if unused after edit (verify no other caller). |
| `src/mes_dashboard/services/ai_query_understanding.py` | add 3 helpers under `_SESSION_LOCK`; fix `ready_to_search` pop (line ~212-213) to preserve `chat_history` | D2/R3. Match existing RLock + deepcopy + TTL patterns (cf. `get_query_session_for_tests`, `_cleanup_expired_sessions`). `chat_history` stored on the same session dict keyed by `conversation_id`; the slot-state pop must clear only slot-filling keys, not `chat_history` (copy-before-pop / restore, or restructure). |
| `tests/test_ai_query_service.py` | add tests per mapping | TestCombinedCallOneCallOnly, TestCombinedCallOutputSchema, TestCombinedCallNullIntent, TestHistoryInjectedIntoCombinedCall, TestProductionHistoryQueryDispatchAdapter, TestNormalizeChartDataNewFunctions, TestCombinedCallMalformedJson, TestCombinedCallPartialJson |
| `tests/test_ai_function_registry.py` | add/extend tests | TestCombinedPromptContainsAll41Functions, TestCombinedPromptTokenBudget, TestProductionHistoryQueryFunctionEntry, TestResourceHistorySummaryFunctionEntry, TestQcGateStatusFunctionEntry, TestQcGateStatusNoParams, TestProductionHistoryQueryParamSchema, TestResourceHistorySummaryParamSchema; extend existing `TestYamlLoading.test_all_known_functions_present` to 41 names (do not duplicate) |
| `tests/test_ai_query_understanding.py` | add tests | TestHistorySurvivesAdvanceQueryStatePop, TestChatHistoryAppendOnSuccess, TestChatHistoryNoAppendOnFailure, TestChatHistoryAppendOnEmptyResult, TestChatHistoryCapEnforcement, TestChatHistoryCapExactBoundary |

## Contract Updates

- API: `contracts/api/api-contract.md` §10 Compatibility Notes — document combined-call behavior and `chat_history` session extension (route surface + envelope unchanged). Bump 1.11.0 → 1.12.0. Also `contracts/api/api-inventory.md` — update `ai_routes.py` row; bump 1.1.10 → 1.1.11.
- CSS/UI: none.
- Env: none (no new env var).
- Data shape: `contracts/data/data-shape-contract.md` — add §2.9 (session store shape incl. `chat_history` pairs, cap 8/16), three new function param schemas, and `normalize_chart_data` output for the three new functions. Bump 1.10.0 → 1.11.0.
- Business logic: `contracts/business/business-rules.md` — add AI-04 (combined-prompt output schema), AI-05 (malformed-JSON fallback / AC-7), AI-06/07/08 (chat_history policy: format, cap/eviction, append-on-success-incl-empty), AI-09 (three new function behaviors + `production_history_query` synchronous Oracle latency expectation). Bump 1.10.0 → 1.11.0.
- CI/CD: none.

## Test Execution Plan

TDD order: write the failing test first, implement, then make it pass. Suggested sequence:
IP-1/IP-3 helpers (unit, tier 0) → IP-2/IP-4 integration → IP-5/IP-6 (contract + dispatch) → resilience/data-boundary. Run `cdd-kit validate` after contract edits.

| acceptance criterion | test file / command | expected signal |
|---|---|---|
| AC-1 | `tests/test_ai_query_service.py::TestCombinedCallOneCallOnly` / `TestCombinedCallOutputSchema` / `TestCombinedCallNullIntent` | exactly one `_call_llm` for select+fill; output `{function,params,explanation}`; null `function` → null-intent path |
| AC-2 | `tests/test_ai_function_registry.py::TestCombinedPromptContainsAll41Functions` / `TestCombinedPromptTokenBudget` | all 41 names present; char/estimated-token count within safe margin of 131K |
| AC-3 | `tests/test_ai_query_service.py::TestHistoryInjectedIntoCombinedCall` ; `tests/test_ai_query_understanding.py::TestHistorySurvivesAdvanceQueryStatePop` | history prepended to combined messages; history survives `ready_to_search` pop (R3 guard) |
| AC-4 | `tests/test_ai_query_understanding.py::TestChatHistoryAppendOnSuccess` / `TestChatHistoryNoAppendOnFailure` / `TestChatHistoryAppendOnEmptyResult` | append on success + empty-result; no append on exception |
| AC-5 | `tests/test_ai_query_understanding.py::TestChatHistoryCapEnforcement` / `TestChatHistoryCapExactBoundary` | cap 8 pairs/16 msgs; FIFO eviction at boundary |
| AC-6 | `tests/test_ai_function_registry.py::TestProductionHistoryQueryFunctionEntry` / `TestResourceHistorySummaryFunctionEntry` / `TestQcGateStatusFunctionEntry` ; `tests/test_ai_query_service.py::TestProductionHistoryQueryDispatchAdapter` / `TestNormalizeChartDataNewFunctions` | 3 entries resolve to correct callables + schemas; raw_params passed as single positional dict; new normalize branch returns expected shape |
| AC-7 | `tests/test_ai_query_service.py::TestCombinedCallMalformedJson` / `TestCombinedCallPartialJson` ; `tests/test_ai_function_registry.py::TestQcGateStatusNoParams` / `TestProductionHistoryQueryParamSchema` / `TestResourceHistorySummaryParamSchema` | malformed/partial JSON → defined fallback, no unhandled exception; param-schema boundaries enforced |
| all (gate) | `pytest tests/test_ai_query_service.py tests/test_ai_function_registry.py tests/test_ai_query_understanding.py -v` ; `pytest tests/ --ignore=tests/e2e --ignore=tests/stress -q` ; `ruff check src/mes_dashboard/services/` ; `cdd-kit validate` ; `cdd-kit gate ai-pipeline-upgrade` | all five required gates green (ci-gates.md) |

## Handoff Constraints

- Implementation agents must not infer missing requirements from chat history.
- Do not re-copy full design, test strategy, CI policy, or contract prose into this plan; follow the source pointers above.
- If this plan omits a required file, behavior, contract, or test, stop and report `blocked`.
- Keep implementation within the file-level plan unless a Context Expansion Request is approved.
- Do NOT delete `build_round1_prompt`/`build_round2_prompt` — `# deprecated` comment only.
- New `chat_history` helpers must reuse the existing `_SESSION_LOCK` (RLock) and deepcopy/TTL patterns already in `ai_query_understanding.py`; do not introduce a second lock.
- History injection must NOT reach text2sql Stage 2 or Round 3 (D2 scope); inject only into the combined call and text2sql Stage 1.
- `production_history_query` dispatch must pass `params` as a single positional dict (`raw_params`), never as kwargs (D3); pin with `TestProductionHistoryQueryDispatchAdapter`.

## Known Risks

- R1 (med, from design.md): combined call may emit lower-quality `params` than the dedicated R2 call → more `validate_intent` 400s. Mitigated by post-hoc default-merge + clarification path; covered by integration tests.
- R2 (med, from design.md): `production_history_query` synchronous Oracle/spool latency may exceed `AI_REQUEST_TIMEOUT` on wide queries. Mitigated by YAML scope/7-day hint; documented in business-rules AI-09. Not a pre-merge gate.
- R3 (low, from design.md): if the `ready_to_search` pop also clears `chat_history`, history silently never accumulates. Pinned by `TestHistorySurvivesAdvanceQueryStatePop` — must fail before the pop fix and pass after.
- Compatibility: `process_query_function` currently imports `build_round1_prompt`/`build_round2_prompt`; after rewrite verify no dangling unused import triggers `ruff` F401 while keeping the builders defined in the registry module.
