# Test Coverage Discipline

These rules exist because the project shipped a class of "silent drop" bugs — a route ignored a filter param; a snapshot path bypassed a filter; a cross-filter dropdown didn't narrow. These bugs shipped through CI green because the tests asserted *what the code did*, not *what the code should do*. See commit `e002c4c` for the systemic remediation.

## Do NOT Use mock.assert_called_once_with() as a Kwarg Whitelist

`mock.assert_called_once_with(...)` requires *exact* kwargs equality. Adding a new param to the production call breaks the assert; the standard "fix" is to add the new param to the call — which silently re-allows the same param to be dropped later.

**Prefer:**
```python
mock_service.assert_called_once()
assert mock_service.call_args.kwargs['bop'] == 'EAC17'
assert mock_service.call_args.kwargs['workflow'] == 'WF1'
```

Evidence: hold-overview route silently dropped `workflow/bop/pj_function` because three independent `assert_called_once_with(...)` blocks omitted them.

## Route Forwarding — Assert Per-Kwarg with Non-Default Values

For every request parameter a Flask route reads, write a test that supplies a non-default value (`?bop=EAC17`) and asserts `mock_service.call_args.kwargs['bop'] == 'EAC17'`. A test that only checks happy-path empty defaults cannot detect a missing `args.get(...)` at the route layer.

## Test Both Snapshot and Oracle Paths

**Services with a snapshot/cache path AND an Oracle fallback must have tests on BOTH paths for every filter kwarg.** Tests that only stub `read_sql_df` (Oracle path) leave the snapshot path — which dominates production traffic when Redis is warm — completely unverified.

The snapshot path lives behind `_get_wip_dataframe()` / `get_cached_wip_data()` / `_get_*_snapshot()`; mock at that layer with a DataFrame fixture that includes the filter column being tested.

Evidence: `get_hold_detail_summary` / `get_hold_detail_lots` / `get_wip_hold_summary` all silently dropped `bop`/`workflow`/`pj_function` on the snapshot path in production.

## Filter Fixtures Must Include EVERY Filter Column

**If `_apply_non_indexed_filters` reads `BOP`/`WORKFLOWNAME`/`PJ_FUNCTION` but the fixture DataFrame only has indexed columns, the function silently no-ops on those filters and the test passes regardless.** When extending a filter, add the column to existing fixtures or write a new fixture-builder helper.

Evidence: `_sample_hold_df()` in `tests/test_wip_service.py` was missing all three non-indexed columns for months.

## Cross-Filter Narrowing Has Its Own Test Surface

For every page with multi-dropdown filters, write tests that assert **"selecting A narrows B"**. Cover at minimum:
- Single-value narrowing
- CSV multi-value union
- Pairwise intersection (A AND B)
- Exclude-self property (selecting `bop=X` should still show all BOP values in the bops dropdown)

Canonical pattern: `tests/test_wip_service.py::TestFilterOptionsCrossFilterNarrowing` and `tests/test_container_filter_cache.py::test_cross_filter_*`

Pages that intentionally do NOT cross-filter should pin that contract with an explicit "does_not_narrow" test. Example: `tests/test_reject_history_service.py::test_get_filter_options_does_not_narrow_packages_by_selection`

## One-of-N-Required Filter Axes — Test Each Axis Empty, Not Just Non-Empty

For validation rules requiring "at least one of N optional axes," test each axis being the EMPTY one while a sibling axis is populated — not just each axis non-empty in isolation. The empty-axis branch often triggers different code (e.g. an `IN ()` vs `1=1` no-op) that isolated non-empty tests never exercise.

Evidence: `eap-alarm-coarse-filter` — `_build_equipment_filter([])` produced invalid SQL (`ORA-00936`) for the EA-08-legal combo `eqp_types=[]` + non-empty `product_lines`; round-1 tests covered `eqp_types`-non-empty and `product_dims`-non-empty separately, never together.

## Module-Level Constants — setattr, Not setenv

