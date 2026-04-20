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
- Passing under current legacy harness: `33`
- Failing under current legacy harness: `0`

What was fixed in this cleanup pass:

- corrected broken relative import paths from `../src/...` to the real module location
- fixed legacy governance test pathing to root-level `docs/`
- hardened `frontend/src/core/api.js` so non-Vite runners do not crash on `import.meta.env`
- updated stale query-tool legacy expectations from default `per_page=200` to current behavior `25`

Implication:

- The legacy suite is runnable again, so it now provides real baseline protection.
- New frontend regression coverage should still prefer the active `vitest` pipeline in `frontend/tests/**`.
- The legacy suite should be treated as compatibility coverage, not the primary place for new tests.

Recommended cleanup order:

1. Keep new composable and component tests in `vitest`
2. Retain legacy tests only when they cover pure-function compatibility checks well
3. Gradually migrate high-value legacy files into `frontend/tests/**` and retire duplicates
