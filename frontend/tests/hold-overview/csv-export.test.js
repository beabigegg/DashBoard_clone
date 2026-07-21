/**
 * Unit tests for hold-overview CSV export helpers.
 *
 * Imports directly from the helper module so tests are independent of the
 * Vue component template.
 *
 * Acceptance criteria covered:
 *   AC-1: button exists (UI, covered by Playwright)
 *   AC-3: 15 columns, header row, display order
 *   AC-4: UTF-8 BOM prefix (﻿)
 *   AC-5: RFC 4180 escaping (comma, quote, newline); null → empty string; empty → header-only
 */

import { describe, it, expect } from 'vitest';
import { _buildCsv, _downloadCsv } from '../../src/hold-overview/csvExport.ts';

// ── Column order as per AC-3 / data-shape §3.15 ─────────────────────────────
const EXPECTED_HEADERS = [
  'Lot ID',
  'Work Order',
  'Qty',
  'Product',
  'Package',
  'Work Center',
  'Hold Reason',
  'Spec',
  'Age',
  'Hold Time',
  'Hold Duration (Hours)',
  'Hold By',
  'Dept',
  'Hold Comment',
  'Future Hold Comment',
];

// Sample lot with all 15 fields populated
const SAMPLE_LOT = {
  lotId: 'LOT001',
  workorder: 'WO-9999',
  qty: 25,
  product: 'PROD-A',
  package: 'PKG-B',
  workcenter: 'WC-01',
  holdReason: 'QUALITY',
  spec: 'SPEC-X',
  age: 3,
  holdTime: '2026-07-18T08:30:00',
  holdDurationHours: 12.5,
  holdBy: 'engineer1',
  dept: 'QC',
  holdComment: 'normal comment',
  futureHoldComment: 'future comment',
};

// ── Header row ───────────────────────────────────────────────────────────────

describe('_buildCsv_produces_header_row', () => {
  it('first line is all 15 column headers in display order', () => {
    const csv = _buildCsv([]);
    const firstLine = csv.split('\n')[0];
    expect(firstLine).toBe(EXPECTED_HEADERS.join(','));
  });
});

// ── Column count ─────────────────────────────────────────────────────────────

describe('_buildCsv_produces_correct_column_count', () => {
  it('data row has 15 comma-separated fields', () => {
    const csv = _buildCsv([SAMPLE_LOT]);
    const lines = csv.split('\n');
    // lines[0] = header, lines[1] = first data row
    expect(lines.length).toBe(2);
    // Count commas + 1 = fields, but must handle quoted commas, so parse header
    const headerFields = lines[0].split(',');
    expect(headerFields.length).toBe(15);
    // Data row should also have 15 fields (no commas in SAMPLE_LOT values)
    const dataFields = lines[1].split(',');
    expect(dataFields.length).toBe(15);
  });
});

// ── RFC 4180 escaping ────────────────────────────────────────────────────────

describe('_buildCsv_escapes_commas', () => {
  it('value containing a comma is wrapped in double quotes', () => {
    const lot = { ...SAMPLE_LOT, holdComment: 'hello, world' };
    const csv = _buildCsv([lot]);
    const dataLine = csv.split('\n')[1];
    expect(dataLine).toContain('"hello, world"');
  });
});

describe('_buildCsv_escapes_quotes', () => {
  it('internal double quotes are doubled inside quoted field', () => {
    const lot = { ...SAMPLE_LOT, holdComment: 'say "hello"' };
    const csv = _buildCsv([lot]);
    const dataLine = csv.split('\n')[1];
    expect(dataLine).toContain('"say ""hello"""');
  });
});

describe('_buildCsv_escapes_newlines', () => {
  it('value containing a newline is wrapped in double quotes', () => {
    const lot = { ...SAMPLE_LOT, holdComment: 'line1\nline2' };
    const csv = _buildCsv([lot]);
    // The embedded newline means split('\n') produces extra elements; check the
    // full CSV string for the correctly quoted field instead.
    expect(csv).toContain('"line1\nline2"');
  });
});

// ── null / undefined → empty string ─────────────────────────────────────────

describe('_buildCsv_null_to_empty', () => {
  it('null field produces empty string (not the string "null")', () => {
    const lot = { ...SAMPLE_LOT, holdComment: null, futureHoldComment: undefined };
    const csv = _buildCsv([lot]);
    const dataLine = csv.split('\n')[1];
    expect(dataLine).not.toContain('null');
    expect(dataLine).not.toContain('undefined');
  });
});

// ── Empty array → header-only, no error ──────────────────────────────────────

describe('_buildCsv_empty_array', () => {
  it('0 rows produces header-only CSV without throwing', () => {
    let csv;
    expect(() => {
      csv = _buildCsv([]);
    }).not.toThrow();
    const lines = csv.split('\n');
    // Only the header row — no trailing newline after it
    expect(lines.length).toBe(1);
    expect(lines[0]).toBe(EXPECTED_HEADERS.join(','));
  });
});

// ── UTF-8 BOM prefix ─────────────────────────────────────────────────────────

describe('_downloadCsv_prepends_bom', () => {
  it('Blob content starts with UTF-8 BOM character (\\uFEFF)', () => {
    // Capture the Blob constructor arguments by monkey-patching globalThis.Blob.
    // We only need to check the parts array — no DOM needed for this assertion.
    const capturedParts = [];
    const OrigBlob = globalThis.Blob;

    globalThis.Blob = class MockBlob {
      constructor(parts, _options) {
        capturedParts.push([...parts]);
      }
    };

    // Stub URL and DOM globals used inside _downloadCsv so they don't throw in
    // a node environment.
    const origCreateObjectURL = globalThis.URL?.createObjectURL;
    const origRevokeObjectURL = globalThis.URL?.revokeObjectURL;
    if (globalThis.URL) {
      globalThis.URL.createObjectURL = () => 'blob:mock';
      globalThis.URL.revokeObjectURL = () => {};
    }

    // Provide minimal document stub if not already present (node env)
    const hadDocument = typeof globalThis.document !== 'undefined';
    if (!hadDocument) {
      globalThis.document = {
        createElement: () => ({ href: '', download: '', click() {} }),
        body: { appendChild: () => {}, removeChild: () => {} },
      };
    }

    try {
      _downloadCsv('header,row\nvalue1,value2', 'test.csv');
      expect(capturedParts.length).toBeGreaterThan(0);
      // The Blob is created with a single string that starts with the UTF-8 BOM
      // character (﻿) followed by the CSV content.
      const blobContent = capturedParts[0][0];
      expect(blobContent.startsWith('﻿')).toBe(true);
    } finally {
      globalThis.Blob = OrigBlob;
      if (globalThis.URL) {
        if (origCreateObjectURL !== undefined) {
          globalThis.URL.createObjectURL = origCreateObjectURL;
        }
        if (origRevokeObjectURL !== undefined) {
          globalThis.URL.revokeObjectURL = origRevokeObjectURL;
        }
      }
      if (!hadDocument) {
        delete globalThis.document;
      }
    }
  });
});
