/** Canonical status colors — single source of truth for chart series and any JS-side rendering.
 * CSS badges/accents use the matching Tailwind design tokens:
 *   UDT → colors.state.danger  (#ef4444)
 *   SDT → colors.state.warning (#f59e0b)
 *   EGT → colors.state.info    (#3b82f6)
 */
export const STATUS_COLORS: Record<string, string> = {
  UDT: '#ef4444',
  SDT: '#f59e0b',
  EGT: '#3b82f6',
};

/** Ordered color palette for BigCategory mosaic chart and TopReasons pills.
 * Categories are ranked by total hours (desc); the i-th category gets CATEGORY_PALETTE[i].
 */
export const CATEGORY_PALETTE: readonly string[] = [
  '#5470c6', '#91cc75', '#fac858', '#ee6666', '#73c0de',
  '#3ba272', '#fc8452', '#9a60b4', '#ea7ccc', '#60a5fa',
];
