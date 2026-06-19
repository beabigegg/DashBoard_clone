# Archive: eap-alarm-unified-job-poc

## Change Summary

This change is the first-in-class POC migrating the `eap_alarm` async worker onto
`BaseChunkedDuckDBJob`, the shared template-method base class designed in P0. A new
`EapAlarmJob(BaseChunkedDuckDBJob)` subclass decomposes `[date_from, date_to]` into
daily TIME chunks, fetches alarm events + detail via `OracleArrowReader` in parallel
(ThreadPoolExecutor, `max_parallel=3`), and defers SET/CLEAR pairing to
`post_aggregate` (which reads all chunk parquets together via a DuckDB glob). A new
unified `enqueue_query_job()` entry-point in `async_query_job_service` replaces the
old route-level inline `enqueue_job` pattern and enforces `always_async=True` / 503
semantics. A feature flag `EAP_ALARM_USE_UNIFIED_JOB` (default off) gates new-vs-legacy
path at the route level. The legacy `run_eap_alarm_query_job` is preserved untouched
(AC-8 coexistence). This change settles the BaseChunkedDuckDBJob template contract,
the unified-enqueue/503 decision tree (D3), and the parity-test template (D6) for all
subsequent P2+ domain migrations.

## Final Behavior

- `EAP_ALARM_USE_UNIFIED_JOB=off` (default): route calls `enqueue_job(... worker_fn=run_eap_alarm_query_job ...)`; zero behavior change.
- `EAP_ALARM_USE_UNIFIED_JOB=on`: route calls `enqueue_query_job("eap-alarm", ...)` → `EapAlarmJob.run()` — parallel Oracle fetch → per-chunk parquet accumulation → `post_aggregate` SET/CLEAR pairing → identical spool file at identical key/path.
- Always-async domain: if async unavailable and flag ON → HTTP 503 (`SERVICE_UNAVAILABLE`, `Retry-After`), never silent sync fallback.
- Spool schema, spool key, and all view endpoints are byte-for-row identical to the legacy path (AC-1 parity).

## Final Contracts Updated

| contract | version | change |
|---|---|---|
| `contracts/env/env-contract.md` | 1.0.14 → 1.0.15 | Added `EAP_ALARM_USE_UNIFIED_JOB` (optional, default `off`) |
| `contracts/env/env.schema.json` | same | Added enum + default for new flag |
| `.env.example` + `.env.example.template` | — | Added flag stub with default |
| `contracts/business/business-rules.md` | 1.22.0 → 1.23.0 | Added ASYNC-06 (always-async + 503), EA-ASYNC (eap-alarm flag routing), 3 Decision Table rows |
| `contracts/api/error-format.md` | 1.1.0 → 1.2.0 | Documented 503 Async Unavailable case (distinct from DB unavailable) |
| `contracts/ci/ci-gate-contract.md` | 1.3.25 → 1.3.26 | Additive gate-compatibility note for eap-alarm-unified-job-poc |
| `contracts/CHANGELOG.md` | — | 3 new version entries |

## Final Tests Added / Updated

| file | type | what it pins |
|---|---|---|
| `tests/test_eap_alarm_unified_job.py` (new, 5 classes / 10 tests) | unit | `EapAlarmJob` template overrides, flag dispatch, 503 path, spool key invariant, AC-8 coexistence |
| `tests/test_job_registry.py::TestAlwaysAsyncField` (3 tests) | unit | `JobTypeConfig.always_async` field + eap-alarm registration |
| `tests/test_async_query_job_service.py::TestEnqueueQueryJob` (4 tests) | unit | `enqueue_query_job()` D3 decision tree (async available, 503, spool-hit short-circuit) |
| `tests/test_base_chunked_duckdb_job.py` | unit | base class re-run as changed-area gate |

Total: 89 + 118 tests across targeted / changed-area / contract phases; all passed.

## Final CI/CD Gates

| tier | gate | when |
|---|---|---|
| 0 | `ruff check .` + `cdd-kit validate` | local / pre-push |
| 1 | `unit-and-integration-tests` (backend-tests.yml) | PR push |
| 1 | `cdd-kit gate eap-alarm-unified-job-poc` | PR |
| 1 | `cdd-kit validate --contracts` | PR |
| 1 | `e2e-tests.yml` (`test_eap_alarm_e2e.py`) | manual dispatch per Tier-1 cycle |
| 3 (nightly) | `nightly-integration-real`, `oracle-fault-injection` | deferred (archive-tasks 3.2) |
| 4 (weekly) | `stress-load`, `soak` | deferred (archive-tasks 3.5) |

