---
change-id: response-shape-adr0007
schema-version: 0.1.0
last-changed: 2026-06-15
---

# Implementation Plan: response-shape-adr0007

## Objective
Declare a named typed response schema for every one of the 158 endpoints in
`contracts/api/api-contract.md`, regenerate `contracts/openapi.json`, build the
Flask test-client sample-capture harness, and confirm the already-wired
`cdd-kit validate --contracts` contract gate passes (AC-1..AC-8). No `src/`
production code is modified (AC-7).

## Execution Scope

### In Scope
- `## Schemas` section + per-endpoint `response schema` cell rewrites in `contracts/api/api-contract.md`.
- `### StandardErrorResponse` Tier-B block in `contracts/api/error-format.md`.
- `contracts/openapi.json` regen via `cdd-kit openapi export`.
- `tests/contract/capture_samples.py`, `tests/contract/response-samples.json`, `tests/contract/samples/*.json`.
- `tests/contract/test_*.py` + `test_no_src_files_modified` in `tests/test_api_contract.py` (per test-plan.md).
- `contracts/CHANGELOG.md` version entry for the api contract bump.

### Out of Scope
- Any edit under `src/` (read-only — route signatures, wrapper shape, auth flow only). AC-7.
- Editing `.github/workflows/contract-driven-gates.yml` — gate step already wired by ci-cd-gatekeeper (ci-gates.md §CI/CD Workflow).
- Frontend schema consumers, business-value correctness, live Oracle/Redis/LDAP (test-plan.md §Out of Scope).
- Authoring `design.md` (not required; classification §Architecture Review = no).

## Required Changes
| id | area | required action | owner agent |
|---|---|---|---|
| IP-1 | contract/api | Append `## Schemas` with one named schema per response shape; rewrite all 158 `response schema` cells to named refs | backend-engineer |
| IP-2 | contract/api | Add `### StandardErrorResponse` Tier-B block to `error-format.md` | backend-engineer |
| IP-3 | contract/openapi | Regenerate `contracts/openapi.json` after IP-1/IP-2 | backend-engineer |
| IP-4 | test-infra | Implement `capture_samples.py` + `response-samples.json` manifest + 158 `samples/*.json` | backend-engineer |
| IP-5 | tests | Add contract/unit tests per test-plan.md §Key Test Names | backend-engineer |
| IP-6 | contract/changelog | Add api contract version entry to `contracts/CHANGELOG.md` | backend-engineer |

## Source Artifact Pointers
| source | relevant pointer | used for |
|---|---|---|
| test-plan.md | AC→test mapping table; §Key Test Names Per File | test files/names to create |
| test-plan.md | §Primary Evidence: Capture-then-Validate Cycle | capture script behavior + auth/error-shape rules |
| ci-gates.md | Required Gates table; §CI/CD Workflow | verification commands; gate already wired |
| tests/contract/README.md | "Field table (Tier A) vs json-schema block (Tier B)"; Manifest format; Flask capture snippet | schema tier rules, `dataPath` envelope, capture pattern |
| contracts/api/api-contract.md | §4 endpoint table (lines 69–249); §2 envelope; §7 Async Job Pattern | endpoint list, success/error envelope, Type A/B branches |
| contracts/api/error-format.md | Standard Error Shape; §Special Cases (410/202/503) | StandardErrorResponse fields + dual-branch endpoints |
| docs/adr/0007-*.md | ADR 0007 Response-shape | adoption rationale (advisory→error) |

