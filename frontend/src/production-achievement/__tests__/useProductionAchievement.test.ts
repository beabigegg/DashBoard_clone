// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { useProductionAchievement } from '../composables/useProductionAchievement';

function jsonResponse(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: { get: () => 'application/json' },
    json: async () => body,
  } as unknown as Response;
}

describe('useProductionAchievement', () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    // core/api.ts's apiGet uses the global fetch too (no MesApi bridge in jsdom)
    global.fetch = vi.fn();
  });

  afterEach(() => {
    global.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it('runQuery populates rows on success', async () => {
    const rows = [
      { output_date: '2026-01-01', shift_code: 'D', workcenter_group: 'A1', actual_output_qty: 100, target_qty: 120, achievement_rate: 0.833 },
    ];
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue(
      jsonResponse({ success: true, data: rows, meta: {} }),
    );

    const { rows: rowsRef, runQuery, hasQueried } = useProductionAchievement();
    await runQuery();

    expect(hasQueried.value).toBe(true);
    expect(rowsRef.value).toEqual(rows);
  });

  it('runQuery sets error and empties rows on network failure (no crash)', async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('network down'));

    const { rows, runQuery, error } = useProductionAchievement();
    await runQuery();

    expect(rows.value).toEqual([]);
    expect(error.value).not.toBe('');
  });

  it('saveTarget succeeds and refetches targets', async () => {
    (global.fetch as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce(jsonResponse({ success: true, data: null, meta: {} })) // PUT
      .mockResolvedValueOnce(jsonResponse({ success: true, data: [], meta: {} })); // GET targets refetch

    const { saveTarget, editForbidden, editError } = useProductionAchievement();
    const ok = await saveTarget({ shift_code: 'D', workcenter_group: 'A1', target_qty: 100 });

    expect(ok).toBe(true);
    expect(editForbidden.value).toBe(false);
    expect(editError.value).toBe('');
  });

  it('saveTarget flips editForbidden on a 403 FORBIDDEN response (graceful degrade)', async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue(
      jsonResponse(
        { success: false, error: { code: 'FORBIDDEN', message: '無權限' }, meta: {} },
        403,
      ),
    );

    const { saveTarget, editForbidden, editError } = useProductionAchievement();
    const ok = await saveTarget({ shift_code: 'D', workcenter_group: 'A1', target_qty: 100 });

    expect(ok).toBe(false);
    expect(editForbidden.value).toBe(true);
    expect(editError.value).not.toBe('');
  });

  it('saveTarget surfaces a 503 without flipping editForbidden (OPS disabled, not a permission denial)', async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue(
      jsonResponse(
        { success: false, error: { code: 'SERVICE_UNAVAILABLE', message: '服務暫停' }, meta: {} },
        503,
      ),
    );

    const { saveTarget, editForbidden, editError } = useProductionAchievement();
    const ok = await saveTarget({ shift_code: 'D', workcenter_group: 'A1', target_qty: 100 });

    expect(ok).toBe(false);
    expect(editForbidden.value).toBe(false);
    expect(editError.value).not.toBe('');
  });

  it('resetFilters clears rows and hasQueried', async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue(
      jsonResponse({ success: true, data: [{ output_date: '2026-01-01', shift_code: 'D', workcenter_group: 'A1', actual_output_qty: 1, target_qty: null, achievement_rate: null }], meta: {} }),
    );
    const { rows, runQuery, hasQueried, resetFilters } = useProductionAchievement();
    await runQuery();
    expect(rows.value.length).toBe(1);

    resetFilters();
    expect(rows.value).toEqual([]);
    expect(hasQueried.value).toBe(false);
  });
});
