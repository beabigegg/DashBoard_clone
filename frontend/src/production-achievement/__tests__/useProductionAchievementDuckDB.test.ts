// @vitest-environment node
/**
 * useProductionAchievementDuckDB — unit tests (TDD: written failing first).
 *
 * Change: production-achievement-overhaul (IP-6)
 * design.md -> DuckDB-WASM rollup; ADR-0016 Extension section (2-stage pipeline).
 *
 * Stage 1 (`pa_rollup_raw`): identical INNER JOIN SPECNAME -> raw workcenter_group
 *   (PA-06, unchanged), now carrying PACKAGE_LF through GROUP BY.
 * Stage 2 (`pa_rollup`, redefined in place): INNER JOIN workcenter_merge_map (D2,
 *   PA-10, exclude-by-absence) + LEFT JOIN package_lf_map (D1, PA-09,
 *   fallback-to-self / '(未分類)').
 * computeDailyView / computeCumulativeView replace the flat computeView()
 * (PA-12/PA-13, D3 aggregate-then-divide).
 *
 * `rollupAndJoin()` below is a pure-JS mirror of the DuckDB SQL for fast,
 * engine-free numeric-correctness coverage (mirrors the previous file's own
 * convention). The authoritative SQL-dialect parity check (real `duckdb`
 * engine) lives in tests/test_frontend_production_achievement_parity.py.
 * Composable-level tests exercise the REAL composable against a mocked DuckDB
 * client (same convention as before).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

// ── Types mirroring §3.28.1 / §3.28.2 / §3.33 / §3.34 ───────────────────────

interface SpoolRow {
  output_date: string;
  shift_code: string;
  SPECNAME: string;
  PACKAGE_LF: string | null;
  actual_output_qty: number;
}

interface SpecMapRow {
  SPECNAME: string;
  workcenter_group: string;
}

interface PackageLfMapRow {
  raw_package_lf: string;
  merged_group: string;
}

interface WorkcenterMergeMapRow {
  raw_workcenter_group: string;
  merged_workcenter_group: string;
}

interface DailyPlanMapRow {
  workcenter_group: string;
  package_lf_group: string;
  daily_plan_qty: number | null;
}

interface RollupRow {
  output_date: string;
  shift_code: string;
  workcenter_group: string;
  package_lf_group: string;
  actual_output_qty: number;
}

const UNCLASSIFIED = '(未分類)';

// ── Pure-JS mirror of the 2-stage pipeline (PA-06/PA-09/PA-10) ──────────────

function rollupAndJoin(
  spoolRows: SpoolRow[],
  specMap: SpecMapRow[],
  workcenterMergeMap: WorkcenterMergeMapRow[],
  packageLfMap: PackageLfMapRow[],
): RollupRow[] {
  const specToGroup = new Map<string, string>();
  for (const row of specMap) {
    specToGroup.set(row.SPECNAME.trim().toUpperCase(), row.workcenter_group);
  }

  // Stage 1: pa_rollup_raw (SPECNAME -> raw workcenter_group, PACKAGE_LF carried through)
  const rawRollup = new Map<string, { output_date: string; shift_code: string; workcenter_group: string; package_lf: string | null; actual_output_qty: number }>();
  for (const row of spoolRows) {
    const rawGroup = specToGroup.get(row.SPECNAME.trim().toUpperCase());
    if (!rawGroup) continue; // PA-06 unmapped-SPECNAME exclusion
    const key = `${row.output_date}||${row.shift_code}||${rawGroup}||${row.PACKAGE_LF ?? ''}`;
    const entry = rawRollup.get(key) || { output_date: row.output_date, shift_code: row.shift_code, workcenter_group: rawGroup, package_lf: row.PACKAGE_LF, actual_output_qty: 0 };
    entry.actual_output_qty += Number(row.actual_output_qty || 0);
    rawRollup.set(key, entry);
  }

  // Stage 2: pa_rollup — INNER JOIN workcenter_merge_map (D2) + LEFT JOIN package_lf_map (D1)
  const wcMergeLookup = new Map<string, string>();
  for (const row of workcenterMergeMap) wcMergeLookup.set(row.raw_workcenter_group, row.merged_workcenter_group);
  const pkgMergeLookup = new Map<string, string>();
  for (const row of packageLfMap) pkgMergeLookup.set(row.raw_package_lf, row.merged_group);

  const rollup = new Map<string, RollupRow>();
  for (const entry of rawRollup.values()) {
    const mergedWc = wcMergeLookup.get(entry.workcenter_group);
    if (mergedWc === undefined) continue; // D2: absence -> excluded (INNER JOIN)
    const rawPkg = entry.package_lf;
    const mergedPkg =
      rawPkg === null || rawPkg === '' ? UNCLASSIFIED : (pkgMergeLookup.get(rawPkg) ?? rawPkg); // D1: absence -> fallback-to-self
    const key = `${entry.output_date}||${entry.shift_code}||${mergedWc}||${mergedPkg}`;
    const row = rollup.get(key) || { output_date: entry.output_date, shift_code: entry.shift_code, workcenter_group: mergedWc, package_lf_group: mergedPkg, actual_output_qty: 0 };
    row.actual_output_qty += entry.actual_output_qty;
    rollup.set(key, row);
  }
  return [...rollup.values()];
}

describe('rollupAndJoin (2-stage pipeline: PA-06 -> PA-09/PA-10)', () => {
  const specMap: SpecMapRow[] = [{ SPECNAME: 'EPOXY D/B', workcenter_group: '焊接_DB' }];

  it('Stage 1 excludes unmapped SPECNAME (PA-06, unchanged)', () => {
    const spool: SpoolRow[] = [{ output_date: '2026-07-01', shift_code: 'D', SPECNAME: 'UNKNOWN', PACKAGE_LF: 'X', actual_output_qty: 10 }];
    expect(rollupAndJoin(spool, specMap, [], [])).toEqual([]);
  });

  it('D2 (workcenter_merge_map): raw workcenter_group absent from the map is EXCLUDED entirely (INNER JOIN, not LEFT JOIN)', () => {
    const spool: SpoolRow[] = [{ output_date: '2026-07-01', shift_code: 'D', SPECNAME: 'Epoxy D/B', PACKAGE_LF: 'SOD-123FL', actual_output_qty: 100 }];
    // No workcenter_merge_map row for 焊接_DB -> absence must exclude, never fall back to itself.
    const rows = rollupAndJoin(spool, specMap, [], []);
    expect(rows).toEqual([]);
  });

  it('D2: raw workcenter_group present in the map is included and renamed to merged_workcenter_group', () => {
    const spool: SpoolRow[] = [{ output_date: '2026-07-01', shift_code: 'D', SPECNAME: 'Epoxy D/B', PACKAGE_LF: null, actual_output_qty: 100 }];
    const wcMap: WorkcenterMergeMapRow[] = [{ raw_workcenter_group: '焊接_DB', merged_workcenter_group: '焊接_DB' }];
    const rows = rollupAndJoin(spool, specMap, wcMap, []);
    expect(rows).toHaveLength(1);
    expect(rows[0].workcenter_group).toBe('焊接_DB');
  });

  it('D2: two raw workcenter_groups merging into one (焊接_DW -> 焊接_WB) combine their actual_output_qty', () => {
    const specMap2: SpecMapRow[] = [
      { SPECNAME: 'SPEC-WB', workcenter_group: '焊接_WB' },
      { SPECNAME: 'SPEC-DW', workcenter_group: '焊接_DW' },
    ];
    const spool: SpoolRow[] = [
      { output_date: '2026-07-01', shift_code: 'D', SPECNAME: 'SPEC-WB', PACKAGE_LF: null, actual_output_qty: 100 },
      { output_date: '2026-07-01', shift_code: 'D', SPECNAME: 'SPEC-DW', PACKAGE_LF: null, actual_output_qty: 50 },
    ];
    const wcMap: WorkcenterMergeMapRow[] = [
      { raw_workcenter_group: '焊接_WB', merged_workcenter_group: '焊接_WB' },
      { raw_workcenter_group: '焊接_DW', merged_workcenter_group: '焊接_WB' },
    ];
    const rows = rollupAndJoin(spool, specMap2, wcMap, []);
    expect(rows).toHaveLength(1);
    expect(rows[0].workcenter_group).toBe('焊接_WB');
    expect(rows[0].actual_output_qty).toBe(150);
  });

  it('D1 (package_lf_map): raw PACKAGE_LF absent from the map falls back to ITSELF (LEFT JOIN, not INNER JOIN)', () => {
    const spool: SpoolRow[] = [{ output_date: '2026-07-01', shift_code: 'D', SPECNAME: 'Epoxy D/B', PACKAGE_LF: 'BRAND-NEW-VALUE', actual_output_qty: 10 }];
    const wcMap: WorkcenterMergeMapRow[] = [{ raw_workcenter_group: '焊接_DB', merged_workcenter_group: '焊接_DB' }];
    const rows = rollupAndJoin(spool, specMap, wcMap, []); // no package_lf_map rows at all
    expect(rows).toHaveLength(1);
    expect(rows[0].package_lf_group).toBe('BRAND-NEW-VALUE'); // fell back to self, not dropped
  });

  it('D1: NULL PACKAGE_LF resolves to the sentinel group (未分類)', () => {
    const spool: SpoolRow[] = [{ output_date: '2026-07-01', shift_code: 'D', SPECNAME: 'Epoxy D/B', PACKAGE_LF: null, actual_output_qty: 10 }];
    const wcMap: WorkcenterMergeMapRow[] = [{ raw_workcenter_group: '焊接_DB', merged_workcenter_group: '焊接_DB' }];
    const rows = rollupAndJoin(spool, specMap, wcMap, []);
    expect(rows[0].package_lf_group).toBe('(未分類)');
  });

  it('D1: blank-string PACKAGE_LF also resolves to (未分類), same as NULL', () => {
    const spool: SpoolRow[] = [{ output_date: '2026-07-01', shift_code: 'D', SPECNAME: 'Epoxy D/B', PACKAGE_LF: '', actual_output_qty: 10 }];
    const wcMap: WorkcenterMergeMapRow[] = [{ raw_workcenter_group: '焊接_DB', merged_workcenter_group: '焊接_DB' }];
    const rows = rollupAndJoin(spool, specMap, wcMap, []);
    expect(rows[0].package_lf_group).toBe('(未分類)');
  });

  it('D1: the 4 confirmed merges resolve raw PACKAGE_LF to their merged_group', () => {
    const spool: SpoolRow[] = [
      { output_date: '2026-07-01', shift_code: 'D', SPECNAME: 'Epoxy D/B', PACKAGE_LF: 'SOD-123FL OP1', actual_output_qty: 10 },
      { output_date: '2026-07-01', shift_code: 'D', SPECNAME: 'Epoxy D/B', PACKAGE_LF: 'TO-277B', actual_output_qty: 5 },
    ];
    const wcMap: WorkcenterMergeMapRow[] = [{ raw_workcenter_group: '焊接_DB', merged_workcenter_group: '焊接_DB' }];
    const pkgMap: PackageLfMapRow[] = [
      { raw_package_lf: 'SOD-123FL OP1', merged_group: 'SOD-123FL' },
      { raw_package_lf: 'TO-277B', merged_group: 'TO-277(B)' },
    ];
    const rows = rollupAndJoin(spool, specMap, wcMap, pkgMap);
    const byGroup = Object.fromEntries(rows.map((r) => [r.package_lf_group, r.actual_output_qty]));
    expect(byGroup['SOD-123FL']).toBe(10);
    expect(byGroup['TO-277(B)']).toBe(5);
  });

  it('D1: a self-referential mapping (raw_package_lf === merged_group) is a harmless no-op, identical to an absent mapping (monkey-test: malformed/redundant settings write)', () => {
    // Nothing in upsert_package_lf() (backend) or this client-side resolution
    // validates against raw===merged — a settings-page admin CAN write this
    // redundant row. Since D1 resolution is `mapping.get(raw, raw)`, a
    // self-referential entry produces the EXACT same output as no entry at
    // all: this is provably safe, not merely "does not crash." (Note: for
    // D2/workcenter_merge_map, raw===merged is the NORMAL/expected shape for
    // every currently-included station — see the DDL seed data — so it is
    // asserted separately above, not adversarial there.)
    const spool: SpoolRow[] = [{ output_date: '2026-07-01', shift_code: 'D', SPECNAME: 'Epoxy D/B', PACKAGE_LF: 'SELF-MAPPED', actual_output_qty: 42 }];
    const wcMap: WorkcenterMergeMapRow[] = [{ raw_workcenter_group: '焊接_DB', merged_workcenter_group: '焊接_DB' }];
    const selfReferentialPkgMap: PackageLfMapRow[] = [{ raw_package_lf: 'SELF-MAPPED', merged_group: 'SELF-MAPPED' }];

    const withSelfMap = rollupAndJoin(spool, specMap, wcMap, selfReferentialPkgMap);
    const withNoMap = rollupAndJoin(spool, specMap, wcMap, []);

    expect(withSelfMap).toEqual(withNoMap);
    expect(withSelfMap).toHaveLength(1);
    expect(withSelfMap[0].package_lf_group).toBe('SELF-MAPPED');
  });

  it('D1/D2 join kinds are not swapped: an excluded workcenter_group never falls back to itself, and an unmapped package_lf is never dropped', () => {
    const spool: SpoolRow[] = [
      { output_date: '2026-07-01', shift_code: 'D', SPECNAME: 'Epoxy D/B', PACKAGE_LF: 'UNMAPPED-PKG', actual_output_qty: 10 },
    ];
    // 焊接_DB has NO row in workcenter_merge_map -> must be excluded (D2), regardless of package_lf_map.
    const rows = rollupAndJoin(spool, specMap, [], []);
    expect(rows).toEqual([]);
  });

  it('empty spool yields empty rows, never an error', () => {
    expect(rollupAndJoin([], specMap, [], [])).toEqual([]);
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

  it('activate() calls checkLocalComputeEligibility with threshold=0 (always activate)', async () => {
    const { useProductionAchievementDuckDB } = await importComposable();
    const composable = useProductionAchievementDuckDB();
    await composable.activate('/api/spool/production_achievement/x.parquet', [], [], [], []);
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
    await expect(composable.activate('url', [], [], [], [])).rejects.toThrow();
    expect(composable.isActive.value).toBe(false);
    expect(composable.error.value.length).toBeGreaterThan(0);
    expect(client.init).not.toHaveBeenCalled();
  });

  it('activate() registers the spool parquet and all 5 inline maps, then builds both rollup stages', async () => {
    const client = await mockedClient();
    client.sendQuery.mockClear();

    const { useProductionAchievementDuckDB } = await importComposable();
    const composable = useProductionAchievementDuckDB();
    const specMap = [{ SPECNAME: 'EPOXY D/B', workcenter_group: '焊接_DB' }];
    const targetsMap = [{ shift_code: 'D', workcenter_group: '焊接_DB', target_qty: 500 }];
    const packageLfMap = [{ raw_package_lf: 'SOD-123FL OP1', merged_group: 'SOD-123FL' }];
    const workcenterMergeMap = [{ raw_workcenter_group: '焊接_DB', merged_workcenter_group: '焊接_DB' }];
    const dailyPlanMap = [{ workcenter_group: '焊接_DB', package_lf_group: 'SOD-123FL', daily_plan_qty: 300 }];
    await composable.activate('/api/spool/production_achievement/x.parquet', specMap, targetsMap, packageLfMap, workcenterMergeMap, dailyPlanMap);

    expect(client.registerParquet).toHaveBeenCalledWith('production_achievement_data', expect.any(ArrayBuffer));
    const sqlCalls = client.sendQuery.mock.calls.map((c: unknown[]) => String(c[0]));
    expect(sqlCalls.some((sql) => sql.includes('pa_spec_workcenter_map') && sql.includes('EPOXY D/B'))).toBe(true);
    expect(sqlCalls.some((sql) => sql.includes('pa_targets_map') && sql.includes('500'))).toBe(true);
    expect(sqlCalls.some((sql) => sql.includes('pa_package_lf_map') && sql.includes('SOD-123FL'))).toBe(true);
    expect(sqlCalls.some((sql) => sql.includes('pa_workcenter_merge_map') && sql.includes('焊接_DB'))).toBe(true);
    expect(sqlCalls.some((sql) => sql.includes('pa_daily_plan_map') && sql.includes('300'))).toBe(true);
    expect(sqlCalls.some((sql) => sql.includes('pa_rollup_raw') && sql.toUpperCase().includes('UPPER(TRIM'))).toBe(true);
    // Stage 2 must show BOTH join kinds distinctly (D2 INNER, D1 LEFT) — never the same kind twice.
    const stage2Sql = sqlCalls.find((sql) => /CREATE OR REPLACE TABLE pa_rollup\s/.test(sql));
    expect(stage2Sql).toBeDefined();
    expect(stage2Sql!.toUpperCase()).toContain('INNER JOIN');
    expect(stage2Sql!.toUpperCase()).toContain('LEFT JOIN');
  });

  it('activate() defaults missing package_lf_map/workcenter_merge_map/daily_plan_map to empty (MYSQL_OPS_ENABLED=false degrade)', async () => {
    const client = await mockedClient();
    const { useProductionAchievementDuckDB } = await importComposable();
    const composable = useProductionAchievementDuckDB();
    await expect(composable.activate('url', [], [])).resolves.toBeUndefined();
    expect(client.registerParquet).toHaveBeenCalled();
  });

  it('activate() sets error + isActive=false and rethrows on DuckDB init failure', async () => {
    const client = await mockedClient();
    client.init.mockRejectedValueOnce(new Error('WASM init failed'));

    const { useProductionAchievementDuckDB } = await importComposable();
    const composable = useProductionAchievementDuckDB();
    await expect(composable.activate('url', [], [], [], [])).rejects.toThrow('WASM init failed');
    expect(composable.isActive.value).toBe(false);
    expect(composable.error.value.length).toBeGreaterThan(0);
  });

  it('computeDailyView() throws when called before activate() (state guard)', async () => {
    const { useProductionAchievementDuckDB } = await importComposable();
    const composable = useProductionAchievementDuckDB();
    await expect(composable.computeDailyView({ workcenterGroup: '焊接_DB', outputDate: '2026-07-14' })).rejects.toThrow();
  });

  it('computeCumulativeView() throws when called before activate() (state guard)', async () => {
    const { useProductionAchievementDuckDB } = await importComposable();
    const composable = useProductionAchievementDuckDB();
    await expect(
      composable.computeCumulativeView({ workcenterGroup: '焊接_DB', startDate: '2026-07-01', endDate: '2026-07-10' }),
    ).rejects.toThrow();
  });

  it('updateTargetsMap() throws when called before activate()', async () => {
    const { useProductionAchievementDuckDB } = await importComposable();
    const composable = useProductionAchievementDuckDB();
    await expect(composable.updateTargetsMap([])).rejects.toThrow();
  });

  it('computeDailyView() sums D+N shifts into a single daily_output_qty per package_lf_group row', async () => {
    const client = await mockedClient();
    client.sendQuery.mockResolvedValue([]); // all CREATE TABLE calls
    client.sendQuery.mockResolvedValueOnce([]); // spec map
    client.sendQuery.mockResolvedValueOnce([]); // targets map
    client.sendQuery.mockResolvedValueOnce([]); // package lf map
    client.sendQuery.mockResolvedValueOnce([]); // workcenter merge map
    client.sendQuery.mockResolvedValueOnce([]); // daily plan map
    client.sendQuery.mockResolvedValueOnce([]); // rollup_raw create
    client.sendQuery.mockResolvedValueOnce([]); // rollup create
    client.sendQuery.mockResolvedValueOnce([
      {
        package_lf_group: 'SOD-123FL',
        d_output_qty: 300,
        n_output_qty: 100,
        daily_output_qty: 400,
        daily_plan_qty: 500,
        achievement_rate: 0.8,
      },
    ]); // computeDailyView SELECT

    const { useProductionAchievementDuckDB } = await importComposable();
    const composable = useProductionAchievementDuckDB();
    await composable.activate('url', [], [], [], [], []);
    const rows = await composable.computeDailyView({ workcenterGroup: '焊接_DB', outputDate: '2026-07-14' });
    expect(rows).toEqual([
      {
        package_lf_group: 'SOD-123FL',
        d_output_qty: 300,
        n_output_qty: 100,
        daily_output_qty: 400,
        daily_plan_qty: 500,
        achievement_rate: 0.8,
      },
    ]);
    const sqlCalls = client.sendQuery.mock.calls.map((c: unknown[]) => String(c[0]));
    const selectSql = sqlCalls[sqlCalls.length - 1];
    expect(selectSql).toContain("'焊接_DB'");
    // Regression: computeDailyView() must scope to exactly ONE output_date --
    // without this filter, the query's own fetch window also captures the
    // PRECEDING day's overnight N-shift tail (PA-03) and silently merges it
    // into this day's N-shift total.
    expect(selectSql).toContain('r.output_date');
    expect(selectSql).toContain("'2026-07-14'");
  });

  it('computeDailyView() null/zero-rate guards mirror PA-12 (missing plan -> null, zero plan -> null, zero actual+plan -> 0.0)', async () => {
    const client = await mockedClient();
    client.sendQuery.mockResolvedValue([]);
    client.sendQuery.mockResolvedValueOnce([]).mockResolvedValueOnce([]).mockResolvedValueOnce([]).mockResolvedValueOnce([]).mockResolvedValueOnce([]);
    client.sendQuery.mockResolvedValueOnce([]).mockResolvedValueOnce([]);
    client.sendQuery.mockResolvedValueOnce([
      { package_lf_group: 'A', d_output_qty: 10, n_output_qty: 0, daily_output_qty: 10, daily_plan_qty: null, achievement_rate: null },
      { package_lf_group: 'B', d_output_qty: 10, n_output_qty: 0, daily_output_qty: 10, daily_plan_qty: 0, achievement_rate: null },
      { package_lf_group: 'C', d_output_qty: 0, n_output_qty: 0, daily_output_qty: 0, daily_plan_qty: 100, achievement_rate: 0 },
    ]);

    const { useProductionAchievementDuckDB } = await importComposable();
    const composable = useProductionAchievementDuckDB();
    await composable.activate('url', [], [], [], [], []);
    const rows = await composable.computeDailyView({ workcenterGroup: '焊接_DB', outputDate: '2026-07-14' });
    expect(rows.find((r) => r.package_lf_group === 'A')!.achievement_rate).toBeNull();
    expect(rows.find((r) => r.package_lf_group === 'B')!.achievement_rate).toBeNull();
    expect(rows.find((r) => r.package_lf_group === 'C')!.achievement_rate).toBe(0);
  });

  it('computeCumulativeView() aggregate-then-divide (D3): per-day trend rate must NOT equal the mean of per-group percentages when plan magnitudes differ', async () => {
    const client = await mockedClient();
    client.sendQuery.mockResolvedValue([]);
    // 5 CREATE TABLE calls (spec/targets/pkg/wc/plan maps) + 2 rollup stage creates
    for (let i = 0; i < 7; i++) client.sendQuery.mockResolvedValueOnce([]);
    // per-group cumulative rows query
    client.sendQuery.mockResolvedValueOnce([
      { package_lf_group: 'BIG', cumulative_actual_qty: 950, daily_plan_qty: 1000 },
      { package_lf_group: 'SMALL', cumulative_actual_qty: 5, daily_plan_qty: 10 },
    ]);
    // per-day trend query: day 1 actual=955 across both groups, plan=1010 (aggregate-then-divide != mean)
    client.sendQuery.mockResolvedValueOnce([{ output_date: '2026-07-01', actual_qty: 955, plan_qty: 1010 }]);

    const { useProductionAchievementDuckDB } = await importComposable();
    const composable = useProductionAchievementDuckDB();
    await composable.activate('url', [], [], [], [], []);
    const result = await composable.computeCumulativeView({ workcenterGroup: '焊接_DB', startDate: '2026-07-01', endDate: '2026-07-01' });

    const aggregateThenDivide = 955 / 1010; // ~0.9455
    const meanOfPercentages = (950 / 1000 + 5 / 10) / 2; // 0.95 exactly — deliberately different
    expect(result.trend[0].achievement_rate).toBeCloseTo(aggregateThenDivide, 6);
    expect(result.trend[0].achievement_rate).not.toBeCloseTo(meanOfPercentages, 3);
  });

  it('computeCumulativeView() trend query formats output_date via strftime -- a raw DuckDB DATE/TIMESTAMP crossing the worker boundary unformatted renders as an epoch-ms integer on the chart x-axis, not a date string', async () => {
    const client = await mockedClient();
    client.sendQuery.mockResolvedValue([]);
    for (let i = 0; i < 7; i++) client.sendQuery.mockResolvedValueOnce([]);
    client.sendQuery.mockResolvedValueOnce([]); // per-group cumulative rows query
    client.sendQuery.mockResolvedValueOnce([]); // per-day trend query

    const { useProductionAchievementDuckDB } = await importComposable();
    const composable = useProductionAchievementDuckDB();
    await composable.activate('url', [], [], [], [], []);
    await composable.computeCumulativeView({ workcenterGroup: '焊接_DB', startDate: '2026-07-01', endDate: '2026-07-01' });

    const sqlCalls = client.sendQuery.mock.calls.map((c: unknown[]) => String(c[0]));
    const trendSql = sqlCalls[sqlCalls.length - 1];
    expect(trendSql).toContain("strftime(CAST(g.output_date AS DATE), '%Y-%m-%d')");
  });

  it('computeCumulativeView() bounds BOTH the per-group rows query and the trend query to [startDate, endDate] -- regression for 當月/自訂區間 including a spillover day (e.g. a 2026-07-01..07-14 month query must never include a 2026-06-30 row from the server fetch window\'s own N-shift-tail buffer, PA-03)', async () => {
    const client = await mockedClient();
    client.sendQuery.mockResolvedValue([]);
    for (let i = 0; i < 7; i++) client.sendQuery.mockResolvedValueOnce([]);
    client.sendQuery.mockResolvedValueOnce([]); // per-group cumulative rows query
    client.sendQuery.mockResolvedValueOnce([]); // per-day trend query

    const { useProductionAchievementDuckDB } = await importComposable();
    const composable = useProductionAchievementDuckDB();
    await composable.activate('url', [], [], [], [], []);
    await composable.computeCumulativeView({ workcenterGroup: '焊接_DB', startDate: '2026-07-01', endDate: '2026-07-14' });

    const sqlCalls = client.sendQuery.mock.calls.map((c: unknown[]) => String(c[0]));
    const rowsSql = sqlCalls[sqlCalls.length - 2];
    const trendSql = sqlCalls[sqlCalls.length - 1];
    for (const sql of [rowsSql, trendSql]) {
      expect(sql).toContain("BETWEEN CAST('2026-07-01' AS DATE) AND CAST('2026-07-14' AS DATE)");
    }
  });

  it('computeCumulativeView() trend rows carry a running cumulative_actual_qty/cumulative_plan_qty/cumulative_achievement_rate for the combo chart (bar = daily actual_qty, line = running cumulative rate) -- accumulated in JS, NOT a SQL window function (engine-independent, avoids any SUM(...) OVER (...) discrepancy)', async () => {
    const client = await mockedClient();
    client.sendQuery.mockResolvedValue([]);
    for (let i = 0; i < 7; i++) client.sendQuery.mockResolvedValueOnce([]);
    client.sendQuery.mockResolvedValueOnce([]); // per-group cumulative rows query
    // Raw SQL only returns PER-DAY actual_qty/plan_qty -- no running totals.
    client.sendQuery.mockResolvedValueOnce([
      { output_date: '2026-07-01', actual_qty: 100, plan_qty: 120 },
      { output_date: '2026-07-02', actual_qty: 150, plan_qty: 120 },
      { output_date: '2026-07-03', actual_qty: 90, plan_qty: null },
    ]);

    const { useProductionAchievementDuckDB } = await importComposable();
    const composable = useProductionAchievementDuckDB();
    await composable.activate('url', [], [], [], [], []);
    const result = await composable.computeCumulativeView({ workcenterGroup: '焊接_DB', startDate: '2026-07-01', endDate: '2026-07-03' });

    expect(result.trend[0].cumulative_actual_qty).toBe(100);
    expect(result.trend[0].cumulative_plan_qty).toBe(120);
    expect(result.trend[0].cumulative_achievement_rate).toBeCloseTo(100 / 120, 6);
    expect(result.trend[1].cumulative_actual_qty).toBe(250);
    expect(result.trend[1].cumulative_achievement_rate).toBeCloseTo(250 / 240, 6);
    // Day 3 has no NEW plan of its own (plan_qty null) but the running total
    // carries forward from day 2 -- never resets to null/0 just because one
    // day contributed nothing new.
    expect(result.trend[2].cumulative_plan_qty).toBe(240);
    expect(result.trend[2].cumulative_achievement_rate).toBeCloseTo(340 / 240, 6);

    const sqlCalls = client.sendQuery.mock.calls.map((c: unknown[]) => String(c[0]));
    const trendSql = sqlCalls[sqlCalls.length - 1];
    expect(trendSql).not.toContain('OVER (');
  });

  it('computeCumulativeView() running cumulative_plan_qty stays null until the FIRST day with a known plan, then never resets to null again', async () => {
    const client = await mockedClient();
    client.sendQuery.mockResolvedValue([]);
    for (let i = 0; i < 7; i++) client.sendQuery.mockResolvedValueOnce([]);
    client.sendQuery.mockResolvedValueOnce([]); // per-group cumulative rows query
    client.sendQuery.mockResolvedValueOnce([
      { output_date: '2026-07-01', actual_qty: 50, plan_qty: null },
      { output_date: '2026-07-02', actual_qty: 60, plan_qty: 100 },
    ]);

    const { useProductionAchievementDuckDB } = await importComposable();
    const composable = useProductionAchievementDuckDB();
    await composable.activate('url', [], [], [], [], []);
    const result = await composable.computeCumulativeView({ workcenterGroup: '焊接_DB', startDate: '2026-07-01', endDate: '2026-07-02' });

    expect(result.trend[0].cumulative_plan_qty).toBeNull();
    expect(result.trend[0].cumulative_achievement_rate).toBeNull();
    expect(result.trend[1].cumulative_actual_qty).toBe(110);
    expect(result.trend[1].cumulative_plan_qty).toBe(100);
    expect(result.trend[1].cumulative_achievement_rate).toBeCloseTo(110 / 100, 6);
  });

  it('computeCumulativeView() scales daily_plan_qty by elapsed_days for 累計計畫', async () => {
    const client = await mockedClient();
    client.sendQuery.mockResolvedValue([]);
    for (let i = 0; i < 7; i++) client.sendQuery.mockResolvedValueOnce([]);
    client.sendQuery.mockResolvedValueOnce([{ package_lf_group: 'SOD-123FL', cumulative_actual_qty: 3000, daily_plan_qty: 500 }]);
    client.sendQuery.mockResolvedValueOnce([]);

    const { useProductionAchievementDuckDB } = await importComposable();
    const composable = useProductionAchievementDuckDB();
    await composable.activate('url', [], [], [], [], []);
    // 2026-07-01 .. 2026-07-05 inclusive = 5 elapsed days
    const result = await composable.computeCumulativeView({ workcenterGroup: '焊接_DB', startDate: '2026-07-01', endDate: '2026-07-05' });
    expect(result.rows[0].cumulative_plan_qty).toBe(2500); // 500 * 5
    expect(result.rows[0].cumulative_diff_qty).toBe(500); // 3000 - 2500
    expect(result.rows[0].cumulative_achievement_rate).toBeCloseTo(3000 / 2500, 6);
  });

  it('computeCumulativeView() null-plan row -> cumulative_plan_qty/diff/rate all null (never Infinity)', async () => {
    const client = await mockedClient();
    client.sendQuery.mockResolvedValue([]);
    for (let i = 0; i < 7; i++) client.sendQuery.mockResolvedValueOnce([]);
    client.sendQuery.mockResolvedValueOnce([{ package_lf_group: '(未分類)', cumulative_actual_qty: 42, daily_plan_qty: null }]);
    client.sendQuery.mockResolvedValueOnce([]);

    const { useProductionAchievementDuckDB } = await importComposable();
    const composable = useProductionAchievementDuckDB();
    await composable.activate('url', [], [], [], [], []);
    const result = await composable.computeCumulativeView({ workcenterGroup: '焊接_DB', startDate: '2026-07-01', endDate: '2026-07-01' });
    expect(result.rows[0].cumulative_plan_qty).toBeNull();
    expect(result.rows[0].cumulative_diff_qty).toBeNull();
    expect(result.rows[0].cumulative_achievement_rate).toBeNull();
  });

  it('deactivate() resets state and releases the DuckDB client', async () => {
    const client = await mockedClient();
    const { useProductionAchievementDuckDB } = await importComposable();
    const composable = useProductionAchievementDuckDB();
    await composable.activate('url', [], [], [], [], []);
    composable.deactivate();
    expect(composable.isActive.value).toBe(false);
    expect(client.destroy).toHaveBeenCalled();
    await expect(composable.computeDailyView({ workcenterGroup: 'x', outputDate: '2026-07-14' })).rejects.toThrow();
  });
});
