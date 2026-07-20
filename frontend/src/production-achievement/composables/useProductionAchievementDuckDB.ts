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
 *
 * Change: production-achievement-oracle-plan-source (PA-11/PA-20/PA-21)
 * Replaces the old static (workcenter_group, package_lf_group) ->
 * daily_plan_qty map (`pa_daily_plan_map`, Excel-imported) with the
 * date-indexed Oracle-sourced `pa_plan_map` (output_date, plan_package_group,
 * planqty_input, planqty_output) — see PlanMapRow. The plan is keyed on
 * PACKAGE ONLY (no station dimension, confirmed against IT's own
 * PROD_ACH.txt/025.txt reference SQL — the same Oracle target broadcasts to
 * every station for that package/day); which COLUMN (input vs output) a
 * given station reads is resolved ONCE per compute call from
 * workcenter_merge_map's `plan_source_side` (PA-20) for the SELECTED
 * station/大項, then embedded as a literal column name in the query text
 * (never per-row — plan_source_side does not vary within one query). Every
 * per-shift target (D/N achievement_rate) is derived client-side as
 * `CEIL(daily_plan_qty / 2)` (PA-21) — there is no separate per-shift Oracle
 * column. Cumulative plan is now a REAL SUM(planqty) over the requested date
 * range (pa_plan_map has one row per package per day), replacing the old
 * `daily_plan_qty * elapsed_days` approximation.
 *
 * Unit fix: production-achievement-oracle-plan-source (K-unit correction)
 * Oracle's plan/target values (pa_plan_map.planqty_input/planqty_output,
 * sourced from MES_WIP_OUTPUTPLAN) are natively in K (thousands of pcs) --
 * confirmed both by IT's own legacy report (025.txt, which divides every
 * actual-output column by 1000 before comparing to the un-divided PLANQTY
 * figures) and by live data (a per-shift target compared 1:1 against raw
 * actual pcs produced nonsensical >90000% rates; dividing actual by 1000
 * produces a sane ~96%). The actual-output side (pa_rollup.actual_output_qty,
 * sourced from DW_MES_LOTWIPHISTORY.TRACKOUTQTY / DW_MES_HM_LOTMOVEOUT.QTY)
 * is raw pcs and always was. Every SUM(r.actual_output_qty) in
 * computeDailyView/computeCumulativeView/the trend query below is therefore
 * divided by 1000.0 at the exact point it becomes a named "*_output_qty"/
 * "*_actual_qty" field -- NOT inside pa_rollup_raw/pa_rollup themselves,
 * which stay raw pcs (Stage 1/Stage 2 only do SPECNAME/PACKAGE_LF grouping
 * correctness, unrelated to this unit concern, and
 * test_frontend_production_achievement_parity.py's dual-tier parity gate
 * compares pa_rollup against a raw-pcs Python golden reference -- converting
 * inside Stage 2 would break that parity test for a reason that has nothing
 * to do with what it protects). No rounding is applied to the /1000.0
 * division, matching 025.txt's own convention (fractional K values, e.g.
 * 12.345, are expected and correct).
 *
 * Change: production-achievement-column-pivot (X-direction 子站 grouping)
 * Expanded (大項) mode (電鍍/切割) no longer emits a row PER 子站 plus a separate
 * 大項小計 subtotal row (Y-direction/row-based grouping). It now emits exactly
 * ONE row per package_lf_group — at the same grain single-layer mode already
 * uses — carrying an additive `substations` column-pivot breakdown (see
 * DailyViewRow.substations/CumulativeViewRow.substations). See
 * computeDailyView/computeCumulativeView's expand branches for the
 * per_child-CTE + MAX(CASE...) pivot approach that replaced the old
 * GROUPING SETS query.
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
const PLAN_MAP_TABLE = 'pa_plan_map';
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
 *  stations have parent_group === merged_workcenter_group.
 *  `plan_source_side` (PA-20) is which Oracle plan column (input/output) the
 *  大項 this row belongs to sources its target from — resolved per 大項, not
 *  per raw row (see `_resolvePlanColumn`). */
