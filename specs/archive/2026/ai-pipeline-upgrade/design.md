# Design: ai-pipeline-upgrade

## Summary
The AI function-mode pipeline collapses its first two sequential LLM calls (R1 intent
classification + R2 parameter filling) into one combined call that returns
`{"function","params","explanation"}`, removing one full network round-trip per query.
A bounded per-conversation `chat_history` is added to the existing `_SESSION_STORE`
so follow-up questions resolve with prior Q&A context. Three new service callables
(`production_history_query`, `resource_history_summary`, `qc_gate_status`) are registered
in `ai_functions.yaml`. The route surface, response envelope, TTL, RLock, and 131K context
window are unchanged; this is an internal data-flow + session-state change.

## Affected Components
| component | file path(s) | nature of change |
|---|---|---|
| Combined prompt builder | `services/ai_function_registry.py` | add `build_combined_prompt()`; retain `build_round1/2_prompt` for tests/agent mode |
| Function pipeline | `services/ai_query_service.py` | `process_query_function()` issues one combined call instead of R1→R2; add malformed-output fallback; history injection; PHF dispatch adapter; `normalize_chart_data` branch for `qc_gate_status` |
| Session store | `services/ai_query_understanding.py` | add `chat_history` key to session dict; helpers `append_chat_turn()` / `get_chat_history()` under existing RLock + TTL |
| Function registry config | `services/ai_functions.yaml` | three new entries (41 total) |
| Callees (read-only) | `services/production_history_service.py`, `resource_history_service.py`, `qc_gate_service.py` | invoked as services; no edits |
| Contracts | `contracts/api`, `contracts/business`, `contracts/data` | AI-04/05/06/07/08/09, §2.9 session shape, three function schemas (contract-reviewer owns) |

## Key Decisions

### D1 — Combined-prompt structure (R1+R2 merge)
- **Chosen**: One combined system prompt = names+descriptions for ALL 41 functions (selection
  layer, the existing R1 catalogue), followed by an instruction to also emit `params`.
  Do NOT inline any single full schema. The model selects AND fills params in one pass; param
  validity is enforced post-hoc by the existing `validate_intent()` against the YAML schema, and
  YAML defaults are filled by the existing default-merge loop. Output: `{"function","params","explanation"}`.
  — *Rejected: inlining the selected function's full schema* — requires knowing the selection
  before building the prompt, which reintroduces the two-call ordering the merge removes.
  — *Rejected: full schemas for all 41 in one prompt* — ~6-8K tokens of param detail the model
  rarely needs; the catalogue + post-hoc validation already bounds param correctness.
- **Fallback (AC-7)**: if the combined call returns `{"function": null}`, omits `function`, or
  `_extract_json_from_text` returns `None`, map to the existing null-intent path — return
  `explanation` (or the canned "無法理解" message) as `answer`, `chart_data=null`,
  `query_used=null`, `params_used=null`. No exception raised. Unknown `function` name still raises
  `ValueError` via `validate_intent` (unchanged 400 behavior).
- **tool_trace**: one entry replaces the prior two — `{"step":1,"function":"combined_select_fill",
  "summary":"function=<name>, params=<keys>"}`. Round 3 trace entry is unchanged.

### D2 — chat_history session design
- **Format**: raw `{"role":"user"|"assistant","content":"..."}` pairs. — *Rejected: condensed
  summary string* — loses thread context the 131K window can afford to keep.
- **Injection placement**: messages = `[system(combined prompt), ...chat_history pairs..., user(current question)]`.
  History after system, before current question (standard OpenAI memory ordering).
- **Cap & eviction**: 8 pairs / 16 messages; FIFO — drop the oldest pair when appending would exceed the cap.
- **Append policy**: append `(user question, assistant answer)` only on successful completion
  (answer returned without exception). On `TimeoutError`/`ConnectionError`/`ValueError`: do NOT append.
  On empty-result (no data): DO append — the exchange is contextually useful.
- **text2sql scope**: inject history into Stage 1 domain classification only. — *Rejected: inject
  into Stage 2 SQL generation* — Stage 2 already carries question context and its retry loop appends
  assistant/user correction turns; extra history dilutes the SQL instruction.
- **Storage**: new `chat_history` key in the existing `_SESSION_STORE` dict (same RLock, same 1800s
  TTL). Session expiry discards history — acceptable; users continue within the TTL. No new env var
  (cap is a code constant); if made tunable later, promote the Env contract.
- **Persistence interaction**: `advance_query_state` pops the session on `ready_to_search`. To keep
  history across turns, the append/read must key on `conversation_id` independently of the
  slot-filling pop — store/read history before the pop or in a separate key that the pop preserves.
  Implementer must ensure the slot-state pop does not also evict `chat_history`.

### D3 — Three new functions
- **production_history_query** — INCLUDE, scope-bounded. The callable is
  `query_production_history(raw_params: Dict)` (single positional dict), incompatible with the
  pipeline's `service_fn(**params)` dispatch. Add a thin dispatch adapter so a `raw_params`-style
  callable receives `params` as one dict instead of kwargs (flag via a YAML field, e.g.
  `dispatch: raw_params`, or a registry-side wrapper). Bound Oracle cost in the YAML param
  description (e.g. 7-day max time-range hint, required `pj_types` or identifier). Document the
  synchronous latency expectation in `business-rules.md` AI-09. — *Rejected: exclude entirely* —
  the report is in scope per AC-6; scoping + adapter is sufficient.
- **resource_history_summary** — expose only `start_date`, `end_date`, `granularity`
  (enum day/week/month/year, default `day`), `workcenter_groups` (optional, `$WORKCENTER_GROUPS`).
  Exclude `families`, `resource_ids`, `is_production`, `is_key`, `is_monitor` (too technical for NL);
  service defaults cover them. `chart_type: kpi` (summary KPI section).
- **qc_gate_status** — no params; `chart_type: table`. Add a `normalize_chart_data` branch returning
  `raw.get("stations", [])` (matches the table pattern). — *Rejected: pass-through raw dict* —
  frontend table renderer expects a list, not `{cache_time, stations}`.

## Migration / Rollback
No schema or data migration. Forward: ship the combined prompt + history + three YAML entries
together (single deploy). `build_round1/2_prompt` are retained, so agent mode and existing tests
keep working. Rollback: revert the four service files and `ai_functions.yaml`; no parquet/spool
cleanup (query-tool-style on-demand; production_history uses its own existing spool lifecycle,
untouched here). `chat_history` lives only in process memory — rollback discards it with no
persistence side effect. Contract version bumps (api 1.12, api-inventory 1.1.11, business-rules 1.11,
data-shape 1.11) revert with the code.

## Open Risks
- **R1 (med)**: combined call must reliably emit valid `params` for the selected function in one shot;
  if param quality regresses vs. the dedicated R2 call, `validate_intent` rejects (400) more often.
  Mitigation: post-hoc default-merge + clarification path; covered by integration tests.
- **R2 (med)**: `production_history_query` synchronous latency may exceed `AI_REQUEST_TIMEOUT`/Oracle
  budget on wide queries. Mitigation: YAML scope hint; AI-09 documents expected timeout behavior.
- **R3 (low)**: `chat_history` eviction must not be bypassed by the slot-state session pop (see D2
  persistence interaction) or history silently never accumulates. Pin with a two-turn integration test.
