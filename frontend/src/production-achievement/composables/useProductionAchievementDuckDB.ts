/**
 * useProductionAchievementDuckDB — DuckDB-WASM composable for
 * production-achievement.
 *
 * Change: production-achievement-overhaul (IP-6)
 * Extends ADR-0016 (production-achievement-async-spool) one level further —
 * see ADR-0016 § Extension for the full current join chain. The server still
 * ships one SPECNAME+PACKAGE_LF-grain spool + 5 inline maps and computes
 * nothing on the request path (data-shape-contract.md §3.28); this composable
 * now runs a 2-stage rollup:
 *
 *   Stage 1 (`pa_rollup_raw`): identical INNER JOIN spool.SPECNAME ->
 *     spec_workcenter_map (PA-06, unchanged case-insensitive join), now also
 *     carrying PACKAGE_LF through the GROUP BY (it did not exist at this
 *     grain before this change).
 *   Stage 2 (`pa_rollup`, redefined in place): pa_rollup_raw
 *     INNER JOIN workcenter_merge_map (PA-10, D2 — explicit-inclusion /
 *       exclude-by-absence: an unmapped raw workcenter_group is DROPPED)
 *     LEFT JOIN package_lf_map (PA-09, D1 — sparse / fallback-to-self:
 *       COALESCE(merged_group, raw_package_lf, '(未分類)'), the OPPOSITE join
 *       kind from workcenter_merge_map — never swap these two).
 *
 * `computeDailyView`/`computeCumulativeView` replace the old flat
 * `computeView()` (PA-12/PA-13): the daily view sums D+N shifts per
 * package_lf_group; the cumulative view additionally builds a per-day trend
 * that aggregates ACROSS ALL package_lf_groups before dividing (D3 —
 * SUM(actual)/SUM(plan), never a mean of per-group percentages).
 */

import { ref, readonly } from 'vue';
import { getDuckDBClient, fetchParquetBuffer } from '../../core/duckdb-client';
import type { DuckDBClient } from '../../core/duckdb-client';
import { checkLocalComputeEligibility } from '../../core/duckdb-activation-policy';

const TABLE_NAME = 'production_achievement_data';
const SPEC_MAP_TABLE = 'pa_spec_workcenter_map';
const TARGETS_TABLE = 'pa_targets_map';
const PACKAGE_LF_MAP_TABLE = 'pa_package_lf_map';
const WORKCENTER_MERGE_MAP_TABLE = 'pa_workcenter_merge_map';
const DAILY_PLAN_MAP_TABLE = 'pa_daily_plan_map';
const ROLLUP_RAW_TABLE = 'pa_rollup_raw';
const ROLLUP_TABLE = 'pa_rollup';

const UNCLASSIFIED_SENTINEL = '(未分類)';

// ── Inline-injected map shapes (data-shape-contract.md §3.28.2/.3/§3.33/§3.34) ──

export interface SpecWorkcenterMapRow {
  SPECNAME: string;
  workcenter_group: string;
}

export interface TargetsMapRow {
  shift_code: string;
  workcenter_group: string;
  target_qty: number | null;
}

/** §3.33 D1 — sparse exceptions-only, fallback-to-self on absence (PA-09). */
export interface PackageLfMapRow {
  raw_package_lf: string;
  merged_group: string;
}

/** §3.33 D2 — explicit-inclusion, exclude-by-absence (PA-10). OPPOSITE default from PackageLfMapRow.
 *  `parent_group` (PA-19) is the 大項 this子站 rolls up under; single-layer
 *  stations have parent_group === merged_workcenter_group. */
export interface WorkcenterMergeMapRow {
  raw_workcenter_group: string;
  merged_workcenter_group: string;
  parent_group: string;
}

export type ProductionSourceMode = 'output' | 'moveout';

/** §3.34 — keyed (workcenter_group, package_lf_group), both already-merged values (PA-11). */
export interface DailyPlanMapRow {
  workcenter_group: string;
  package_lf_group: string;
  daily_plan_qty: number | null;
}

// ── Computed view row shapes (PA-12 daily / PA-13 cumulative) ───────────────

export interface DailyViewRow {
  package_lf_group: string;
  /** The 子站 (merged workcenter_group), present only in expanded (大項) mode
   *  (PA-19); undefined for a single-layer station selection. On a 大項小計
   *  subtotal row it carries the 大項 (parent_group) name for the label. */
  workcenter_group?: string;
  /** PA-19: true on the per-package 大項小計 row (電鍍/切割 expanded mode). The
   *  子站 leaf rows show 轉出/產出 actuals only (null plan/achievement); the
   *  subtotal row carries the 大項-total D/N/合計 plus the parent-keyed 計畫 and
   *  the 大項-level 達成率. Undefined/false on every leaf and single-layer row. */
  is_subtotal?: boolean;
  d_output_qty: number;
  n_output_qty: number;
  daily_output_qty: number;
  daily_plan_qty: number | null;
  achievement_rate: number | null;
}