export interface WorkcenterMergeMapRow {
  raw_workcenter_group: string;
  merged_workcenter_group: string;
  parent_group: string;
  plan_source_side: 'input' | 'output';
}

export type ProductionSourceMode = 'output' | 'moveout';

/** Change: production-achievement-column-pivot. Per-子站 breakdown attached to
 *  an expanded (大項) mode DailyViewRow — see DailyViewRow.substations. */
export interface SubstationDailyQty {
  workcenter_group: string;
  d_output_qty: number;
  n_output_qty: number;
  daily_output_qty: number;
}

/** Change: production-achievement-column-pivot. Per-子站 breakdown attached to
 *  an expanded (大項) mode CumulativeViewRow — see CumulativeViewRow.substations. */
export interface SubstationCumulativeQty {
  workcenter_group: string;
  cumulative_actual_qty: number;
}

/** Oracle-sourced plan/target rows (business-rules.md PA-11, replaces the old
 *  Excel-imported DailyPlanMapRow). Keyed on (output_date, plan_package_group)
 *  ONLY — no station dimension; the same target broadcasts to every station
 *  for that package/day (confirmed against IT's PROD_ACH.txt/025.txt). Which
 *  column (planqty_input vs planqty_output) a given station reads is decided
 *  client-side per query via workcenter_merge_map's plan_source_side (PA-20). */
export interface PlanMapRow {
  output_date: string;
  plan_package_group: string;
  planqty_input: number | null;
  planqty_output: number | null;
}

// ── Computed view row shapes (PA-12 daily / PA-13 cumulative) ───────────────

export interface DailyViewRow {
  package_lf_group: string;
  d_output_qty: number;
  n_output_qty: number;
  daily_output_qty: number;
  daily_plan_qty: number | null;
  achievement_rate: number | null;
  /** PA-21: CEIL(daily_plan_qty / 2), null when daily_plan_qty is null. */
  shift_plan_qty: number | null;
  /** d_output_qty / shift_plan_qty; null when shift_plan_qty is null or 0. */
  d_achievement_rate: number | null;
  /** n_output_qty / shift_plan_qty; null when shift_plan_qty is null or 0. */
  n_achievement_rate: number | null;
  /** Change: production-achievement-column-pivot (PA-19 column direction).
   *  Present ONLY in expanded (大項) mode (電鍍/切割) — the per-子站 breakdown
   *  for the column-grouped detail table, in the SAME stable substation order
   *  useProductionAchievement.ts's `expandedSubstations` exposes (the single
   *  source of truth threaded into `computeDailyView`'s `substations` option
   *  and back out here, so the SQL pivot and the UI header can never drift
   *  apart). Every row is now at the same package-total grain regardless of
   *  mode — d_output_qty/n_output_qty/daily_output_qty/achievement_rate above
   *  already carry the 大項-level totals (what the old row-based expanded mode
   *  put on a separate 大項小計 subtotal row); `substations` is purely an
   *  additive breakdown, never a different grain. Undefined in single-layer
   *  mode. */
  substations?: SubstationDailyQty[];
}

