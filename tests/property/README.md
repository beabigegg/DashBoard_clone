# Property-Based Tests

This directory contains [Hypothesis](https://hypothesis.readthedocs.io/) property-based tests (PBT)
for MES Dashboard backend modules. These complement the enumeration-style fuzz tests in
`tests/routes/test_fuzz_routes.py` by systematically exploring the input space.

## Running locally

```bash
# Default (ci profile — 100 examples per test)
conda run -n mes-dashboard pytest -m property -v

# Nightly profile (1000 examples)
HYPOTHESIS_PROFILE=nightly conda run -n mes-dashboard pytest -m property -v

# Fast dev profile (20 examples — iterate quickly while writing tests)
HYPOTHESIS_PROFILE=dev conda run -n mes-dashboard pytest -m property -v

# Single test file
conda run -n mes-dashboard pytest tests/property/test_request_validation_robustness.py -v
```

## Profiles

| Profile | `max_examples` | Use case |
|---------|---------------|----------|
| `ci` (default) | 100 | PR runs — fast feedback |
| `nightly` | 1000 | Nightly deep search |
| `dev` | 20 | Local iteration while writing tests |

Set the active profile with the `HYPOTHESIS_PROFILE` environment variable. The profile is
loaded once in `conftest.py` at collection time.

## Failure shrinking and the example database

When Hypothesis finds a failure it automatically shrinks the input to the minimal reproducing
case and writes it to `.hypothesis/examples/`. On the next run that example is replayed first.

`.hypothesis/examples/` is tracked in git (failure shrinks only — see `.gitignore`). This means
CI and local environments share known-failing cases so failures don't disappear between runs.

To prune a stale failure example, delete the relevant file under `.hypothesis/examples/` and commit.

## Strategy catalogue

All reusable strategies live in `tests/property/strategies.py`.

| Symbol | Type | Description |
|--------|------|-------------|
| `arbitrary_text` | `str` | Unconstrained text including unicode and control chars |
| `short_text` | `str` | Text up to 50 chars |
| `url_safe_text` | `str` | URL-safe characters only, up to 256 chars |
| `nonempty_text` | `str` | 1–200 chars |
| `arbitrary_int` | `int` | Full 32-bit range |
| `page_int` | `int` | –1000 to 10 000 (pagination boundary territory) |
| `size_int` | `int` | –100 to 10 000 (page-size boundary territory) |
| `valid_sort_key` | `str` | One of the known-good yield-alert sort keys |
| `unknown_sort_key` | `str` | Any string NOT in the valid sort-key set |
| `filter_dict` | `dict` | Optional filter keys with list-of-string values |
| `synthetic_row` | `dict` | One DataFrame row (string cells matching filter columns) |
| `synthetic_dataset` | `list[dict]` | 0–50 synthetic rows |
| `valid_date_str` | `str` | ISO-8601 date string |
| `arbitrary_date_str` | `str \| None` | Mix of valid, invalid, empty, and None dates |
| `url_state` | `dict` | Minimal URL state object (tab, input type, values) |

## Adding a new property test

1. **Pick a target**: choose a pure function with a clear contract (validation, codec, normalisation).
2. **Identify the invariant**: what must always hold regardless of input?
   - *Robustness*: never raise an unexpected exception type
   - *Idempotence*: `f(f(x)) == f(x)`
   - *Round-trip*: `decode(encode(x)) == x`
   - *Subset*: filtered result ⊆ unfiltered result
3. **Write the test** with `@pytest.mark.property` and `@given(...)`:

   ```python
   import pytest
   from hypothesis import given
   from tests.property.strategies import arbitrary_text

   @pytest.mark.property
   @given(value=arbitrary_text)
   def test_my_function_robustness(value):
       try:
           result = my_function(value)
           assert result is not None  # or whatever the contract says
       except MyDeclaredError:
           pass  # allowed exception
   ```

4. **Add strategies** to `strategies.py` if the new test needs reusable generators.
5. Run locally with `HYPOTHESIS_PROFILE=dev` first to iterate fast, then `ci` before pushing.