export interface CumulativeViewRow {
  package_lf_group: string;
  /** The 子站 (merged workcenter_group), present only in expanded (大項) mode
   *  (PA-19). On a 大項小計 subtotal row it carries the 大項 name. */
  workcenter_group?: string;
  /** PA-19: true on the per-package 大項小計 row — see DailyViewRow.is_subtotal. */
  is_subtotal?: boolean;
  cumulative_actual_qty: number;
  cumulative_plan_qty: number | null;
  cumulative_diff_qty: number | null;
  cumulative_achievement_rate: number | null;
}

export interface CumulativeTrendPoint {
  output_date: string;
  actual_qty: number;
  plan_qty: number | null;
  achievement_rate: number | null;
  /** Running SUM(actual_qty) from the first day of the range through this day (inclusive). */
  cumulative_actual_qty: number;
  /** Running SUM(plan_qty) from the first day of the range through this day; null only when no day-to-date has a known plan. */
  cumulative_plan_qty: number | null;
  /** cumulative_actual_qty / cumulative_plan_qty; null when cumulative_plan_qty is null or 0. */
  cumulative_achievement_rate: number | null;
}

export interface CumulativeViewResult {
  rows: CumulativeViewRow[];
  trend: CumulativeTrendPoint[];
}

export interface ComputeDailyViewOptions {
  /** The selected station. In single-layer mode it is the子站 workcenter_group
   *  (filter on workcenter_group); in expanded mode (PA-19) it is the 大項
   *  parent_group (filter on parent_group, rows split per子站). */
  workcenterGroup: string;
  /** PA-19: when true, `workcenterGroup` is treated as a 大項 (parent_group)
   *  and each returned row additionally carries its子站 `workcenter_group`,
   *  grouped by (package_lf_group,子站). Used for 電鍍/切割. */
  expand?: boolean;
  /**
   * The single target calendar day ('YYYY-MM-DD'), required so the rollup
   * filters to EXACTLY this output_date (PA-03/PA-06 grouping key). Without
   * this filter, a "today"/"yesterday" query's own Oracle fetch window
   * (`[start_date 00:00, ...)`) also captures the tail of the PRECEDING
   * day's overnight N shift (00:00:00-07:29:59, which PA-03 attributes back
   * to `start_date - 1`) — that data would silently merge into the
   * requested day's N-shift total instead of staying under its own day.
   */
  outputDate: string;
}

export interface ComputeCumulativeViewOptions {
  workcenterGroup: string;
  /** PA-19: expanded (大項) mode — see ComputeDailyViewOptions.expand. */
  expand?: boolean;
  /** Already-resolved/capped date bounds (useProductionAchievement.ts owns resolveMonthPeriod()/range-end capping). */
  startDate: string;
  endDate: string;
}

// ── SQL literal helpers ──────────────────────────────────────────────────────
//
// The DuckDB-WASM worker protocol (workers/duckdb-worker.js) only exposes a
// raw `query(sql)` call — no parameter binding — so small server-provided
// arrays are embedded as escaped SQL literals. Values originate from the
// server's own JSON response (already validated there), not free-form user
// input, but are still quote-escaped defensively.

function sqlString(value: unknown): string {
  return `'${String(value ?? '').replace(/'/g, "''")}'`;
}

function sqlNumberOrNull(value: unknown): string {
  if (value === null || value === undefined || value === '') return 'NULL';
  const n = Number(value);
  return Number.isFinite(n) ? String(n) : 'NULL';
}

interface ValuesColumn {
  name: string;
  type: string;
  kind: 'string' | 'number';
}

/**
 * Build a `CREATE OR REPLACE TABLE <name> AS ...` statement from an array of
 * plain-object rows. A bare `VALUES (...)` list requires >= 1 row, so the
 * empty-array case emits a typed zero-row SELECT instead (an empty inline map
 * is a valid degraded state — data-shape-contract.md §3.28.3/§3.30/§3.31/§3.32
 * MYSQL_OPS_ENABLED=false notes).
 */
