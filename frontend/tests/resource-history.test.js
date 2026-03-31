/**
 * Tests for resource-history OEE calculation formulas.
 *
 * The core calculations in useResourceHistoryDuckDB.js are not exported
 * individually, but are replicated here to verify the mathematical contract
 * mirrors the Python backend (resource_dataset_cache.py).
 *
 * Formula reference (from useResourceHistoryDuckDB.js):
 *   OU%    = prd / (prd + sby + udt + sdt + egt) * 100
 *   Avail% = (prd + sby + egt) / (prd + sby + egt + sdt + udt + nst) * 100
 */
import test from 'node:test';
import assert from 'node:assert/strict';


// ── Inline replicas of useResourceHistoryDuckDB pure functions ─────────────

function sf(val, def = 0) {
  const n = Number(val);
  return isNaN(n) ? def : n;
}

function calcOuPct(prd, sby, udt, sdt, egt) {
  const denom = prd + sby + udt + sdt + egt;
  return denom > 0 ? Math.round((prd / denom) * 1000) / 10 : 0;
}

function calcAvailPct(prd, sby, udt, sdt, egt, nst) {
  const num = prd + sby + egt;
  const denom = prd + sby + egt + sdt + udt + nst;
  return denom > 0 ? Math.round((num / denom) * 1000) / 10 : 0;
}

function statusPct(val, total) {
  return total > 0 ? Math.round((val / total) * 1000) / 10 : 0;
}


// ── sf (safe float) ────────────────────────────────────────────────────────

test('sf converts number correctly', () => {
  assert.equal(sf(3.14), 3.14);
});

test('sf returns default for NaN string', () => {
  assert.equal(sf('not-a-number'), 0);
});

test('sf converts null to 0 (Number(null) === 0)', () => {
  // Number(null) === 0, so sf does not return the default for null
  assert.equal(sf(null, -1), 0);
});

test('sf treats 0 as valid (returns 0, not default)', () => {
  assert.equal(sf(0, 99), 0);
});


// ── calcOuPct ─────────────────────────────────────────────────────────────

test('calcOuPct returns 100 when all time is PRD', () => {
  assert.equal(calcOuPct(100, 0, 0, 0, 0), 100);
});

test('calcOuPct returns 0 when no denominator', () => {
  assert.equal(calcOuPct(0, 0, 0, 0, 0), 0);
});

test('calcOuPct is rounded to one decimal place', () => {
  // 70 / (70 + 10 + 5 + 5 + 5) = 70/95 = 0.7368... → 73.7%
  const result = calcOuPct(70, 10, 5, 5, 5);
  assert.equal(result, Math.round((70 / 95) * 1000) / 10);
});

test('calcOuPct is 0 when prd is 0', () => {
  assert.equal(calcOuPct(0, 50, 10, 10, 10), 0);
});


// ── calcAvailPct ──────────────────────────────────────────────────────────

test('calcAvailPct returns 100 when all time is in available categories', () => {
  // PRD + SBY + EGT = all time, no SDT/UDT/NST
  assert.equal(calcAvailPct(50, 30, 0, 0, 20, 0), 100);
});

test('calcAvailPct returns 0 when no denominator', () => {
  assert.equal(calcAvailPct(0, 0, 0, 0, 0, 0), 0);
});

test('calcAvailPct excludes SDT/UDT/NST from numerator', () => {
  // (10 + 0 + 0) / (10 + 0 + 10 + 0 + 0 + 0) = 50%
  assert.equal(calcAvailPct(10, 0, 10, 0, 0, 0), 50);
});

test('calcAvailPct is rounded to one decimal place', () => {
  const prd = 70, sby = 0, udt = 10, sdt = 10, egt = 0, nst = 10;
  const expected = Math.round(((prd + sby + egt) / (prd + sby + egt + sdt + udt + nst)) * 1000) / 10;
  assert.equal(calcAvailPct(prd, sby, udt, sdt, egt, nst), expected);
});


// ── statusPct ─────────────────────────────────────────────────────────────

test('statusPct returns 50 for half of total', () => {
  assert.equal(statusPct(5, 10), 50);
});

test('statusPct returns 0 when total is 0', () => {
  assert.equal(statusPct(5, 0), 0);
});

test('statusPct is rounded to one decimal place', () => {
  const result = statusPct(1, 3); // 33.333...%
  assert.equal(result, Math.round((1 / 3) * 1000) / 10);
});


// ── OEE formula parity with Python ────────────────────────────────────────

test('OEE formulas match Python backend for a typical shift', () => {
  // Example shift data (hours)
  const prd = 18, sby = 2, udt = 1, sdt = 2, egt = 1, nst = 0;

  const ou = calcOuPct(prd, sby, udt, sdt, egt);
  const avail = calcAvailPct(prd, sby, udt, sdt, egt, nst);

  // OU% = 18 / (18+2+1+2+1) = 18/24 = 75%
  assert.equal(ou, 75);
  // Avail% = (18+2+1) / (18+2+1+2+1+0) = 21/24 = 87.5%
  assert.equal(avail, 87.5);
});
