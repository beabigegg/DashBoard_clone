# Tailwind Design Tokens Mapping

## Goal

Map existing portal visual language into a stable token set for phased migration.

## Color tokens

- `brand.500` / `brand.600` / `brand.700`: primary brand actions and active navigation states.
- `accent.500`: gradient accent endpoint for shell headers.
- `surface.app` / `surface.card` / `surface.muted`: app background, card surfaces, muted blocks.
- `stroke.soft` / `stroke.panel`: border hierarchy.
- `state.success` / `state.warning` / `state.danger` / `state.neutral`: status dots and health states.

## Typography tokens

- `fontFamily.sans`: `Noto Sans TC`, `Microsoft JhengHei`, system fallback.

## Layout tokens

- `spacing.shell`: outer shell padding.
- `spacing.panel`: panel interior spacing.
- `spacing.nav`: sidebar item horizontal spacing.
- `spacing.block`: vertical rhythm baseline.

## Radius and elevation tokens

- `borderRadius.shell`: shell and main card radius.
- `borderRadius.card`: smaller control/card radius.
- `boxShadow.soft`: light containers (sidebar).
- `boxShadow.panel`: content panel container.
- `boxShadow.shell`: header gradient card emphasis.

## Z-index token

- `zIndex.popup`: status popup / overlay layer.

## Migration note

Tokens are intentionally aligned with current portal values to minimize visual drift during iframe decommission.
