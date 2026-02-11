# Legacy Wrapper Telemetry Contract

## Status

- Retired after wrapper decommission.
- `POST /api/portal/wrapper-telemetry` has been removed.
- Reference only for historical migration traceability.

## Wrapper scope

- `/job-query`
- `/excel-query`
- `/query-tool`
- `/tmtt-defect`

## Client events

- `wrapper_loaded`: wrapper route rendered in shell.
- `launch`: user clicked "進入既有頁面" and navigation handoff started.

## API endpoint

- `POST /api/portal/wrapper-telemetry`
- Payload:
  - `event_type: string`
  - `route: string` (must be one of wrapper scope routes)
  - `page_name?: string`
  - `drawer_name?: string`
  - `duration_ms?: number`
  - `ts?: string`

## Validation

- Reject unknown routes with `400`.
- Reject missing `event_type` with `400`.

## Fallback behavior

- Wrapper UI always provides direct anchor navigation to the legacy route.
- Telemetry failure must not block navigation.
