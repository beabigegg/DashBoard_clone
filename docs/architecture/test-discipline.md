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

## Module-Level Constants — setattr, Not setenv

**Module-level constants frozen at import time cannot be overridden via `monkeypatch.setenv()`.** When a service reads `os.getenv(...)` into a module-level constant (e.g., `_USE_ROW_COUNT_CHUNKING = os.getenv("USE_ROW_COUNT_CHUNKING", "").lower() == "true"`), the value is frozen at the first import. Patching the env var after import has no effect.

**Always patch the attribute directly:**
```python
monkeypatch.setattr("mes_dashboard.services.<service>._USE_ROW_COUNT_CHUNKING", True)
```

The same rule applies to any module-level `requests.Session`, integer constants, or feature-flag booleans.

Evidence: `tests/integration/test_rowcount_flag_parity.py` — all flag-toggle tests use `setattr`.

## Env-Var Contract Tests Must Pin Default Values

**A test that only checks `"VAR_NAME" in contract_text` passes even when the documented default is wrong.** For every env var with a code default, add a companion test that imports the module-level constant and asserts it equals the value stated in `env-contract.md`.

Pattern: `tests/test_env_contract.py::TestEngineDefaultsMatchContract` — caught BQE-05 (contract said `prod=3`, code default was `5`).

Evidence: `batch-rowcount-unification`.

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
