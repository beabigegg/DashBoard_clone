# Rollback Strategy (Shell / Router / Wrapper)

## Scope

- Shell entry failures (`/portal-shell`, route guards, navigation API)
- Legacy route integration failures (`job-query`, `excel-query`, `query-tool`, `tmtt-defect`)

## Immediate actions

1. Flip `PORTAL_SPA_ENABLED=false`.
2. Confirm `/` portal route responds and sidebar route links render.
3. Verify core routes (`/wip-overview`, `/resource`, `/qc-gate`) return 2xx.
4. Verify legacy routes (`/job-query`, `/excel-query`, `/query-tool`, `/tmtt-defect`) return 2xx.

## Validation checkpoints (<=15 minutes)

- `GET /api/portal/navigation` returns deterministic drawer/page list.
- No spike in 5xx for portal and legacy routes.
- Smoke flows for one P0 page and one legacy page pass.

## Legacy route fallback

- If a legacy route fails hard, temporarily hide it from drawer config (`page_status.json`) and announce maintenance route.

## Post-rollback follow-up

- Capture failed gate(s), timestamp, and impacted routes.
- Generate incident summary with fix candidate and rehearsal re-entry criteria.
