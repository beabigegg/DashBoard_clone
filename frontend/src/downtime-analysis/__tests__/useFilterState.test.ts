import { describe, it, expect, vi } from 'vitest';
import { useFilterState } from '../composables/useFilterState';

describe('useFilterState', () => {
  describe('initial state', () => {
    it('initialises all array filters as empty', () => {
      const { state } = useFilterState();
      expect(state.workcenter_groups).toEqual([]);
      expect(state.families).toEqual([]);
      expect(state.resource_ids).toEqual([]);
      expect(state.package_groups).toEqual([]);
      expect(state.big_categories).toEqual([]);
      expect(state.status_types).toEqual([]);
    });

    it('initialises date fields as empty strings', () => {
      const { state } = useFilterState();
      expect(state.start_date).toBe('');
      expect(state.end_date).toBe('');
    });

    it('initialises granularity as day', () => {
      const { state } = useFilterState();
      expect(state.granularity).toBe('day');
    });
  });

  describe('updateField', () => {
    it('updates a single field', () => {
      const { state, updateField } = useFilterState();
      updateField('start_date', '2026-01-01');
      expect(state.start_date).toBe('2026-01-01');
    });

    it('updating resource_ids updates the state', () => {
      const { state, updateField } = useFilterState();
      updateField('resource_ids', ['R-001', 'R-002']);
      expect(state.resource_ids).toEqual(['R-001', 'R-002']);
    });
  });

  describe('updateAll', () => {
    it('updates multiple fields at once', () => {
      const { state, updateAll } = useFilterState();
      updateAll({ start_date: '2026-01-01', end_date: '2026-01-31', granularity: 'week' });
      expect(state.start_date).toBe('2026-01-01');
      expect(state.end_date).toBe('2026-01-31');
      expect(state.granularity).toBe('week');
    });
  });

  describe('reset', () => {
    it('resets all fields to defaults after modification', () => {
      const { state, updateField, reset } = useFilterState();
      updateField('start_date', '2026-01-01');
      updateField('resource_ids', ['R-001']);
      reset();
      expect(state.start_date).toBe('');
      expect(state.resource_ids).toEqual([]);
    });
  });

  describe('cross-narrow callback', () => {
    it('invokes callback when updateField is called', () => {
      const { updateField, onCrossNarrow } = useFilterState();
      const cb = vi.fn();
      onCrossNarrow(cb);
      updateField('resource_ids', ['R-42']);
      expect(cb).toHaveBeenCalledOnce();
      expect(cb.mock.calls[0][0].resource_ids).toEqual(['R-42']);
    });

    it('invokes callback when updateAll is called', () => {
      const { updateAll, onCrossNarrow } = useFilterState();
      const cb = vi.fn();
      onCrossNarrow(cb);
      updateAll({ workcenter_groups: ['WCG-1'] });
      expect(cb).toHaveBeenCalledOnce();
      expect(cb.mock.calls[0][0].workcenter_groups).toEqual(['WCG-1']);
    });

    it('callback receives full state snapshot', () => {
      const { updateField, onCrossNarrow } = useFilterState();
      const received: unknown[] = [];
      onCrossNarrow((s) => received.push({ ...s }));
      updateField('start_date', '2026-05-01');
      updateField('resource_ids', ['R-99']);
      expect(received).toHaveLength(2);
      expect((received[1] as Record<string, unknown>).resource_ids).toEqual(['R-99']);
    });

    it('multiple callbacks are all invoked', () => {
      const { updateField, onCrossNarrow } = useFilterState();
      const cb1 = vi.fn();
      const cb2 = vi.fn();
      onCrossNarrow(cb1);
      onCrossNarrow(cb2);
      updateField('families', ['F-1']);
      expect(cb1).toHaveBeenCalledOnce();
      expect(cb2).toHaveBeenCalledOnce();
    });
  });

  describe('hasEquipmentFilter', () => {
    it('is false when resource_ids is empty', () => {
      const { hasEquipmentFilter } = useFilterState();
      expect(hasEquipmentFilter.value).toBe(false);
    });

    it('is true when resource_ids has values', () => {
      const { updateField, hasEquipmentFilter } = useFilterState();
      updateField('resource_ids', ['R-001']);
      expect(hasEquipmentFilter.value).toBe(true);
    });
  });

  describe('buildQueryBody', () => {
    it('includes start_date and end_date always', () => {
      const { updateAll, buildQueryBody } = useFilterState();
      updateAll({ start_date: '2026-01-01', end_date: '2026-01-31' });
      const body = buildQueryBody();
      expect(body.start_date).toBe('2026-01-01');
      expect(body.end_date).toBe('2026-01-31');
    });

    it('omits empty arrays', () => {
      const { updateAll, buildQueryBody } = useFilterState();
      updateAll({ start_date: '2026-01-01', end_date: '2026-01-31' });
      const body = buildQueryBody();
      expect(body.workcenter_groups).toBeUndefined();
      expect(body.families).toBeUndefined();
      expect(body.resource_ids).toBeUndefined();
    });

    it('includes non-empty arrays', () => {
      const { updateAll, buildQueryBody } = useFilterState();
      updateAll({
        start_date: '2026-01-01',
        end_date: '2026-01-31',
        resource_ids: ['R-42'],
        status_types: ['UDT'],
      });
      const body = buildQueryBody();
      expect(body.resource_ids).toEqual(['R-42']);
      expect(body.status_types).toEqual(['UDT']);
    });
  });

  describe('setDefaultDates', () => {
    it('sets start_date and end_date to recent dates', () => {
      const { state, setDefaultDates } = useFilterState();
      setDefaultDates();
      expect(state.start_date).toMatch(/^\d{4}-\d{2}-\d{2}$/);
      expect(state.end_date).toMatch(/^\d{4}-\d{2}-\d{2}$/);
      // end_date should be yesterday or today
      const today = new Date();
      const end = new Date(state.end_date);
      expect(end.getTime()).toBeLessThanOrEqual(today.getTime());
    });
  });
});
