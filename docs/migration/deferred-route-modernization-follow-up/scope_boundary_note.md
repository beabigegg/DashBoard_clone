# Scope Boundary Note

## Change

`deferred-route-modernization-follow-up`

## Scope Clarification

Deferred routes (`/tables`, `/excel-query`, `/query-tool`, `/mid-section-defect`) are **in-scope** for this follow-up change regardless of their current page status (`dev` or `released`).

The **released-only restriction does not apply** to this change. These routes were intentionally deferred from phase 1 to control blast radius and are now the explicit modernization target.

## What Is In-Scope

- `/tables` — currently `dev` in page registry
- `/excel-query` — currently `dev` in page registry
- `/query-tool` — currently `dev` in page registry
- `/mid-section-defect` — currently `dev` in page registry

## What Is NOT In-Scope

- Phase-1 routes that are already modernized and governed (10 report + 2 admin routes)
- Routes outside the deferred matrix
- Backend business data semantics beyond compatibility safeguards
- Unrelated admin/report features not in the deferred matrix

## Policy

- Phase-1 in-scope routes SHALL NOT be reopened by this change unless explicitly required for shared governance wiring.
- Deferred routes adopt identical governance rigor (contracts, parity, manual acceptance, bug replay) as phase-1 routes.
