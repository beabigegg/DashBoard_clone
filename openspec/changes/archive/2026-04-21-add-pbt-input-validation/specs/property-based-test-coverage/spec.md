## ADDED Requirements

### Requirement: Property-based tests SHALL exist under `tests/property/`
The repository SHALL contain a dedicated `tests/property/` directory housing all `hypothesis`-based property tests, with a `conftest.py` that registers `ci` and `nightly` Hypothesis profiles.

#### Scenario: Directory and conftest exist
- **WHEN** the test suite is collected
- **THEN** `tests/property/` SHALL exist with `__init__.py` and `conftest.py`
- **THEN** `conftest.py` SHALL register at least two Hypothesis profiles named `ci` (max_examples=100) and `nightly` (max_examples=1000)

#### Scenario: Profile selectable via environment variable
- **WHEN** pytest is invoked with `HYPOTHESIS_PROFILE=nightly`
- **THEN** the `nightly` profile SHALL be active and `max_examples` SHALL be 1000

### Requirement: Hypothesis SHALL be a managed development dependency
`hypothesis` SHALL appear in `environment.yml` (dev section) and `requirements-dev.txt` with a pinned minor version.

#### Scenario: Dependency present
- **WHEN** a developer runs `conda env update -n mes-dashboard -f environment.yml`
- **THEN** `hypothesis` SHALL be installed at the pinned minor version

### Requirement: Pytest SHALL recognise a `property` marker
`pytest.ini` (or equivalent config) SHALL register a `property` marker so tests can be filtered with `pytest -m property`.

#### Scenario: Marker filter selects only property tests
- **WHEN** `pytest -m property` runs
- **THEN** only tests under `tests/property/` (or otherwise marked `@pytest.mark.property`) SHALL execute

### Requirement: `core/request_validation` SHALL have property tests covering robustness, idempotence and round-trip
A property test module SHALL exercise `core/request_validation.py` with Hypothesis-generated inputs to verify validation behaviour.

#### Scenario: Arbitrary text input does not raise unexpected exceptions
- **WHEN** Hypothesis generates arbitrary `text()` (including unicode, control chars, very long strings) as a candidate parameter
- **THEN** validation SHALL either return a structured result or raise an exception type from the declared validation-error hierarchy
- **THEN** validation SHALL NEVER raise `Exception`, `KeyError`, `IndexError`, `AttributeError`, `TypeError`, or `ValueError` directly

#### Scenario: Validation is idempotent
- **WHEN** a candidate input passes validation once and produces normalised value `V1`
- **THEN** revalidating `V1` SHALL produce the same value `V1` (no further mutation)

#### Scenario: Out-of-range integers degrade safely
- **WHEN** Hypothesis generates integers including negative, zero, and values larger than the documented maximum for paginated parameters (e.g. `page`, `size`)
- **THEN** validation SHALL clamp / reject according to the documented contract WITHOUT raising un-typed exceptions

### Requirement: URL state codec SHALL have property tests verifying round-trip integrity
A property test module SHALL verify that the URL-state encode/decode pair (used by query-tool and similar pages) preserves semantically equivalent state.

#### Scenario: Encode then decode round-trips
- **WHEN** Hypothesis generates a structurally valid state object `S`
- **THEN** `decode(encode(S))` SHALL be semantically equal to `S` (same fields, same values, possibly normalised)

#### Scenario: Decode of arbitrary string does not crash
- **WHEN** Hypothesis generates arbitrary URL-safe strings
- **THEN** `decode(input)` SHALL return either a valid dict (possibly empty) or raise `ValueError` from malformed percent-encoding, never an unhandled exception
- **NOTE**: The URL state codec is implemented in frontend JavaScript (`query-tool/App.vue`). Python-side tests verify `urllib.parse.parse_qs`, which is what `flask.request.args` builds on. No Python `URLStateDecodeError` type exists.

### Requirement: Filter normalisation SHALL have property tests verifying semantic-subset invariant
A property test module SHALL verify that filter normalisation does not widen the result set: any data point matching the normalised filter MUST also match the original filter.

#### Scenario: Normalised filter result set is a subset
- **WHEN** Hypothesis generates a raw filter `F` and a sample dataset `D`
- **THEN** the set of rows in `D` matching `normalize(F)` SHALL be a subset of the rows matching `F` (i.e. normalisation never adds matches)

#### Scenario: Normalisation is idempotent
- **WHEN** a filter `F` is normalised to produce `F1`
- **THEN** `normalize(F1)` SHALL equal `F1`

### Requirement: Pagination & sort parameters SHALL have property tests verifying safe defaults
A property test module SHALL verify that pagination (`page`, `size`, `offset`) and sort parameters degrade to documented defaults rather than crashing on adversarial input.

#### Scenario: Negative or zero page degrades to default
- **WHEN** Hypothesis supplies `page <= 0`
- **THEN** the validated `page` SHALL be set to the documented default (`1`) AND no exception SHALL be raised

#### Scenario: Oversized size is clamped
- **WHEN** Hypothesis supplies `size > MAX_PAGE_SIZE`
- **THEN** the validated `size` SHALL be clamped to `MAX_PAGE_SIZE` AND no exception SHALL be raised

#### Scenario: Unknown sort key degrades to documented default
- **WHEN** Hypothesis supplies a sort key not in the allow-list
- **THEN** the sort key SHALL be silently normalised to the default key (`date_bucket`) AND no exception SHALL be raised
- **NOTE**: `yield_alert_service.VALID_SORT_FIELDS` / `yield_alert_dataset_cache.get_alerts` use silent degradation, not rejection. Any future validation layer that raises `ValidationError` must be tested separately.

### Requirement: Hypothesis example database SHALL persist failure cases for reproduction
The Hypothesis example database SHALL be configured so that failure-shrinking outputs are persisted to a known location and can be replayed in CI and locally.

#### Scenario: Failure shrinks are written to the example database
- **WHEN** a property test fails under Hypothesis
- **THEN** the minimised failing example SHALL be written under `.hypothesis/examples/`
- **THEN** subsequent test runs SHALL replay this example before generating new ones

#### Scenario: Example database size is bounded
- **WHEN** the `.hypothesis/examples/` directory grows beyond a configured budget
- **THEN** the policy documented in `tests/property/README.md` SHALL describe pruning (e.g. retain only the most recent N failure shrinks)

### Requirement: Property test module SHALL have a README documenting strategies and conventions
`tests/property/README.md` SHALL document: (a) how to run PBT locally, (b) how to switch profiles, (c) the catalogue of strategies in use, (d) conventions for adding a new property test.

#### Scenario: README present and discoverable
- **WHEN** a developer opens `tests/property/`
- **THEN** `README.md` SHALL exist with sections "Running locally", "Profiles", "Strategy catalogue", and "Adding a new property test"
