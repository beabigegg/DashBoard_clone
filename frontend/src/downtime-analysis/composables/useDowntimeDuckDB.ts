/**
 * useDowntimeDuckDB — DuckDB-WASM composable for downtime-analysis.
 *
 * Change: downtime-browser-duckdb
 * Design: design.md D1-D8; implementation-plan.md IP-7, IP-8
 * AC-3: cross-shift merge + job-bridge parity vs Python _merge_cross_shift_events/_bridge_jobid
 * AC-4: server-authoritative taxonomy for BigCategory mapping
 * AC-7: explicit error states; NEVER silent empty table (CLAUDE.md Type-A note)
 * AC-8: browser-blob CSV export (D2)
 *
 * Lifecycle:
 *   1. Server returns {base_spool_url, jobs_spool_url, query_id, taxonomy}
 *   2. activate() downloads both parquets, registers them in DuckDB-WASM,
 *      runs the cross-shift merge + job-bridge SQL once → produces merged_events
 *   3. All view queries run against merged_events (zero API round-trips)
 *   4. Filter changes call queryKpi / queryDailyTrend / queryBigCategory /
 *      queryEquipmentDetail / queryEventDetail directly
 *
 * State machine:
 *   idle    → loading → ready   (activate success)
 *   loading → error             (WASM init, fetch 404, merge SQL error)
 *   ready   → idle              (deactivate)
 *
 * ADR-0003: full parquet must be in memory before merge SQL runs. Do NOT chunk.
 */

import { ref, readonly } from 'vue';
import { getDuckDBClient, fetchParquetBuffer } from '../../core/duckdb-client';
import type { DuckDBClient } from '../../core/duckdb-client';

// ── Types ────────────────────────────────────────────────────────────────────

export interface TaxonomyShape {
  map: [string, string][];      // [reason, category] exact-match rows
  prefixes: [string, string][]; // [prefix, category] prefix-match rules
  egt_category: string;         // output category for OLDSTATUSNAME == 'EGT'
  fallback: string;             // unknown/blank reasons
}

export interface DowntimeFilters {
  resourceIds?: string[];
  bigCategories?: string[];
  statusTypes?: string[];
  granularity?: 'day' | 'week' | 'month';
}

export interface KpiResult {
  total_hours: number;
  udt_hours: number;
  sdt_hours: number;
  egt_hours: number;
  event_count: number;
  avg_event_min: number;
}

export interface DailyTrendRow {
  date: string;
  udt_hours: number;
  sdt_hours: number;
  egt_hours: number;
  total_hours: number;
}

export interface BigCategoryRow {
  category: string;
  hours: number;
  event_count: number;
  pct: number;
}

export interface ResourceLookupEntry {
  resource_name: string | null;
  workcenter: string | null;
  family: string | null;
}

export interface EquipmentDetailRow {
  resource_id: string;
  resource_name: string | null;
  workcenter: string | null;
  family: string | null;
  udt_hours: number;
  sdt_hours: number;
  egt_hours: number;
  total_hours: number;
  event_count: number;
  udt_event_count: number;
  sdt_event_count: number;
  egt_event_count: number;
}

