# Change Classification

## Change Types
- primary: feature-enhancement, business-logic-change
- secondary: api-behavior-change (AI query response/contract surface)

## Risk Level
- medium

## Impact Radius
- module-level (AI query pipeline: `ai_query_service`, `ai_function_registry`, `ai_query_understanding`, `ai_functions.yaml`), with module-bounded ripple to the three newly-registered services (`production_history_service`, `resource_history_service`, `qc_gate_service`) as callees only.

## Tier
- 2

## Architecture Review Required
- yes
- reason: Item 1 merges two sequential LLM calls into one combined prompt (a data-flow change in the AI pipeline). Item 2 adds cross-question conversation state (`chat_history`) into the shared `_SESSION_STORE`, which is a concurrency-sensitive, TTL-bound, memory-growth surface (threading.RLock, 1800s TTL, cap of 8 pairs / 16 messages). These are non-obvious design decisions (prompt-format compatibility, session memory bounds, history truncation policy, fallback when combined-call output is malformed) that should be decided in `design.md` before implementation.

## Required Artifacts
Always required: change-request.md, change-classification.md, implementation-plan.md, test-plan.md, ci-gates.md, tasks.yml, context-manifest.md
Required optional: design.md (Architecture Review Required = yes)

## Optional Artifacts (default: no — set yes only with explicit reason)

| artifact | create? | reason |
|---|---|---|
| current-behavior.md | no | Current 2-call R1/R2 flow is described in change-request.md and design.md §current-flow. |
| proposal.md | no | No separate product investigation needed; scope is engineer-specified. |
| spec.md | no | No user-facing behavior decision beyond what design.md/implementation-plan.md cover. |
| design.md | yes | Architecture Review Required = yes (LLM-call data-flow merge + shared session-state memory/concurrency decisions). |
| qa-report.md | no | Routine pass/fail evidence goes in agent-log; promote only if blocking finding appears. |
| regression-report.md | no | Covered by updated tests; use agent-log pointer unless a pre-existing failure must be excluded. |
| visual-review-report.md | no | No UI output change. |
| monkey-test-report.md | no | Not a fuzz-surfaced change. |
| stress-soak-report.md | no | chat_history growth is bounded; promote to yes only if soak surfaces unbounded growth. |

## Required Contracts
- API: yes — AI query endpoint behavior changes (single-call function mode, history-aware responses). Update `contracts/api/api-contract.md` if the AI query request/response shape or `conversation_id` semantics change.
- CSS/UI: no
- Env: no — no new env var (131K context window and TTL are existing config). Promote if design introduces a tunable history-cap env var.
- Data shape: yes — three new function entries in `ai_functions.yaml` define new function/param schemas; `chat_history` adds a new session-state shape. Update `contracts/data/data-shape-contract.md`.
- Business logic: yes — function-selection/param-fill behavior (combined prompt), history-injection policy (last N turns, cap 8 pairs), and semantics of the three new functions. Update `contracts/business/business-rules.md`.
- CI/CD: no

## Required Tests
- unit: yes — `build_combined_prompt()` output structure; chat_history append/truncation (cap 8 pairs / 16 messages); `_SESSION_STORE` field management under TTL; per-kwarg forwarding of history into each LLM call.
- contract: yes — three new `ai_functions.yaml` entries resolve to correct callables and param schemas; combined-prompt output schema `{"function","params","explanation"}`; AI endpoint response contract.
- integration: yes — end-to-end `process_query_function()` single-call path (mock LLM) including malformed-output fallback; history carried across two questions in one `conversation_id`.
- E2E: no
- visual: no
- data-boundary: yes — function param schema boundary for three new functions (e.g., `qc_gate_status` with no params; param validation for `production_history_query` / `resource_history_summary`).
- resilience: yes — behavior when combined LLM call returns invalid/partial JSON; concurrent access under RLock; TTL boundary.
- fuzz/monkey: no
- stress: no
- soak: consider — capture as test-plan consideration; promote to stress-soak-report.md only if soak surfaces unbounded memory growth.

## Required Agents
- spec-architect — write `design.md` before planner
- implementation-planner — write `implementation-plan.md` after design + contracts + tests are known
- backend-engineer — implement all three pipeline items + three new functions + tests (TDD)
- test-strategist — write `test-plan.md`
- contract-reviewer — review API / data-shape / business-rule contract updates
- qa-reviewer — release readiness (always last)

## Inferred Acceptance Criteria
- AC-1: In function mode, a single combined LLM call returns `{"function": "...", "params": {...}, "explanation": "..."}`, and `process_query_function()` no longer issues a separate R2 LLM call.
- AC-2: All 38 existing function schemas plus the 3 new ones are presented in one combined system prompt without exceeding the confirmed 131K context window.
- AC-3: Within one `conversation_id` session, the last N turns are injected as `messages` history into each LLM call so a follow-up question resolves using prior Q&A context.
- AC-4: After a successful answer, the user question and AI answer summary are appended to `chat_history` in `_SESSION_STORE`, respecting the existing RLock and 1800s TTL.
- AC-5: `chat_history` is capped at 8 pairs (16 messages); the oldest turns are evicted when the cap is exceeded, bounding session memory.
- AC-6: `ai_functions.yaml` registers `production_history_query`, `resource_history_summary`, and `qc_gate_status`, each resolving to the correct callable with a valid param schema.
- AC-7: When the combined LLM call returns malformed or partial JSON, the pipeline degrades safely (defined fallback / error response) rather than raising an unhandled exception.

## Tasks Not Applicable
- not-applicable: 2.2 (CSS/UI contract), 2.3 (Env contract), 2.6 (CI/CD contract), 3.3 (E2E tests — Tier 2), 3.5 (stress/soak — Tier 2), 4.2 (Frontend — backend-only), 4.3 (no deploy changes), 5.1 (UI/UX review — no UI), 5.2 (Visual review — no UI)

## Clarifications or Assumptions
- No atomic split warranted — all three items share the same 4-5 files and the R1+R2 merge and history-injection both modify the same LLM-call path.
- No new environment variable is introduced; if design introduces a tunable (e.g., history cap) as an env var, promote Env contract to required.
- The AI query endpoint already exists in `ai_routes.py`; this changes its internal behavior, not its route surface.
- Open question for spec-architect: history-injection format — raw `messages` role pairs vs. condensed summary, and placement relative to the 38 function schemas in the combined prompt. This affects token budgeting against the 131K window.
