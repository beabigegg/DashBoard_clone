// @vitest-environment jsdom
/**
 * Unit tests for useUphPerformanceViews composable
 *
 * Validates:
 * - fetchRanking never issues a request when pj_types is empty (the ranking
 *   block must stay empty/prompting until a Type is chosen — confirmed #2)
 * - fetchTrend defaults group_by to 'family' (confirmed #3)
 * - fetchAllViews fans out trend + detail unconditionally but gates ranking
 *   on the caller-supplied ranking Type selection
 * - detail per_page is clamped to the contract's 200 cap
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';

const apiGetMock = vi.fn();

vi.mock('../../src/core/api.js', () => ({
  apiGet: (...args) => apiGetMock(...args),
}));

import { useUphPerformanceViews } from '../../src/uph-performance/composables/useUphPerformanceViews.js';

describe('useUphPerformanceViews', () => {
  let views;

  beforeEach(() => {
    apiGetMock.mockReset();
    views = useUphPerformanceViews();
  });

  describe('fetchRanking gating (confirmed #2)', () => {
    it('does not call the API when pj_types is an empty array', async () => {
      await views.fetchRanking('q-1', []);
      expect(apiGetMock).not.toHaveBeenCalled();
      expect(views.ranking.items).toEqual([]);
    });

    it('does not call the API when queryId is falsy', async () => {
      await views.fetchRanking('', ['TYPE-A']);
      expect(apiGetMock).not.toHaveBeenCalled();
    });

    it('calls the ranking endpoint with pj_type[] when at least one Type is selected', async () => {
      apiGetMock.mockResolvedValueOnce({
        data: {
          items: [{ equipment_id: 'GDBA-001', workcenter_name: 'WC-1', db_wb_label: '焊接_DB', pj_type: 'TYPE-A', avg_uph: 12.5, sample_count: 10 }],
          pj_types: ['TYPE-A'],
        },
      });
      await views.fetchRanking('q-1', ['TYPE-A']);
      expect(apiGetMock).toHaveBeenCalledTimes(1);
      const calledUrl = apiGetMock.mock.calls[0][0];
      expect(calledUrl).toContain('/api/uph-performance/ranking');
      expect(calledUrl).toContain('query_id=q-1');
      expect(calledUrl).toContain('pj_type%5B%5D=TYPE-A');
      expect(views.ranking.items).toHaveLength(1);
      expect(views.ranking.items[0].avg_uph).toBe(12.5);
    });
  });

  describe('fetchTrend default group_by (confirmed #3)', () => {
    it('trendGroupBy ref defaults to family', () => {
      expect(views.trendGroupBy.value).toBe('family');
    });

    it('fetchTrend uses trendGroupBy.value when no explicit groupBy is passed', async () => {
      apiGetMock.mockResolvedValueOnce({ data: { labels: [], series: [], group_by: 'family' } });
      await views.fetchTrend('q-1', {});
      const calledUrl = apiGetMock.mock.calls[0][0];
      expect(calledUrl).toContain('group_by=family');
    });

    it('a missing hour bucket stored as null is preserved verbatim (not coerced to 0)', async () => {
      apiGetMock.mockResolvedValueOnce({
        data: { labels: ['08:00', '09:00'], series: [{ name: 'GDBA', data: [5, null] }], group_by: 'family' },
      });
      await views.fetchTrend('q-1', {});
      expect(views.trend.series[0].data).toEqual([5, null]);
    });
  });

  describe('fetchAllViews fan-out', () => {
    it('fetches trend + detail unconditionally, and ranking only when types are given', async () => {
      apiGetMock.mockResolvedValue({ data: {} });
      await views.fetchAllViews('q-1', {}, []);
      const calledUrls = apiGetMock.mock.calls.map((c) => c[0]);
      expect(calledUrls.some((u) => u.includes('/trend'))).toBe(true);
      expect(calledUrls.some((u) => u.includes('/detail'))).toBe(true);
      expect(calledUrls.some((u) => u.includes('/ranking'))).toBe(false);
    });

    it('fetches ranking too when a non-empty ranking Type list is given', async () => {
      apiGetMock.mockResolvedValue({ data: {} });
      await views.fetchAllViews('q-1', {}, ['TYPE-A']);
      const calledUrls = apiGetMock.mock.calls.map((c) => c[0]);
      expect(calledUrls.some((u) => u.includes('/ranking'))).toBe(true);
    });
  });

  describe('fetchFilterOptions fine-filter cross-narrowing params', () => {
    it('with no fineParams (default {}), calls the endpoint with only query_id (unchanged post-spool call site)', async () => {
      apiGetMock.mockResolvedValueOnce({ data: { equipment_id_options: ['GDBA-001'] } });
      const result = await views.fetchFilterOptions('q-1');
      expect(apiGetMock).toHaveBeenCalledTimes(1);
      const calledUrl = apiGetMock.mock.calls[0][0];
      expect(calledUrl).toContain('/api/uph-performance/filter-options');
      expect(calledUrl).toContain('query_id=q-1');
      expect(calledUrl).not.toContain('equipment_id');
      expect(result).toEqual({ equipment_id_options: ['GDBA-001'] });
    });

    it('merges fineParams into the query string, mirroring fetchTrend/fetchDetail', async () => {
      apiGetMock.mockResolvedValueOnce({ data: {} });
      await views.fetchFilterOptions('q-1', { 'equipment_id[]': ['GDBA-001'], 'package[]': ['PKG-X'] });
      const calledUrl = apiGetMock.mock.calls[0][0];
      expect(calledUrl).toContain('query_id=q-1');
      expect(calledUrl).toContain('equipment_id%5B%5D=GDBA-001');
      expect(calledUrl).toContain('package%5B%5D=PKG-X');
    });

    it('returns null (not throwing) when queryId is falsy, without calling the API', async () => {
      const result = await views.fetchFilterOptions('', { 'equipment_id[]': ['GDBA-001'] });
      expect(apiGetMock).not.toHaveBeenCalled();
      expect(result).toBeNull();
    });

    it('returns null when the response has success:false', async () => {
      apiGetMock.mockResolvedValueOnce({ success: false });
      const result = await views.fetchFilterOptions('q-1', { 'package[]': ['PKG-X'] });
      expect(result).toBeNull();
    });
  });

  describe('fetchDetail per_page cap', () => {
    it('clamps per_page to the contract max of 200', async () => {
      apiGetMock.mockResolvedValueOnce({ data: { rows: [], meta: { page: 1, per_page: 200, total_count: 0, total_pages: 1 } } });
      await views.fetchDetail('q-1', {}, 1, 500);
      const calledUrl = apiGetMock.mock.calls[0][0];
      expect(calledUrl).toContain('per_page=200');
    });
  });

  describe('resetAll', () => {
    it('clears trend, ranking, and detail state', async () => {
      apiGetMock.mockResolvedValue({
        data: { labels: ['a'], series: [{ name: 'x', data: [1] }], items: [{ equipment_id: 'e' }], pj_types: ['t'], rows: [{ lot_id: 'l' }], meta: { page: 1, per_page: 20, total_count: 1, total_pages: 1 }, group_by: 'family' },
      });
      await views.fetchTrend('q-1', {});
      await views.fetchRanking('q-1', ['TYPE-A']);
      await views.fetchDetail('q-1', {});
      views.resetAll();
      expect(views.trend.labels).toEqual([]);
      expect(views.ranking.items).toEqual([]);
      expect(views.detail.rows).toEqual([]);
      expect(views.detail.meta.total_count).toBe(0);
    });
  });
});
