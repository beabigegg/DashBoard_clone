## Purpose
Define stable requirements for expanded design tokens in the Tailwind configuration.

## Requirements

### Requirement: Tailwind config SHALL include expanded shadow scale

The `tailwind.config.js` SHALL define a 5-level semantic shadow scale replacing the current 3-level system.

#### Scenario: Shadow scale definition
- **WHEN** `tailwind.config.js` boxShadow theme is configured
- **THEN** it SHALL define: `xs` (1px 2px), `sm` (1px 4px), `md` (4px 12px), `lg` (8px 24px), `xl` (16px 48px)
- **THEN** `soft` and `panel` SHALL be preserved as aliases mapping to `sm` and `md` respectively for backward compatibility
- **THEN** `shell` SHALL NOT be aliased to a neutral shadow -- it SHALL be preserved as-is (`0 4px 12px rgba(0, 128, 200, 0.25)`) because it carries brand-blue coloring for interactive chrome elements and is semantically distinct from neutral elevation shadows

### Requirement: Tailwind config SHALL include Inter font for Latin text

#### Scenario: Font family stack
- **WHEN** the `fontFamily.sans` is configured
- **THEN** the stack SHALL be `['Inter', 'Noto Sans TC', 'Microsoft JhengHei', 'system-ui', 'sans-serif']`

#### Scenario: Inter font file hosting
- **WHEN** the application loads
- **THEN** Inter variable font (woff2) SHALL be loaded from local assets (not CDN)
- **THEN** `@font-face` SHALL use `font-display: swap` to prevent FOIT

#### Scenario: Tabular numbers for data display
- **WHEN** numeric data is displayed in tables or summary cards
- **THEN** the `font-variant-numeric: tabular-nums` property SHALL be applied via a `.tabular-nums` utility class

### Requirement: Tailwind config SHALL include extended brand color palette

#### Scenario: Brand color extensions
- **WHEN** `tailwind.config.js` brand colors are configured
- **THEN** it SHALL include `brand.400` (lighter than 500) and `brand.900` (darkest)

### Requirement: Tailwind config SHALL include extended border radius tokens

#### Scenario: Border radius tokens
- **WHEN** `tailwind.config.js` borderRadius is configured
- **THEN** it SHALL include `pill` (999px) for chip/badge elements and `button` (6px) for button elements
- **THEN** existing `shell` (10px) and `card` (8px) SHALL be preserved

### Requirement: CSS variables SHALL include page transition tokens

#### Scenario: Motion token extensions
- **WHEN** `:root` CSS variables are defined in `styles/tailwind.css`
- **THEN** it SHALL include `--motion-stagger` (50ms) for sequential element animation delay
- **THEN** page transition durations SHALL use the existing `--motion-normal` (200ms) and `--motion-fast` (150ms) tokens; no new page-specific duration variables are required