**Module-level constants frozen at import time cannot be overridden via `monkeypatch.setenv()`.** When a service reads `os.getenv(...)` into a module-level constant (e.g., `_USE_ROW_COUNT_CHUNKING = os.getenv("USE_ROW_COUNT_CHUNKING", "").lower() == "true"`), the value is frozen at the first import. Patching the env var after import has no effect.

**Always patch the attribute directly:**
```python
monkeypatch.setattr("mes_dashboard.services.<service>._USE_ROW_COUNT_CHUNKING", True)
```

The same rule applies to any module-level `requests.Session`, integer constants, or feature-flag booleans.

Evidence: `tests/integration/test_rowcount_flag_parity.py` — all flag-toggle tests use `setattr`.

## Threaded Tests — Apply All Monkeypatches Before Thread Launch

**In tests that spawn worker threads, all `monkeypatch.setattr()` calls must complete before any threads are launched.** Using `patch()` or `patch.object()` inside thread bodies causes a concurrent restore race: whichever thread exits last restores the original attribute, overwriting patches still needed by concurrently running threads — and because Python's `unittest.mock` does global attribute teardown, it can leave stale mocks visible to test modules that run afterward.

```python
# CORRECT — all patches before thread launch
monkeypatch.setattr("mes_dashboard.services.hold_query_job_service._HOLD_USE_RQ", True)
monkeypatch.setattr("mes_dashboard.core.global_concurrency.HEAVY_QUERY_MAX_CONCURRENT", 3)
threads = [threading.Thread(target=worker) for _ in range(N)]
for t in threads: t.start()
for t in threads: t.join()

# WRONG — patch() inside thread body; __exit__ on thread teardown restores attribute mid-run
def worker():
    with patch("mes_dashboard.services.hold_query_job_service._HOLD_USE_RQ", True):
        ...  # races with other threads' teardown
```

Evidence: `rq-semaphore-wiring` — `tests/integration/test_rq_semaphore_wiring.py` replaced `patch()`-in-threads with `monkeypatch`-before-threads after `tests/test_hold_dataset_cache.py::test_long_range_triggers_engine` failed with `RuntimeError: oracle fault` in test run `test-runs/20260620-100337` due to the concurrent attribute restore race.

## Env-Var Contract Tests Must Pin Default Values

**A test that only checks `"VAR_NAME" in contract_text` passes even when the documented default is wrong.** For every env var with a code default, add a companion test that imports the module-level constant and asserts it equals the value stated in `env-contract.md`.

Pattern: `tests/test_env_contract.py::TestEngineDefaultsMatchContract` — caught BQE-05 (contract said `prod=3`, code default was `5`).

Evidence: `batch-rowcount-unification`.

## Enum-Validated Identifiers Used in Exact-Match SQL — Verify Against Real Data

Before shipping a closed-enum validation rule for a field later used in an exact-match SQL clause (`col IN (...)`), pull a live read-only sample and confirm the enum's format actually equals real column values — not just a display-derived prefix/format. A format mismatch means every legally-validated request silently matches zero rows.

Evidence: `eap-alarm-coarse-filter` EA-07 — a closed 10-value `eqp_types` enum (4-char codes) was validated against a format that never equals real `EQUIPMENT_ID` values (`<prefix>-<instance>`, e.g. `GWBK-0241`); dead code from ship (2026-06-30) to discovery (2026-07-01), confirmed via live 17/17 `RESOURCENAME`-to-`EQUIPMENT_ID` sample.

## Check pytestmark Before Adding Tests to tests/integration/

**Files like `tests/integration/test_oracle_error_path.py` carry `pytestmark = pytest.mark.integration_real` at the top**, which silently skips all tests in that module unless `pytest --run-integration-real` is passed. A mock-based test placed there will appear to pass in CI because it is simply skipped, not executed.

Keep mock-based tests in an unmarked file (e.g., `tests/integration/test_rowcount_flag_parity.py`).

Evidence: `batch-rowcount-unification` — `TestPartialChunkFailure` would have been silently skipped if placed in `test_oracle_error_path.py`.

