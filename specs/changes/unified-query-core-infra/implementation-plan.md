---
change-id: unified-query-core-infra
schema-version: 0.1.0
last-changed: 2026-06-18
---

# Implementation Plan: unified-query-core-infra

## Objective

Ship three new, caller-less `core/` infrastructure modules plus their env and
data-shape contract additions and tests, establishing the
"Oracle parallel chunk → pyarrow RecordBatch → DuckDB (on-disk spill) →
canonical parquet spool" pipeline that all P1–P5 domain migrations will build on.
No existing route, service, worker, or frontend module is touched. The diff must
be confined to: 3 new `core/*.py` files, env contract files, the data-shape
contract, and new test files. (AC-1..AC-8)

## Execution Scope

### In Scope
- `src/mes_dashboard/core/oracle_arrow_reader.py` (new) — D3/D6 streaming reader + lazy per-worker pool
- `src/mes_dashboard/core/query_cost_policy.py` (new) — D5 4-layer cost classifier + per-domain `CostPolicy`
- `src/mes_dashboard/core/base_chunked_duckdb_job.py` (new) — D1/D2/D7 template-method base class
- Env contract: add `DUCKDB_JOB_DIR`; deprecate (do not remove) the `*_ASYNC_DAY_THRESHOLD` vars (D4, D5)
- Data-shape contract: document Oracle → Arrow RecordBatch → DuckDB/parquet streaming boundary + row-level invariants
- New unit / contract / integration / data-boundary / resilience tests

### Out of Scope
- Migrating any domain (eap_alarm, production, reject, resource, material_trace, downtime) — that is P1+
- Modifying any existing route, service, worker, frontend, or `batch_query_engine.py` logic
- Removing `*_ASYNC_DAY_THRESHOLD` vars (removal is P5 per deprecate-2-minors)
- Wiring the 3 modules to any caller (they ship with zero callers; verified by AC-7)
- New pip dependencies (use existing `oracledb`, `pyarrow`, `duckdb`, stdlib `threading`/`concurrent.futures`)
- New CI workflow files (existing pytest discovery already covers `tests/`)

## Required Changes

| id | area | required action | owner agent |
|---|---|---|---|
| IP-1 | core/oracle_arrow_reader.py | New `OracleArrowReader`: lazy per-worker session pool (min=2, max=12–15), `chunk_iter(sql, params, chunk_size) -> Iterator[pyarrow.RecordBatch]`, one conn per call with `finally: conn.close()`, no pandas. Per D3/D6. | backend-engineer |
| IP-2 | core/query_cost_policy.py | New `CostPolicy` record + `classify_query_cost(domain, params) -> Literal["SYNC","ASYNC"]` with 4-layer short-circuit L0→L1→L2→L3; emit deprecation warning when `*_ASYNC_DAY_THRESHOLD` env still read. Per D5. | backend-engineer |
| IP-3 | core/base_chunked_duckdb_job.py | New `BaseChunkedDuckDBJob(ABC)` + `ChunkStrategy` enum; `run()` template method; abstract hooks; two reduction paths keyed by `requires_cross_chunk_reduction`; `writer_lock: threading.Lock`; progress bracket 5→15→90→100; job-temp create/delete in `finally`. Per D1/D2/D7. | backend-engineer |
| IP-4 | contracts/env | Add `DUCKDB_JOB_DIR` (default `{QUERY_SPOOL_DIR}/../duckdb_jobs`) to env-contract.md + .env.example.template + env.schema.json; add deprecation notices to `*_ASYNC_DAY_THRESHOLD` rows. Per D4. | backend-engineer |
| IP-5 | contracts/data | Add data-shape section for Oracle → Arrow RecordBatch → DuckDB/parquet boundary + chunk row-level invariants. | backend-engineer |
| IP-6 | tests (unit/contract/data-boundary/resilience) | Author unit + contract + data-boundary + resilience tests (mock Oracle). | test-strategist + backend-engineer |
| IP-7 | tests/integration | Author real-infra integration tests (`pytestmark = pytest.mark.integration_real`). | test-strategist + backend-engineer |
| IP-8 | ci-gates | Confirm `backend-tests.yml` discovers the 3 new root-level test files; confirm `tests/integration/` runs nightly only; no new workflow. Fill `ci-gates.md`. | ci-cd-gatekeeper |
| IP-9 | contract review | Review env + data-shape additions; confirm no API/business drift; confirm `DUCKDB_JOB_DIR` default matches D4. | contract-reviewer |
| IP-10 | qa | Tier-1 gate: AC-1..AC-8 met, `test-evidence.yml` complete, no waiver fields. | qa-reviewer |

