/**
 * useProductionAchievementDuckDB — DuckDB-WASM composable for
 * production-achievement.
 *
 * Change: production-achievement-async-spool (ADR-0016)
 * IP-6: activate(spoolUrl, spec_workcenter_map, targets_map) downloads the
 * SPECNAME-grain parquet spool (data-shape-contract.md §3.28.1) and computes
 * PA-06 (SPECNAME -> workcenter_group rollup) + PA-07 (target join +
 * achievement_rate) entirely client-side in DuckDB-WASM SQL. No server-side
 * Python performs this computation on the request path any more
 * (business-rules.md PA-06/PA-07 "Implementation locus" notes).
 *
 * Mirrors resource-history's useResourceHistoryDuckDB.ts lifecycle
 * (activate -> computeView -> deactivate), with two production-achievement
 * -specific differences:
 *   - Q1 (design.md, RESOLVED): the local-compute activation threshold is
 *     overridden to 0 here — DuckDB-WASM always activates on a spool hit (no
 *     row-count gate, unlike resource_history's >= threshold gate). A
 *     browser without WASM/Worker support gets an explicit "unsupported"
 *     error from activate() — there is no hidden server-side rollup to fall
 *     back to.
 *   - spec_workcenter_map / targets_map are small inline arrays injected by
 *     the server alongside spool_download_url (Q2, data-shape-contract.md
 *     §3.28.2/.3), not derived from the spool itself — they are registered
 *     as small in-memory DuckDB tables via a literal VALUES list (the
 *     Worker's message protocol only exposes 'register' for Parquet buffers
 *     and 'query' for arbitrary SQL; there is no JSON-register message type).
 */

import { ref, readonly } from 'vue';
import { getDuckDBClient, fetchParquetBuffer } from '../../core/duckdb-client';
import type { DuckDBClient } from '../../core/duckdb-client';
import { checkLocalComputeEligibility } from '../../core/duckdb-activation-policy';
import type { ProductionAchievementReportRow } from './useProductionAchievement';

const TABLE_NAME = 'production_achievement_data';
const SPEC_MAP_TABLE = 'pa_spec_workcenter_map';
const TARGETS_TABLE = 'pa_targets_map';
const ROLLUP_TABLE = 'pa_rollup';

// ── Inline-injected map shapes (data-shape-contract.md §3.28.2/.3) ──────────

export interface SpecWorkcenterMapRow {
  SPECNAME: string;
  workcenter_group: string;
}

export interface TargetsMapRow {
  shift_code: string;
  workcenter_group: string;
  target_qty: number | null;
}

export interface ComputeViewOptions {
  /** Client-side narrowing only — the spool itself is never re-fetched for these. */
  shiftCode?: string;
  workcenterGroup?: string;
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
 * empty-array case emits a typed zero-row SELECT instead (empty
 * spec_workcenter_map / targets_map is a valid degraded state — data-shape
 * -contract.md §3.28.3 MYSQL_OPS_ENABLED=false note).
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

  /**
   * PA-06 rollup: join the SPECNAME-grain spool to spec_workcenter_map via
   * UPPER(TRIM(SPECNAME)) on BOTH sides — must equal the backend's
   * `str(specname).strip().upper()` (business-rules.md PA-06) or rows
   * silently drop out of the parity diff. Rows whose SPECNAME has no mapping
   * entry are excluded (INNER JOIN — unmapped-SPECNAME exclusion).
   */
  async function _buildRollup(): Promise<void> {
    const sql = `
      CREATE OR REPLACE TABLE ${ROLLUP_TABLE} AS
      SELECT
        s.output_date AS output_date,
        s.shift_code AS shift_code,
        m.workcenter_group AS workcenter_group,
        SUM(s.actual_output_qty) AS actual_output_qty
      FROM ${TABLE_NAME} s
      INNER JOIN ${SPEC_MAP_TABLE} m
        ON UPPER(TRIM(CAST(s.SPECNAME AS VARCHAR))) = UPPER(TRIM(CAST(m.SPECNAME AS VARCHAR)))
      GROUP BY s.output_date, s.shift_code, m.workcenter_group
    `;
    await _client!.sendQuery(sql);
  }

  /**
   * Activate local compute mode.
   * @param spoolUrl          - SPECNAME-grain Parquet spool download URL (§3.28.1)
   * @param specWorkcenterMap - inline SPECNAME -> workcenter_group map (§3.28.2)
   * @param targetsMap        - inline (shift_code, workcenter_group) -> target_qty map (§3.28.3)
   * @throws when WASM is unsupported (explicit unsupported state, no server
   *         fallback), the parquet fetch fails, or DuckDB init/SQL fails.
   */
  async function activate(
    spoolUrl: string,
    specWorkcenterMap: SpecWorkcenterMapRow[],
    targetsMap: TargetsMapRow[],
  ): Promise<void> {
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
   * re-downloading the spool parquet or rebuilding the PA-06 rollup — only
   * PA-07's join input changed. Call computeView() afterwards to re-render.
   */
  async function updateTargetsMap(targetsMap: TargetsMapRow[]): Promise<void> {
    if (!_isRegistered || !_client) throw new Error('DuckDB not initialised');
    await _client.sendQuery(buildTargetsMapSql(targetsMap || []));
  }

  /**
   * PA-07: LEFT JOIN the PA-06 rollup against targets_map on
   * (shift_code, workcenter_group). achievement_rate is null when the
   * target is missing or 0 (never Infinity); 0.0 when actual=0 and a
   * non-null non-zero target exists (business-rules.md PA-07).
   */
  async function computeView(options: ComputeViewOptions = {}): Promise<ProductionAchievementReportRow[]> {
    if (!_isRegistered || !_client) throw new Error('DuckDB not initialised');

    const whereClauses: string[] = [];
    if (options.shiftCode) whereClauses.push(`r.shift_code = ${sqlString(options.shiftCode)}`);
    if (options.workcenterGroup) whereClauses.push(`r.workcenter_group = ${sqlString(options.workcenterGroup)}`);
    const where = whereClauses.length ? `WHERE ${whereClauses.join(' AND ')}` : '';

    const sql = `
      SELECT
        strftime(CAST(r.output_date AS DATE), '%Y-%m-%d') AS output_date,
        r.shift_code AS shift_code,
        r.workcenter_group AS workcenter_group,
        r.actual_output_qty AS actual_output_qty,
        t.target_qty AS target_qty,
        CASE
          WHEN t.target_qty IS NULL THEN NULL
          WHEN t.target_qty = 0 THEN NULL
          ELSE CAST(r.actual_output_qty AS DOUBLE) / t.target_qty
        END AS achievement_rate
      FROM ${ROLLUP_TABLE} r
      LEFT JOIN ${TARGETS_TABLE} t
        ON r.shift_code = t.shift_code AND r.workcenter_group = t.workcenter_group
      ${where}
      ORDER BY r.output_date, r.shift_code, r.workcenter_group
    `;
    const rows = await _client.sendQuery(sql);
    return (rows as Record<string, unknown>[]).map((row) => ({
      output_date: String(row.output_date ?? ''),
      shift_code: String(row.shift_code ?? ''),
      workcenter_group: String(row.workcenter_group ?? ''),
      actual_output_qty: sf(row.actual_output_qty),
      target_qty: nullableNumber(row.target_qty),
      achievement_rate: nullableNumber(row.achievement_rate),
    }));
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
    computeView,
    updateTargetsMap,
    deactivate,
  };
}