## Execution Order (backend-engineer follows in sequence)
1. **Read** README.md Tier A/B rules + the `## Schemas` mechanics, then `cdd-kit contract schema set` / `endpoint set` help. Read api-contract.md §4 table + §7 and error-format.md §Special Cases. Read-only confirm wrapper key in `src/mes_dashboard/core/response.py` and auth flow in `services/auth_service.py`.
2. **IP-2** — add `### StandardErrorResponse` Tier-B `json-schema` block in error-format.md matching the Standard Error Shape (`success:false`, `error:{code,message,details}`, `meta:{timestamp,app_version}`).
3. **IP-1** — append `## Schemas` to api-contract.md and rewrite each of the 158 `response schema` cells to a named ref. Classify each endpoint Tier A vs Tier B (guide below). Reuse shared schemas (`AckResponse`, `StandardErrorResponse`) rather than per-endpoint duplicates.
4. **IP-3** — regenerate: `cdd-kit openapi export --out contracts/openapi.json`. Target is `contracts/openapi.json` (NOT the README's `contracts/api/openapi.json` example path).
5. **IP-4** — implement `capture_samples.py` (Flask test-client, `create_app({"TESTING": True})`; login first for `required` endpoints), run it to emit 158 `samples/*.json`, and write `response-samples.json` (use `{sample, dataPath:"data"}` form for `success_response`-wrapped payloads).
6. **IP-5** — add tests per test-plan.md; extend `tests/test_api_contract.py` with `test_no_src_files_modified`.
7. **IP-6** — bump api schema-version in api-contract.md front-matter + add `contracts/CHANGELOG.md` entry (per CLAUDE.md: version entries go to CHANGELOG.md only).
8. Run verification commands (below).

## Schema Naming Conventions
- Shared ack: `AckResponse` (`{ok:true}` / `{ok:true, message}`). Shared error: `StandardErrorResponse`.
- Row object: `<Feature>DetailRow` / `<Feature>SummaryRow` / `<Feature>Row`; PascalCase feature derived from path segment (e.g. `RejectHistoryDetailRow`).
- List endpoints: point cell at `<Feature>...Row[]` (`[]` suffix, README Tier A rule).
- Async 202 branch: `<Feature>JobAccepted` (`{async:true, job_id, status_url, status}`). Pair with the 200 schema (see Special Cases).
- Health: `HealthPayload`. Auth: `AuthSessionResponse` (or `AckResponse` where body is ack-only — confirm from captured sample).

## Tier Classification Guide (README "Field table vs json-schema block")
- **Tier A (field table)** — primitive fields only (`string/integer/number/boolean`), `enum(...)`, named-schema ref, `[]` suffix. Use for `AckResponse`, flat row objects, simple lists.
- **Tier B (`json-schema` block)** — anything richer: arrays of free-form/nested objects, nested objects, unions/multi-branch, conditional shapes. Use for `StandardErrorResponse`, summary payloads with nested arrays (e.g. `topReasons`), and 202/200 dual-branch unions.

## Special Cases
- **202/200 dual-branch** (reject-history, yield-alert, production-history, trace, material-trace, downtime, hold-history, resource-history per §7): declare TWO named schemas — sync-200 payload + `<Feature>JobAccepted` (202). Capture the offline sample for whichever branch the test-client returns; the other branch's schema still must exist for openapi resolution.
- **410 CACHE_EXPIRED** (hold-history, resource-history view endpoints): the offline sample IS the error envelope → validate against `StandardErrorResponse` (test-plan.md §Primary Evidence).
- **Stream/binary** (`*.parquet`, `csv-stream` exports): Tier-A content-type declaration only — no JSON body schema; mark the cell as the binary/stream content type, not a JSON ref.
- **Auth endpoints** (`/api/auth/*`): capture by calling `POST /api/auth/login` first (test-client session cookie), then capture `me`/`heartbeat`/`logout` in the same session (AC-3).
- **DB/Redis-backed endpoints offline**: capture returns `{success:false, error:...}` → that is the contracted offline shape and must validate against `StandardErrorResponse`.

## Contract Updates
- API: IP-1 (`## Schemas` + 158 cell rewrites) and IP-2 (`StandardErrorResponse`). Bump api front-matter `schema-version`.
- CSS/UI: none. Env: none. Business logic: none.
- Data shape: confirm conformance rules in `contracts/data/data-shape-contract.md` are satisfied by the captured samples (classification §Required Contracts); no rule rewrite expected.
- CI/CD: none in this plan — gate step already wired (ci-gates.md). Do not edit the workflow file.

## Test Execution Plan
| acceptance criterion | test file / command | expected signal |
|---|---|---|
| AC-1 | tests/contract/test_schema_coverage.py | non-prose response-schema cell count == 158 |
| AC-2 | tests/contract/test_openapi_schema_resolution.py | all `$ref` resolve; operationId count == 158 |
| AC-3 | tests/contract/test_capture_samples.py | script exits 0; auth session cookie set; 158 sample files |
| AC-4 | tests/contract/test_manifest_completeness.py | manifest keys map to known endpoints; all sample paths exist |
| AC-5 | tests/contract/ | `cdd-kit validate --contracts` exit 0 over 158 samples |
| AC-6 | tests/contract/test_doctor_clean.py | 0 "Response-shape" warnings in `cdd-kit doctor` |
| AC-7 | tests/test_api_contract.py | `git diff --name-only HEAD` returns 0 `src/` paths |
| AC-8 | tests/contract/test_gate_wiring.py | workflow contains `cdd-kit validate --contracts` step |

Required test phases: collect, targeted, changed-area (test-plan.md §Notes; floor per references/sdd-tdd-policy.md). Generate evidence with `cdd-kit test run`; bounded select target is the `tests/contract/` directory.

Verification commands (run in `mes-dashboard` conda env):
- `python tests/contract/capture_samples.py`
- `cdd-kit openapi export --check --out contracts/openapi.json`
- `cdd-kit validate --contracts`
- `cdd-kit validate` and `cdd-kit doctor`
- `pytest tests/contract/ tests/test_api_contract.py`

## Handoff Constraints
- Implementation agents must not infer missing requirements from chat history.
- Do not re-copy full design, test strategy, CI policy, or contract prose into this plan; follow the source pointers above.
- If this plan omits a required file, behavior, contract, or test, stop and report `blocked`.
- Keep implementation within the file-level plan unless a Context Expansion Request is approved.
- Do NOT edit any `src/` file (AC-7) or the CI workflow file (already wired).
- `capture_samples.py` content is defined by test-plan.md §Primary Evidence — implement to that spec; do not invent additional behavior.

## Known Risks
- README capture snippet writes to `contracts/api/openapi.json`; this repo's canonical target is `contracts/openapi.json` (manifest + ci-gates.md). Use `contracts/openapi.json`.
- 202/200 dual-branch endpoints: the test-client offline run typically hits one branch only — the unselected branch's schema must still be declared for openapi `$ref` resolution (AC-2) even without a captured sample.
- Some endpoints return the error envelope offline; misclassifying their schema as the success row will fail AC-5. Validate the offline shape against `StandardErrorResponse`.
- `.cdd/code-map.yml` not consulted (contract/test artifacts dominate this change; no src edits). If route-signature ambiguity arises during capture, read-only inspect the specific route file under the allowed `src/mes_dashboard/routes/` path.
- If endpoint count drifts from 158 during cell rewrite, reconcile against `contracts/api/api-inventory.md` before declaring AC-1 complete.
