# Archive: eap-alarm-coarse-filter

## Change Summary

Round 1 (2026-06-30) expanded the EAP ALARM coarse spool filter from a fixed `(date + machines)` pair to `(date + machines? + lot_ids? + product_dims?)`, requiring at least one of the three non-date axes (EA-08), pushing `lot_ids` (`LOT_ID IN (...)`) and `product_dims` (per-dim `EXISTS` semi-join against `DWH.DW_MES_CONTAINER`) into the Oracle worker query, and adding `GET /api/eap-alarm/product-filter-options`. Round 2 (2026-07-01), tracked in the same still-open change directory rather than as a new change, fixed a production bug and a data-model defect discovered in that same delivered scope before archive: (1) `_build_equipment_filter([])` produced invalid SQL (`AND e.EQUIPMENT_ID IN ()`) causing `ORA-00936: missing expression` for the EA-08-legal combination `eqp_types=[]` + non-empty product dim; (2) EA-07's closed 10-value `eqp_types` enum had never actually worked (real `EQUIPMENT_ID` values are `<prefix>-<instance>`, e.g. `GWBK-0241`, never a bare 4-char code, so the enum-validated values could never match via the worker's exact-match `IN (...)` clause) and was replaced with `lot_ids`-style free-form string validation, aligned with the plant-wide `RESOURCENAME`/`RESOURCEFAMILYNAME` model the frontend's 型號/機台 cascade already used. The frontend `FilterBar.vue` was also fixed so that selecting only a 型號 (family) with no specific 機台 expands to all machines in that family at submit time, and so the submit button is enabled by a family-only selection (a companion `canSubmit` gap found mid-implementation).

## Final Behavior

- A coarse-filter request with `eqp_types=[]` and any non-empty `lot_ids`/`pj_types`/`product_lines`/`pj_bops` succeeds and returns rows unrestricted by equipment (worker applies a `1=1` no-op predicate).
- `eqp_types`, when supplied, accepts any non-empty whitespace-stripped string (real `EQUIPMENT_ID`/`RESOURCENAME` values); no closed-enum membership check remains.
- FilterBar: family selected + specific machine(s) selected → submits exactly those machines. Family selected + no machine selected → submits every machine in that family. Neither selected + a product dim selected → submits an empty machines list (relies on the `1=1` no-op fix). Family-only selection alone now enables the submit button.
- Product-dimension filtering (`lot_ids`/`pj_types`/`product_lines`/`pj_bops`, via the `CONTAINERNAME = LOT_ID` EXISTS bridge) is unchanged from round 1.

## Final Contracts Updated

- `contracts/business/business-rules.md`: EA-01, EA-07 (rewritten in round 2), EA-08 (touched up in round 2), EA-09, EA-10. Schema-version 1.34.0 → 1.36.0 (round 1) → re-sequenced to 1.41.0 (round 2, see Production Reality Findings).
- `contracts/data/data-shape-contract.md`: §3.17 spool-key dims, EXISTS mapping, product-filter-options payload (round 1 only).
- `contracts/api/api-contract.md` + `api-inventory.md`: `POST /api/eap-alarm/spool` optional dims, `GET /api/eap-alarm/product-filter-options` (round 1 only; round 2 made no API/schema-visible change).
- `contracts/openapi.json` + `contracts/api/openapi.json`: regenerated in round 1; confirmed unnecessary in round 2 (no machine-encoded enum existed for `eqp_types` in either export).
- `contracts/CHANGELOG.md`: entries for both rounds.

## Final Tests Added / Updated

- `tests/test_eap_alarm_service.py`: `TestAtLeastOneFilterRequired`, `TestLotIdNormalization`, `TestProductDimsFilter`, `TestSchemaVersionIsPinned` (round 1); `TestEquipmentFilterEmptyNoOp`, `TestMachinesValidation::test_full_equipment_id_string_no_error`, `test_out_of_old_enum_value_no_longer_raises` (round 2).
- `tests/integration/test_eap_alarm_coarse_filter.py`: `TestEapAlarmWorkerFnNewDims` (round 1, moved from an `integration_real`-marked file to fix a PR-gate coverage gap found in round-1 QA).
- `tests/integration/test_eap_alarm_data_boundary.py`, `tests/integration/test_eap_alarm_resilience.py`: round 1 cases plus round 2's `test_empty_eqp_types_with_product_dims_only_builds_valid_sql` (the production-regression red-green signal).
- `frontend/tests/unit/eap-alarm-filter.test.js`, `frontend/tests/playwright/eap-alarm-filters.spec.ts`: round 1 coarse-filter UI cases plus round 2's family-expansion and `canSubmit` cases.
- `test-evidence.yml`: both rounds' phases green; round 2 required a reconciliation because `cdd-kit test run` overwrites the command recorded per phase name rather than appending, so backend-only and frontend-only agent runs were each silently discarding the other's evidence for the same phase slot until combined `pytest ... && npm ...` commands were run per required phase (see Lessons).

## Final CI/CD Gates

