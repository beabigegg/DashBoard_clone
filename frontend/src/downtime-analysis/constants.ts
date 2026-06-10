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
