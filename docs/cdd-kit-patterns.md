# CDD Kit Operational Patterns

Promoted learnings from project history — common gotchas when running cdd-kit in this project.

## Version Sync with CI

**Keep local cdd-kit in sync with CI.** CI runs `npm install -g contract-driven-delivery` without a version pin (always installs latest). New releases may add required artifacts (e.g., `implementation-plan.md` in 2.0.18). After any CI `spec traceability` failure, upgrade locally:

```bash
npm install -g contract-driven-delivery
cdd-kit validate
```

Evidence: `hold-history-detail-flat-table` / `reject-material-flat-table` — local 2.0.17 passed; CI 2.0.18 failed on missing `implementation-plan.md`.

## ci-gates.md Required Section Headers

**`cdd-kit gate` validates `ci-gates.md` by checking for the literal strings** "workflow", "promotion policy", and "rollback policy". Always include these exact section headers or the gate fails regardless of content:

```markdown
## CI/CD Workflow
## Promotion Policy
## Rollback Policy
```

Evidence: `migrate-query-tool-ts` — gate failed on first run; passed after adding the three headers.

## Section-6 Tasks Before `cdd-kit gate --strict`

- **Tasks 6.2** (PR required gates) and **6.3** (Informational gates) may be marked `done` before CI confirmation when all local Tier 1 gate commands pass and CI runs the identical commands.
- **Task 6.4** (nightly/weekly/manual gates) should be marked `skipped` when no such gates are defined for the change.
- Leaving any section-6 task in `pending` blocks the pre-commit hook.

Evidence: `migrate-material-trace-ts` — pre-commit hook rejected commit with 6.2/6.3/6.4 all `pending`.

## contracts/CHANGELOG.md — Only Version Location

**`cdd-kit validate --versions` scans only `contracts/CHANGELOG.md`** for entries matching `## [<type> <version>]` (e.g., `## [api 1.12.0]`). CHANGELOG entries written inside individual contract files (`api-contract.md`, `business-rules.md`, etc.) are never checked and will cause a gate failure.

Always write version entries to `contracts/CHANGELOG.md`, never to the individual files.

Evidence: `ai-pipeline-upgrade` — backend-engineer embedded entries in individual files; gate failed until entries were moved to `contracts/CHANGELOG.md`.

## context-manifest.md Allowed Paths — Directory Paths Only

**Use directory-level paths, not glob patterns** in `## Allowed Paths`. `cdd-kit context check` rejects glob patterns and causes a preflight failure.

```
# Correct
frontend/src/core/

# Wrong — causes preflight failure
frontend/src/core/**/*.ts
```

Evidence: `migrate-shared-ui-ts` — initial manifest used glob patterns and failed preflight.


## `jsonschema` pip Dependency for `cdd-kit validate --contracts`

**`cdd-kit validate --contracts` requires `pip install jsonschema`** before the step in any CI job, and locally when `response-samples.json` exists. It is not bundled with cdd-kit and is not pre-installed on `ubuntu-latest`.

```yaml
- name: Install Python contract dependencies
  run: pip install jsonschema

- name: Validate contracts and gates
  run: cdd-kit validate
```

The same applies locally: if `tests/contract/response-samples.json` exists and `jsonschema` is absent, `cdd-kit validate` exits non-zero with "jsonschema package is not installed" — even in conda envs where it is absent.

Evidence: `response-shape-adr0007` — CI run 27599574084 "Validate contracts and gates" step; fixed by commit `bf7ba1e`.
