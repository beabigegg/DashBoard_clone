/**
 * Tests for frontend/src/core/schema-guard.js
 *
 * Covers:
 * - Happy path: valid primitives, optional fields, nested objects
 * - Missing required field → returns false + warns
 * - Wrong type → returns false + warns
 * - Nested object validation
 * - Array spec validation
 * - Optional fields (? suffix) accept null/undefined
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { assertShape, _resetWarned } from '../src/core/schema-guard.js';

beforeEach(() => {
  vi.clearAllMocks();
  _resetWarned();
  vi.spyOn(console, 'warn').mockImplementation(() => {});
});

describe('assertShape — primitives', () => {
  it('string: accepts string value', () => {
    expect(assertShape('hello', 'string', 'field')).toBe(true);
    expect(console.warn).not.toHaveBeenCalled();
  });

  it('string: rejects number', () => {
    expect(assertShape(42, 'string', 'field')).toBe(false);
    expect(console.warn).toHaveBeenCalled();
  });

  it('string?: accepts null', () => {
    expect(assertShape(null, 'string?', 'field')).toBe(true);
  });

  it('string?: accepts undefined', () => {
    expect(assertShape(undefined, 'string?', 'field')).toBe(true);
  });

  it('string?: rejects number', () => {
    expect(assertShape(42, 'string?', 'field')).toBe(false);
  });

  it('number: accepts number', () => {
    expect(assertShape(3.14, 'number', 'field')).toBe(true);
  });

  it('number: rejects NaN', () => {
    expect(assertShape(NaN, 'number', 'field')).toBe(false);
    expect(console.warn).toHaveBeenCalled();
  });

  it('number: rejects string', () => {
    expect(assertShape('42', 'number', 'field')).toBe(false);
  });

  it('number?: accepts null', () => {
    expect(assertShape(null, 'number?', 'field')).toBe(true);
  });

  it('number-int: accepts integer', () => {
    expect(assertShape(5, 'number-int', 'field')).toBe(true);
  });

  it('number-int: rejects float', () => {
    expect(assertShape(3.14, 'number-int', 'field')).toBe(false);
  });

  it('string-iso-date: accepts ISO date', () => {
    expect(assertShape('2024-01-01', 'string-iso-date', 'field')).toBe(true);
    expect(assertShape('2024-01-01T00:00:00Z', 'string-iso-date', 'field')).toBe(true);
  });

  it('string-iso-date: rejects non-ISO string', () => {
    expect(assertShape('01/01/2024', 'string-iso-date', 'field')).toBe(false);
    expect(assertShape('2024/01/01', 'string-iso-date', 'field')).toBe(false);
  });

  it('array: accepts array', () => {
    expect(assertShape([1, 2, 3], 'array', 'field')).toBe(true);
  });

  it('array: rejects object', () => {
    expect(assertShape({ length: 3 }, 'array', 'field')).toBe(false);
  });

  it('boolean: accepts true/false', () => {
    expect(assertShape(true, 'boolean', 'field')).toBe(true);
    expect(assertShape(false, 'boolean', 'field')).toBe(true);
  });

  it('boolean: rejects truthy non-boolean', () => {
    expect(assertShape(1, 'boolean', 'field')).toBe(false);
  });
});

describe('assertShape — nested objects', () => {
  it('validates nested object with all required fields', () => {
    const spec = { name: 'string', count: 'number' };
    expect(assertShape({ name: 'test', count: 5 }, spec, 'obj')).toBe(true);
    expect(console.warn).not.toHaveBeenCalled();
  });

  it('warns and returns false for missing required field', () => {
    const spec = { name: 'string', count: 'number' };
    expect(assertShape({ name: 'test' }, spec, 'obj')).toBe(false);
    expect(console.warn).toHaveBeenCalled();
  });

  it('passes with optional fields absent', () => {
    const spec = { name: 'string', description: 'string?' };
    expect(assertShape({ name: 'test' }, spec, 'obj')).toBe(true);
  });

  it('warns on wrong type in nested field', () => {
    const spec = { count: 'number' };
    expect(assertShape({ count: 'not-a-number' }, spec, 'obj')).toBe(false);
    expect(console.warn).toHaveBeenCalled();
  });

  it('validates deeply nested objects', () => {
    const spec = { summary: { total: 'number', items: 'array' } };
    const valid = { summary: { total: 10, items: [] } };
    expect(assertShape(valid, spec, 'root')).toBe(true);
  });

  it('rejects non-object when object spec given', () => {
    const spec = { name: 'string' };
    expect(assertShape('not-an-object', spec, 'root')).toBe(false);
  });
});

describe('assertShape — array items', () => {
  it('validates each array item against itemSpec', () => {
    const spec = { __array: { name: 'string', value: 'number' } };
    const valid = [{ name: 'a', value: 1 }, { name: 'b', value: 2 }];
    expect(assertShape(valid, spec, 'items')).toBe(true);
  });

  it('rejects array with invalid item', () => {
    const spec = { __array: { name: 'string' } };
    const invalid = [{ name: 'a' }, { name: 42 }];
    expect(assertShape(invalid, spec, 'items')).toBe(false);
    expect(console.warn).toHaveBeenCalled();
  });

  it('rejects non-array for __array spec', () => {
    const spec = { __array: 'string' };
    expect(assertShape('not-array', spec, 'items')).toBe(false);
  });

  it('accepts empty array for __array spec', () => {
    const spec = { __array: { name: 'string' } };
    expect(assertShape([], spec, 'items')).toBe(true);
  });
});
