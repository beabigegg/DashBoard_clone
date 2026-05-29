/**
 * Format a date string from Oracle DATE columns that may be serialised as midnight UTC.
 *
 * CRITICAL: Oracle DATE columns serialised as midnight UTC (T00:00:00) must NOT be passed
 * to new Date() in a non-UTC locale — this causes a ±8h TZ shift (e.g. UTC+8 turns midnight
 * into 08:00:00). Inspect raw H/M/S via regex BEFORE calling new Date().
 *
 * Pattern from CLAUDE.md Frontend Date Formatting Notes.
 * Applies to: start_ts, end_ts, CREATEDATE, COMPLETEDATE, FIRSTCLOCKONDATE, LASTCLOCKOFFDATE
 */
export function formatDowntimeDate(raw: string): string {
  if (!raw) return '—';

  // Check raw H/M/S before any Date() call
  const match = raw.match(/T(\d{2}):(\d{2}):(\d{2})/);
  if (match && match[1] === '00' && match[2] === '00' && match[3] === '00') {
    // midnight-UTC: extract Y/M/D from string directly, no new Date()
    const [datePart] = raw.split('T');
    return datePart; // e.g. "2026-05-27"
  }

  // Non-midnight: use Date() with local timezone
  return new Date(raw).toLocaleString('zh-TW', { timeZone: 'Asia/Taipei' });
}

/**
 * Format just the date portion (YYYY-MM-DD) from an ISO 8601 string.
 * Safe for Oracle DATE midnight-UTC columns.
 */
export function formatDowntimeDateOnly(raw: string): string {
  if (!raw) return '—';

  // Check raw H/M/S before any Date() call
  const match = raw.match(/T(\d{2}):(\d{2}):(\d{2})/);
  if (match && match[1] === '00' && match[2] === '00' && match[3] === '00') {
    // midnight-UTC: extract Y/M/D from string directly, no new Date()
    const [datePart] = raw.split('T');
    return datePart;
  }

  // Non-midnight: the string has a valid date portion before 'T'
  // For non-midnight ISO strings, the date portion before 'T' is the local date
  // (since we already confirmed H != 00 or M != 00 or S != 00 above).
  // Using the raw string date portion avoids timezone issues for date-only display.
  if (raw.includes('T')) {
    return raw.slice(0, 10);
  }
  // Plain date string (no T)
  return raw.slice(0, 10);
}
