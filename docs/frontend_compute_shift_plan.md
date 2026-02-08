# Frontend Compute Shift Plan

## Targeted Calculations

## Resource History (migrated to frontend helpers)
- `ou_pct`
- `availability_pct`
- status percentages:
  - `prd_pct`
  - `sby_pct`
  - `udt_pct`
  - `sdt_pct`
  - `egt_pct`
  - `nst_pct`

These are now computed by `frontend/src/core/compute.js` via:
- `buildResourceKpiFromHours`
- `calcOuPct`
- `calcAvailabilityPct`
- `calcStatusPct`

## Parity Rules

1. Rounding rule
- one decimal place, identical to backend (`round(..., 1)`)

2. Formula rule
- OU%: `PRD / (PRD + SBY + UDT + SDT + EGT)`
- Availability%: `(PRD + SBY + EGT) / (PRD + SBY + EGT + SDT + UDT + NST)`
- Status%: `status_hours / total_hours`

3. Zero denominator rule
- all percentages return `0`

4. Data compatibility rule
- backend keeps existing fields to preserve API compatibility
- frontend recomputes display values from hours for deterministic parity

## Validation

- Python backend formula baseline: `mes_dashboard.services.resource_history_service`
- Frontend parity check: `tests/test_frontend_compute_parity.py`
