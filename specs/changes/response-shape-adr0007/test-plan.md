---
change-id: response-shape-adr0007
schema-version: 0.1.0
last-changed: 2026-06-15
risk: medium
tier: 1
---

# Test Plan: response-shape-adr0007

## Acceptance Criteria → Test Mapping

| criterion id | test family | test file path | tier |
|---|---|---|---|
| AC-1 (158 endpoints have named typed schemas) | contract | tests/contract/test_schema_coverage.py | 0 |
| AC-2 (openapi.json carries resolved schemas) | contract | tests/contract/test_openapi_schema_resolution.py | 0 |
| AC-3 (capture_samples.py captures real responses via Flask test-client) | unit | tests/contract/test_capture_samples.py | 0 |
| AC-4 (response-samples.json manifest + samples/*.json exist) | contract | tests/contract/test_manifest_completeness.py | 0 |
| AC-5 (cdd-kit validate --contracts passes all 158 samples) | data-boundary | tests/contract/ | 1 |
| AC-6 (cdd-kit doctor 0 Response-shape warnings) | contract | tests/contract/test_doctor_clean.py | 1 |
| AC-7 (no src/ changes) | unit | tests/test_api_contract.py | 0 |
| AC-8 (validate --contracts wired into contract gate) | contract | tests/contract/test_gate_wiring.py | 0 |

## Test Families Required

| family | tier | notes |
|---|---|---|
| unit | Tier 0 | capture helper; Flask test-client auth flow; no-src-diff guard |
| contract | Tier 0/1 | schema count, openapi.json `$ref` resolution, manifest completeness, gate wiring, doctor clean |
| data-boundary | Tier 1 | `cdd-kit validate --contracts` against all 158 captured samples; error-envelope shapes are valid captures |

## Primary Evidence: Capture-then-Validate Cycle

`python tests/contract/capture_samples.py` → writes `tests/contract/samples/*.json` → `cdd-kit validate --contracts` reads `tests/contract/response-samples.json` + `contracts/openapi.json` and asserts every sample conforms to its declared schema. Zero exit code from `cdd-kit validate --contracts` is the AC-5 assertion; zero "Response-shape" lines in `cdd-kit doctor` stdout is the AC-6 assertion. Both run as CI contract-gate steps.

Auth-required endpoints: capture script calls `POST /api/auth/login` via Flask test-client first, then issues real requests in the same session. Endpoints backed by Oracle/Redis return their error-envelope (e.g. `{"success": false, "error": "..."}`) — that IS the contracted offline shape and must match the declared schema.

## Key Test Names Per File

**tests/contract/test_capture_samples.py** (AC-3)
- `test_capture_runs_without_error` — script exits 0 against `create_app({"TESTING": True})`
- `test_auth_endpoints_get_session_cookie` — login returns 200 + `Set-Cookie` before capture
- `test_samples_dir_has_158_files` — `tests/contract/samples/` count == 158 after run

**tests/contract/test_schema_coverage.py** (AC-1)
- `test_all_158_endpoints_have_typed_schema_ref` — parse api-contract.md, assert non-prose response-schema cell count == 158

**tests/contract/test_openapi_schema_resolution.py** (AC-2)
- `test_openapi_json_no_unresolved_refs` — walk `$ref` nodes in `contracts/openapi.json`, assert each resolves within the document
- `test_openapi_operation_count` — assert operationId count == 158

**tests/contract/test_manifest_completeness.py** (AC-4)
- `test_manifest_keys_match_known_endpoints` — every key in `response-samples.json` maps to a known endpoint; no orphans
- `test_all_sample_files_exist_on_disk` — every `samples/<file>.json` path in manifest exists

**tests/contract/test_doctor_clean.py** (AC-6)
- `test_doctor_response_shape_zero_warnings` — run `cdd-kit doctor` via subprocess, grep stdout, assert 0 "Response-shape" warnings

**tests/contract/test_gate_wiring.py** (AC-8)
- `test_ci_yml_contains_validate_contracts_step` — read `.github/workflows/contract-driven-gates.yml`, assert `cdd-kit validate --contracts` is present as a step command

**tests/test_api_contract.py** (AC-7, extend existing)
- `test_no_src_files_modified` — `git diff --name-only HEAD` returns 0 paths under `src/`

## Test Update Contract

| existing test | action | reason |
|---|---|---|
| tests/test_api_contract.py | extend | add `test_no_src_files_modified` for AC-7 |

## Out of Scope

- E2E / Playwright tests (no browser interaction)
- Resilience, monkey, stress, soak
- Live Oracle, Redis, or LDAP in any test
- Business-logic correctness of payload values
- Frontend schema consumers

## Notes

Tier-0 tests run in < 30s: static file parsing + in-process Flask test-client only. Tier-1 is the `cdd-kit validate --contracts` CI gate command; AC-5/AC-6 have no standalone pytest file — the bounded target for `cdd-kit test select` is the `tests/contract/` directory, which covers the collect phase. AC-5/AC-6 are additionally proven by the CI gate steps recorded in ci-gates.md.