export interface EquipmentDetailResult {
  data: EquipmentDetailRow[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface EventDetailJobEnrichment {
  job_id: string | null;
  job_order_name: string | null;
  job_model: string | null;
  symptom: string | null;
  cause: string | null;
  repair: string | null;
  handler: string | null;
  wait_min: number | null;
  repair_min: number | null;
  wait_assign_min: number | null;
  wait_ack_min: number | null;
  inspect_min: number | null;
  close_wait_min: number | null;
  job_create_date: string | null;
  job_complete_date: string | null;
  match_ambiguous: boolean;
}

export interface EventDetailRow {
  event_id: string;
  resource_id: string;
  status: string;
  reason: string | null;
  category: string;
  start_ts: string;
  end_ts: string;
  hours: number;
  match_source: 'jobid' | 'overlap' | 'none';
  job: EventDetailJobEnrichment | null;
}

export interface EventDetailResult {
  data: EventDetailRow[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface TopReasonRow {
  reason: string;
  status: string;
  big_category: string;
  total_hours: number;
  event_count: number;
  avg_min: number;
}

export type ComposableState = 'idle' | 'loading' | 'ready' | 'error';

/**
 * Classifies DuckDB activation errors into three user-facing categories.
 *   fetch     — network / HTTP failure downloading parquet files
 *   wasm_init — DuckDB-WASM client init failure (browser incompatibility)
 *   compute   — SQL error during cross-shift merge or job-bridge
 */
export type DuckdbErrorKind = 'fetch' | 'wasm_init' | 'compute';

// ── SQL constants ────────────────────────────────────────────────────────────

/** Merge gap tolerance in seconds (mirrors _MERGE_GAP_SECONDS = 60) */
const MERGE_GAP_SECONDS = 60;

/**
 * Cross-shift merge SQL (mirrors _CROSS_SHIFT_MERGE_SQL from downtime_analysis_service.py).
 * Reads from "base_events" DuckDB view/table, returns merged logical events.
 * Must be run on the FULL parquet before any view query (ADR-0003).
 */
const CROSS_SHIFT_MERGE_SQL = `
WITH sorted_events AS (
    SELECT
        *,
        COALESCE(TRY_CAST(HOURS AS DOUBLE), 0.0)        AS _hours_num,
        TRY_CAST(OLDLASTSTATUSCHANGEDATE AS TIMESTAMP)   AS _estart,
        TRY_CAST(LASTSTATUSCHANGEDATE    AS TIMESTAMP)   AS _eend,
        TRIM(CAST(HISTORYID      AS VARCHAR))             AS _h,
        TRIM(CAST(OLDSTATUSNAME  AS VARCHAR))             AS _s,
        COALESCE(NULLIF(TRIM(CAST(OLDREASONNAME AS VARCHAR)), ''), '') AS _r
    FROM base_events
    ORDER BY
        TRIM(CAST(HISTORYID     AS VARCHAR)),
        TRIM(CAST(OLDSTATUSNAME AS VARCHAR)),
        COALESCE(NULLIF(TRIM(CAST(OLDREASONNAME AS VARCHAR)), ''), ''),
        TRY_CAST(OLDLASTSTATUSCHANGEDATE AS TIMESTAMP) NULLS LAST
),
numbered AS (
    SELECT *, ROW_NUMBER() OVER () AS _srn
    FROM sorted_events
),
lagged AS (
    SELECT *,
        LAG(_h)    OVER (ORDER BY _srn) AS _ph,
        LAG(_s)    OVER (ORDER BY _srn) AS _ps,
        LAG(_r)    OVER (ORDER BY _srn) AS _pr,
        LAG(_eend) OVER (ORDER BY _srn) AS _prev_end
    FROM numbered
),
breaks AS (
    SELECT *,
        CASE
            WHEN _ph IS NULL                                                 THEN 1
            WHEN _h  != _ph                                                  THEN 1
            WHEN _s  != _ps                                                  THEN 1
            WHEN _r  != COALESCE(_pr, '')                                    THEN 1
            WHEN _prev_end IS NULL                                           THEN 1
            WHEN datediff('second', _prev_end, _estart) > {gap_seconds}      THEN 1
            ELSE 0
        END AS _is_break
    FROM lagged
),
run_ids AS (
    SELECT *,
        SUM(_is_break) OVER (
            ORDER BY _srn
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS _run_id
    FROM breaks
)
SELECT
    FIRST(_h)                                                                             AS HISTORYID,
    FIRST(_s)                                                                             AS OLDSTATUSNAME,
    FIRST(NULLIF(TRIM(CAST(OLDREASONNAME AS VARCHAR)), ''))
        FILTER (WHERE NULLIF(TRIM(CAST(OLDREASONNAME AS VARCHAR)), '') IS NOT NULL)       AS OLDREASONNAME,
    MIN(_estart)                                                                          AS event_start,
    MAX(_eend)                                                                            AS event_end,
    ROUND(SUM(_hours_num), 6)                                                             AS hours,
    COUNT(*)                                                                              AS fragment_count,
    FIRST(CAST(JOBID AS VARCHAR)) FILTER (WHERE JOBID IS NOT NULL)                        AS JOBID
FROM run_ids
GROUP BY _run_id
ORDER BY HISTORYID, event_start
`;

/**
 * Job-overlap bridge SQL (mirrors _bridge_jobid Path B ranking logic).
 * Reads from merged_events + job_bridge tables.
 * Assigns job enrichment via direct JOBID match (Path A) or overlap tiebreak (Path B).
 */
const JOB_BRIDGE_SQL = `
WITH path_a_base AS (
    -- Path A: events that have JOBID and a matching job
    SELECT
        e.HISTORYID,
        e.OLDSTATUSNAME,
        e.OLDREASONNAME,
        e.event_start,
        e.event_end,
        e.hours,
        e.fragment_count,
        e.JOBID,
        j.JOBID                    AS _matched_jobid,
        j.SYMPTOMCODENAME,
        j.CAUSECODENAME,
        j.REPAIRCODENAME,
        j.COMPLETE_FULLNAME,
        j.FIRSTCLOCKONDATE,
        j.LASTCLOCKOFFDATE,
        j.JOBORDERNAME,
        j.JOBMODELNAME,
        j.ASSIGNED_DATE,
        j.ACK_DATE,
        j.INSPECT_START,
        j.INSPECT_END,
        j.CREATEDATE,
        j.COMPLETEDATE,
        'jobid'                    AS match_source,
        FALSE                      AS match_ambiguous
    FROM merged_events e
    INNER JOIN job_bridge j
        ON TRIM(CAST(e.JOBID AS VARCHAR)) = TRIM(CAST(j.JOBID AS VARCHAR))
    WHERE e.JOBID IS NOT NULL
),
path_a_orphan AS (
    -- Path A orphan: has JOBID but no matching job
    SELECT
        e.HISTORYID,
        e.OLDSTATUSNAME,
        e.OLDREASONNAME,
        e.event_start,
        e.event_end,
        e.hours,
        e.fragment_count,
        e.JOBID,
        NULL::VARCHAR              AS _matched_jobid,
        NULL::VARCHAR              AS SYMPTOMCODENAME,
        NULL::VARCHAR              AS CAUSECODENAME,
        NULL::VARCHAR              AS REPAIRCODENAME,
        NULL::VARCHAR              AS COMPLETE_FULLNAME,
        NULL::TIMESTAMP            AS FIRSTCLOCKONDATE,
        NULL::TIMESTAMP            AS LASTCLOCKOFFDATE,
        NULL::VARCHAR              AS JOBORDERNAME,
        NULL::VARCHAR              AS JOBMODELNAME,
        NULL::TIMESTAMP            AS ASSIGNED_DATE,
        NULL::TIMESTAMP            AS ACK_DATE,
        NULL::TIMESTAMP            AS INSPECT_START,
        NULL::TIMESTAMP            AS INSPECT_END,
        NULL::TIMESTAMP            AS CREATEDATE,
        NULL::TIMESTAMP            AS COMPLETEDATE,
        'none'                     AS match_source,
        FALSE                      AS match_ambiguous
    FROM merged_events e
    WHERE e.JOBID IS NOT NULL
      AND NOT EXISTS (
          SELECT 1 FROM job_bridge j
          WHERE TRIM(CAST(e.JOBID AS VARCHAR)) = TRIM(CAST(j.JOBID AS VARCHAR))
      )
),
path_b_overlap AS (
    -- Path B: no JOBID, find best overlapping job by resource + time overlap
    SELECT
        e.HISTORYID,
        e.OLDSTATUSNAME,
        e.OLDREASONNAME,
        e.event_start,
        e.event_end,
        e.hours,
        e.fragment_count,
        e.JOBID,
        j.JOBID                    AS _matched_jobid,
        j.SYMPTOMCODENAME,
        j.CAUSECODENAME,
        j.REPAIRCODENAME,
        j.COMPLETE_FULLNAME,
        j.FIRSTCLOCKONDATE,
        j.LASTCLOCKOFFDATE,
        j.JOBORDERNAME,
        j.JOBMODELNAME,
        j.ASSIGNED_DATE,
        j.ACK_DATE,
        j.INSPECT_START,
        j.INSPECT_END,
        j.CREATEDATE,
        j.COMPLETEDATE,
        epoch(
            LEAST(e.event_end, COALESCE(j.COMPLETEDATE, j.LASTCLOCKOFFDATE)) -
            GREATEST(e.event_start, j.CREATEDATE)
        )                          AS _overlap_sec,
        ROW_NUMBER() OVER (
            PARTITION BY e.HISTORYID, e.event_start
            ORDER BY
                epoch(
                    LEAST(e.event_end, COALESCE(j.COMPLETEDATE, j.LASTCLOCKOFFDATE)) -
                    GREATEST(e.event_start, j.CREATEDATE)
                ) DESC,
                j.CREATEDATE ASC,
                j.JOBID ASC
        ) AS _rank,
        MAX(epoch(
            LEAST(e.event_end, COALESCE(j.COMPLETEDATE, j.LASTCLOCKOFFDATE)) -
            GREATEST(e.event_start, j.CREATEDATE)
        )) OVER (PARTITION BY e.HISTORYID, e.event_start) AS _max_overlap_sec
    FROM merged_events e
    LEFT JOIN job_bridge j
        ON TRIM(CAST(j.RESOURCEID AS VARCHAR)) = TRIM(CAST(e.HISTORYID AS VARCHAR))
        AND COALESCE(j.COMPLETEDATE, j.LASTCLOCKOFFDATE) IS NOT NULL
        AND COALESCE(j.COMPLETEDATE, j.LASTCLOCKOFFDATE) > e.event_start
        AND j.CREATEDATE < e.event_end
    WHERE e.JOBID IS NULL
),
path_b_winners AS (
    SELECT
        HISTORYID, OLDSTATUSNAME, OLDREASONNAME, event_start, event_end, hours, fragment_count, JOBID,
        _matched_jobid, SYMPTOMCODENAME, CAUSECODENAME, REPAIRCODENAME, COMPLETE_FULLNAME,
        FIRSTCLOCKONDATE, LASTCLOCKOFFDATE, JOBORDERNAME, JOBMODELNAME,
        ASSIGNED_DATE, ACK_DATE, INSPECT_START, INSPECT_END, CREATEDATE, COMPLETEDATE,
        CASE WHEN _matched_jobid IS NOT NULL THEN 'overlap' ELSE 'none' END AS match_source,
        -- Ambiguous: runner-up exists and runner-up overlap >= 80% of winner overlap
        CASE
            WHEN _rank = 1 AND _overlap_sec IS NOT NULL AND _overlap_sec > 0
              AND (SELECT MIN(b2._overlap_sec) FROM path_b_overlap b2
                   WHERE b2.HISTORYID = path_b_overlap.HISTORYID
                     AND b2.event_start = path_b_overlap.event_start
                     AND b2._rank = 2) >= 0.8 * _overlap_sec
            THEN TRUE
            ELSE FALSE
        END AS match_ambiguous
    FROM path_b_overlap
    WHERE _rank = 1
      AND _matched_jobid IS NOT NULL
),
path_b_no_job AS (
    -- Events with no JOBID and no overlap candidates (LEFT JOIN produced NULL job)
    SELECT
        HISTORYID, OLDSTATUSNAME, OLDREASONNAME, event_start, event_end, hours, fragment_count, JOBID,
        NULL::VARCHAR   AS _matched_jobid,
        NULL::VARCHAR   AS SYMPTOMCODENAME,
        NULL::VARCHAR   AS CAUSECODENAME,
        NULL::VARCHAR   AS REPAIRCODENAME,
        NULL::VARCHAR   AS COMPLETE_FULLNAME,
        NULL::TIMESTAMP AS FIRSTCLOCKONDATE,
        NULL::TIMESTAMP AS LASTCLOCKOFFDATE,
        NULL::VARCHAR   AS JOBORDERNAME,
        NULL::VARCHAR   AS JOBMODELNAME,
        NULL::TIMESTAMP AS ASSIGNED_DATE,
        NULL::TIMESTAMP AS ACK_DATE,
        NULL::TIMESTAMP AS INSPECT_START,
        NULL::TIMESTAMP AS INSPECT_END,
        NULL::TIMESTAMP AS CREATEDATE,
        NULL::TIMESTAMP AS COMPLETEDATE,
        'none'          AS match_source,
        FALSE           AS match_ambiguous
    FROM merged_events e
    WHERE e.JOBID IS NULL
      AND NOT EXISTS (
          SELECT 1 FROM job_bridge j
          WHERE TRIM(CAST(j.RESOURCEID AS VARCHAR)) = TRIM(CAST(e.HISTORYID AS VARCHAR))
            AND COALESCE(j.COMPLETEDATE, j.LASTCLOCKOFFDATE) IS NOT NULL
            AND COALESCE(j.COMPLETEDATE, j.LASTCLOCKOFFDATE) > e.event_start
            AND j.CREATEDATE < e.event_end
      )
)
SELECT
    HISTORYID, OLDSTATUSNAME, OLDREASONNAME, event_start, event_end, hours, fragment_count, JOBID,
    _matched_jobid, SYMPTOMCODENAME, CAUSECODENAME, REPAIRCODENAME, COMPLETE_FULLNAME,
    FIRSTCLOCKONDATE, LASTCLOCKOFFDATE, JOBORDERNAME, JOBMODELNAME,
    ASSIGNED_DATE, ACK_DATE, INSPECT_START, INSPECT_END, CREATEDATE, COMPLETEDATE,
    match_source, match_ambiguous
FROM path_a_base
UNION ALL
SELECT
    HISTORYID, OLDSTATUSNAME, OLDREASONNAME, event_start, event_end, hours, fragment_count, JOBID,
    _matched_jobid, SYMPTOMCODENAME, CAUSECODENAME, REPAIRCODENAME, COMPLETE_FULLNAME,
    FIRSTCLOCKONDATE, LASTCLOCKOFFDATE, JOBORDERNAME, JOBMODELNAME,
    ASSIGNED_DATE, ACK_DATE, INSPECT_START, INSPECT_END, CREATEDATE, COMPLETEDATE,
    match_source, match_ambiguous
FROM path_a_orphan
UNION ALL
SELECT
    HISTORYID, OLDSTATUSNAME, OLDREASONNAME, event_start, event_end, hours, fragment_count, JOBID,
    _matched_jobid, SYMPTOMCODENAME, CAUSECODENAME, REPAIRCODENAME, COMPLETE_FULLNAME,
    FIRSTCLOCKONDATE, LASTCLOCKOFFDATE, JOBORDERNAME, JOBMODELNAME,
    ASSIGNED_DATE, ACK_DATE, INSPECT_START, INSPECT_END, CREATEDATE, COMPLETEDATE,
    match_source, match_ambiguous
FROM path_b_winners
UNION ALL
SELECT
    HISTORYID, OLDSTATUSNAME, OLDREASONNAME, event_start, event_end, hours, fragment_count, JOBID,
    _matched_jobid, SYMPTOMCODENAME, CAUSECODENAME, REPAIRCODENAME, COMPLETE_FULLNAME,
    FIRSTCLOCKONDATE, LASTCLOCKOFFDATE, JOBORDERNAME, JOBMODELNAME,
    ASSIGNED_DATE, ACK_DATE, INSPECT_START, INSPECT_END, CREATEDATE, COMPLETEDATE,
    match_source, match_ambiguous
FROM path_b_no_job
ORDER BY HISTORYID, event_start
`;

// ── Helpers ──────────────────────────────────────────────────────────────────

function sf(val: unknown, def = 0): number {
  const n = Number(val);
  return isNaN(n) ? def : n;
}

function nullableStr(val: unknown): string | null {
  if (val === null || val === undefined) return null;
  const s = String(val).trim();
  if (!s || s === 'null' || s === 'undefined' || s === 'NaT' || s === 'nan') return null;
  return s;
}

function nullableFloat(val: unknown): number | null {
  const n = Number(val);
  return isNaN(n) ? null : Math.round(n * 100) / 100;
}

function toIsoString(val: unknown): string | null {
  if (val === null || val === undefined) return null;
  const s = String(val).trim();
  if (!s || s === 'null') return null;
  try {
    const d = new Date(s);
    if (isNaN(d.getTime())) return null;
    return d.toISOString();
  } catch {
    return null;
  }
}

/**
 * Apply server-authoritative taxonomy to map OLDREASONNAME + OLDSTATUSNAME → big category.
 * Rules (priority order):
 * 1. OLDSTATUSNAME == 'EGT' → egt_category (always, regardless of reason)
 * 2. Strip reason; exact lookup in taxonomy.map
 * 3. Prefix match in taxonomy.prefixes
 * 4. fallback
 */
function applyTaxonomyMapping(
  reason: string | null,
  status: string,
  taxonomy: TaxonomyShape
): string {
  if (status.trim() === 'EGT') return taxonomy.egt_category;
  const stripped = (reason ?? '').trim();
  if (!stripped) return taxonomy.fallback;
  const exact = taxonomy.map.find(([r]) => r === stripped);
  if (exact) return exact[1];
  const prefix = taxonomy.prefixes.find(([p]) => stripped.startsWith(p));
  if (prefix) return prefix[1];
  return taxonomy.fallback;
}

/**
 * Build SQL WHERE clause from DowntimeFilters.
 * Runs against "bridged_events" table which has HISTORYID, OLDSTATUSNAME, big_category columns.
 */
function buildFilterClause(filters: DowntimeFilters): { sql: string; params: Record<string, unknown> } {
  const conditions: string[] = [];
  const params: Record<string, unknown> = {};

  if (filters.resourceIds && filters.resourceIds.length > 0) {
    const placeholders = filters.resourceIds.map((_, i) => `$res${i}`).join(', ');
    filters.resourceIds.forEach((id, i) => { params[`res${i}`] = id; });
    conditions.push(`TRIM(CAST(HISTORYID AS VARCHAR)) IN (${placeholders})`);
  }

  if (filters.statusTypes && filters.statusTypes.length > 0) {
    const placeholders = filters.statusTypes.map((_, i) => `$st${i}`).join(', ');
    filters.statusTypes.forEach((st, i) => { params[`st${i}`] = st; });
    conditions.push(`TRIM(CAST(OLDSTATUSNAME AS VARCHAR)) IN (${placeholders})`);
  }

  if (filters.bigCategories && filters.bigCategories.length > 0) {
    const placeholders = filters.bigCategories.map((_, i) => `$bc${i}`).join(', ');
    filters.bigCategories.forEach((bc, i) => { params[`bc${i}`] = bc; });
    conditions.push(`big_category IN (${placeholders})`);
  }

  const sql = conditions.length > 0 ? `WHERE ${conditions.join(' AND ')}` : '';
  return { sql, params };
}

/**
 * Interpolate named params ($key) into SQL string.
 * Simple implementation: replaces $key with quoted/numeric values.
 * DuckDB-WASM JS client does not support parameterized queries via sendQuery,
 * so we interpolate safe values (all from server-provided filter arrays).
 */
function interpolateParams(sql: string, params: Record<string, unknown>): string {
  let result = sql;
  for (const [key, val] of Object.entries(params)) {
    const escaped = typeof val === 'string'
      ? `'${val.replace(/'/g, "''")}'`
      : String(val);
    result = result.replace(new RegExp(`\\$${key}\\b`, 'g'), escaped);
  }
  return result;
}

// ── CSV export helper ────────────────────────────────────────────────────────

function rowsToCsv(headers: string[], rows: Record<string, unknown>[]): string {
  const escape = (v: unknown): string => {
    if (v === null || v === undefined) return '';
    const s = String(v);
    if (s.includes(',') || s.includes('"') || s.includes('\n')) {
      return `"${s.replace(/"/g, '""')}"`;
    }
    return s;
  };
  const lines = [
    headers.join(','),
    ...rows.map((row) => headers.map((h) => escape(row[h])).join(','))
  ];
  return lines.join('\n');
}

function downloadCsv(content: string, filename: string): void {
  const blob = new Blob(['﻿' + content], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.style.display = 'none';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

// ── Main composable ───────────────────────────────────────────────────────────

export function useDowntimeDuckDB() {
  const state = ref<ComposableState>('idle');
  const errorMessage = ref('');
  const errorKind = ref<DuckdbErrorKind | null>(null);

  let _client: DuckDBClient | null = null;
  let _taxonomy: TaxonomyShape | null = null;
  let _resourceLookup: Record<string, ResourceLookupEntry> = {};
  let _isMerged = false;

  /**
   * Guard: throw if composable is not in 'ready' state.
   * Prevents silent empty-table failures (CLAUDE.md Type-A rule).
   */
  function _assertReady(op: string): void {
    if (state.value !== 'ready') {
      throw new Error(
        `useDowntimeDuckDB: cannot call ${op}() — state is '${state.value}' (expected 'ready'). ` +
        'Call activate() first and wait for it to resolve.'
      );
    }
  }

  /**
   * Build taxonomy CASE expression for SQL.
   * Used in queries that need big_category derived inline.
   * Generates a SQL CASE WHEN chain for DuckDB.
   */
  function _buildCategoryExpr(taxonomy: TaxonomyShape): string {
    const egtCat = taxonomy.egt_category.replace(/'/g, "''");
    const fallback = taxonomy.fallback.replace(/'/g, "''");

    const exactCases = taxonomy.map
      .map(([reason, cat]) => {
        const r = reason.replace(/'/g, "''");
        const c = cat.replace(/'/g, "''");
        return `WHEN TRIM(CAST(OLDREASONNAME AS VARCHAR)) = '${r}' THEN '${c}'`;
      })
      .join('\n            ');

    const prefixCases = taxonomy.prefixes
      .map(([prefix, cat]) => {
        const p = prefix.replace(/'/g, "''");
        const c = cat.replace(/'/g, "''");
        return `WHEN TRIM(CAST(OLDREASONNAME AS VARCHAR)) LIKE '${p}%' THEN '${c}'`;
      })
      .join('\n            ');

    return (
      `CASE\n` +
      `            WHEN TRIM(CAST(OLDSTATUSNAME AS VARCHAR)) = 'EGT' THEN '${egtCat}'\n` +
      (exactCases ? `            ${exactCases}\n` : '') +
      (prefixCases ? `            ${prefixCases}\n` : '') +
      `            ELSE '${fallback}'\n` +
      `        END`
    );
  }

  /**
   * Activate DuckDB-WASM compute mode.
   * 1. Init client
   * 2. Download both parquets (atomicity: both or neither)
   * 3. Register as DuckDB tables
   * 4. Run cross-shift merge → CREATE TABLE merged_events
   * 5. Run job-bridge SQL → CREATE TABLE bridged_events (with big_category)
   *
   * @throws on any failure (WASM init, fetch 404, merge SQL error)
   */
  async function activate(
    baseSpool: string,
    jobsSpool: string,
    taxonomy: TaxonomyShape,
    resourceLookup: Record<string, ResourceLookupEntry> = {}
  ): Promise<void> {
    state.value = 'loading';
    errorMessage.value = '';
    errorKind.value = null;
    _taxonomy = null;
    _resourceLookup = resourceLookup;
    _isMerged = false;

    // Phase 1: WASM init
    try {
      _client = getDuckDBClient();
      await _client.init();
    } catch (initErr) {
      const msg = String((initErr as Error)?.message ?? initErr);
      errorMessage.value = msg;
      errorKind.value = 'wasm_init';
      state.value = 'error';
      console.warn('[downtime-analysis] DuckDB WASM init failed:', initErr);
      throw initErr;
    }

    // Phase 2: Parquet fetch (two-parquet atomicity, AC-7)
    let baseBuffer: ArrayBuffer;
    let jobsBuffer: ArrayBuffer;
    try {
      [baseBuffer, jobsBuffer] = await Promise.all([
        fetchParquetBuffer(baseSpool),
        fetchParquetBuffer(jobsSpool),
      ]);
    } catch (fetchErr) {
      const msg = String((fetchErr as Error)?.message ?? fetchErr);
      errorMessage.value = `Downtime parquet download failed: ${msg}`;
      errorKind.value = 'fetch';
      state.value = 'error';
      console.warn('[downtime-analysis] Parquet fetch failed:', fetchErr);
      throw new Error(`Downtime parquet download failed: ${msg}`);
    }

    // Phase 3: SQL compute (register → merge → bridge)
    try {
      // Register parquets as DuckDB tables
      await _client.registerParquet('base_events', baseBuffer);
      await _client.registerParquet('job_bridge', jobsBuffer);

      // Run cross-shift merge (must be full dataset per ADR-0003)
      const mergeSQL = CROSS_SHIFT_MERGE_SQL.replace(
        /\{gap_seconds\}/g,
        String(MERGE_GAP_SECONDS)
      );
      await _client.sendQuery(`CREATE OR REPLACE TABLE merged_events AS ${mergeSQL}`);

      // Build category expression and run bridge SQL
      const catExpr = _buildCategoryExpr(taxonomy);
      const bridgeSQL = `
        CREATE OR REPLACE TABLE bridged_events AS
        SELECT
            b.*,
            ${catExpr} AS big_category
        FROM (${JOB_BRIDGE_SQL}) b
      `;
      await _client.sendQuery(bridgeSQL);

      _taxonomy = taxonomy;
      _isMerged = true;
      state.value = 'ready';
    } catch (computeErr) {
      const msg = String((computeErr as Error)?.message ?? computeErr);
      errorMessage.value = msg;
      errorKind.value = 'compute';
      state.value = 'error';
      console.warn('[downtime-analysis] DuckDB compute (merge/bridge) failed:', computeErr);
      throw computeErr;
    }
  }

  /**
   * Query KPI summary: total_hours, udt/sdt/egt breakdown, event_count, avg_event_min.
   * Zero API round-trips after activate().
   */
  async function queryKpi(filters: DowntimeFilters): Promise<KpiResult> {
    _assertReady('queryKpi');
    const { sql: where, params } = buildFilterClause(filters);
    const rawSQL = `
      SELECT
        SUM(hours) AS total_hours,
        SUM(CASE WHEN TRIM(CAST(OLDSTATUSNAME AS VARCHAR)) = 'UDT' THEN hours ELSE 0 END) AS udt_hours,
        SUM(CASE WHEN TRIM(CAST(OLDSTATUSNAME AS VARCHAR)) = 'SDT' THEN hours ELSE 0 END) AS sdt_hours,
        SUM(CASE WHEN TRIM(CAST(OLDSTATUSNAME AS VARCHAR)) = 'EGT' THEN hours ELSE 0 END) AS egt_hours,
        COUNT(*) AS event_count
      FROM bridged_events
      ${where}
    `;
    const sql = interpolateParams(rawSQL, params);
    const rows = await _client!.sendQuery(sql);
    const row = (rows[0] as Record<string, unknown>) ?? {};
    const totalHours = sf(row.total_hours);
    const eventCount = sf(row.event_count);
    return {
      total_hours: Math.round(totalHours * 100) / 100,
      udt_hours: Math.round(sf(row.udt_hours) * 100) / 100,
      sdt_hours: Math.round(sf(row.sdt_hours) * 100) / 100,
      egt_hours: Math.round(sf(row.egt_hours) * 100) / 100,
      event_count: Math.round(eventCount),
      avg_event_min: eventCount > 0 ? Math.round((totalHours / eventCount) * 60 * 10) / 10 : 0,
    };
  }

  /**
   * Query daily trend rows sorted by date.
   */
  async function queryDailyTrend(filters: DowntimeFilters): Promise<DailyTrendRow[]> {
    _assertReady('queryDailyTrend');
    const { sql: where, params } = buildFilterClause(filters);
    const gran = filters.granularity ?? 'day';
    const dateExpr = gran === 'week'
      ? "strftime(date_trunc('week', CAST(event_start AS DATE)), '%G-W%V')"
      : gran === 'month'
        ? "strftime(date_trunc('month', CAST(event_start AS DATE)), '%Y-%m')"
        : "strftime(CAST(event_start AS DATE), '%Y-%m-%d')";
    const rawSQL = `
      SELECT
        ${dateExpr} AS date,
        SUM(CASE WHEN TRIM(CAST(OLDSTATUSNAME AS VARCHAR)) = 'UDT' THEN hours ELSE 0 END) AS udt_hours,
        SUM(CASE WHEN TRIM(CAST(OLDSTATUSNAME AS VARCHAR)) = 'SDT' THEN hours ELSE 0 END) AS sdt_hours,
        SUM(CASE WHEN TRIM(CAST(OLDSTATUSNAME AS VARCHAR)) = 'EGT' THEN hours ELSE 0 END) AS egt_hours,
        SUM(hours) AS total_hours
      FROM bridged_events
      ${where}
      GROUP BY 1
      ORDER BY 1
    `;
    const sql = interpolateParams(rawSQL, params);
    const rows = await _client!.sendQuery(sql);
    return (rows as Record<string, unknown>[]).map((row) => ({
      date: String(row.date ?? ''),
      udt_hours: Math.round(sf(row.udt_hours) * 100) / 100,
      sdt_hours: Math.round(sf(row.sdt_hours) * 100) / 100,
      egt_hours: Math.round(sf(row.egt_hours) * 100) / 100,
      total_hours: Math.round(sf(row.total_hours) * 100) / 100,
    }));
  }

  /**
   * Query BigCategory aggregation with taxonomy-driven category mapping.
   */
  async function queryBigCategory(filters: DowntimeFilters): Promise<BigCategoryRow[]> {
    _assertReady('queryBigCategory');
    const { sql: where, params } = buildFilterClause(filters);
    const rawSQL = `
      SELECT
        big_category AS category,
        SUM(hours)   AS hours,
        COUNT(*)     AS event_count
      FROM bridged_events
      ${where}
      GROUP BY big_category
      ORDER BY hours DESC
    `;
    const sql = interpolateParams(rawSQL, params);
    const rows = await _client!.sendQuery(sql);
    const typedRows = rows as Record<string, unknown>[];

    // Calculate total for pct
    const totalHours = typedRows.reduce((acc, r) => acc + sf(r.hours), 0);

    return typedRows.map((row) => {
      const hours = sf(row.hours);
      return {
        category: String(row.category ?? ''),
        hours: Math.round(hours * 100) / 100,
        event_count: Math.round(sf(row.event_count)),
        pct: totalHours > 0 ? Math.round((hours / totalHours) * 10000) / 100 : 0,
      };
    });
  }

  /**
   * Query top N reasons by total downtime hours.
   * Uses bridged_events which already has big_category applied.
   * ES-1: Called in refreshDuckdbViews so TopReasonsTable is populated in DuckDB mode.
   */
  async function queryTopReasons(filters: DowntimeFilters, limit = 10): Promise<TopReasonRow[]> {
    _assertReady('queryTopReasons');
    const { sql: where, params } = buildFilterClause(filters);
    const rawSQL = `
      SELECT
        COALESCE(NULLIF(TRIM(CAST(OLDREASONNAME AS VARCHAR)), ''), '(無原因)') AS reason,
        TRIM(CAST(OLDSTATUSNAME AS VARCHAR)) AS status,
        big_category,
        SUM(hours)   AS total_hours,
        COUNT(*)     AS event_count,
        CASE WHEN COUNT(*) > 0 THEN SUM(hours) / COUNT(*) * 60.0 ELSE 0 END AS avg_min
      FROM bridged_events
      ${where}
      GROUP BY 1, 2, 3
      ORDER BY total_hours DESC
      LIMIT ${limit}
    `;
    const sql = interpolateParams(rawSQL, params);
    const rows = await _client!.sendQuery(sql);
    return (rows as Record<string, unknown>[]).map((row) => ({
      reason: String(row.reason ?? ''),
      status: String(row.status ?? ''),
      big_category: String(row.big_category ?? ''),
      total_hours: Math.round(sf(row.total_hours) * 100) / 100,
      event_count: Math.round(sf(row.event_count)),
      avg_min: Math.round(sf(row.avg_min) * 10) / 10,
    }));
  }

  /**
   * Query equipment detail table with optional pagination.
   */
  async function queryEquipmentDetail(
    filters: DowntimeFilters,
    page = 1,
    pageSize = 200
  ): Promise<EquipmentDetailResult> {
    _assertReady('queryEquipmentDetail');
    const { sql: where, params } = buildFilterClause(filters);
    const offset = (page - 1) * pageSize;

    // Count total
    const countSQL = interpolateParams(
      `SELECT COUNT(DISTINCT TRIM(CAST(HISTORYID AS VARCHAR))) AS cnt FROM bridged_events ${where}`,
      params
    );
    const countRows = await _client!.sendQuery(countSQL);
    const total = sf((countRows[0] as Record<string, unknown>)?.cnt ?? 0);

    const rawSQL = `
      SELECT
        TRIM(CAST(HISTORYID AS VARCHAR))  AS resource_id,
        SUM(CASE WHEN TRIM(CAST(OLDSTATUSNAME AS VARCHAR)) = 'UDT' THEN hours ELSE 0 END) AS udt_hours,
        SUM(CASE WHEN TRIM(CAST(OLDSTATUSNAME AS VARCHAR)) = 'SDT' THEN hours ELSE 0 END) AS sdt_hours,
        SUM(CASE WHEN TRIM(CAST(OLDSTATUSNAME AS VARCHAR)) = 'EGT' THEN hours ELSE 0 END) AS egt_hours,
        SUM(hours) AS total_hours,
        COUNT(*) AS event_count,
        COUNT(CASE WHEN TRIM(CAST(OLDSTATUSNAME AS VARCHAR)) = 'UDT' THEN 1 END) AS udt_event_count,
        COUNT(CASE WHEN TRIM(CAST(OLDSTATUSNAME AS VARCHAR)) = 'SDT' THEN 1 END) AS sdt_event_count,
        COUNT(CASE WHEN TRIM(CAST(OLDSTATUSNAME AS VARCHAR)) = 'EGT' THEN 1 END) AS egt_event_count
      FROM bridged_events
      ${where}
      GROUP BY TRIM(CAST(HISTORYID AS VARCHAR))
      ORDER BY total_hours DESC
      LIMIT ${pageSize} OFFSET ${offset}
    `;
    const sql = interpolateParams(rawSQL, params);
    const rows = await _client!.sendQuery(sql);
    const data: EquipmentDetailRow[] = (rows as Record<string, unknown>[]).map((row) => {
      const rid = String(row.resource_id ?? '');
      const info = _resourceLookup[rid] ?? {};
      return {
        resource_id: rid,
        resource_name: info.resource_name ?? null,
        workcenter: info.workcenter ?? null,
        family: info.family ?? null,
        udt_hours: Math.round(sf(row.udt_hours) * 100) / 100,
        sdt_hours: Math.round(sf(row.sdt_hours) * 100) / 100,
        egt_hours: Math.round(sf(row.egt_hours) * 100) / 100,
        total_hours: Math.round(sf(row.total_hours) * 100) / 100,
        event_count: Math.round(sf(row.event_count)),
        udt_event_count: Math.round(sf(row.udt_event_count)),
        sdt_event_count: Math.round(sf(row.sdt_event_count)),
        egt_event_count: Math.round(sf(row.egt_event_count)),
      };
    });

    return {
      data,
      total: Math.round(total),
      page,
      page_size: pageSize,
      total_pages: Math.ceil(total / pageSize),
    };
  }

  /**
   * Query event detail table with job enrichment and optional pagination.
   */
  async function queryEventDetail(
    filters: DowntimeFilters,
    page = 1,
    pageSize = 200
  ): Promise<EventDetailResult> {
    _assertReady('queryEventDetail');
    const { sql: where, params } = buildFilterClause(filters);
    const offset = (page - 1) * pageSize;

    // Count total
    const countSQL = interpolateParams(
      `SELECT COUNT(*) AS cnt FROM bridged_events ${where}`,
      params
    );
    const countRows = await _client!.sendQuery(countSQL);
    const total = sf((countRows[0] as Record<string, unknown>)?.cnt ?? 0);

    const rawSQL = `
      SELECT
        TRIM(CAST(HISTORYID AS VARCHAR))                              AS HISTORYID,
        TRIM(CAST(OLDSTATUSNAME AS VARCHAR))                         AS OLDSTATUSNAME,
        OLDREASONNAME,
        big_category,
        STRFTIME(event_start, '%Y-%m-%dT%H:%M:%S')                  AS event_start,
        STRFTIME(event_end,   '%Y-%m-%dT%H:%M:%S')                  AS event_end,
        hours,
        match_source,
        match_ambiguous,
        _matched_jobid,
        SYMPTOMCODENAME,
        CAUSECODENAME,
        REPAIRCODENAME,
        COMPLETE_FULLNAME,
        STRFTIME(FIRSTCLOCKONDATE,  '%Y-%m-%dT%H:%M:%S')            AS FIRSTCLOCKONDATE,
        STRFTIME(LASTCLOCKOFFDATE,  '%Y-%m-%dT%H:%M:%S')            AS LASTCLOCKOFFDATE,
        JOBORDERNAME,
        JOBMODELNAME,
        STRFTIME(ASSIGNED_DATE, '%Y-%m-%dT%H:%M:%S')                AS ASSIGNED_DATE,
        STRFTIME(ACK_DATE,      '%Y-%m-%dT%H:%M:%S')                AS ACK_DATE,
        STRFTIME(INSPECT_START, '%Y-%m-%dT%H:%M:%S')                AS INSPECT_START,
        STRFTIME(INSPECT_END,   '%Y-%m-%dT%H:%M:%S')                AS INSPECT_END,
        STRFTIME(CREATEDATE,    '%Y-%m-%dT%H:%M:%S')                AS CREATEDATE,
        STRFTIME(COMPLETEDATE,  '%Y-%m-%dT%H:%M:%S')                AS COMPLETEDATE
      FROM bridged_events
      ${where}
      ORDER BY HISTORYID, event_start
      LIMIT ${pageSize} OFFSET ${offset}
    `;
    const sql = interpolateParams(rawSQL, params);
    const rows = await _client!.sendQuery(sql);

    const data: EventDetailRow[] = (rows as Record<string, unknown>[]).map((row, idx) => {
      const hasJob = nullableStr(row._matched_jobid) !== null;

      // Derive wait/repair/inspect minutes
      const firstClockOn = row.FIRSTCLOCKONDATE ? new Date(String(row.FIRSTCLOCKONDATE)) : null;
      const lastClockOff = row.LASTCLOCKOFFDATE ? new Date(String(row.LASTCLOCKOFFDATE)) : null;
      const createDate = row.CREATEDATE ? new Date(String(row.CREATEDATE)) : null;
      const completeDate = row.COMPLETEDATE ? new Date(String(row.COMPLETEDATE)) : null;
      const assignedDate = row.ASSIGNED_DATE ? new Date(String(row.ASSIGNED_DATE)) : null;
      const ackDate = row.ACK_DATE ? new Date(String(row.ACK_DATE)) : null;
      const inspectStart = row.INSPECT_START ? new Date(String(row.INSPECT_START)) : null;
      const inspectEnd = row.INSPECT_END ? new Date(String(row.INSPECT_END)) : null;

      function diffMin(end: Date | null, start: Date | null): number | null {
        if (!end || !start) return null;
        const diff = (end.getTime() - start.getTime()) / 60000;
        return diff >= 0 ? Math.round(diff * 100) / 100 : null;
      }

      const job: EventDetailJobEnrichment | null = hasJob
        ? {
            job_id: nullableStr(row._matched_jobid),
            job_order_name: nullableStr(row.JOBORDERNAME),
            job_model: nullableStr(row.JOBMODELNAME),
            symptom: nullableStr(row.SYMPTOMCODENAME),
            cause: nullableStr(row.CAUSECODENAME),
            repair: nullableStr(row.REPAIRCODENAME),
            handler: nullableStr(row.COMPLETE_FULLNAME),
            wait_min: diffMin(firstClockOn, createDate),
            repair_min: diffMin(lastClockOff, firstClockOn),
            wait_assign_min: diffMin(assignedDate, createDate),
            wait_ack_min: diffMin(ackDate, assignedDate),
            inspect_min: diffMin(inspectEnd, inspectStart),
            close_wait_min: diffMin(completeDate, lastClockOff),
            job_create_date: toIsoString(row.CREATEDATE),
            job_complete_date: toIsoString(row.COMPLETEDATE),
            match_ambiguous: Boolean(row.match_ambiguous),
          }
        : null;

      return {
        event_id: `${String(row.HISTORYID ?? '')}_${idx}_${String(row.event_start ?? '')}`,
        resource_id: String(row.HISTORYID ?? ''),
        status: String(row.OLDSTATUSNAME ?? ''),
        reason: nullableStr(row.OLDREASONNAME),
        category: String(row.big_category ?? ''),
        start_ts: toIsoString(row.event_start) ?? '',
        end_ts: toIsoString(row.event_end) ?? '',
        hours: Math.round(sf(row.hours) * 100) / 100,
        match_source: (row.match_source as 'jobid' | 'overlap' | 'none') ?? 'none',
        job,
      };
    });

    return {
      data,
      total: Math.round(total),
      page,
      page_size: pageSize,
      total_pages: Math.ceil(total / pageSize),
    };
  }

  /**
   * Export filtered data as browser-blob CSV (design.md D2).
   * Uses the already-computed bridged_events — guarantees CSV = what user sees.
   * Zero server RAM cost (all computation in-browser).
   *
   * @param filters - same filters applied to the current view
   * @param viewName - 'equipment' or 'event' table
   */
  /**
   * Export filtered data as browser-blob CSV (design.md D2).
   * Returns a Promise that rejects if the DuckDB query or blob download fails (E-3).
   * Caller should handle the rejection and show an error to the user.
   */
  async function exportCsv(filters: DowntimeFilters, viewName: 'equipment' | 'event' = 'event'): Promise<void> {
    if (state.value !== 'ready') {
      console.warn('[downtime-analysis] exportCsv: composable not ready');
      return;
    }
    await _doExportCsv(filters, viewName);
  }

  async function _doExportCsv(filters: DowntimeFilters, viewName: 'equipment' | 'event'): Promise<void> {
    if (viewName === 'equipment') {
      const result = await queryEquipmentDetail(filters, 1, 50000);
      const headers = ['resource_id', 'udt_hours', 'sdt_hours', 'egt_hours', 'total_hours', 'event_count'];
      const csv = rowsToCsv(headers, result.data as unknown as Record<string, unknown>[]);
      downloadCsv(csv, 'downtime_equipment_detail.csv');
    } else {
      const result = await queryEventDetail(filters, 1, 50000);
      const headers = ['event_id', 'resource_id', 'status', 'reason', 'category', 'start_ts', 'end_ts', 'hours', 'match_source'];
      const csv = rowsToCsv(headers, result.data as unknown as Record<string, unknown>[]);
      downloadCsv(csv, 'downtime_event_detail.csv');
    }
    // No catch — let caller handle; rethrow surfaces the error to exportCsv callers (E-3)
  }

  /** Release DuckDB resources and reset to idle state. */
  function deactivate(): void {
    if (_client) {
      _client.destroy();
      _client = null;
    }
    state.value = 'idle';
    errorMessage.value = '';
    errorKind.value = null;
    _taxonomy = null;
    _isMerged = false;
  }

  return {
    state: readonly(state),
    errorMessage: readonly(errorMessage),
    errorKind: readonly(errorKind),
    activate,
    queryKpi,
    queryDailyTrend,
    queryBigCategory,
    queryTopReasons,
    queryEquipmentDetail,
    queryEventDetail,
    exportCsv,
    deactivate,
  };
}
