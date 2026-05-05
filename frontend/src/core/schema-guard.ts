/**
 * Lightweight runtime schema guard for API response validation.
 *
 * Design constraints:
 * - Zero runtime dependencies (no zod/ajv/yup)
 * - DEV-mode only: warnings via console.warn, never throws in production
 * - Spec language is intentionally conservative (7 primitives + nested objects + arrays)
 *
 * Spec primitives:
 *   'string'        — value must be typeof string
 *   'string?'       — string or null/undefined
 *   'number'        — value must be typeof number (and not NaN)
 *   'number?'       — number or null/undefined
 *   'number-int'    — integer number
 *   'string-iso-date' — string matching ISO 8601 date/datetime prefix
 *   'array'         — value must be an Array
 *   'boolean'       — value must be typeof boolean
 *   'boolean?'      — boolean or null/undefined
 *
 * Nested object spec: plain JS object { key: spec, key2: spec2, ... }
 * Array item spec: { __array: itemSpec } — every item is validated against itemSpec
 */

import type { FieldSpec } from './endpoint-schemas.js';

const _warned = new Set<string>();
const _isVerbose = (): boolean =>
  typeof localStorage !== 'undefined' && localStorage.getItem('schema-guard-verbose') === '1';

function _warn(key: string, msg: string): void {
  if (_isVerbose() || !_warned.has(key)) {
    _warned.add(key);
    console.warn(`[schema-guard] ${msg}`);
  }
}

/**
 * Assert that value matches spec. Calls console.warn (DEV only) on mismatch.
 *
 * @param value - Value to check
 * @param spec - Spec string or nested object spec
 * @param path - Dot-separated path for error messages
 * @returns true if valid, false if mismatch
 */
export function assertShape(value: unknown, spec: FieldSpec, path = ''): boolean {
  if (typeof spec === 'string') {
    return _checkPrimitive(value, spec, path);
  }

  if (spec && typeof spec === 'object' && !Array.isArray(spec)) {
    if ('__array' in spec) {
      return _checkArrayItems(value, (spec as { __array: FieldSpec }).__array, path);
    }
    return _checkObject(value, spec as Record<string, FieldSpec>, path);
  }

  _warn(`assertShape:unknown:${path}`, `Unknown spec type at '${path}': ${typeof spec}`);
  return false;
}

function _checkPrimitive(value: unknown, spec: string, path: string): boolean {
  const optional = spec.endsWith('?');
  const baseSpec = optional ? spec.slice(0, -1) : spec;

  if (optional && (value === null || value === undefined)) {
    return true;
  }

  switch (baseSpec) {
    case 'string':
      if (typeof value !== 'string') {
        _warn(`type:${path}`, `'${path}' expected string, got ${_typeof(value)}: ${_preview(value)}`);
        return false;
      }
      return true;

    case 'number':
      if (typeof value !== 'number' || isNaN(value)) {
        _warn(`type:${path}`, `'${path}' expected number, got ${_typeof(value)}: ${_preview(value)}`);
        return false;
      }
      return true;

    case 'number-int':
      if (typeof value !== 'number' || !Number.isInteger(value)) {
        _warn(`type:${path}`, `'${path}' expected integer, got ${_typeof(value)}: ${_preview(value)}`);
        return false;
      }
      return true;

    case 'string-iso-date':
      if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}/.test(value)) {
        _warn(`type:${path}`, `'${path}' expected ISO date string, got: ${_preview(value)}`);
        return false;
      }
      return true;

    case 'array':
      if (!Array.isArray(value)) {
        _warn(`type:${path}`, `'${path}' expected array, got ${_typeof(value)}`);
        return false;
      }
      return true;

    case 'boolean':
      if (typeof value !== 'boolean') {
        _warn(`type:${path}`, `'${path}' expected boolean, got ${_typeof(value)}: ${_preview(value)}`);
        return false;
      }
      return true;

    default:
      _warn(`unknown-spec:${path}`, `Unknown spec primitive '${spec}' at '${path}'`);
      return false;
  }
}

function _checkObject(value: unknown, spec: Record<string, FieldSpec>, path: string): boolean {
  if (value === null || value === undefined || typeof value !== 'object' || Array.isArray(value)) {
    _warn(`type:${path}`, `'${path}' expected object, got ${_typeof(value)}`);
    return false;
  }

  const obj = value as Record<string, unknown>;
  let valid = true;
  for (const [key, fieldSpec] of Object.entries(spec)) {
    const fieldPath = path ? `${path}.${key}` : key;
    const optional = typeof fieldSpec === 'string' && fieldSpec.endsWith('?');

    if (!(key in obj)) {
      if (!optional) {
        _warn(`missing:${fieldPath}`, `Missing required field '${fieldPath}'`);
        valid = false;
      }
      continue;
    }

    if (!assertShape(obj[key], fieldSpec, fieldPath)) {
      valid = false;
    }
  }
  return valid;
}

function _checkArrayItems(value: unknown, itemSpec: FieldSpec, path: string): boolean {
  if (!Array.isArray(value)) {
    _warn(`type:${path}`, `'${path}' expected array for item validation, got ${_typeof(value)}`);
    return false;
  }
  let valid = true;
  for (let i = 0; i < value.length; i++) {
    if (!assertShape(value[i], itemSpec, `${path}[${i}]`)) {
      valid = false;
      break; // Only report first failure to reduce noise
    }
  }
  return valid;
}

function _typeof(value: unknown): string {
  if (value === null) return 'null';
  if (Array.isArray(value)) return 'array';
  return typeof value;
}

function _preview(value: unknown): string {
  try {
    const str = JSON.stringify(value);
    return str && str.length > 50 ? str.slice(0, 50) + '...' : str ?? String(value);
  } catch {
    return String(value);
  }
}

/**
 * Reset warned set (for testing only).
 */
export function _resetWarned(): void {
  _warned.clear();
}
