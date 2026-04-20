# Legacy Test Audit

Date: 2026-04-20

Command used:

```bash
cd frontend
for f in tests/legacy/*.test.js; do
  node --test "$f"
done
```

Current status:

- Total files: `33`
- Passing under current legacy harness: `12`
- Failing under current legacy harness: `21`

Failure categories:

- `18` files: broken relative import paths such as `../src/...` resolving to `frontend/tests/src/...`
- `2` files: missing file paths referenced by the test harness (`ENOENT`)
- `1` file: Vite runtime dependency (`import.meta.env`) executed under plain `node --test`

Implication:

- A large part of `frontend/tests/legacy/` is not giving real regression protection today.
- These tests can look present in the repo while being effectively dead under the current harness.
- New frontend regression coverage should prefer the active `vitest` pipeline in `frontend/tests/**`.

Examples of broken-import failures:

- `tests/legacy/autocomplete.test.js`
- `tests/legacy/material-trace-composables.test.js`
- `tests/legacy/portal-shell-route-query.test.js`
- `tests/legacy/yield-alert-center-utils.test.js`

Example of runtime-harness mismatch:

- `tests/legacy/query-tool-composables.test.js`
  - imports production modules that reference `import.meta.env`
  - this is incompatible with plain `node --test`

Recommended cleanup order:

1. Migrate behaviorally important composable tests to `vitest`
2. Fix or remove dead legacy files with broken `../src/...` import paths
3. Keep only legacy tests that still run cleanly and cover non-Vite pure functions
