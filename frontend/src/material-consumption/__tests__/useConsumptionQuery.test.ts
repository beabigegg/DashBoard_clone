// @vitest-environment jsdom
/**
 * Unit tests for useConsumptionQuery composable
 * Change: material-part-consumption
 *
 * AC-3: granularity switch calls GET /view (NOT POST /query)
 * AC-5: sync/async detail polling
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { nextTick } from 'vue';

// We mock the core api module to avoid real fetch calls
vi.mock('../../core/api', () => ({
  apiPost: vi.fn(),
  apiGet: vi.fn(),
}));

import { apiPost, apiGet } from '../../core/api';
import { useConsumptionQuery } from '../composables/useConsumptionQuery';

const mockApiPost = vi.mocked(apiPost);
const mockApiGet = vi.mocked(apiGet);

describe('useConsumptionQuery', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('polls_job_status_until_done', async () => {
    // First POST /detail returns 202 async
    mockApiPost.mockResolvedValueOnce({
      success: true,
      data: {
        async: true,
        job_id: 'job-abc-123',
      },
    });

    // First GET /detail/job returns pending
    mockApiGet
      .mockResolvedValueOnce({ success: true, data: { status: 'pending' } })
      // Second GET returns completed (the status set by complete_job()) with query_id
      .mockResolvedValueOnce({ success: true, data: { status: 'completed', query_id: 'q-xyz' } });

    // GET /detail/page to load data after done
    mockApiGet.mockResolvedValueOnce({
      success: true,
      data: {
        rows: [{ material_part: 'PartA' }],
        pagination: { page: 1, total_pages: 1, total_rows: 1, per_page: 50 },
      },
    });

    const query = useConsumptionQuery();

    // Submit detail query
    const submitPromise = query.submitDetail({
      material_parts: ['PartA'],
      start_date: '2026-01-01',
      end_date: '2026-01-31',
    });

    await nextTick();

    // Advance timer to trigger first poll
    vi.advanceTimersByTime(2100);
    await nextTick();

    // Advance timer for second poll (done)
    vi.advanceTimersByTime(2100);
    await nextTick();
    await Promise.resolve(); // flush microtasks

    await submitPromise;

    // After done, composable should have fetched the first page
    // The detail query_id should be set
    expect(query.detailQueryId.value).toBe('q-xyz');
    expect(query.isDetailLoading.value).toBe(false);
  });

  it('resets_on_new_query_submit', async () => {
    // Set up first query result
    mockApiPost.mockResolvedValue({
      success: true,
      data: {
        query_id: 'q-first',
        kpi: { total_consumed: 500, total_required: 600, efficiency_pct: 83.3, lot_count: 10, workorder_count: 5 },
        trend: [{ period: '2026-W01', material_part: 'PartA', total_consumed: 500 }],
        type_breakdown: [],
      },
    });

    const query = useConsumptionQuery();
    await query.submitQuery({
      material_parts: ['PartA'],
      start_date: '2026-01-01',
      end_date: '2026-01-31',
      granularity: 'week',
    });
    await nextTick();

    expect(query.queryId.value).toBe('q-first');
    expect(query.trend.value.length).toBeGreaterThan(0);

    // Submit a new query — state should reset first
    mockApiPost.mockResolvedValue({
      success: true,
      data: {
        query_id: 'q-second',
        kpi: { total_consumed: 0, total_required: 0, efficiency_pct: 0, lot_count: 0, workorder_count: 0 },
        trend: [],
        type_breakdown: [],
      },
    });

    await query.submitQuery({
      material_parts: ['PartB'],
      start_date: '2026-02-01',
      end_date: '2026-02-28',
      granularity: 'month',
    });
    await nextTick();

    // Previous results should be gone; new query_id set
    expect(query.queryId.value).toBe('q-second');
    expect(query.trend.value).toHaveLength(0);
  });

  it('applyView_sends_types_as_repeated_params_without_oracle', async () => {
    // First, get a query_id via submitQuery
    mockApiPost.mockResolvedValueOnce({
      success: true,
      data: {
        query_id: 'q-applyview',
        kpi: { total_consumed: 100, total_required: 120, efficiency_pct: 83.3, lot_count: 5, workorder_count: 2 },
        trend: [],
        type_breakdown: [],
      },
    });
    const query = useConsumptionQuery();
    await query.submitQuery({
      material_parts: ['PartA'],
      start_date: '2026-01-01',
      end_date: '2026-01-31',
    });
    await nextTick();

    // applyView should use GET (apiGet), NOT apiPost
    mockApiGet.mockResolvedValueOnce({
      success: true,
      data: {
        trend: [{ period: '2026-01-01', material_part: 'PartA', total_consumed: 50 }],
        type_breakdown: [],
        kpi: { total_consumed: 50, total_required: 60, efficiency_pct: 83.3, lot_count: 3, workorder_count: 1 },
      },
    });

    await query.applyView('day', ['TypeA', 'TypeB']);
    await nextTick();

    // Verify apiGet was called (not apiPost for Oracle re-query)
    expect(mockApiGet).toHaveBeenCalledOnce();
    // The GET params should include granularity=day and types=['TypeA','TypeB']
    const callArgs = mockApiGet.mock.calls[0];
    const params = (callArgs[1] as { params: Record<string, unknown> }).params;
    expect(params['granularity']).toBe('day');
    expect(params['types']).toEqual(['TypeA', 'TypeB']);

    // apiPost should only have been called once (the initial submitQuery)
    expect(mockApiPost).toHaveBeenCalledOnce();

    // Trend should be updated
    expect(query.trend.value).toHaveLength(1);
    expect(query.currentGranularity.value).toBe('day');
  });
});
