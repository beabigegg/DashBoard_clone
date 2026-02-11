# Motion Baseline Guidelines (Vue Transition First)

## Baseline principles

1. Motion clarifies state change, not decoration.
2. Default to short transitions (180ms - 240ms) with easing.
3. Keep animation on container level (route/panel/filter-chip), avoid animating large table row sets.

## Standard transitions

- Route change: `route-fade` (`opacity + translateY`) in portal shell.
- Drawer navigation: hover/active transition on sidebar links.
- Filter apply/remove: `TransitionGroup` chip enter/leave motion.
- Data refresh pulse: panel-level pulse when chart/table refresh is running.

## Accessibility

- Respect `prefers-reduced-motion: reduce`.
- All key transitions must have non-animated fallback styles.
- Motion must not block interaction or delay data rendering.
