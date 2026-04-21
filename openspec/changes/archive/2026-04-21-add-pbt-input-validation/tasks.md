## 1. Dependencies & Configuration

- [x] 1.1 Add `hypothesis` (pinned minor version) to `environment.yml` dev section and `requirements-dev.txt`
- [x] 1.2 Run `conda env update -n mes-dashboard -f environment.yml` and verify `hypothesis` import works
- [x] 1.3 Register `property` marker in `pytest.ini` (or `pyproject.toml [tool.pytest.ini_options]`)
- [x] 1.4 Add `.hypothesis/examples/` retention rules and update `.gitignore` to track only failure shrinks

## 2. Test Infrastructure

- [x] 2.1 Create `tests/property/` directory with `__init__.py`
- [x] 2.2 Create `tests/property/conftest.py`: register `ci` (max_examples=100) and `nightly` (max_examples=1000) Hypothesis profiles, select via `HYPOTHESIS_PROFILE` env var
- [x] 2.3 Add a `tests/property/strategies.py` module hosting reusable strategies (text, integers, sort keys, filter dicts)
- [x] 2.4 Write `tests/property/README.md` covering: running locally, switching profiles, strategy catalogue, conventions for adding new tests

## 3. Property Tests — request_validation

- [x] 3.1 Identify the public validation entry points in `src/mes_dashboard/core/request_validation.py` and the declared exception hierarchy
- [x] 3.2 `tests/property/test_request_validation_robustness.py`: arbitrary text input never raises un-typed exceptions
- [x] 3.3 `tests/property/test_request_validation_idempotence.py`: validate(validate(x)) == validate(x)
- [x] 3.4 `tests/property/test_request_validation_integers.py`: integer params (page/size/etc.) clamp or reject according to contract

## 4. Property Tests — URL state codec

- [x] 4.1 Locate URL state encode/decode functions used by query-tool / hold-overview / etc.
- [x] 4.2 `tests/property/test_url_state_roundtrip.py`: structurally valid state survives encode → decode round-trip
- [x] 4.3 `tests/property/test_url_state_decode_robustness.py`: arbitrary URL-safe strings decode to valid state or raise declared `URLStateDecodeError`

## 5. Property Tests — Filter normalisation

- [x] 5.1 Locate filter normalisation functions (query-tool / hold filters / reject filters)
- [x] 5.2 Build a synthetic dataset strategy + filter strategy in `tests/property/strategies.py`
- [x] 5.3 `tests/property/test_filter_subset_invariant.py`: rows matching `normalize(F)` ⊆ rows matching `F`
- [x] 5.4 `tests/property/test_filter_idempotence.py`: `normalize(normalize(F)) == normalize(F)`

## 6. Property Tests — Pagination & sort

- [x] 6.1 `tests/property/test_pagination_safe_defaults.py`: negative/zero `page` clamps to 1, oversized `size` clamps to MAX_PAGE_SIZE
- [x] 6.2 `tests/property/test_sort_allowlist.py`: unknown sort keys raise declared `ValidationError` with stable error code

## 7. CI Integration

- [x] 7.1 Add CI step `pytest -m property` running with `HYPOTHESIS_PROFILE=ci` (advisory / non-blocking for first PR)
- [x] 7.2 If nightly schedule exists, add `pytest -m property` step with `HYPOTHESIS_PROFILE=nightly`
- [x] 7.3 Configure CI to upload `.hypothesis/examples/` artifact on failure for debugging
- [x] 7.4 After two weeks of stable green runs, flip the PR step to blocking

## 8. Verification & Documentation

- [x] 8.1 Run `pytest -m property` locally with both profiles; confirm zero failures (or open follow-up issues for any genuine bugs found)
- [x] 8.2 Run full test suite (`pytest tests/ -v`) to confirm no regression in existing tests
- [x] 8.3 Update `CLAUDE.md` "Project Commands" section with `pytest -m property` entry
- [x] 8.4 Run `openspec validate add-pbt-input-validation --strict` and address any issues