function buildValuesTableSql(
  tableName: string,
  columns: ValuesColumn[],
  rows: Record<string, unknown>[],
): string {
  const colNames = columns.map((c) => c.name).join(', ');
  if (!rows.length) {
    const nullSelect = columns.map((c) => `CAST(NULL AS ${c.type}) AS ${c.name}`).join(', ');
    return `CREATE OR REPLACE TABLE ${tableName} AS SELECT ${nullSelect} WHERE FALSE`;
  }
  const valuesRows = rows
    .map((row) => {
      const vals = columns
        .map((c) => (c.kind === 'number' ? sqlNumberOrNull(row[c.name]) : sqlString(row[c.name])))
        .join(', ');
      return `(${vals})`;
    })
    .join(',\n    ');
  return `CREATE OR REPLACE TABLE ${tableName} AS SELECT * FROM (VALUES\n    ${valuesRows}\n  ) AS t(${colNames})`;
}

function buildSpecWorkcenterMapSql(rows: SpecWorkcenterMapRow[]): string {
  return buildValuesTableSql(
    SPEC_MAP_TABLE,
    [
      { name: 'SPECNAME', type: 'VARCHAR', kind: 'string' },
      { name: 'workcenter_group', type: 'VARCHAR', kind: 'string' },
    ],
    rows as unknown as Record<string, unknown>[],
  );
}

function buildTargetsMapSql(rows: TargetsMapRow[]): string {
  return buildValuesTableSql(
    TARGETS_TABLE,
    [
      { name: 'shift_code', type: 'VARCHAR', kind: 'string' },
      { name: 'workcenter_group', type: 'VARCHAR', kind: 'string' },
      { name: 'target_qty', type: 'INTEGER', kind: 'number' },
    ],
    rows as unknown as Record<string, unknown>[],
  );
}

/** D1 map (PA-09) — LEFT JOIN target, fallback-to-self on absence. */
function buildPackageLfMapSql(rows: PackageLfMapRow[]): string {
  return buildValuesTableSql(
    PACKAGE_LF_MAP_TABLE,
    [
      { name: 'raw_package_lf', type: 'VARCHAR', kind: 'string' },
      { name: 'merged_group', type: 'VARCHAR', kind: 'string' },
    ],
    rows as unknown as Record<string, unknown>[],
  );
}

/** D2 map (PA-10) — INNER JOIN target, exclude-by-absence. OPPOSITE default from PackageLfMapRow above.
 *  Carries parent_group (PA-19) for the子站->大項 rollup. */
function buildWorkcenterMergeMapSql(rows: WorkcenterMergeMapRow[]): string {
  // Backfill parent_group === merged when a row omits it (defensive: a legacy
  // server payload without parent_group must still place the子站 under itself).
  const normalized = rows.map((r) => ({
    raw_workcenter_group: r.raw_workcenter_group,
    merged_workcenter_group: r.merged_workcenter_group,
    parent_group: r.parent_group || r.merged_workcenter_group,
  }));
  return buildValuesTableSql(
    WORKCENTER_MERGE_MAP_TABLE,
    [
      { name: 'raw_workcenter_group', type: 'VARCHAR', kind: 'string' },
      { name: 'merged_workcenter_group', type: 'VARCHAR', kind: 'string' },
      { name: 'parent_group', type: 'VARCHAR', kind: 'string' },
    ],
    normalized as unknown as Record<string, unknown>[],
  );
}

function buildDailyPlanMapSql(rows: DailyPlanMapRow[]): string {
  return buildValuesTableSql(
    DAILY_PLAN_MAP_TABLE,
    [
      { name: 'workcenter_group', type: 'VARCHAR', kind: 'string' },
      { name: 'package_lf_group', type: 'VARCHAR', kind: 'string' },
      { name: 'daily_plan_qty', type: 'INTEGER', kind: 'number' },
    ],
    rows as unknown as Record<string, unknown>[],
  );
}

function eligibilityErrorMessage(reason: string): string {
  if (reason === 'browser_unsupported') {
    return '此瀏覽器不支援本頁面所需的資料運算功能（DuckDB-WASM），請改用 Chrome、Edge 等現代瀏覽器後再試';
  }
  return '無法啟用本機資料運算，請稍後再試';
}

function sf(val: unknown, def = 0): number {
  const n = Number(val);
  return Number.isFinite(n) ? n : def;
}

function nullableNumber(val: unknown): number | null {
  if (val === null || val === undefined) return null;
  const n = Number(val);
  return Number.isFinite(n) ? n : null;
}

/** Inclusive day count between two 'YYYY-MM-DD' strings (PA-13 elapsed_days). */
function daysBetweenInclusive(startDate: string, endDate: string): number {
  const start = new Date(`${startDate}T00:00:00Z`);
  const end = new Date(`${endDate}T00:00:00Z`);
  const diffMs = end.getTime() - start.getTime();
  const days = Math.round(diffMs / 86400000) + 1;
  return Number.isFinite(days) && days > 0 ? days : 1;
}

