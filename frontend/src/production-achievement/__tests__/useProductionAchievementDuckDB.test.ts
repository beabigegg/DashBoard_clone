// @vitest-environment node
/**
 * useProductionAchievementDuckDB — unit tests (TDD: written failing first).
 *
 * Change: production-achievement-async-spool (ADR-0016)
 * AC-7: PA-06 rollup (SPECNAME -> workcenter_group, case-insensitive join key)
 *       + PA-07 target join / achievement_rate null-zero guards
 * AC-8: activation threshold overridden to 0 (always activate on spool hit)
 *
 * `rollupAndJoin()` below is a pure-JS mirror of the DuckDB SQL built by
 * _buildRollup()/computeView() in useProductionAchievementDuckDB.ts — used
 * here for fast, engine-free numeric-correctness coverage. The authoritative
 * SQL-dialect parity check (same SQL text executed via the real `duckdb`
 * engine) lives in tests/test_frontend_production_achievement_parity.py.
 * Composable-level tests below (activation policy call, state machine,
 * error surfacing) exercise the REAL composable against a mocked DuckDB
 * client, mirroring downtime-analysis's useDowntimeDuckDB.test.ts pattern.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

// ── Types mirroring §3.28.1/.2/.3 ────────────────────────────────────────────

interface SpoolRow {
  output_date: string;
  shift_code: string;
  SPECNAME: string;
  actual_output_qty: number;
}

interface SpecMapRow {
  SPECNAME: string;
  workcenter_group: string;
}

interface TargetsMapRow {
  shift_code: string;
  workcenter_group: string;
  target_qty: number | null;
}

interface ReportRow {
  output_date: string;
  shift_code: string;
  workcenter_group: string;
  actual_output_qty: number;
  target_qty: number | null;
  achievement_rate: number | null;
}

// ── Pure-JS mirror of the composable's SQL (PA-06 rollup + PA-07 join) ──────

function rollupAndJoin(
  spoolRows: SpoolRow[],
  specMap: SpecMapRow[],
  targetsMap: TargetsMapRow[],
  filters: { shiftCode?: string; workcenterGroup?: string } = {},
): ReportRow[] {
  const specToGroup = new Map<string, string>();
  for (const row of specMap) {
    specToGroup.set(row.SPECNAME.trim().toUpperCase(), row.workcenter_group);
  }

  const rollup = new Map<string, { output_date: string; shift_code: string; workcenter_group: string; actual_output_qty: number }>();
  for (const row of spoolRows) {
    const group = specToGroup.get(row.SPECNAME.trim().toUpperCase());
    if (!group) continue; // PA-06 unmapped-SPECNAME exclusion
    const key = `${row.output_date}||${row.shift_code}||${group}`;
    const entry = rollup.get(key) || { output_date: row.output_date, shift_code: row.shift_code, workcenter_group: group, actual_output_qty: 0 };
    entry.actual_output_qty += Number(row.actual_output_qty || 0);
    rollup.set(key, entry);
  }

  const targetLookup = new Map<string, number | null>();
  for (const t of targetsMap) {
    targetLookup.set(`${t.shift_code}||${t.workcenter_group}`, t.target_qty);
  }

  let rows: ReportRow[] = [...rollup.values()].map((r) => {
    const target = targetLookup.has(`${r.shift_code}||${r.workcenter_group}`)
      ? targetLookup.get(`${r.shift_code}||${r.workcenter_group}`)!
      : null;
    let rate: number | null;
    if (target === null || target === 0) {
      rate = null; // PA-07: missing OR zero target -> null, never Infinity
    } else {
      rate = r.actual_output_qty / target;
    }
    return { ...r, target_qty: target, achievement_rate: rate };
  });

  if (filters.shiftCode) rows = rows.filter((r) => r.shift_code === filters.shiftCode);
  if (filters.workcenterGroup) rows = rows.filter((r) => r.workcenter_group === filters.workcenterGroup);

  rows.sort((a, b) =>
    a.output_date.localeCompare(b.output_date) ||
    a.shift_code.localeCompare(b.shift_code) ||
    a.workcenter_group.localeCompare(b.workcenter_group),
  );
  return rows;
}

describe('rollupAndJoin (PA-06 rollup parity mirror)', () => {
  const specMap: SpecMapRow[] = [
    { SPECNAME: 'EPOXY D/B', workcenter_group: '焊接_DB' },
    { SPECNAME: '金線製程', workcenter_group: '焊接_WB' },
  ];

  it('groups by (output_date, shift_code, workcenter_group), collapsing case-variant SPECNAMEs', () => {
    const spool: SpoolRow[] = [
      { output_date: '2026-04-27', shift_code: 'D', SPECNAME: 'Epoxy D/B', actual_output_qty: 100 },
      { output_date: '2026-04-27', shift_code: 'D', SPECNAME: 'epoxy d/b', actual_output_qty: 50 },
    ];
    const rows = rollupAndJoin(spool, specMap, []);
    expect(rows).toHaveLength(1);
    expect(rows[0].workcenter_group).toBe('焊接_DB');
    expect(rows[0].actual_output_qty).toBe(150);
  });

  it('excludes SPECNAMEs with no spec_workcenter_map entry (unmapped, data-boundary not error)', () => {
    const spool: SpoolRow[] = [
      { output_date: '2026-04-27', shift_code: 'D', SPECNAME: 'UNKNOWN_SPEC', actual_output_qty: 999 },
    ];
    const rows = rollupAndJoin(spool, specMap, []);
    expect(rows).toEqual([]);
  });

  it('produces separate rows per distinct workcenter_group for the same output_date/shift_code', () => {
    const spool: SpoolRow[] = [
      { output_date: '2026-04-27', shift_code: 'N', SPECNAME: 'Epoxy D/B', actual_output_qty: 10 },
      { output_date: '2026-04-27', shift_code: 'N', SPECNAME: '金線製程', actual_output_qty: 20 },
    ];
    const rows = rollupAndJoin(spool, specMap, []);
    expect(rows.map((r) => r.workcenter_group).sort()).toEqual(['焊接_DB', '焊接_WB']);
  });

  it('empty spool yields empty rows, never an error', () => {
    expect(rollupAndJoin([], specMap, [])).toEqual([]);
  });
});

describe('rollupAndJoin (PA-07 achievement_rate guards)', () => {
  const specMap: SpecMapRow[] = [{ SPECNAME: 'EPOXY D/B', workcenter_group: '焊接_DB' }];
  const spool: SpoolRow[] = [
    { output_date: '2026-04-27', shift_code: 'D', SPECNAME: 'Epoxy D/B', actual_output_qty: 250 },
  ];

  it('missing target row -> achievement_rate null', () => {
    const rows = rollupAndJoin(spool, specMap, []);
    expect(rows[0].target_qty).toBeNull();
    expect(rows[0].achievement_rate).toBeNull();
  });

  it('stored target_qty=0 -> achievement_rate null, never Infinity', () => {
    const targets: TargetsMapRow[] = [{ shift_code: 'D', workcenter_group: '焊接_DB', target_qty: 0 }];
    const rows = rollupAndJoin(spool, specMap, targets);
    expect(rows[0].target_qty).toBe(0);
    expect(rows[0].achievement_rate).toBeNull();
    expect(rows[0].achievement_rate).not.toBe(Infinity);
  });

  it('zero actual_output_qty + non-null non-zero target -> achievement_rate 0.0 (not null)', () => {
    const zeroSpool: SpoolRow[] = [
      { output_date: '2026-04-27', shift_code: 'D', SPECNAME: 'Epoxy D/B', actual_output_qty: 0 },
    ];
    const targets: TargetsMapRow[] = [{ shift_code: 'D', workcenter_group: '焊接_DB', target_qty: 500 }];
    const rows = rollupAndJoin(zeroSpool, specMap, targets);
    expect(rows[0].actual_output_qty).toBe(0);
    expect(rows[0].achievement_rate).toBe(0.0);
  });

  it('normal division computes actual/target', () => {
    const targets: TargetsMapRow[] = [{ shift_code: 'D', workcenter_group: '焊接_DB', target_qty: 500 }];
    const rows = rollupAndJoin(spool, specMap, targets);
    expect(rows[0].achievement_rate).toBe(0.5);
  });

  it('client-side shift_code/workcenter_group filters narrow the result set', () => {
    const targets: TargetsMapRow[] = [{ shift_code: 'D', workcenter_group: '焊接_DB', target_qty: 500 }];
    const matched = rollupAndJoin(spool, specMap, targets, { shiftCode: 'D', workcenterGroup: '焊接_DB' });
    const unmatched = rollupAndJoin(spool, specMap, targets, { shiftCode: 'N' });
    expect(matched).toHaveLength(1);
    expect(unmatched).toHaveLength(0);
  });
});

// ── Mocks for the real composable's DuckDB client + activation policy ───────

const eligibilityMock = vi.fn().mockReturnValue({ eligible: true, reason: 'ok' });

vi.mock('../../core/duckdb-activation-policy', () => ({
  checkLocalComputeEligibility: (...args: unknown[]) => eligibilityMock(...args),
}));

vi.mock('../../core/duckdb-client', () => {
  const mockClient = {
    init: vi.fn().mockResolvedValue(undefined),
    registerParquet: vi.fn().mockResolvedValue(undefined),
    sendQuery: vi.fn().mockResolvedValue([]),
    destroy: vi.fn(),
  };
  return {
    getDuckDBClient: vi.fn().mockReturnValue(mockClient),
    fetchParquetBuffer: vi.fn().mockResolvedValue(new ArrayBuffer(8)),
    isDuckDBSupported: vi.fn().mockReturnValue(true),
  };
});

async function importComposable() {
  return import('../composables/useProductionAchievementDuckDB');
}

async function mockedClient() {
  const mod = await import('../../core/duckdb-client');
  return mod.getDuckDBClient() as unknown as {
    init: ReturnType<typeof vi.fn>;
    registerParquet: ReturnType<typeof vi.fn>;
    sendQuery: ReturnType<typeof vi.fn>;
    destroy: ReturnType<typeof vi.fn>;
  };
}

describe('useProductionAchievementDuckDB composable', () => {
  beforeEach(() => {
    // Clear call history on the shared mocked DuckDB client singleton between
    // tests (getDuckDBClient() returns the SAME mock instance every call,
    // mirroring the real module's singleton) — implementations set via
    // mockResolvedValue survive clearAllMocks(), only call history resets.
    vi.clearAllMocks();
    eligibilityMock.mockReturnValue({ eligible: true, reason: 'ok' });
  });

  it('starts inactive/idle before activate()', async () => {
    const { useProductionAchievementDuckDB } = await importComposable();
    const composable = useProductionAchievementDuckDB();
    expect(composable.isActive.value).toBe(false);
    expect(composable.isLoading.value).toBe(false);
    expect(composable.error.value).toBe('');
  });

  it('activate() calls checkLocalComputeEligibility with threshold=0 (AC-8, always activate)', async () => {
    const { useProductionAchievementDuckDB } = await importComposable();
    const composable = useProductionAchievementDuckDB();
    await composable.activate('/api/spool/production_achievement/x.parquet', [], []);
    expect(eligibilityMock).toHaveBeenCalledWith(
      expect.objectContaining({ spoolDownloadUrl: '/api/spool/production_achievement/x.parquet', threshold: 0 }),
    );
    expect(composable.isActive.value).toBe(true);
  });

  it('activate() throws an explicit unsupported error when WASM is unsupported — no hidden server fallback', async () => {
    eligibilityMock.mockReturnValue({ eligible: false, reason: 'browser_unsupported' });
    const client = await mockedClient();

    const { useProductionAchievementDuckDB } = await importComposable();
    const composable = useProductionAchievementDuckDB();
    await expect(composable.activate('url', [], [])).rejects.toThrow();
    expect(composable.isActive.value).toBe(false);
    expect(composable.error.value.length).toBeGreaterThan(0);
    // No attempt to init the DuckDB client — nothing to fall back to.
    expect(client.init).not.toHaveBeenCalled();
  });

  it('activate() registers the spool parquet and both inline maps, then builds the rollup', async () => {
    const client = await mockedClient();
    client.sendQuery.mockClear();

    const { useProductionAchievementDuckDB } = await importComposable();
    const composable = useProductionAchievementDuckDB();
    const specMap: SpecMapRow[] = [{ SPECNAME: 'EPOXY D/B', workcenter_group: '焊接_DB' }];
    const targetsMap: TargetsMapRow[] = [{ shift_code: 'D', workcenter_group: '焊接_DB', target_qty: 500 }];
    await composable.activate('/api/spool/production_achievement/x.parquet', specMap, targetsMap);

    expect(client.registerParquet).toHaveBeenCalledWith('production_achievement_data', expect.any(ArrayBuffer));
    const sqlCalls = client.sendQuery.mock.calls.map((c: unknown[]) => String(c[0]));
    expect(sqlCalls.some((sql) => sql.includes('pa_spec_workcenter_map') && sql.includes('EPOXY D/B'))).toBe(true);
    expect(sqlCalls.some((sql) => sql.includes('pa_targets_map') && sql.includes('500'))).toBe(true);
    expect(sqlCalls.some((sql) => sql.includes('pa_rollup') && sql.toUpperCase().includes('UPPER(TRIM'))).toBe(true);
  });

  it('activate() sets error + isActive=false and rethrows on DuckDB init failure', async () => {
    const client = await mockedClient();
    client.init.mockRejectedValueOnce(new Error('WASM init failed'));

    const { useProductionAchievementDuckDB } = await importComposable();
    const composable = useProductionAchievementDuckDB();
    await expect(composable.activate('url', [], [])).rejects.toThrow('WASM init failed');
    expect(composable.isActive.value).toBe(false);
    expect(composable.error.value.length).toBeGreaterThan(0);
  });

  it('computeView() throws when called before activate() (state guard)', async () => {
    const { useProductionAchievementDuckDB } = await importComposable();
    const composable = useProductionAchievementDuckDB();
    await expect(composable.computeView()).rejects.toThrow();
  });

  it('updateTargetsMap() throws when called before activate()', async () => {
    const { useProductionAchievementDuckDB } = await importComposable();
    const composable = useProductionAchievementDuckDB();
    await expect(composable.updateTargetsMap([])).rejects.toThrow();
  });

  it('computeView() maps raw query rows into typed ProductionAchievementReportRow shape, empty spool -> empty rows', async () => {
    const client = await mockedClient();
    client.sendQuery.mockResolvedValueOnce([]); // spec map create
    client.sendQuery.mockResolvedValueOnce([]); // targets map create
    client.sendQuery.mockResolvedValueOnce([]); // rollup create
    client.sendQuery.mockResolvedValueOnce([
      {
        output_date: '2026-04-27',
        shift_code: 'D',
        workcenter_group: '焊接_DB',
        actual_output_qty: 150,
        target_qty: null,
        achievement_rate: null,
      },
    ]); // final SELECT for computeView()

    const { useProductionAchievementDuckDB } = await importComposable();
    const composable = useProductionAchievementDuckDB();
    await composable.activate('url', [{ SPECNAME: 'X', workcenter_group: 'Y' }], []);
    const rows = await composable.computeView();
    expect(rows).toEqual([
      {
        output_date: '2026-04-27',
        shift_code: 'D',
        workcenter_group: '焊接_DB',
        actual_output_qty: 150,
        target_qty: null,
        achievement_rate: null,
      },
    ]);
  });

  it('computeView() with a fully empty spool result returns an empty array, never an error', async () => {
    const client = await mockedClient();
    client.sendQuery.mockResolvedValue([]);

    const { useProductionAchievementDuckDB } = await importComposable();
    const composable = useProductionAchievementDuckDB();
    await composable.activate('url', [], []);
    const rows = await composable.computeView();
    expect(rows).toEqual([]);
  });

  it('deactivate() resets state and releases the DuckDB client', async () => {
    const client = await mockedClient();
    const { useProductionAchievementDuckDB } = await importComposable();
    const composable = useProductionAchievementDuckDB();
    await composable.activate('url', [], []);
    composable.deactivate();
    expect(composable.isActive.value).toBe(false);
    expect(client.destroy).toHaveBeenCalled();
    await expect(composable.computeView()).rejects.toThrow();
  });
});