## Production Reality Findings

- **R1 resolution**: `BaseChunkedDuckDBJob._fan_out_append` was incomplete in P0 (discarded batches). backend-engineer extended the base with a per-chunk parquet sink (`chunk-N.parquet`) so the append pattern is reusable by P2+ migrations without subclass override. Option A (extend base minimally) was chosen over Option B (subclass-only override).

- **ADR-0009 non-obvious flag value**: `EapAlarmJob` uses `requires_cross_chunk_reduction=False` despite a genuine cross-row SET/CLEAR reduction. This is correct because `post_aggregate` re-reads ALL chunk parquets together (DuckDB glob) and applies the reduction there — the flag controls the fan-out phase only, not whether a cross-row reduction exists. ADR-0009 documents this reversal-sensitive decision.

- **always_async field vs per-call arg**: spec-architect recommended `sync_fallback_allowed` as a per-call arg (not a registry field) while `always_async` goes in `JobTypeConfig`. This two-layer split was implemented: registry stores the domain-class invariant (`always_async`), route call passes the request-scoped preference (`sync_fallback_allowed`).

- **E2E deferred**: `test_eap_alarm_e2e.py` covers the flag-OFF path via existing spec; flag-ON GunicornHarness parity is deferred to nightly (archive-task 3.3) per ci-gates.md §Required Gates tier 3.

- **stress-soak-report.md**: The P0 `tier-floor-override` was invalidated when P1 landed the first real `EapAlarmJob` caller (ThreadPoolExecutor + Oracle). `stress-soak-report.md` is required by change-classification.md and authored in `specs/changes/eap-alarm-unified-job-poc/`; Tier 4 weekly gates are deferred (archive-task 3.5) but the report must exist pre-merge per ci-gates.md §Promotion Policy.

## Lessons Promoted to Standards

**L-1 — BJ-01: `requires_cross_chunk_reduction` governs write topology only** (promote-to-contract)
- Target: `contracts/business/business-rules.md` — new `## BaseChunkedDuckDBJob Fan-out Rules` section; schema-version 1.26.0 → 1.26.1
- Rule: `requires_cross_chunk_reduction=False` selects multi-parquet fan-out; any domain whose reduction spans chunk boundaries MUST perform it in `post_aggregate` (DuckDB glob). The flag does NOT mean "no cross-row reduction exists".
- Evidence: design.md §D1; ADR-0009; `tests/test_eap_alarm_unified_job.py` AC-2 seam fixture

**L-2 — P2+ parity-test template (dual-tier: mock-seam unit + real-path parquet diff)** (promote-to-guidance)
- Target (body): `docs/architecture/test-discipline.md` — new section `## P2+ Domain Migration — Dual-Tier Parity Test Template`
- Target (trigger): `CLAUDE.md` — one-liner added to "Test coverage discipline" region
- Evidence: design.md §D6; `tests/test_eap_alarm_unified_job.py` (5 test classes); change-classifier.yml finding "AC-1/AC-8 establish the parity-testing template for all P2+ migrations"

**L-3 — tier-floor-override invalidation upon first real caller** (promote-to-guidance, amendment)
- Target: `CLAUDE.md` — amend existing tier-floor-override bullet to add invalidation condition
- Rule: when the first real caller lands, the P0 override is invalidated; owning change must be Tier 1 and stress-soak-report.md required
- Evidence: change-classifier.yml finding "P0 tier-floor-override invalidated by P1 wiring a real caller; stress/soak now required"; change-classification.md §Optional Artifacts (stress-soak-report.md: yes)

## Follow-up Work

- **Flag promotion** (`EAP_ALARM_USE_UNIFIED_JOB=on`): blocked on nightly AC-4 GunicornHarness parity (archive-task 3.2) + weekly soak evidence (archive-task 3.5).
- **P2+ parity-test template**: every subsequent domain migration must reproduce the D6 dual-tier strategy (mock cross-chunk-seam unit + real parquet-diff integration).
- **Oracle pool lifecycle tests** (`test_oracle_arrow_pool_lifecycle.py`): nightly oracle-fault-injection gate; not yet run against real Oracle.
- **`stress-soak-report.md` Tier 4 evidence**: stress (ThreadPoolExecutor concurrency) and soak (heap linearity) runs deferred to weekly gate post-merge.

## Cold Data Warning

This archive is historical evidence. Current requirements live in `contracts/` and active project guidance (`CLAUDE.md`). Do not treat this file as a specification for future behavior.
