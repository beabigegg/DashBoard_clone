# Drawer Governance Contract (Portal No-Iframe Migration)

## Scope

This contract defines drawer behavior that must remain stable during migration.

## Canonical Responsibilities

Drawer metadata is responsible for:

- Information architecture grouping.
- Display order.
- Access visibility (`admin_only`).

Drawer metadata is not responsible for:

- Content embedding mode (`iframe`, `toolFrame`).
- Rendering technology selection (Jinja vs SPA route view).

## Contract Rules

1. Drawer IDs must be unique and non-empty.
2. Page routes must be unique and non-empty.
3. `page.drawer_id` (when present) must reference an existing drawer.
4. `order` values (when present) must be positive integers.
5. Page status must be one of `released` or `dev`.
6. Visibility outcomes must be deterministic for admin/non-admin users.

## Deterministic Rendering Order

Drawers:

- Primary sort by `order` ascending.
- Secondary sort by `name` ascending.

Pages in each drawer:

- Primary sort by `order` ascending.
- Secondary sort by `(name or route)` ascending.

## Visibility Semantics

- Non-admin users can view only `released` pages in non-admin-only drawers.
- Admin users can view all drawer-assigned pages according to current page status policy.
- Drawers with zero visible pages are hidden.

## Validation Artifacts

- `baseline_drawer_contract_validation.json`
- `baseline_drawer_visibility.json`