## Source Artifact Pointers

| source | relevant pointer | used for |
|---|---|---|
| design.md | D1 (ChunkStrategy taxonomy) | `ChunkStrategy` enum values TIME/ID_LIST/ROW_COUNT/SINGLE in IP-3 |
| design.md | D2 (two reduction paths) | `requires_cross_chunk_reduction` False=multi-parquet append / True=single DuckDB + writer_lock in IP-3 |
| design.md | D3 (per-worker lazy pool) | pool created post-fork on first access, never at import (ADR-0004) in IP-1 |
| design.md | D4 (`DUCKDB_JOB_DIR` default) | pinned default `{QUERY_SPOOL_DIR}/../duckdb_jobs` in IP-4 |
| design.md | D5 (4-layer cost policy) | L0..L3 short-circuit order + deprecation in IP-2 |
| design.md | D6 (Arrow streaming, pool sizing) | one conn/chunk, `finally: conn.close()`, min=2/max=12–15 in IP-1 |
| design.md | D7 (job-temp lifecycle) | `{DUCKDB_JOB_DIR}/{namespace}/{job_id}.duckdb`, delete in finally, TTL orphan reaper in IP-3 |
| query-dataflow-unification.md | §4.1 `BaseChunkedDuckDBJob` pseudocode | `run()` step sequence + hook signatures in IP-3 |
| query-dataflow-unification.md | §4.2 pool strategy | two-level concurrency, conn return discipline in IP-1/IP-3 |
| query-dataflow-unification.md | §6 First Milestone acceptance | scope-limit: only build the abstractions, no eap_alarm POC here |
| cache-spool-patterns.md | §Type B async (progress bracket) | coarse 5→15→90→100 in IP-3 |
| docs/adr/0003 | row-chunking exclusion | SINGLE/group-key path for cross-row reduction in IP-3 |
| docs/adr/0004 | preload/fork-safety | lazy post-fork pool justification in IP-1 |
| test-plan.md | AC→test mapping table | tests to write/run (filled by test-strategist) |
| ci-gates.md | required gates table | verification commands (filled by ci-cd-gatekeeper) |

## File-Level Plan

