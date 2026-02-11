# Wave B Rewrite Entry Criteria and Native Cutover Gate

Last updated: 2026-02-11

Source of truth: `wave-b-rewrite-entry-criteria.json`

## Gate Rule

- If a Wave B route is switched to `render_mode=native` while `native_cutover_ready=false`, cutover validation must fail.
- `native_cutover_ready=true` requires:
  - `evidence.smoke = pass`
  - `evidence.parity = pass`
  - `evidence.telemetry = pass` or `n/a`

## Current Status

| Route | Smoke Evidence | Parity Evidence | Telemetry Evidence | Native Cutover Ready |
| --- | --- | --- | --- | --- |
| `/job-query` | pass | pass | pass | true |
| `/excel-query` | pass | pass | pass | true |
| `/query-tool` | pass | pass | pass | true |
| `/tmtt-defect` | pass | pass | pass | true |

Current policy outcome: all Wave B pages meet native cutover entry criteria.
