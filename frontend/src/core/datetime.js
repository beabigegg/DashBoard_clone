/**
 * Shared datetime formatting utilities for admin dashboard.
 */

const _logTimeFormatter = new Intl.DateTimeFormat('zh-TW', {
  hour12: false,
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
});

/**
 * Format a log timestamp ISO string for display.
 *
 * Converts to user's local timezone using zh-TW locale, 24-hour clock.
 * Returns '-' for null/undefined/empty input.
 * Returns the original value if it cannot be parsed.
 *
 * @param {string|null|undefined} iso - ISO 8601 timestamp string
 * @returns {string} Formatted date string or '-' or original value
 */
export function formatLogTime(iso) {
  if (iso == null || iso === '') return '-';
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return _logTimeFormatter.format(d);
  } catch {
    return iso;
  }
}