| path or glob | action | notes |
|---|---|---|
| src/mes_dashboard/core/oracle_arrow_reader.py | create | `from __future__ import annotations`; `OracleArrowReader` class; `__init_pool()` lazy (min=2, max=12–15) post-fork; `chunk_iter(sql, params, chunk_size) -> Iterator[pyarrow.RecordBatch]`; acquire one conn, `finally: conn.close()`; never returns pandas. Build before IP-3. |
| src/mes_dashboard/core/query_cost_policy.py | create | `CostPolicy` (namedtuple/dataclass: always_async, day_threshold, row_threshold, row_count_fn); `classify_query_cost(domain, params)` L0 spool-hit→SYNC, L1 always-async (trace/eap_alarm/msd)→ASYNC, L2 date_span≥threshold→ASYNC, L3 COUNT(*)≥row_threshold(200k)→ASYNC; `warnings.warn(DeprecationWarning)` on `*_ASYNC_DAY_THRESHOLD` read. No DB calls at import. |
| src/mes_dashboard/core/base_chunked_duckdb_job.py | create | imports OracleArrowReader; `ChunkStrategy(Enum)` = TIME/ID_LIST/ROW_COUNT/SINGLE; `BaseChunkedDuckDBJob(ABC)` attrs namespace/job_prefix/requires_cross_chunk_reduction/chunk_strategy/max_parallel; abstract `pre_query`/`build_chunk_sql`/`post_aggregate`; default `chunk_to_duckdb`/`progress_report`; `run()` template; `writer_lock = threading.Lock()`; `_open_job_duckdb`/`_cleanup_job_duckdb` (delete in `finally`); two reduction paths per D2. Build last. |
| contracts/env/env-contract.md | edit | Add `DUCKDB_JOB_DIR` row (storage; default `{QUERY_SPOOL_DIR}/../duckdb_jobs`; relative→CWD, abs for Docker; restart required) + prose entry. Add "**Deprecated** (removal P5)" note + warning text to each `*_ASYNC_DAY_THRESHOLD` row. Bump `schema-version`. |
| contracts/env/.env.example.template | edit | Add `DUCKDB_JOB_DIR=` example line matching the pinned default. |
| contracts/env/env.schema.json | edit | Add `DUCKDB_JOB_DIR` property (type string, default = pinned value, description). |
| contracts/data/data-shape-contract.md | edit | New section: Oracle → pyarrow RecordBatch → DuckDB/parquet streaming boundary; invariants: no row duplication across chunks, no row loss, no pandas in path, Oracle DATE/CHAR strip semantics, null/empty-chunk handling. |
| tests/test_oracle_arrow_reader.py | create | unit + data-boundary (mock Oracle); see Test Execution Plan. |
| tests/test_query_cost_policy.py | create | unit (4 layers + short-circuit + deprecation warning). |
| tests/test_base_chunked_duckdb_job.py | create | unit (4 strategies × 2 reduction paths, hook order, progress, writer_lock). |
| tests/contract/test_env_duckdb_job_dir.py | create | pins `DUCKDB_JOB_DIR` name AND default value. |
| tests/integration/test_oracle_arrow_pool_lifecycle.py | create | `pytestmark = pytest.mark.integration_real`; pool exhaustion+recovery, writer_lock under concurrent chunks, job-temp lifecycle + orphan TTL. |

## Contract Updates

- API: none (no HTTP endpoints).
- CSS/UI: none.
- Env: add `DUCKDB_JOB_DIR` (pinned default `{QUERY_SPOOL_DIR}/../duckdb_jobs`, D4) to env-contract.md + .env.example.template + env.schema.json; deprecate (not remove) `*_ASYNC_DAY_THRESHOLD` vars with runtime warning. See IP-4.
- Data shape: document Oracle → Arrow RecordBatch → DuckDB/parquet streaming boundary + chunk row-level invariants in data-shape-contract.md. See IP-5.
- Business logic: none — `classify_query_cost` is infrastructure routing policy, not an MES domain rule (per classification §2.5).
- CI/CD: no new workflow; confirm `backend-tests.yml` covers new tests and that `tests/integration/` is nightly-only (ci-gates.md, IP-8).

## Test Execution Plan

