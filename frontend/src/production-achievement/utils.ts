/**
 * Production-Achievement display helpers.
 *
 * `target_qty` and `achievement_rate` are nullable per data-shape-contract.md
 * §3.25/§3.26 (missing target row, zero target denominator). These helpers
 * centralize the "—" placeholder rendering so the table/chart never show
 * `null`, `NaN`, or `Infinity` to the user (business-rules.md PA-07).
 */

const NULL_DISPLAY = '—';

/** Format a nullable integer quantity for table/chart display. */
export function formatQty(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return NULL_DISPLAY;
  }
  return Math.round(value).toLocaleString('zh-TW');
}

/**
 * Format a nullable achievement rate (0..N ratio, e.g. 0.87) as a percentage
 * string. Never renders Infinity/NaN — both degrade to the "—" placeholder,
 * matching the backend's null contract (business-rules.md PA-07).
 */
export function formatAchievementRate(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return NULL_DISPLAY;
  }
  return `${(value * 100).toFixed(1)}%`;
}

/** Numeric-only rate for chart series (null → 0 so the bar/line simply has no height). */
export function achievementRateForChart(value: number | null | undefined): number {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return 0;
  }
  return value * 100;
}

/**
 * Client-side validation for the target_qty edit form.
 * Mirrors data-shape-contract.md §3.26: non-negative integer only.
 * Returns an empty string when valid, or a Traditional-Chinese error message.
 */
export function validateTargetQtyInput(raw: string): string {
  const trimmed = raw.trim();
  if (trimmed === '') return '目標值為必填';
  if (!/^-?\d+(\.\d+)?$/.test(trimmed)) return '目標值必須為數字';
  const n = Number(trimmed);
  if (!Number.isFinite(n)) return '目標值必須為數字';
  if (!Number.isInteger(n)) return '目標值必須為整數';
  if (n < 0) return '目標值不可為負數';
  return '';
}

export { NULL_DISPLAY };
