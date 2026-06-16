/**
 * CSV export helpers for hold-overview.
 *
 * Mirrors the pattern used in hold-history/App.vue (_buildCsv / _downloadCsv).
 *
 * Acceptance criteria:
 *   AC-3: 13 columns in display order
 *   AC-4: UTF-8 BOM prefix (﻿)
 *   AC-5: RFC 4180 escaping; null/missing → empty string; empty → header-only
 */

// ── Column definitions (AC-3) ────────────────────────────────────────────────
// Display order must match data-shape-contract §3.15

const CSV_HEADERS: string[] = [
  'Lot ID',
  'Work Order',
  'Qty',
  'Product',
  'Package',
  'Work Center',
  'Hold Reason',
  'Spec',
  'Age',
  'Hold By',
  'Dept',
  'Hold Comment',
  'Future Hold Comment',
];

// JSON keys corresponding to each header (same index order)
const CSV_KEYS: string[] = [
  'lotId',
  'workorder',
  'qty',
  'product',
  'package',
  'workcenter',
  'holdReason',
  'spec',
  'age',
  'holdBy',
  'dept',
  'holdComment',
  'futureHoldComment',
];

/**
 * RFC 4180: wrap a value in double quotes if it contains commas, quotes,
 * or newlines; double any internal double quotes.
 */
export function _toCsvField(value: unknown): string {
  const s = String(value ?? '');
  return s.includes(',') || s.includes('"') || s.includes('\n')
    ? `"${s.replace(/"/g, '""')}"`
    : s;
}

/**
 * Build a full CSV string from an array of lot records.
 * Always emits the header row; returns header-only when rows is empty.
 */
export function _buildCsv(rows: Record<string, unknown>[]): string {
  const headerLine = CSV_HEADERS.join(',');
  if (!Array.isArray(rows) || rows.length === 0) {
    return headerLine;
  }
  const dataLines = rows.map((row) =>
    CSV_KEYS.map((key) => _toCsvField(row[key])).join(','),
  );
  return [headerLine, ...dataLines].join('\n');
}

/**
 * Trigger a browser Blob download.
 * Prepends a UTF-8 BOM (﻿) so Excel opens the file correctly.
 */
export function _downloadCsv(content: string, filename: string): void {
  const blob = new Blob(['﻿' + content], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
