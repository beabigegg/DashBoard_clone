/**
 * AC-9: URL param pre-population for new WIP filter fields.
 *
 * Verifies that workflow / bop / pjFunction round-trip correctly through
 * buildWipOverviewQueryParams (serialisation) and that the param key for
 * pjFunction is 'pj_function' on the wire (matching what App.vue reads back
 * via parseCsvParam('pj_function')).
 */

import { describe, it, expect } from 'vitest';
import {
  buildWipOverviewQueryParams,
} from '../../src/core/wip-derive';

describe('wip-url-params — buildWipOverviewQueryParams new fields', () => {
  it('serialises workflow, bop, pjFunction when non-empty', () => {
    const params = buildWipOverviewQueryParams({
      workflow: ['WF-A'],
      bop: ['B1'],
      pjFunction: ['FN'],
    });
    expect(params.workflow).toBe('WF-A');
    expect(params.bop).toBe('B1');
    expect(params.pj_function).toBe('FN');
  });

  it('serialises multiple values comma-joined', () => {
    const params = buildWipOverviewQueryParams({
      workflow: ['WF-A', 'WF-B'],
      bop: ['B1', 'B2'],
      pjFunction: ['FN1', 'FN2'],
    });
    expect(params.workflow).toBe('WF-A,WF-B');
    expect(params.bop).toBe('B1,B2');
    expect(params.pj_function).toBe('FN1,FN2');
  });

  it('omits keys when arrays are empty', () => {
    const params = buildWipOverviewQueryParams({
      workflow: [],
      bop: [],
      pjFunction: [],
    });
    expect('workflow' in params).toBe(false);
    expect('bop' in params).toBe(false);
    expect('pj_function' in params).toBe(false);
  });

  it('omits keys when fields are undefined', () => {
    const params = buildWipOverviewQueryParams({});
    expect('workflow' in params).toBe(false);
    expect('bop' in params).toBe(false);
    expect('pj_function' in params).toBe(false);
  });

  it('pj_function key matches what App.vue reads from URL (parseCsvParam("pj_function"))', () => {
    // The App.vue parseCsvParam reads window.location.search by param name.
    // buildWipOverviewQueryParams must emit 'pj_function' (not 'pjFunction')
    // so the round-trip URL → param → filter works.
    const params = buildWipOverviewQueryParams({ pjFunction: ['FN'] });
    expect(Object.keys(params)).toContain('pj_function');
    expect(Object.keys(params)).not.toContain('pjFunction');
  });

  it('does not affect existing fields when new fields are empty', () => {
    const params = buildWipOverviewQueryParams({
      workorder: ['WO-001'],
      workflow: [],
      bop: [],
      pjFunction: [],
    });
    expect(params.workorder).toBe('WO-001');
    expect('workflow' in params).toBe(false);
  });

  it('coerces string input to serialised form', () => {
    const params = buildWipOverviewQueryParams({
      workflow: 'WF-A',
      bop: 'B1',
      pjFunction: 'FN',
    });
    expect(params.workflow).toBe('WF-A');
    expect(params.bop).toBe('B1');
    expect(params.pj_function).toBe('FN');
  });
});