export interface CumulativeViewRow {
  package_lf_group: string;
  cumulative_actual_qty: number;
  cumulative_plan_qty: number | null;
  cumulative_diff_qty: number | null;
  cumulative_achievement_rate: number | null;
  /** Change: production-achievement-column-pivot — see DailyViewRow.substations.
   *  Present ONLY in expanded (大項) mode; no D/N split (cumulative view never
   *  had one). Undefined in single-layer mode. */
  substations?: SubstationCumulativeQty[];
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
   *  and each returned row additionally carries a `substations` column-pivot
   *  breakdown (see DailyViewRow.substations). Used for 電鍍/切割. */
  expand?: boolean;
  /** Change: production-achievement-column-pivot. REQUIRED when `expand` is
   *  true — the ordered list of子站 (merged_workcenter_group) under the
   *  selected 大項, exactly as useProductionAchievement.ts's
   *  `expandedSubstations` exposes it (first-seen order from the report's own
   *  workcenter_merge_map). This is the SINGLE source of truth for both the
   *  SQL pivot's column order (col0_*, col1_*, ...) and the JS mapping back
   *  from those positional columns to `substations[].workcenter_group` below
   *  — never re-derived independently, so the two can never drift apart.
   *  Ignored when `expand` is false/absent. */
  substations?: string[];
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
  /** REQUIRED when `expand` is true — see ComputeDailyViewOptions.substations. */
  substations?: string[];
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

function buildPlanMapSql(rows: PlanMapRow[]): string {
  return buildValuesTableSql(
    PLAN_MAP_TABLE,
    [
      { name: 'output_date', type: 'VARCHAR', kind: 'string' },
      { name: 'plan_package_group', type: 'VARCHAR', kind: 'string' },
      { name: 'planqty_input', type: 'INTEGER', kind: 'number' },
      { name: 'planqty_output', type: 'INTEGER', kind: 'number' },
    ],
    rows as unknown as Record<string, unknown>[],
  );
}

/** PA-20: resolve which Oracle plan column (input/output) `selection` (a
 *  merged_workcenter_group in single-layer mode, a parent_group in expanded
 *  大項 mode — both keys are present as `parent_group` in workcenterMergeMap
 *  rows, single-layer stations having parent_group === merged_workcenter_group)
 *  sources its target from. Defaults to 'input' (the column DDL default) when
 *  the selection isn't found — never throws, matches this feature's
 *  degrade-to-null-target posture rather than blocking the view. */
function buildPlanSourceSideMap(rows: WorkcenterMergeMapRow[]): Map<string, 'input' | 'output'> {
  const map = new Map<string, 'input' | 'output'>();
  for (const row of rows) {
    const parent = row.parent_group || row.merged_workcenter_group;
    if (map.has(parent)) continue;
    map.set(parent, row.plan_source_side === 'output' ? 'output' : 'input');
  }
  return map;
}

/**
 * Change: production-achievement-column-pivot. Positional column aliases
 * (col0_d, col1_d, ...) for the expanded (大項) mode column-pivot, one per
 * `metricFields` entry per substation in `substations` (ordered — index i
 * maps 1:1 to `substations[i]`). Positional aliases avoid using the raw
 * (often Chinese) substation name as a SQL identifier entirely — no
 * quoting/encoding risk — the caller maps `col{i}_{suffix}` back to
 * `substations[i]` in JS using the SAME array, never re-derived.
 * `sourceExpr` is the fully-qualified column to pivot from (e.g.
 * `per_child.d_output_qty`); `matchExpr` is the fully-qualified
 * workcenter_group column to match against (e.g. `per_child.workcenter_group`).
 */
function buildPivotColumnsSql(
  substations: string[],
  matchExpr: string,
  metricFields: { suffix: string; sourceExpr: string }[],
): string {
  return substations
    .map((name, i) =>
      metricFields
        .map(
          (f) =>
            `    MAX(CASE WHEN ${matchExpr} = ${sqlString(name)} THEN ${f.sourceExpr} ELSE 0 END) AS col${i}_${f.suffix}`,
        )
        .join(',\n'),
    )
    .join(',\n');
}

/**
 * Bugfix (post-review): computeDailyView's expanded (大項) branch is a
 * TWO-level query — an inner `per_child` CTE (package,子站 grain), wrapped by
 * a `sub` derived table that both re-aggregates per_child up to the package
 * grain AND pivots per_child's rows into col{i}_{suffix} columns via
 * buildPivotColumnsSql, wrapped AGAIN by an outer SELECT that computes the
 * achievement_rate/d_/n_achievement_rate CASE expressions from `sub`'s plain
 * columns (mirrors the single-layer branch's two-level nesting, needed
 * because those CASE expressions read daily_plan_qty/shift_plan_qty which
 * only exist once the plan LEFT JOIN + per-package GROUP BY has run). The
 * outer SELECT must therefore reference `sub`'s ALREADY-PIVOTED col{i}_*
 * columns as plain column refs — re-emitting buildPivotColumnsSql's
 * MAX(CASE WHEN per_child... ) expression there throws a DuckDB
 * BinderException, since per_child is out of scope outside `sub`. Must be
 * called with the SAME `substations`/metric-suffix shape buildPivotColumnsSql
 * built `sub`'s columns from.
 */
function buildPivotColumnRefsSql(
  substations: string[],
  metricFields: { suffix: string }[],
): string {
  return substations
    .map((_, i) => metricFields.map((f) => `    col${i}_${f.suffix}`).join(',\n'))
    .join(',\n');
}

/** Change: production-achievement-column-pivot. Maps the positional
 *  `col{i}_{suffix}` columns a pivot query returns back into a per-substation
 *  breakdown array, using the EXACT same ordered `substations` list the SQL
 *  was built from (see buildPivotColumnsSql) — index and name can never
 *  mismatch since both sides read from the same array. */
function mapPivotColumns(
  row: Record<string, unknown>,
  substations: string[],
  metricFields: { suffix: string; outKey: string }[],
): Record<string, unknown>[] {
  return substations.map((name, i) => {
    const entry: Record<string, unknown> = { workcenter_group: name };
    for (const f of metricFields) {
      entry[f.outKey] = sf(row[`col${i}_${f.suffix}`]);
    }
    return entry;
  });
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

// ── Main composable ───────────────────────────────────────────────────────────

export function useProductionAchievementDuckDB() {
  const isActive = ref(false);
  const isLoading = ref(false);
  const error = ref('');

  let _client: DuckDBClient | null = null;
  let _isRegistered = false;
  let _sourceMode: ProductionSourceMode = 'output';
  let _planSourceSideByParentGroup: Map<string, 'input' | 'output'> = new Map();

  /** PA-20: resolve which plan column the CURRENT selection (a
   *  merged_workcenter_group or, in expanded 大項 mode, a parent_group) reads
   *  from — see `buildPlanSourceSideMap`'s doc comment for the key shape. */
  function _resolvePlanColumn(selection: string): 'planqty_input' | 'planqty_output' {
    return _planSourceSideByParentGroup.get(selection) === 'output'
      ? 'planqty_output'
      : 'planqty_input';
  }

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
   * @param workcenterMergeMap - inline workcenter merge map, D2 (§3.33), now carrying plan_source_side (PA-20)
   * @param planMap            - inline Oracle-sourced (output_date, plan_package_group) -> planqty_input/output map (PA-11)
   * @throws when WASM is unsupported (explicit unsupported state, no server
   *         fallback), the parquet fetch fails, or DuckDB init/SQL fails.
   */
  async function activate(
    spoolUrl: string,
    specWorkcenterMap: SpecWorkcenterMapRow[],
    targetsMap: TargetsMapRow[],
    packageLfMap: PackageLfMapRow[] = [],
    workcenterMergeMap: WorkcenterMergeMapRow[] = [],
    planMap: PlanMapRow[] = [],
    sourceMode: ProductionSourceMode = 'output',
  ): Promise<void> {
    _sourceMode = sourceMode;
    _planSourceSideByParentGroup = buildPlanSourceSideMap(workcenterMergeMap || []);
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
      await _client.sendQuery(buildPlanMapSql(planMap || []));
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
   * total, LEFT JOIN plan_map (PA-11, Oracle-sourced) on
   * (plan_package_group, output_date) reading whichever column (input/output)
   * `_resolvePlanColumn` resolves for the selection (PA-20).
   * achievement_rate is null when the plan row is missing or 0 (never
   * Infinity); 0.0 when daily output is 0 and a non-null non-zero plan exists.
   * shift_plan_qty = CEIL(daily_plan_qty / 2) (PA-21); d_/n_achievement_rate
   * divide each shift's own actual by shift_plan_qty (fixes the previous bug
   * of dividing a single shift's output by the FULL daily plan).
   */
  async function computeDailyView(options: ComputeDailyViewOptions): Promise<DailyViewRow[]> {
    if (!_isRegistered || !_client) throw new Error('DuckDB not initialised');
    const sel = sqlString(options.workcenterGroup);
    const outputDate = sqlString(options.outputDate);
    const expand = options.expand === true;
    const planCol = _resolvePlanColumn(options.workcenterGroup);

    if (!expand) {
      // Single-layer station: one row per package. plan_map joins on
      // package_lf_group + the exact day (which IS the parent for a
      // single-layer station), PA-11.
      const sql = `
        SELECT
          package_lf_group,
          d_output_qty,
          n_output_qty,
          daily_output_qty,
          daily_plan_qty,
          shift_plan_qty,
          CASE
            WHEN daily_plan_qty IS NULL THEN NULL
            WHEN daily_plan_qty = 0 THEN NULL
            ELSE CAST(daily_output_qty AS DOUBLE) / daily_plan_qty
          END AS achievement_rate,
          CASE
            WHEN shift_plan_qty IS NULL THEN NULL
            WHEN shift_plan_qty = 0 THEN NULL
            ELSE CAST(d_output_qty AS DOUBLE) / shift_plan_qty
          END AS d_achievement_rate,
          CASE
            WHEN shift_plan_qty IS NULL THEN NULL
            WHEN shift_plan_qty = 0 THEN NULL
            ELSE CAST(n_output_qty AS DOUBLE) / shift_plan_qty
          END AS n_achievement_rate
        FROM (
          SELECT
            r.package_lf_group AS package_lf_group,
            SUM(CASE WHEN r.shift_code = 'D' THEN r.actual_output_qty ELSE 0 END) / 1000.0 AS d_output_qty,
            SUM(CASE WHEN r.shift_code = 'N' THEN r.actual_output_qty ELSE 0 END) / 1000.0 AS n_output_qty,
            SUM(r.actual_output_qty) / 1000.0 AS daily_output_qty,
            MAX(pm.${planCol}) AS daily_plan_qty,
            CEIL(MAX(pm.${planCol}) / 2.0) AS shift_plan_qty
          FROM ${ROLLUP_TABLE} r
          LEFT JOIN ${PLAN_MAP_TABLE} pm
            ON pm.plan_package_group = r.package_lf_group
            AND CAST(pm.output_date AS DATE) = CAST(${outputDate} AS DATE)
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
        shift_plan_qty: nullableNumber(row.shift_plan_qty),
        d_achievement_rate: nullableNumber(row.d_achievement_rate),
        n_achievement_rate: nullableNumber(row.n_achievement_rate),
      }));
    }

    // Change: production-achievement-column-pivot (PA-19 column direction).
    // Expanded (大項) mode (電鍍/切割): filter on parent_group and emit ONE row
    // per package at the SAME package-total grain the single-layer branch
    // above already produces (what used to be the row-based 大項小計 subtotal
    // row) -- plus a `substations` column-pivot breakdown attached to it. A
    // `per_child` CTE first aggregates to the (package,子站) grain (identical
    // per-child SUMs the OLD GROUPING SETS leaf grain computed); the outer
    // pivot query then does BOTH:
    //   (a) SUM(...) the per_child rows back up to one row per package -- this
    //       SUM-of-subgroup-sums is mathematically identical to the OLD
    //       GROUPING SETS package-only (is_subtotal=1) grain, just reshaped
    //       from a GROUPING SETS pass into a two-level aggregation -- and
    //   (b) MAX(CASE WHEN workcenter_group = <substation> THEN ... ELSE 0 END)
    //       pivots each substation's own d/n/daily values into POSITIONAL
    //       col{i}_d/col{i}_n/col{i}_daily columns (i = substations[i]'s
    //       index) -- sanitized aliases, never the raw (often Chinese)
    //       substation name as a SQL identifier. `substations` must be the
    //       SAME ordered list useProductionAchievement.ts's
    //       expandedSubstations exposes; mapPivotColumns() below maps
    //       col{i}_* back to substations[i] using that identical array, so
    //       index and name can never mismatch.
    // The plan LEFT JOIN and achievement_rate/shift_plan_qty/d_/n_achievement
    // -rate CASE expressions are copied verbatim from the single-layer branch
    // above (same keys: package + exact day; same NULL/zero guards; same
    // formulas) -- this pivoted row is now at exactly the grain the
    // single-layer branch already handles, so no is_subtotal branching is
    // needed anymore. plan_map has at most one row per (package, day), so the
    // LEFT JOIN before GROUP BY package_lf_group never fans out.
    const substations = options.substations && options.substations.length ? options.substations : [options.workcenterGroup];
    const pivotMetricFields = [{ suffix: 'd' }, { suffix: 'n' }, { suffix: 'daily' }];
    const pivotCols = buildPivotColumnsSql(substations, 'per_child.workcenter_group', [
      { suffix: 'd', sourceExpr: 'per_child.d_output_qty' },
      { suffix: 'n', sourceExpr: 'per_child.n_output_qty' },
      { suffix: 'daily', sourceExpr: 'per_child.daily_output_qty' },
    ]);
    // Bugfix (post-review): the outer SELECT reads `sub`'s already-pivoted
    // col{i}_* columns as plain refs (buildPivotColumnRefsSql), NOT the
    // per_child-referencing MAX(CASE...) expression (pivotCols) -- per_child
    // is out of scope in the outer FROM (sub). See buildPivotColumnRefsSql's
    // doc comment.
    const pivotColRefs = buildPivotColumnRefsSql(substations, pivotMetricFields);
    const sql = `
      WITH per_child AS (
        SELECT
          r.package_lf_group AS package_lf_group,
          r.workcenter_group AS workcenter_group,
          SUM(CASE WHEN r.shift_code = 'D' THEN r.actual_output_qty ELSE 0 END) / 1000.0 AS d_output_qty,
          SUM(CASE WHEN r.shift_code = 'N' THEN r.actual_output_qty ELSE 0 END) / 1000.0 AS n_output_qty,
          SUM(r.actual_output_qty) / 1000.0 AS daily_output_qty
        FROM ${ROLLUP_TABLE} r
        WHERE r.parent_group = ${sel}
          AND CAST(r.output_date AS DATE) = CAST(${outputDate} AS DATE)
        GROUP BY r.package_lf_group, r.workcenter_group
      )
      SELECT
        package_lf_group,
        d_output_qty,
        n_output_qty,
        daily_output_qty,
        daily_plan_qty,
        shift_plan_qty,
        CASE
          WHEN daily_plan_qty IS NULL THEN NULL
          WHEN daily_plan_qty = 0 THEN NULL
          ELSE CAST(daily_output_qty AS DOUBLE) / daily_plan_qty
        END AS achievement_rate,
        CASE
          WHEN shift_plan_qty IS NULL THEN NULL
          WHEN shift_plan_qty = 0 THEN NULL
          ELSE CAST(d_output_qty AS DOUBLE) / shift_plan_qty
        END AS d_achievement_rate,
        CASE
          WHEN shift_plan_qty IS NULL THEN NULL
          WHEN shift_plan_qty = 0 THEN NULL
          ELSE CAST(n_output_qty AS DOUBLE) / shift_plan_qty
        END AS n_achievement_rate,
${pivotColRefs}
      FROM (
        SELECT
          per_child.package_lf_group AS package_lf_group,
          SUM(per_child.d_output_qty) AS d_output_qty,
          SUM(per_child.n_output_qty) AS n_output_qty,
          SUM(per_child.daily_output_qty) AS daily_output_qty,
          MAX(pm.${planCol}) AS daily_plan_qty,
          CEIL(MAX(pm.${planCol}) / 2.0) AS shift_plan_qty,
${pivotCols}
        FROM per_child
        LEFT JOIN ${PLAN_MAP_TABLE} pm
          ON pm.plan_package_group = per_child.package_lf_group
          AND CAST(pm.output_date AS DATE) = CAST(${outputDate} AS DATE)
        GROUP BY per_child.package_lf_group
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
      shift_plan_qty: nullableNumber(row.shift_plan_qty),
      d_achievement_rate: nullableNumber(row.d_achievement_rate),
      n_achievement_rate: nullableNumber(row.n_achievement_rate),
      substations: mapPivotColumns(row, substations, [
        { suffix: 'd', outKey: 'd_output_qty' },
        { suffix: 'n', outKey: 'n_output_qty' },
        { suffix: 'daily', outKey: 'daily_output_qty' },
      ]) as unknown as SubstationDailyQty[],
    }));
  }

  /**
   * PA-13: CumulativeView — per-package_lf_group cumulative rows, plan side
   * now a REAL SUM(planqty) over [startDate, endDate] from the Oracle-sourced
   * pa_plan_map (one row per package per day) — replaces the old
   * daily_plan_qty * elapsed_days approximation — PLUS a daily trend that
   * aggregates ACROSS ALL package_lf_groups before dividing (D3 —
   * SUM(actual)/SUM(plan) per day, never a mean of each group's own
   * percentage). Which plan column (input/output) is read is resolved once
   * per call via `_resolvePlanColumn` (PA-20), same as computeDailyView.
   */
  async function computeCumulativeView(options: ComputeCumulativeViewOptions): Promise<CumulativeViewResult> {
    if (!_isRegistered || !_client) throw new Error('DuckDB not initialised');
    const sel = sqlString(options.workcenterGroup);
    const startDate = sqlString(options.startDate);
    const endDate = sqlString(options.endDate);
    const expand = options.expand === true;
    const planCol = _resolvePlanColumn(options.workcenterGroup);
    // Every cumulative plan SUM below is wrapped in CAST(... AS DOUBLE): planqty_input/
    // output are registered as INTEGER (buildPlanMapSql), and DuckDB-WASM promotes
    // SUM(INTEGER) to a 128-bit HUGEINT that serializes to JS as a limb-object
    // ({0:..,1:..,2:..,3:..}) rather than a Number — nullableNumber() then coerces
    // that object to NaN -> null, blanking 累計計畫/累計達成率 for the whole period.
    // The daily view is immune because it reads MAX(planqty) (stays INTEGER), not SUM.
    // CAST to DOUBLE keeps the summed value a plain JS number.
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
          SUM(r.actual_output_qty) / 1000.0 AS cumulative_actual_qty,
          MAX(plan_totals.cumulative_plan_qty) AS cumulative_plan_qty
        FROM ${ROLLUP_TABLE} r
        LEFT JOIN (
          SELECT plan_package_group, CAST(SUM(${planCol}) AS DOUBLE) AS cumulative_plan_qty
          FROM ${PLAN_MAP_TABLE}
          WHERE CAST(output_date AS DATE) BETWEEN CAST(${startDate} AS DATE) AND CAST(${endDate} AS DATE)
          GROUP BY plan_package_group
        ) plan_totals ON plan_totals.plan_package_group = r.package_lf_group
        WHERE r.workcenter_group = ${sel}
          AND CAST(r.output_date AS DATE) BETWEEN CAST(${startDate} AS DATE) AND CAST(${endDate} AS DATE)
        GROUP BY r.package_lf_group
        ORDER BY r.package_lf_group
      `;
      const rawRows = await _client.sendQuery(rowsSql);
      rows = (rawRows as Record<string, unknown>[]).map((row) => {
        const actual = sf(row.cumulative_actual_qty);
        const cumulativePlan = nullableNumber(row.cumulative_plan_qty);
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
      // Change: production-achievement-column-pivot (PA-19 column direction).
      // Expanded (大項) mode: same per_child CTE + pivot approach as
      // computeDailyView -- a `per_child` CTE aggregates to the (package,子站)
      // grain, then the outer query SUMs it back up to one row per package
      // (mathematically identical to the OLD GROUPING SETS package-only
      // subtotal grain) while ALSO pivoting each substation's own
      // cumulative_actual_qty into a positional col{i}_actual column (no D/N
      // split in cumulative mode). The plan LEFT JOIN/cumulative_plan_qty
      // formula is copied verbatim from the single-layer branch above (same
      // key: package + date range; plan_totals has at most one row per
      // package, so no fan-out).
      const substations = options.substations && options.substations.length ? options.substations : [options.workcenterGroup];
      const pivotCols = buildPivotColumnsSql(substations, 'per_child.workcenter_group', [
        { suffix: 'actual', sourceExpr: 'per_child.cumulative_actual_qty' },
      ]);
      const rowsSql = `
        WITH per_child AS (
          SELECT
            r.package_lf_group AS package_lf_group,
            r.workcenter_group AS workcenter_group,
            SUM(r.actual_output_qty) / 1000.0 AS cumulative_actual_qty
          FROM ${ROLLUP_TABLE} r
          WHERE r.parent_group = ${sel}
            AND CAST(r.output_date AS DATE) BETWEEN CAST(${startDate} AS DATE) AND CAST(${endDate} AS DATE)
          GROUP BY r.package_lf_group, r.workcenter_group
        )
        SELECT
          per_child.package_lf_group AS package_lf_group,
          SUM(per_child.cumulative_actual_qty) AS cumulative_actual_qty,
          MAX(plan_totals.cumulative_plan_qty) AS cumulative_plan_qty,
${pivotCols}
        FROM per_child
        LEFT JOIN (
          SELECT plan_package_group, CAST(SUM(${planCol}) AS DOUBLE) AS cumulative_plan_qty
          FROM ${PLAN_MAP_TABLE}
          WHERE CAST(output_date AS DATE) BETWEEN CAST(${startDate} AS DATE) AND CAST(${endDate} AS DATE)
          GROUP BY plan_package_group
        ) plan_totals ON plan_totals.plan_package_group = per_child.package_lf_group
        GROUP BY per_child.package_lf_group
        ORDER BY per_child.package_lf_group
      `;
      const rawRows = await _client.sendQuery(rowsSql);
      rows = (rawRows as Record<string, unknown>[]).map((row) => {
        const actual = sf(row.cumulative_actual_qty);
        const cumulativePlan = nullableNumber(row.cumulative_plan_qty);
        const diff = cumulativePlan === null ? null : actual - cumulativePlan;
        const rate = cumulativePlan === null || cumulativePlan === 0 ? null : actual / cumulativePlan;
        return {
          package_lf_group: String(row.package_lf_group ?? ''),
          cumulative_actual_qty: actual,
          cumulative_plan_qty: cumulativePlan,
          cumulative_diff_qty: diff,
          cumulative_achievement_rate: rate,
          substations: mapPivotColumns(row, substations, [
            { suffix: 'actual', outKey: 'cumulative_actual_qty' },
          ]) as unknown as SubstationCumulativeQty[],
        };
      });
    }

    // D3 aggregate-then-divide trend: sum actual and (known) plan across ALL
    // package_lf_groups for each day BEFORE dividing. A package_lf_group with
    // no plan_map row for that exact day contributes 0 to that day's plan sum
    // (SQL SUM ignores NULL) rather than making the whole day's rate unknown —
    // this mirrors summing only the KNOWN plans, consistent with how the
    // detail rows above already show a "—" only for THAT group's own missing
    // plan. Only per-day actual_qty/plan_qty come from SQL; the RUNNING
    // cumulative total is a plain JS scan below (not a SQL window function) —
    // rows are already ORDER BY output_date, so a linear accumulation is
    // simplest and sidesteps any engine-specific behavior around
    // SUM(...) OVER (...). Trend aggregates ACROSS ALL package_lf_groups (and,
    // in expanded 大項 mode, all子站) under the selection for each day, then
    // divides (D3). The trend is a 大項-level line regardless of mode, so it
    // rolls the子站 up to (day, package) and joins pa_plan_map on
    // (package, THAT day) — pa_plan_map has no station dimension at all, so
    // unlike the old daily_plan_map join there is no `= sel` half to the join
    // condition anymore.
    const trendSql = `
      SELECT
        strftime(CAST(g.output_date AS DATE), '%Y-%m-%d') AS output_date,
        SUM(g.actual_output_qty) / 1000.0 AS actual_qty,
        CAST(SUM(pm.${planCol}) AS DOUBLE) AS plan_qty
      FROM (
        SELECT output_date, package_lf_group, SUM(actual_output_qty) AS actual_output_qty
        FROM ${ROLLUP_TABLE}
        WHERE ${filterCol} = ${sel}
          AND CAST(output_date AS DATE) BETWEEN CAST(${startDate} AS DATE) AND CAST(${endDate} AS DATE)
        GROUP BY output_date, package_lf_group
      ) g
      LEFT JOIN ${PLAN_MAP_TABLE} pm
        ON pm.plan_package_group = g.package_lf_group
        AND CAST(pm.output_date AS DATE) = CAST(g.output_date AS DATE)
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