## Use ast.parse() to Prove Absence of Removed Startup Calls

**When a daemon thread call or startup side-effect is removed from `app.py`, a mock-based test cannot prove absence** — if the call were accidentally re-added, mocks would simply run it normally and still pass.

Use `ast.parse(source)` and walk `ast.Call` nodes to assert the removed function name does NOT appear anywhere in the file. This permanently blocks re-introduction without a test failure.

```python
import ast
source = Path("src/mes_dashboard/app.py").read_text()
tree = ast.parse(source)
call_names = {n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call) and hasattr(n.func, 'id')}
assert 'start_duckdb_prewarm' not in call_names
```

Pattern: `tests/test_app_startup.py::TestDaemonPrewarmRemovedFromApp`

Evidence: `unify-duckdb-prewarm-rq`.

## Partial-Trackout Fixtures — Different TRACKINQTY Per Session

**Always include at least one fixture where partials of the same `TRACKINTIMESTAMP` have *different* `TRACKINQTY` values** (use real arithmetic: `TRACKINQTY[N+1] = TRACKINQTY[N] − TRACKOUTQTY[N]`). A fixture with uniform `TRACKINQTY` across partials cannot distinguish a 4-key from a 5-key aggregation design — both pass.

Evidence: `tests/test_production_history_sql_runtime.py::test_partial_merge_same_trackin_time_different_trackin_qty`

## P2+ Domain Migration — Dual-Tier Parity Test Template

Every domain migrated onto `BaseChunkedDuckDBJob` must reproduce two test tiers:

1. **Unit tier (chunk-seam fixture)**: mock `OracleArrowReader.chunk_iter` with Arrow batches that straddle a chunk seam (e.g., a SET event in chunk-1, its CLEAR in chunk-2). Assert that `post_aggregate` produces exactly one paired row — not two orphaned half-rows. Proves cross-seam reduction correctness without Oracle.

2. **Integration tier (parquet diff)**: run both the legacy `worker_fn` and the new `BaseChunkedDuckDBJob` subclass against the same seeded spool input. Diff the two output parquets: schema equality (column names + types), rowcount equality, and order-insensitive row-set equality on the business key (e.g., `(EQP_ID, ALARM_ID, ALARM_START)`). Count-only parity misses pairing regressions when the EAV pivot moves from pandas to DuckDB SQL.

Evidence: `eap-alarm-unified-job-poc` design.md §D6; `tests/test_eap_alarm_unified_job.py` (5 test classes); change-classifier findings "AC-1/AC-8 establish the parity-testing template for all P2+ migrations".

## Async Route↔Worker Signature Contract — Bind-Test Required

**A route unit test that mocks `enqueue_query_job`/`enqueue_job_dynamic` must ALSO assert the enqueued kwargs bind to the worker entry function's signature** — mocking the enqueue call only proves the route calls it, never that the shape is consumable by the worker. `enqueue_job_dynamic` builds `kwargs={"job_id": ..., **params}`; if the worker signature is `(job_id, params)`, the route must nest `params={"params": {...}}` — a flat `params={start_date, end_date}` spreads into unexpected top-level kwargs, raising `TypeError` only at worker runtime.

```python
route_params = mock_enqueue.call_args.kwargs["params"]
rq_kwargs = {"job_id": "test-id", **route_params}
inspect.signature(worker_fn).bind(**rq_kwargs).apply_defaults()  # TypeError if shape mismatches
```

Pattern: `tests/test_production_achievement_routes.py::test_report_enqueue_params_bind_to_worker_signature`.

Evidence: `production-achievement-async-spool` PV-2 — found only by driving the real enqueue→worker flow; the mocked route tests had passed CI with the wrong (flat) shape.

## _APPROVED_CALLERS — New Controlled-Module Callers Must Be Explicitly Approved

