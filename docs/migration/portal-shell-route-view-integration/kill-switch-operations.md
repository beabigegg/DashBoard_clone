# Kill-Switch Operations: Shell Route-View Migration

Last updated: 2026-02-11

## Purpose

Provide a rapid, operator-safe mechanism to recover service usability when severe regressions occur after shell cutover.

## Trigger Conditions

- Critical route failures on shell core paths (`/portal-shell`, `/api/portal/navigation`).
- Multiple P0 smoke failures across Wave A/Wave B pages.
- Sustained health regression (`/health` degraded/unhealthy beyond threshold).

## Kill-Switch Command

- Set `PORTAL_SPA_ENABLED=false` in deployment environment.
- Restart application workers.

## Verification Checklist (must complete in order)

1. `GET /` responds and routes to legacy portal.
2. `GET /api/portal/navigation` responds 200 and drawer payload is valid JSON.
3. `GET /health` reports no new critical errors after rollback.
4. Critical page routes remain reachable: `/wip-overview`, `/resource`, `/qc-gate`, `/job-query`, `/excel-query`, `/query-tool`, `/tmtt-defect`.

## Page-level Partial Kill-Switch

- If issue is route-scoped, patch affected route contract to fallback strategy and redeploy frontend shell assets only.
- Keep unaffected routes in native mode to avoid global disruption.

## Escalation

- If kill-switch does not restore stable behavior within 15 minutes, escalate to full rollback runbook and incident bridge.
