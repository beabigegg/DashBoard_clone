/**
 * Tests for frontend/src/core/unwrap-api-result.js
 *
 * Covers:
 * - Standard success envelope → returns full envelope
 * - Error envelope → throws with server message
 * - Legacy response (no success field) → returns as-is
 * - Malformed/null responses → safe fallback
 * - unwrapApiData variant → returns .data directly
 */

import { describe, it, expect } from 'vitest';
import { unwrapApiResult, unwrapApiData } from '../src/core/unwrap-api-result.js';

describe('unwrapApiResult', () => {
  it('returns full envelope when success is true', () => {
    const response = { success: true, data: { total: 5 }, meta: { timestamp: '2024-01-01' } };
    const result = unwrapApiResult(response, 'fallback');
    expect(result).toBe(response);
    expect(result.data.total).toBe(5);
  });

  it('throws Error when success is false with server message', () => {
    const response = {
      success: false,
      error: { code: 'VALIDATION_ERROR', message: '日期格式錯誤' },
      meta: {},
    };
    expect(() => unwrapApiResult(response, 'fallback')).toThrow('日期格式錯誤');
  });

  it('throws with fallback message when error.message is missing', () => {
    const response = { success: false, error: {}, meta: {} };
    expect(() => unwrapApiResult(response, 'fallback message')).toThrow('fallback message');
  });

  it('throws with string error field (legacy error format)', () => {
    const response = { success: false, error: '查詢失敗', meta: {} };
    expect(() => unwrapApiResult(response, 'fallback')).toThrow('查詢失敗');
  });

  it('returns result as-is for legacy response without success field', () => {
    const legacy = { query_id: 'old-123', total: 10 };
    const result = unwrapApiResult(legacy, 'fallback');
    expect(result).toBe(legacy);
    expect(result.query_id).toBe('old-123');
  });

  it('returns null as-is (does not throw)', () => {
    const result = unwrapApiResult(null, 'fallback');
    expect(result).toBeNull();
  });

  it('returns undefined as-is (does not throw)', () => {
    const result = unwrapApiResult(undefined, 'fallback');
    expect(result).toBeUndefined();
  });

  it('handles missing fallbackMessage gracefully', () => {
    const response = { success: false, error: { code: 'ERR' }, meta: {} };
    expect(() => unwrapApiResult(response)).toThrow();
  });
});

describe('unwrapApiData', () => {
  it('returns data field when success is true', () => {
    const response = { success: true, data: { items: [1, 2, 3] }, meta: {} };
    const data = unwrapApiData(response, 'fallback');
    expect(data).toEqual({ items: [1, 2, 3] });
  });

  it('throws when success is false', () => {
    const response = { success: false, error: { message: 'oops' }, meta: {} };
    expect(() => unwrapApiData(response, 'fallback')).toThrow('oops');
  });

  it('returns null data field correctly', () => {
    const response = { success: true, data: null, meta: {} };
    const data = unwrapApiData(response, 'fallback');
    expect(data).toBeNull();
  });

  it('returns response itself for legacy (no data field)', () => {
    const legacy = { items: [], total: 0 };
    const data = unwrapApiData(legacy, 'fallback');
    expect(data).toBe(legacy);
  });
});