Per `ci-gates.md`: 7 required PR-gate checks (backend unit+integration ×4 suites, frontend unit, css-check, type-check, contract-validation, openapi-sync, playwright e2e). No new gate workflows; existing eap-alarm CI jobs cover both rounds. Tier-3 nightly real-Oracle path unchanged and remains informational.

## Production Reality Findings

- **Round-1 QA (2026-06-30) found and the team fixed two blocking gaps before merge**: a contract-version-skip caused by an interleaved concurrent change, and a mock-based test class incorrectly marked `integration_real` (hiding it from the PR-required gate).
- **Round-1's own backend-engineer agent-log carried a disproven claim**: "`_build_equipment_filter([])` ... safe by design." This was wrong — the exact combination it described (`eqp_types=[]` + product-dims-only) produced `ORA-00936` in production. Neither round-1's tests nor its QA review exercised this specific combination at the SQL-execution level; the unit tests exercised `eqp_types`-non-empty and `product_dims`-non-empty paths separately.
- **Round-2 discovered a second, independent defect in the same delivered scope**: EA-07's 10-value closed enum for `eqp_types` had never functioned, because the worker's exact-match `EQUIPMENT_ID IN (...)` predicate could never match a bare 4-char enum value against real `<prefix>-<instance>` equipment IDs. This was confirmed via a live read-only Oracle sample (17/17 `RESOURCENAME` values matched `EQUIPMENT_ID` exactly; `RESOURCEFAMILYNAME` mapped to the frontend's 型號 label) rather than assumed.
- **Round-2 hit the same class of concurrent-contract-edit collision** round-1 did (a different concurrent change, `yield-alert-kpi-csv-parity`, bumped the same `contracts/business/business-rules.md` file's frontmatter to 1.40.0 while this change's 1.39.0 bump was still uncommitted). Resolved by re-sequencing this change's entry to 1.41.0 (sitting after theirs in both the top-level `contracts/CHANGELOG.md` and the in-file mirror) and committing with `--no-verify` after confirming every other gate check passed cleanly and the only failure was the version-skip check comparing against git HEAD (which cannot be satisfied by renumbering alone while both changes are uncommitted on the same baseline) — decision made explicitly with the user, not assumed.

## Lessons Promoted to Standards

All three reviewed by `contract-reviewer` and classified `promote-to-guidance` (none required a `contracts/` schema-version bump — all target `docs/` guidance files referenced by `CLAUDE.md`'s `cdd-kit:learnings` region):

1. **One-of-N-required filter axes need an axis-empty test, not just axis-non-empty tests.** Added to `docs/architecture/test-discipline.md` (new section after "Cross-Filter Narrowing Has Its Own Test Surface") + one-line pointer in `CLAUDE.md`. Evidence: the ORA-00936 production bug — round-1 tests exercised `eqp_types` and `product_dims` non-empty separately, never `eqp_types=[]` + `product_dims`-non-empty together.
2. **Closed-enum validation feeding an exact-match SQL clause needs verification against real data before shipping.** Added to `docs/architecture/test-discipline.md` (new section after "Env-Var Contract Tests Must Pin Default Values") + one-line pointer in `CLAUDE.md`. Evidence: EA-07's 10-value enum was dead code from ship to discovery because it never matched real `EQUIPMENT_ID` format.
3. **Concurrent CDD sessions bumping the same contract file's schema-version collide at the git-HEAD level, not just at the changelog-prose level.** Added to `docs/cdd-kit-patterns.md` (new section after "Parallel Implementation Agents Racing on test-evidence.yml") + one-line pointer in `CLAUDE.md`. Evidence: this change collided with `mid-section-defect` previously and `yield-alert-kpi-csv-parity` this round, both on `contracts/business/business-rules.md`.

Verified `cdd-kit validate --contracts` still passes after all doc/CLAUDE.md edits; ran `cdd-kit context-scan` to refresh indexes.

## Follow-up Work

- ADR-0008 is still `proposed` and its decision text says the spool key is `sha256(sorted(eqp_types))` only; it predates the 5-dim key and EXISTS semi-join this change shipped. Flagged for the ADR owner to amend (not this change's code).
- `DW_MES_CONTAINER.CONTAINERNAME` CHAR-padding TRIM parity remains the most likely correctness foot-gun per design.md; covered by the data-boundary test but worth remembering for future EAP-alarm/product-dim work.
- Whoever owns the EAP/SECS gateway config should confirm why alarm code 6075 on equipment `GWBK-0330` never carries an `AlarmCode` detail parameter (0/46 occurrences in a live sample, vs. 100% coverage for every other alarm code on the same equipment in the same window) — this is a genuine upstream data gap unrelated to this change's code, discovered while the user was validating the fix in production.

## Cold Data Warning

This archive is historical evidence. Current requirements live in `contracts/` and active project guidance (`CLAUDE.md`). Do not use this file as a source of current behavior — re-read `contracts/business/business-rules.md` EA-07/EA-08 for the authoritative current rule.
