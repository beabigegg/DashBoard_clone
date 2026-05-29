import { describe, it, expect, vi, afterEach } from 'vitest';
import { formatDowntimeDate, formatDowntimeDateOnly } from '../formatDowntimeDate';

describe('formatDowntimeDate', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('midnight-UTC detection (H/M/S all 00)', () => {
    it('extracts Y/M/D directly from string — never calls new Date()', () => {
      // Spy on Date constructor to assert it is NOT called
      const DateSpy = vi.spyOn(globalThis, 'Date');

      const result = formatDowntimeDate('2026-05-27T00:00:00');
      expect(result).toBe('2026-05-27');

      // The Date constructor must NOT have been called with the midnight-UTC string
      const callsWithMidnight = DateSpy.mock.calls.filter(
        (args) => args[0] === '2026-05-27T00:00:00',
      );
      expect(callsWithMidnight.length).toBe(0);
    });

    it('returns date portion for midnight-UTC ISO 8601 with Z suffix', () => {
      const result = formatDowntimeDate('2026-01-15T00:00:00Z');
      // The regex checks T(\d{2}):(\d{2}):(\d{2}) — even with Z we extract YYYY-MM-DD
      // The split on 'T' gives the date part before 'T'
      expect(result).toBe('2026-01-15');
    });

    it('handles midnight-UTC for Oracle CREATEDATE pattern', () => {
      expect(formatDowntimeDate('2025-12-31T00:00:00')).toBe('2025-12-31');
    });

    it('handles midnight-UTC for FIRSTCLOCKONDATE pattern', () => {
      expect(formatDowntimeDate('2026-03-01T00:00:00')).toBe('2026-03-01');
    });
  });

  describe('non-midnight: calls new Date() normally', () => {
    it('returns a localized string for non-midnight timestamps', () => {
      // Non-midnight should return a truthy string (toLocaleString output)
      const result = formatDowntimeDate('2026-05-27T08:30:00');
      expect(typeof result).toBe('string');
      expect(result.length).toBeGreaterThan(0);
      // Must not be the raw datePart
      expect(result).not.toBe('2026-05-27');
    });

    it('returns a localized string for seconds=30', () => {
      const result = formatDowntimeDate('2026-05-27T14:22:30');
      expect(typeof result).toBe('string');
      expect(result).not.toBe('2026-05-27');
    });

    it('returns a localized string for hour-only match but minutes non-zero', () => {
      const result = formatDowntimeDate('2026-05-27T00:01:00');
      expect(typeof result).toBe('string');
      expect(result).not.toBe('2026-05-27');
    });
  });

  describe('edge cases', () => {
    it('returns em dash for empty string', () => {
      expect(formatDowntimeDate('')).toBe('—');
    });

    it('returns em dash for null-ish empty input', () => {
      // TypeScript won't allow null directly, but guard handles runtime nulls
      expect(formatDowntimeDate('' as string)).toBe('—');
    });
  });
});

describe('formatDowntimeDateOnly', () => {
  it('extracts YYYY-MM-DD from midnight-UTC string without Date()', () => {
    const DateSpy = vi.spyOn(globalThis, 'Date');
    const result = formatDowntimeDateOnly('2026-04-10T00:00:00');
    expect(result).toBe('2026-04-10');
    const callsWithMidnight = DateSpy.mock.calls.filter(
      (args) => args[0] === '2026-04-10T00:00:00',
    );
    expect(callsWithMidnight.length).toBe(0);
  });

  it('returns YYYY-MM-DD for non-midnight date string', () => {
    // Non-midnight: should return formatted date portion
    const result = formatDowntimeDateOnly('2026-04-10T10:30:00');
    expect(result).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });

  it('returns em dash for empty input', () => {
    expect(formatDowntimeDateOnly('')).toBe('—');
  });
});
