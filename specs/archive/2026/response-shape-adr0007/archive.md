---
change-id: response-shape-adr0007
archived: 2026-06-16
---

# Archive: response-shape-adr0007

> **Cold Data Warning**: This archive is historical evidence. Current requirements live in `contracts/` and active project guidance.

## Change Summary

ADR 0007 Response-shape migration: declared a named typed response schema for all 177 endpoints in `contracts/api/api-contract.md`, regenerated `contracts/openapi.json`, built the Flask test-client sample-capture harness (`tests/contract/capture_samples.py`), captured 177 endpoint samples, and wired `cdd-kit validate --contracts` as a required Tier-1 CI gate. No `src/` production code was modified (AC-7 confirmed).

## Final Behavior

- `cdd-kit validate --contracts` now enforces response-body shape for 176 sampled endpoints (one binary/parquet endpoint has no JSON body schema by design).
- `cdd-kit doctor` reports ≥160 typed response endpoints (was 0 with advisory warning).
- All 177 `response schema` cells in `api-contract.md` reference named schemas under `## Schemas` (plain names, no `→` prefix).
- `contracts/openapi.json` carries 20 component schemas and 160+ operations with `$ref` linkages.
- CI gate `contract-driven-gates` job now runs `cdd-kit openapi export --check` then `cdd-kit validate --contracts` on every push.

## Final Contracts Updated

| contract | change |
|---|---|
| `contracts/api/api-contract.md` | Added `## Schemas` section (20 named schemas); rewrote all 177 `response schema` cells to named refs |
| `contracts/api/error-format.md` | Added `### StandardErrorResponse` Tier-B json-schema block |
| `contracts/openapi.json` | Regenerated (177 endpoints, 20 component schemas) |
| `contracts/api/openapi.json` | Regenerated (same content, alternate path) |
| `contracts/ci/ci-gate-contract.md` | Added `response-shape-validate` gate row; schema-version → 1.3.24 |
| `contracts/CHANGELOG.md` | Added `[ci 1.3.24] — 2026-06-15` entry |

## Final Tests Added / Updated

| file | purpose | AC |
|---|---|---|
| `tests/contract/capture_samples.py` | Flask test-client capture for 177 endpoints | AC-3 |
| `tests/contract/response-samples.json` | Manifest mapping endpoints to sample files | AC-4 |
| `tests/contract/samples/*.json` (177 files) | Captured offline responses | AC-3 |
| `tests/contract/test_schema_coverage.py` | ≥158 non-prose response-schema cells | AC-1 |
| `tests/contract/test_openapi_schema_resolution.py` | ≥100 `$ref`-linked operations | AC-2 |
| `tests/contract/test_capture_samples.py` | capture script exits 0; 177 sample files exist | AC-3 |
| `tests/contract/test_manifest_completeness.py` | manifest keys map to known endpoints | AC-4 |
| `tests/contract/test_doctor_clean.py` | no "0 with a typed response schema" warning | AC-6 |
| `tests/contract/test_gate_wiring.py` | workflow contains `cdd-kit validate --contracts` | AC-8 |
| `tests/test_api_contract.py` | `test_no_src_files_modified` — no src/ edits | AC-7 |

## Final CI/CD Gates

| gate | tier | command |
|---|---|---|
| `contract-validate` | 0 | `cdd-kit validate` |
| `openapi-sync` | 1 | `cdd-kit openapi export --check --out contracts/openapi.json` |
| `response-shape-validate` | 1 | `cdd-kit validate --contracts` |

Both new steps added to `.github/workflows/contract-driven-gates.yml` job `contract-and-fast-tests`. `jsonschema` pip install required before the validate step.

## Production Reality Findings

1. **`→` prefix silently breaks $ref generation.** The initial implementation used `→ SchemaName` in response schema cells (following a prose convention). `cdd-kit` treats anything not matching `/^[A-Za-z][A-Za-z0-9_]*$/` as prose — no `$ref` is generated, and `validate --contracts` reports "checked 0 sampled endpoint(s)" (vacuous pass). Fix: strip all `→` prefixes; use bare schema names.

2. **`dataPath` semantics.** `dataPath: "data"` in `response-samples.json` drills into the envelope's `data` field before schema validation. Since `GenericSuccessResponse` and all schemas here describe the full `{success, data/error, meta}` envelope, `dataPath` must be absent. Using it caused 65 validation failures (array vs object type mismatch; offline error responses have no `data` key).

3. **`jsonschema` not in CI Python environment.** The `cdd-kit validate --contracts` command requires the `jsonschema` Python package at runtime. It is not bundled with cdd-kit and is not installed by default on `ubuntu-latest`. Required: `pip install jsonschema` before the validate step.

4. **Tier-A field table headers.** `cdd-kit` requires `| field | type | required |` column headers for a field table to be compiled as a named schema. The wrong headers (`| name | type | description |`) cause the table to be silently skipped. All schemas were converted to Tier-B json-schema blocks instead (equivalent outcome, though Tier-A would also work with correct headers).

5. **openapi.json drift from background agent.** A concurrent background agent re-ran `capture_samples.py` and modified `contracts/api/api-contract.md` after the commit, causing `contracts/openapi.json` to drift. Detected by `cdd-kit openapi export --check` failing in CI. Fix: re-run export and commit.

6. **178 endpoint rows vs 158 nominal.** The api-contract.md table contains some duplicate rows for the downtime-analysis/query endpoint. Acceptance criterion AC-1 uses `≥158`; actual cell count is 178. Both are valid.

## Lessons Promoted to Standards

| lesson | target | what was added | evidence |
|---|---|---|---|
| A+B+D (response schema cell format, dataPath, Tier-A headers) | `contracts/api/api-contract.md` §Schema Authoring Rules | 4-bullet authoring rule section; schema-version → 1.22.0 | archive.md Findings #1, #2, #4; `contracts/CHANGELOG.md` [api 1.22.0] |
| E (openapi.json regeneration obligation) | `contracts/api/api-contract.md` §Schema Authoring Rules | 4th bullet: regen + commit after every schema/endpoint edit | archive.md Finding #5; CI failure run 27599624864 |
| C (jsonschema pip dep) | `CLAUDE.md` CDD Kit ops cluster (one line); `docs/cdd-kit-patterns.md` §jsonschema pip Dependency | One-line pointer in CLAUDE.md; full detail section in cdd-kit-patterns.md | CI failure run 27599574084; commit bf7ba1e |

## Follow-up Work

- The one binary/parquet endpoint (`GET /api/spool/yield_alert_dataset/{query_id}.parquet`) has no JSON body schema; the warning in the gate output is expected and benign.
- 60 request body schemas remain "free-form prose" in the contract (not typed). A future change could add typed request schemas for high-value endpoints.
- Tier-A field tables could replace some Tier-B json-schema blocks for simpler schemas (pure flat rows), reducing verbosity in `api-contract.md`.
