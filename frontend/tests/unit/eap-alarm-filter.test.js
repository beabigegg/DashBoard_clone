/**
 * Unit tests for useEapAlarmFilter composable
 *
 * Validates:
 * - _lastCommitted re-sync after fetchFilterOptions (snapshot-diff rule)
 * - buildFineFilterParams returns correct URL params
 * - Fine filter state management
 * - Default date range is set correctly
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { useEapAlarmFilter } from '../../src/eap-alarm/composables/useEapAlarmFilter.js';

// Vitest runs in jsdom environment; Vue reactivity should work fine.

describe('useEapAlarmFilter', () => {
  let filter;

  beforeEach(() => {
    filter = useEapAlarmFilter();
  });

  it('initializes coarse filter with empty machines list', () => {
    expect(Array.isArray(filter.coarseFilter.machines)).toBe(true);
    expect(filter.coarseFilter.machines).toHaveLength(0);
  });

  it('initializes fine filter as empty', () => {
    expect(filter.fineFilter.alarm_text).toHaveLength(0);
    expect(filter.fineFilter.eqp_id).toHaveLength(0);
  });

  it('setDefaultDateRange sets date_from before date_to', () => {
    filter.setDefaultDateRange();
    expect(filter.coarseFilter.date_from).toBeTruthy();
    expect(filter.coarseFilter.date_to).toBeTruthy();
    expect(filter.coarseFilter.date_from < filter.coarseFilter.date_to).toBe(true);
  });

  describe('_lastCommitted re-sync (snapshot-diff rule)', () => {
    it('applyFilterOptions re-syncs _lastCommitted from current fine filter selection', () => {
      // Set fine filter before calling applyFilterOptions
      filter.fineFilter.alarm_text = ['ALARM_A', 'ALARM_B'];
      filter.fineFilter.eqp_id = ['EQ-01'];

      const mockOptions = {
        alarm_text_options: ['ALARM_A', 'ALARM_B', 'ALARM_C'],
        equipment_id_options: ['EQ-01', 'EQ-02'],
      };

      filter.applyFilterOptions(mockOptions);

      // Filter options should be applied
      expect(filter.filterOptions.alarm_text_options).toEqual(['ALARM_A', 'ALARM_B', 'ALARM_C']);
      expect(filter.filterOptions.equipment_id_options).toEqual(['EQ-01', 'EQ-02']);

      // hasFineFilterChanged() should return false right after applyFilterOptions
      // because _lastCommitted was re-synced from current selection
      expect(filter.hasFineFilterChanged()).toBe(false);
    });

    it('hasFineFilterChanged returns false immediately after applyFilterOptions', () => {
      filter.fineFilter.alarm_text = ['TEST'];
      filter.applyFilterOptions({
        alarm_text_options: ['TEST', 'OTHER'],
        equipment_id_options: [],
      });
      // _lastCommitted re-synced: no change
      expect(filter.hasFineFilterChanged()).toBe(false);
    });

    it('hasFineFilterChanged returns true when fine filter changes after re-sync', () => {
      filter.applyFilterOptions({
        alarm_text_options: ['ALARM_A'],
        equipment_id_options: [],
      });
      // _lastCommitted = {alarm_text: [], eqp_id: []}

      // Now change the fine filter
      filter.fineFilter.alarm_text = ['ALARM_A'];

      expect(filter.hasFineFilterChanged()).toBe(true);
    });

    it('resetFineFilter re-syncs _lastCommitted', () => {
      filter.fineFilter.alarm_text = ['ALARM_A'];

      filter.resetFineFilter();

      // After reset, fine filter is empty and _lastCommitted is re-synced
      expect(filter.fineFilter.alarm_text).toHaveLength(0);
      expect(filter.hasFineFilterChanged()).toBe(false);
    });

    it('commitFineFilter re-syncs _lastCommitted from current selection', () => {
      filter.fineFilter.alarm_text = ['ALARM_A'];
      // Before commit: changed
      expect(filter.hasFineFilterChanged()).toBe(true);

      filter.commitFineFilter();
      // After commit: no longer changed
      expect(filter.hasFineFilterChanged()).toBe(false);
    });
  });

  describe('buildFineFilterParams', () => {
    it('returns only query_id when fine filter is empty', () => {
      filter.setQueryId('q-001');
      const params = filter.buildFineFilterParams();
      expect(params.query_id).toBe('q-001');
      expect(params['alarm_text[]']).toBeUndefined();
      expect(params['equipment_id[]']).toBeUndefined();
    });

    it('includes alarm_text array when filter is set', () => {
      filter.setQueryId('q-002');
      filter.fineFilter.alarm_text = ['ALARM_A', 'ALARM_B'];
      const params = filter.buildFineFilterParams();
      expect(params['alarm_text[]']).toEqual(['ALARM_A', 'ALARM_B']);
    });

    it('includes eqp_id array as equipment_id when filter is set', () => {
      filter.setQueryId('q-004');
      filter.fineFilter.eqp_id = ['EQ-01', 'EQ-02'];
      const params = filter.buildFineFilterParams();
      expect(params['equipment_id[]']).toEqual(['EQ-01', 'EQ-02']);
    });
  });

  describe('setQueryId / spoolReady', () => {
    it('sets queryId and spoolReady on non-empty id', () => {
      filter.setQueryId('q-xyz');
      expect(filter.queryId.value).toBe('q-xyz');
      expect(filter.spoolReady.value).toBe(true);
    });

    it('sets spoolReady to false on empty id', () => {
      filter.setQueryId('');
      expect(filter.spoolReady.value).toBe(false);
    });
  });
});