// ── Main composable ───────────────────────────────────────────────────────────

export function useProductionAchievementDuckDB() {
  const isActive = ref(false);
  const isLoading = ref(false);
  const error = ref('');

  let _client: DuckDBClient | null = null;
  let _isRegistered = false;
  let _sourceMode: ProductionSourceMode = 'output';

  /**
   * Stage 1 (`pa_rollup_raw`) — produce the (output_date, shift_code,
   * raw_workcenter_group, raw_package_lf) grain that workcenter_merge_map keys
   * on. Two source shapes (PA-18):
   *   'output': the spool is SPECNAME-grain, so INNER JOIN spec_workcenter_map
   *     (PA-06, case-insensitive) to resolve SPECNAME -> raw workcenter_group.
   *   'moveout': the spool ALREADY carries raw_workcenter_group (=FROMWORKCENTER),
   *     so no join — just carry it and PACKAGE_LF through the GROUP BY.
   */
  async function _buildRollupRaw(): Promise<void> {
    const sql = _sourceMode === 'moveout'
      ? `
      CREATE OR REPLACE TABLE ${ROLLUP_RAW_TABLE} AS
      SELECT
        s.output_date AS output_date,
        s.shift_code AS shift_code,
        s.raw_workcenter_group AS raw_workcenter_group,
        s.PACKAGE_LF AS raw_package_lf,
        SUM(s.actual_output_qty) AS actual_output_qty
      FROM ${TABLE_NAME} s
      GROUP BY s.output_date, s.shift_code, s.raw_workcenter_group, s.PACKAGE_LF
    `
      : `
      CREATE OR REPLACE TABLE ${ROLLUP_RAW_TABLE} AS
      SELECT
        s.output_date AS output_date,
        s.shift_code AS shift_code,
        m.workcenter_group AS raw_workcenter_group,
        s.PACKAGE_LF AS raw_package_lf,
        SUM(s.actual_output_qty) AS actual_output_qty
      FROM ${TABLE_NAME} s
      INNER JOIN ${SPEC_MAP_TABLE} m
        ON UPPER(TRIM(CAST(s.SPECNAME AS VARCHAR))) = UPPER(TRIM(CAST(m.SPECNAME AS VARCHAR)))
      GROUP BY s.output_date, s.shift_code, m.workcenter_group, s.PACKAGE_LF
    `;
    await _client!.sendQuery(sql);
  }

  /**
   * Stage 2 (`pa_rollup`, redefined in place) — INNER JOIN workcenter_merge_map
   * (PA-10, D2: a raw workcenter_group with no row is EXCLUDED — never LEFT
   * JOIN) + LEFT JOIN package_lf_map (PA-09, D1: a raw PACKAGE_LF with no row
   * falls back to itself, NULL/blank -> '(未分類)' — never INNER JOIN). These
   * are deliberately opposite join kinds; do not "normalize" them to match.
   * Carries `parent_group` (PA-19, the 大項) alongside `workcenter_group`
   * (the子站) so the detail table can filter by either level.
   */
  async function _buildRollup(): Promise<void> {
    const pkgExpr = `COALESCE(pm.merged_group, NULLIF(CAST(r.raw_package_lf AS VARCHAR), ''), ${sqlString(UNCLASSIFIED_SENTINEL)})`;
    const sql = `
      CREATE OR REPLACE TABLE ${ROLLUP_TABLE} AS
      SELECT
        r.output_date AS output_date,
        r.shift_code AS shift_code,
        wm.merged_workcenter_group AS workcenter_group,
        wm.parent_group AS parent_group,
        ${pkgExpr} AS package_lf_group,
        SUM(r.actual_output_qty) AS actual_output_qty
      FROM ${ROLLUP_RAW_TABLE} r
      INNER JOIN ${WORKCENTER_MERGE_MAP_TABLE} wm
        ON r.raw_workcenter_group = wm.raw_workcenter_group
      LEFT JOIN ${PACKAGE_LF_MAP_TABLE} pm
        ON r.raw_package_lf = pm.raw_package_lf
      GROUP BY r.output_date, r.shift_code, wm.merged_workcenter_group, wm.parent_group,
        ${pkgExpr}
    `;
    await _client!.sendQuery(sql);
  }

  /**
   * Activate local compute mode.
   * @param spoolUrl           - SPECNAME+PACKAGE_LF-grain Parquet spool download URL (§3.28.1)
   * @param specWorkcenterMap  - inline SPECNAME -> workcenter_group map (§3.28.2)
   * @param targetsMap         - inline (shift_code, workcenter_group) -> target_qty map (§3.28.3)
   * @param packageLfMap       - inline PACKAGE_LF merge map, D1 (§3.33)
   * @param workcenterMergeMap - inline workcenter merge map, D2 (§3.33)
   * @param dailyPlanMap       - inline (workcenter_group, package_lf_group) -> daily_plan_qty map (§3.34)
   * @throws when WASM is unsupported (explicit unsupported state, no server
   *         fallback), the parquet fetch fails, or DuckDB init/SQL fails.
   */
  async function activate(
    spoolUrl: string,
    specWorkcenterMap: SpecWorkcenterMapRow[],
    targetsMap: TargetsMapRow[],
    packageLfMap: PackageLfMapRow[] = [],
    workcenterMergeMap: WorkcenterMergeMapRow[] = [],
    dailyPlanMap: DailyPlanMapRow[] = [],
    sourceMode: ProductionSourceMode = 'output',
  ): Promise<void> {
    _sourceMode = sourceMode;
    isLoading.value = true;
    error.value = '';

    // Q1 (design.md, RESOLVED): threshold overridden to 0 — always activate
    // on a spool hit. isDuckDBSupported()/no-url guards still apply.
    const eligibility = checkLocalComputeEligibility({
      spoolDownloadUrl: spoolUrl,
      totalRowCount: 0,
      threshold: 0,
    });
    if (!eligibility.eligible) {
      const message = eligibilityErrorMessage(eligibility.reason);
      error.value = message;
      isActive.value = false;
      isLoading.value = false;
      throw new Error(message);
    }

    try {
      _client = getDuckDBClient();
      await _client.init();
      const buffer = await fetchParquetBuffer(spoolUrl);
      await _client.registerParquet(TABLE_NAME, buffer);
      await _client.sendQuery(buildSpecWorkcenterMapSql(specWorkcenterMap || []));
      await _client.sendQuery(buildTargetsMapSql(targetsMap || []));
      await _client.sendQuery(buildPackageLfMapSql(packageLfMap || []));
      await _client.sendQuery(buildWorkcenterMergeMapSql(workcenterMergeMap || []));
      await _client.sendQuery(buildDailyPlanMapSql(dailyPlanMap || []));
      await _buildRollupRaw();
      await _buildRollup();
      _isRegistered = true;
      isActive.value = true;
    } catch (err) {
      error.value = String((err as Error)?.message ?? err);
      isActive.value = false;
      console.warn('[production-achievement] DuckDB activation failed:', err);
      throw err;
    } finally {
      isLoading.value = false;
    }
  }

  /**
   * Re-register targets_map only (e.g. after a target-value PUT) without
   * re-downloading the spool parquet or rebuilding the rollup stages — only
   * PA-07's join input changed. Call computeDailyView/computeCumulativeView
   * afterwards to re-render.
   */
  async function updateTargetsMap(targetsMap: TargetsMapRow[]): Promise<void> {
    if (!_isRegistered || !_client) throw new Error('DuckDB not initialised');
    await _client.sendQuery(buildTargetsMapSql(targetsMap || []));
  }

  /**
   * PA-12: DailyView — one row per package_lf_group for the selected
   * (already-merged) workcenter_group, summing D+N shifts into a single daily
   * total, LEFT JOIN daily_plan_map on (workcenter_group, package_lf_group).
   * achievement_rate is null when the plan row is missing or 0 (never
   * Infinity); 0.0 when daily output is 0 and a non-null non-zero plan exists.
   */
  async function computeDailyView(options: ComputeDailyViewOptions): Promise<DailyViewRow[]> {
    if (!_isRegistered || !_client) throw new Error('DuckDB not initialised');
    const sel = sqlString(options.workcenterGroup);
    const outputDate = sqlString(options.outputDate);
    const expand = options.expand === true;

    if (!expand) {
      // Single-layer station: one row per package. daily_plan joins on the
      // selected workcenter_group (which IS the parent for a single-layer
      // station), PA-11.
      const sql = `
        SELECT
          package_lf_group,
          d_output_qty,
          n_output_qty,
          daily_output_qty,
          daily_plan_qty,
          CASE
            WHEN daily_plan_qty IS NULL THEN NULL
            WHEN daily_plan_qty = 0 THEN NULL
            ELSE CAST(daily_output_qty AS DOUBLE) / daily_plan_qty
          END AS achievement_rate
        FROM (
          SELECT
            r.package_lf_group AS package_lf_group,
            SUM(CASE WHEN r.shift_code = 'D' THEN r.actual_output_qty ELSE 0 END) AS d_output_qty,
            SUM(CASE WHEN r.shift_code = 'N' THEN r.actual_output_qty ELSE 0 END) AS n_output_qty,
            SUM(r.actual_output_qty) AS daily_output_qty,
            MAX(dp.daily_plan_qty) AS daily_plan_qty
          FROM ${ROLLUP_TABLE} r
          LEFT JOIN ${DAILY_PLAN_MAP_TABLE} dp
            ON r.workcenter_group = dp.workcenter_group AND r.package_lf_group = dp.package_lf_group
          WHERE r.workcenter_group = ${sel}
            AND CAST(r.output_date AS DATE) = CAST(${outputDate} AS DATE)
          GROUP BY r.package_lf_group
        ) sub
        ORDER BY package_lf_group
      `;
      const rows = await _client.sendQuery(sql);
      return (rows as Record<string, unknown>[]).map((row) => ({
        package_lf_group: String(row.package_lf_group ?? ''),
        d_output_qty: sf(row.d_output_qty),
        n_output_qty: sf(row.n_output_qty),
        daily_output_qty: sf(row.daily_output_qty),
        daily_plan_qty: nullableNumber(row.daily_plan_qty),
        achievement_rate: nullableNumber(row.achievement_rate),
      }));
    }

    // PA-19 expanded (大項) mode (電鍍/切割): filter on parent_group and emit,
    // per package, one leaf row per子站 (actuals only) PLUS a per-package
    // 大項小計 row. GROUPING SETS produces both grains in one pass; GROUPING()=1
    // marks the subtotal grain (子站 aggregated away). The 每日計畫 is keyed on
    // the 大項/parent (= the selection), NOT the子站 — so it attaches ONLY to the
    // subtotal row (leaf rows show a null plan/達成率, the parent-total achievement
    // lives on the小計 row, matching the Excel report). The plan join can touch
    // leaf grains too, but the is_subtotal CASE nulls it there; quantities are
    // pre-aggregated in `agg` before the join, so no fan-out. ORDER BY puts each
    // package's leaf子站 rows first (is_subtotal 0) then its小計 (is_subtotal 1).
    const sql = `
      SELECT
        agg.package_lf_group AS package_lf_group,
        agg.workcenter_group AS workcenter_group,
        agg.is_subtotal AS is_subtotal,
        agg.d_output_qty AS d_output_qty,
        agg.n_output_qty AS n_output_qty,
        agg.daily_output_qty AS daily_output_qty,
        CASE WHEN agg.is_subtotal = 1 THEN dp.daily_plan_qty ELSE NULL END AS daily_plan_qty,
        CASE
          WHEN agg.is_subtotal = 1 AND dp.daily_plan_qty IS NOT NULL AND dp.daily_plan_qty <> 0
          THEN CAST(agg.daily_output_qty AS DOUBLE) / dp.daily_plan_qty
          ELSE NULL
        END AS achievement_rate
      FROM (
        SELECT
          r.package_lf_group AS package_lf_group,
          r.workcenter_group AS workcenter_group,
          GROUPING(r.workcenter_group) AS is_subtotal,
          SUM(CASE WHEN r.shift_code = 'D' THEN r.actual_output_qty ELSE 0 END) AS d_output_qty,
          SUM(CASE WHEN r.shift_code = 'N' THEN r.actual_output_qty ELSE 0 END) AS n_output_qty,
          SUM(r.actual_output_qty) AS daily_output_qty
        FROM ${ROLLUP_TABLE} r
        WHERE r.parent_group = ${sel}
          AND CAST(r.output_date AS DATE) = CAST(${outputDate} AS DATE)
        GROUP BY GROUPING SETS ((r.package_lf_group, r.workcenter_group), (r.package_lf_group))
      ) agg
      LEFT JOIN ${DAILY_PLAN_MAP_TABLE} dp
        ON dp.workcenter_group = ${sel} AND dp.package_lf_group = agg.package_lf_group
      ORDER BY agg.package_lf_group, agg.is_subtotal, agg.workcenter_group
    `;
    const rows = await _client.sendQuery(sql);
    return (rows as Record<string, unknown>[]).map((row) => {
      const isSubtotal = Number(row.is_subtotal) === 1;
      return {
        package_lf_group: String(row.package_lf_group ?? ''),
        // subtotal rows carry the 大項 (selection) name for the小計 label
        workcenter_group: isSubtotal ? options.workcenterGroup : String(row.workcenter_group ?? ''),
        is_subtotal: isSubtotal,
        d_output_qty: sf(row.d_output_qty),
        n_output_qty: sf(row.n_output_qty),
        daily_output_qty: sf(row.daily_output_qty),
        daily_plan_qty: nullableNumber(row.daily_plan_qty),
        achievement_rate: nullableNumber(row.achievement_rate),
      };
    });
  }

  /**
   * PA-13: CumulativeView — per-package_lf_group cumulative rows (計畫 scaled
   * by elapsed_days, computed in JS from the already-resolved/capped
   * start/end dates) PLUS a daily trend that aggregates ACROSS ALL
   * package_lf_groups before dividing (D3 — SUM(actual)/SUM(plan) per day,
   * never a mean of each group's own percentage).
   */
  async function computeCumulativeView(options: ComputeCumulativeViewOptions): Promise<CumulativeViewResult> {
    if (!_isRegistered || !_client) throw new Error('DuckDB not initialised');
    const sel = sqlString(options.workcenterGroup);
    const startDate = sqlString(options.startDate);
    const endDate = sqlString(options.endDate);
    const elapsedDays = daysBetweenInclusive(options.startDate, options.endDate);
    const expand = options.expand === true;
    // PA-19: expanded (大項) mode filters on parent_group and splits per子站
    // (see computeDailyView). Single-layer mode filters on workcenter_group.
    const filterCol = expand ? 'parent_group' : 'workcenter_group';

    // Date-bound to [startDate, endDate] — without this filter, the server's
    // own Oracle fetch window (widened to capture the requested range's
    // overnight N-shift tails, PA-03) leaves spillover rows in ROLLUP_TABLE
    // dated just outside the requested range (e.g. a 當月 query for
    // 2026-07-01..07-14 also carries a 2026-06-30 spillover row) that must
    // never count toward this period's cumulative totals or trend.
    let rows: CumulativeViewRow[];
    if (!expand) {
      const rowsSql = `
        SELECT
          r.package_lf_group AS package_lf_group,
          SUM(r.actual_output_qty) AS cumulative_actual_qty,
          MAX(dp.daily_plan_qty) AS daily_plan_qty
        FROM ${ROLLUP_TABLE} r
        LEFT JOIN ${DAILY_PLAN_MAP_TABLE} dp
          ON r.workcenter_group = dp.workcenter_group AND r.package_lf_group = dp.package_lf_group
        WHERE r.workcenter_group = ${sel}
          AND CAST(r.output_date AS DATE) BETWEEN CAST(${startDate} AS DATE) AND CAST(${endDate} AS DATE)
        GROUP BY r.package_lf_group
        ORDER BY r.package_lf_group
      `;
      const rawRows = await _client.sendQuery(rowsSql);
      rows = (rawRows as Record<string, unknown>[]).map((row) => {
        const dailyPlan = nullableNumber(row.daily_plan_qty);
        const actual = sf(row.cumulative_actual_qty);
        const cumulativePlan = dailyPlan === null ? null : dailyPlan * elapsedDays;
        const diff = cumulativePlan === null ? null : actual - cumulativePlan;
        const rate = cumulativePlan === null || cumulativePlan === 0 ? null : actual / cumulativePlan;
        return {
          package_lf_group: String(row.package_lf_group ?? ''),
          cumulative_actual_qty: actual,
          cumulative_plan_qty: cumulativePlan,
          cumulative_diff_qty: diff,
          cumulative_achievement_rate: rate,
        };
      });
    } else {
      // PA-19 expanded (大項) mode: 子站 leaf rows (actuals only) + per-package
      // 大項小計 (parent-keyed 累計計畫/達成率). Mirrors computeDailyView's
      // GROUPING SETS structure — the 累計計畫 attaches ONLY to the subtotal grain
      // (plan is keyed on the 大項/parent = the selection), leaf子站 rows show a
      // null plan/差異/達成率.
      const rowsSql = `
        SELECT
          agg.package_lf_group AS package_lf_group,
          agg.workcenter_group AS workcenter_group,
          agg.is_subtotal AS is_subtotal,
          agg.cumulative_actual_qty AS cumulative_actual_qty,
          CASE WHEN agg.is_subtotal = 1 THEN dp.daily_plan_qty ELSE NULL END AS daily_plan_qty
        FROM (
          SELECT
            r.package_lf_group AS package_lf_group,
            r.workcenter_group AS workcenter_group,
            GROUPING(r.workcenter_group) AS is_subtotal,
            SUM(r.actual_output_qty) AS cumulative_actual_qty
          FROM ${ROLLUP_TABLE} r
          WHERE r.parent_group = ${sel}
            AND CAST(r.output_date AS DATE) BETWEEN CAST(${startDate} AS DATE) AND CAST(${endDate} AS DATE)
          GROUP BY GROUPING SETS ((r.package_lf_group, r.workcenter_group), (r.package_lf_group))
        ) agg
        LEFT JOIN ${DAILY_PLAN_MAP_TABLE} dp
          ON dp.workcenter_group = ${sel} AND dp.package_lf_group = agg.package_lf_group
        ORDER BY agg.package_lf_group, agg.is_subtotal, agg.workcenter_group
      `;
      const rawRows = await _client.sendQuery(rowsSql);
      rows = (rawRows as Record<string, unknown>[]).map((row) => {
        const isSubtotal = Number(row.is_subtotal) === 1;
        const dailyPlan = nullableNumber(row.daily_plan_qty);
        const actual = sf(row.cumulative_actual_qty);
        const cumulativePlan = dailyPlan === null ? null : dailyPlan * elapsedDays;
        const diff = cumulativePlan === null ? null : actual - cumulativePlan;
        const rate = cumulativePlan === null || cumulativePlan === 0 ? null : actual / cumulativePlan;
        return {
          package_lf_group: String(row.package_lf_group ?? ''),
          workcenter_group: isSubtotal ? options.workcenterGroup : String(row.workcenter_group ?? ''),
          is_subtotal: isSubtotal,
          cumulative_actual_qty: actual,
          cumulative_plan_qty: cumulativePlan,
          cumulative_diff_qty: diff,
          cumulative_achievement_rate: rate,
        };
      });
    }

    // D3 aggregate-then-divide trend: sum actual and (known) plan across ALL
    // package_lf_groups for each day BEFORE dividing. A package_lf_group with
    // no daily_plan_map row contributes 0 to that day's plan sum (SQL SUM
    // ignores NULL) rather than making the whole day's rate unknown — this
    // mirrors summing only the KNOWN plans, consistent with how the detail
    // rows above already show a "—" only for THAT group's own missing plan.
    // Only per-day actual_qty/plan_qty come from SQL; the RUNNING cumulative
    // total is a plain JS scan below (not a SQL window function) — rows are
    // already ORDER BY output_date, so a linear accumulation is simplest and
    // sidesteps any engine-specific behavior around SUM(...) OVER (...).
    // Trend aggregates ACROSS ALL package_lf_groups (and, in expanded 大項 mode,
    // all子站) under the selection for each day, then divides (D3). The trend is
    // a 大項-level line regardless of mode, so it rolls the子站 up to (day,
    // package) and joins the 每日計畫 on the SELECTION (= the parent 大項 in
    // expanded mode, = the station in single-layer mode) — the plan is keyed on
    // that value in BOTH modes (PA-19), so no子站 split is needed here.
    const trendSql = `
      SELECT
        strftime(CAST(g.output_date AS DATE), '%Y-%m-%d') AS output_date,
        SUM(g.actual_output_qty) AS actual_qty,
        SUM(dp.daily_plan_qty) AS plan_qty
      FROM (
        SELECT output_date, package_lf_group, SUM(actual_output_qty) AS actual_output_qty
        FROM ${ROLLUP_TABLE}
        WHERE ${filterCol} = ${sel}
          AND CAST(output_date AS DATE) BETWEEN CAST(${startDate} AS DATE) AND CAST(${endDate} AS DATE)
        GROUP BY output_date, package_lf_group
      ) g
      LEFT JOIN ${DAILY_PLAN_MAP_TABLE} dp
        ON dp.workcenter_group = ${sel} AND dp.package_lf_group = g.package_lf_group
      GROUP BY g.output_date
      ORDER BY g.output_date
    `;
    const rawTrend = await _client.sendQuery(trendSql);
    let runningActual = 0;
    let runningPlan: number | null = null;
    const trend: CumulativeTrendPoint[] = (rawTrend as Record<string, unknown>[]).map((row) => {
      const actual = sf(row.actual_qty);
      const plan = nullableNumber(row.plan_qty);
      const rate = plan === null || plan === 0 ? null : actual / plan;
      runningActual += actual;
      if (plan !== null) runningPlan = (runningPlan ?? 0) + plan;
      const cumulativeRate = runningPlan === null || runningPlan === 0 ? null : runningActual / runningPlan;
      return {
        output_date: String(row.output_date ?? ''),
        actual_qty: actual,
        plan_qty: plan,
        achievement_rate: rate,
        cumulative_actual_qty: runningActual,
        cumulative_plan_qty: runningPlan,
        cumulative_achievement_rate: cumulativeRate,
      };
    });

    return { rows, trend };
  }

  /** Tear down local mode and release DuckDB resources. */
  function deactivate(): void {
    if (_client) {
      _client.destroy();
      _client = null;
    }
    isActive.value = false;
    isLoading.value = false;
    error.value = '';
    _isRegistered = false;
  }

  return {
    isActive: readonly(isActive),
    isLoading: readonly(isLoading),
    error: readonly(error),
    activate,
    computeDailyView,
    computeCumulativeView,
    updateTargetsMap,
    deactivate,
  };
}
