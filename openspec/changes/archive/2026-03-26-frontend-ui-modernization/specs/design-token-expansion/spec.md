## ADDED Requirements

### Requirement: Tailwind config SHALL include expanded shadow scale

The `tailwind.config.js` SHALL define a 5-level semantic shadow scale replacing the current 3-level system.

#### Scenario: Shadow scale definition
- **WHEN** `tailwind.config.js` boxShadow theme is configured
- **THEN** it SHALL define: `xs` (1px 2px), `sm` (1px 4px), `md` (4px 12px), `lg` (8px 24px), `xl` (16px 48px)
- **THEN** `soft` and `panel` SHALL be preserved as aliases mapping to `sm` and `md` respectively for backward compatibility
- **THEN** `shell` SHALL NOT be aliased to a neutral shadow — it SHALL be preserved as-is (`0 4px 12px rgba(0, 128, 200, 0.25)`) because it carries brand-blue coloring for interactive chrome elements and is semantically distinct from neutral elevation shadows

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

## MODIFIED Requirements

### Requirement: Frontend styles SHALL be governed by Tailwind design tokens
The frontend SHALL enforce `frontend/tailwind.config.js` as the single source of truth for design tokens. Shared visual semantics SHALL be expressed through token-backed Tailwind/shared layers, and token consumption in CSS SHALL use `theme()` rather than route-local token variables.

#### Scenario: Shared token usage across in-scope modules
- **WHEN** two modules render equivalent UI semantics (for example card, filter chip, primary action, status indicator)
- **THEN** they SHALL use the same token-backed semantics from `tailwind.config.js`
- **THEN** visual output SHALL remain consistent across those modules

#### Scenario: Token introduction and consumption governance
- **WHEN** a new design token is introduced
- **THEN** it SHALL be added under `theme.extend` in `frontend/tailwind.config.js`
- **THEN** CSS token consumption SHALL use `theme('...')` paths instead of introducing route-local `:root` token variables

#### Scenario: text.muted meets WCAG AA contrast
- **WHEN** `text.muted` is used on white/light backgrounds
- **THEN** the token value SHALL be `#64748b` or darker to achieve minimum 4.5:1 contrast ratio

#### Scenario: Shadow tokens use semantic naming
- **WHEN** shadow tokens are consumed in CSS or Tailwind classes
- **THEN** they SHALL use the semantic scale (`shadow-xs` through `shadow-xl`) or legacy aliases (`shadow-soft`, `shadow-panel`)
- **THEN** `shadow-shell` SHALL remain available for brand-chrome interactive elements only; new code SHALL NOT use it for content elevation
- **THEN** new code SHALL prefer semantic scale names over legacy aliases for neutral elevation