`tests/test_query_cost_policy.py::TestNoPandasAndNoCallers::test_no_caller_outside_tests` enforces a zero-caller policy for controlled internal modules (`oracle_arrow_reader`, `query_cost_policy`, `base_chunked_duckdb_job`). Any source file that **intentionally** imports from one of these must be added to the `_APPROVED_CALLERS` dict **in the same PR**:

```python
_APPROVED_CALLERS: dict = {
    "oracle_arrow_reader": {"material_trace_duckdb_runtime"},
    "base_chunked_duckdb_job": {"eap_alarm_worker", ..., "material_trace_duckdb_runtime"},
}
```

Missing entry → CI failure: `"Found caller of oracle_arrow_reader in src/…/your_module.py — If this is intentional, add 'your_module' to _APPROVED_CALLERS['oracle_arrow_reader']."` Also update `tests/test_job_registry.py` count when adding a new job type via `register_job_type()`.

Evidence: `material-trace-streaming-migration` (tests/test_query_cost_policy.py:L336, tests/test_job_registry.py:L220).

## Cross-Change Spec Gaps — xfail(strict=True) as Tripwire

When an async worker path and a sync path produce structurally different outputs (column name casing, field naming, envelope shape) and the gap is acknowledged but deferred to a future change, mark the schema-parity test with `pytest.mark.xfail(strict=True, reason="...")` — **not** `xfail` without `strict`, and not `skip`.

**Why `strict=True`?** Plain `xfail` silently passes (xfail-consumed) if the test unexpectedly starts passing — meaning an accidental half-fix of the gap would go undetected. `strict=True` converts the expected-failure into a tripwire: if the test passes before the `xfail` is explicitly removed, CI fails with `XPASS`. This ensures the gap cannot be accidentally closed without a deliberate decision to remove the marker.

**How to resolve:** When the assembly layer is implemented, remove the `xfail` decorator; the test becomes a required green assertion.

```python
@pytest.mark.xfail(
    strict=True,
    reason="AC-7: async spool emits raw Oracle column names (LOTID, WIP_STATUS); "
           "sync path returns camelCase (lotId, wipStatus). "
           "Resolve before worker activation."
)
def test_async_row_schema_matches_sync_path():
    ...
```

Evidence: `wip-rq-worker-chunks-cleanup` `tests/integration/test_wip_rowcount_rq_routing.py::TestAsyncRowSchemaMatchesSyncPath`; qa-reviewer.yml ac-summary.

## Over-Limit Boundary Tests Must Strictly Exceed the Cap

When testing that a configurable limit (date range, row count, file size) is enforced, the test input must strictly *exceed* the cap — not equal it. An input that equals the cap passes validation (inclusive upper-bound check) and silently routes to the success path, making the test assert the wrong branch without ever failing.

**Pattern:**
```python
# BAD — 2025-01-01 to 2025-12-31 is exactly 365 days = cap → passes validation → test hits enqueue path
start_date, end_date = "2025-01-01", "2025-12-31"

# GOOD — range strictly exceeds 365-day cap → validation fires → assert rejection keyword
start_date, end_date = "2024-01-01", "2025-03-01"
assert "天" in response.json["message"]  # or whatever the rejection token is
```

Evidence: `rh-primary-prefilter` backend-engineer.yml §known-risks #3; commit `6988392b` fixed `test_query_rejects_date_range_over_half_year` reaching the enqueue path instead of the rejection path.

## Legacy Test Suite — Constant Pin Drift

`tests/legacy/*.test.js` runs as a glob in CI (`node --test tests/legacy/*.test.js`); a stale pin in any file fails the entire suite.

When a commit changes a module-level constant (e.g., `PRIMARY_QUERY_MAX_DAYS`) or a manifest-derived structure (e.g., drawer order arrays in `navigationManifest.js`), grep `tests/legacy/` for the old value and update all pin assertions in the same commit.

Evidence: `rh-remove-supplementary-filter` archive.md §Production Reality Findings #6; commit `6988392b` fixed `reject-history-date-range-limit.test.js` (190→365) and `portal-shell-navigation.test.js` (drawer order `[1,2,3,4,6]`→`[1,2,3,4,5]`).