| acceptance criterion | test file / command | expected signal |
|---|---|---|
| AC-1 | tests/test_base_chunked_duckdb_job.py | `run()` invokes pre_query→build_chunk_sql→chunk_to_duckdb→post_aggregate→progress in order; all 4 ChunkStrategy values dispatch correctly |
| AC-2 | tests/test_base_chunked_duckdb_job.py | `requires_cross_chunk_reduction=False` → multi-parquet append, no writer_lock contention; `=True` → serialized INSERT under writer_lock into one DuckDB file |
| AC-3 | tests/test_oracle_arrow_reader.py | `chunk_iter` yields `pyarrow.RecordBatch`; one conn/call; `finally: conn.close()` returns conn even on mid-chunk error (mock Oracle) |
| AC-3 | tests/integration/test_oracle_arrow_pool_lifecycle.py | real pool exhaustion then recovery; no leaked connections (nightly real-infra lane) |
| AC-4 | tests/test_query_cost_policy.py | 4-layer short-circuit returns correct SYNC/ASYNC; earlier layer short-circuits later; L0 spool-hit→SYNC overrides all |
| AC-5 | tests/integration/test_oracle_arrow_pool_lifecycle.py | job-temp created at `{DUCKDB_JOB_DIR}/{namespace}/{job_id}.duckdb`, deleted on completion; mid-job failure releases conn + cleans temp; orphan TTL reaps survivors |
| AC-6 | tests/contract/test_env_duckdb_job_dir.py | asserts `DUCKDB_JOB_DIR` present in env-contract.md, .env.example.template, env.schema.json AND default value matches D4 |
| AC-7 | tests/test_query_cost_policy.py / cdd-kit gate diff scope | no new pip dep; grep proves zero callers of the 3 modules outside tests; diff confined to allowed paths |
| AC-8 | tests/test_oracle_arrow_reader.py | data-boundary: null/empty chunk, Oracle DATE midnight-UTC, CHAR strip handled without row loss/dup |
| (deprecation) | tests/test_query_cost_policy.py | `DeprecationWarning` raised when a `*_ASYNC_DAY_THRESHOLD` env var is read |

Required test phases (floor): `collect`, `targeted`, `changed-area`; add `contract`
(env + data-shape affected) and `full` for final/CI. Integration tests are
nightly-only (`integration_real`), not run in pre-merge targeted/changed-area
phases. Implementation agents generate evidence via `cdd-kit test run`; full
ladder lives in test-plan.md / references/sdd-tdd-policy.md.

## Handoff Constraints

- Implementation agents must not infer missing requirements from chat history.
- Do not re-copy full design, test strategy, CI policy, or contract prose into this plan; follow the source pointers above.
- If this plan omits a required file, behavior, contract, or test, stop and report `blocked`.
- Keep implementation within the file-level plan unless a Context Expansion Request is approved.
- Build order is load-bearing: IP-1 (oracle_arrow_reader) → IP-2 (query_cost_policy) → IP-3 (base_chunked_duckdb_job), because base_chunked_duckdb_job imports OracleArrowReader.
- The 3 modules MUST ship with zero callers; do NOT wire eap_alarm or any domain (that is P1, out of scope).

## Known Risks

- **`*_ASYNC_DAY_THRESHOLD` count mismatch.** Design/classification say "7 vars" but env-contract.md currently documents only 3 (`DOWNTIME_`, `HOLD_`, `RESOURCE_`); architecture §1.3/§2.2 imply production/reject/yield/msd route via spool-miss, not a day threshold. backend-engineer must enumerate the actual deployed set (grep `src/`, `config/`, `.env.example.template`) and deprecate whatever exists — do NOT invent vars to reach 7. Flag to contract-reviewer if the set differs from 3.
- **Fork-safety.** A pool created at import would corrupt under `preload_app=True` (ADR-0004). The lazy-post-fork requirement (D3) is easy to violate; the integration test must assert no pool object exists pre-first-access.
- **ADR-0003 seam-safety is design-time only.** A domain mis-classified as ROW_COUNT/TIME would silently halve cross-row aggregates. Not exploitable here (no domain wired), but `ChunkStrategy` + `requires_cross_chunk_reduction` must be authored so a future domain cannot pick ROW_COUNT/TIME with cross-chunk reduction without an explicit override.
- **DuckDB single-writer.** writer_lock serialization is correctness-critical for the `=True` path; the concurrent-chunk integration test must prove no interleaved/corrupted writes.
- **Oracle session quota.** Pool max 12–15 per worker × N workers may exceed DBA budget — out of scope to resolve here, but note for P1 enablement (design Open Risks).
- ci-gates.md and test-plan.md are still scaffolds at planning time; ci-cd-gatekeeper (IP-8) and test-strategist (IP-6/IP-7) must fill them before the gate. This plan's Test Execution Plan is the fallback AC→test map until then.
