/**
 * useRejectHistoryDuckDB — DuckDB-WASM composable for reject-history.
 *
 * When the server returns spool_download_url (total_row_count >= 5000),
 * this composable takes over view computation from the server:
 *   1. Download Parquet from spool URL
 *   2. Register into DuckDB-WASM as 'reject_data' table
 *   3. Execute sub-view SQL locally (analytics_raw / summary / detail / batch_pareto)
 *   4. Handle filter / sort / page changes without calling /view API
 *
 * SQL logic mirrors reject_cache_sql_runtime.py.
 */

import { ref, readonly } from 'vue';
import { getDuckDBClient, isDuckDBSupported } from '../core/duckdb-client';

// ── Types ─────────────────────────────────────────────────────────────────────

/** Raw row returned from the DuckDB analytics_raw sub-view query. */
export interface AnalyticsRawRow {
  bucket_date: string;
  reason: string;
  MOVEIN_QTY: number;
  REJECT_TOTAL_QTY: number;
  DEFECT_QTY: number;
  AFFECTED_LOT_COUNT: number;
  AFFECTED_WORKORDER_COUNT: number;
}

/** Aggregated summary across all analytics_raw rows. */
export interface SummaryData {
  MOVEIN_QTY: number;
  REJECT_TOTAL_QTY: number;
  DEFECT_QTY: number;
  REJECT_RATE_PCT: number;
  DEFECT_RATE_PCT: number;
  REJECT_SHARE_PCT: number;
  AFFECTED_LOT_COUNT: number;
  AFFECTED_WORKORDER_COUNT: number;
}

/** One row from the detail (lot-level) query result. */
export interface DetailRow {
  TXN_TIME: string | null;
  TXN_DAY: string | null;
  TXN_MONTH: string | null;
  WORKCENTER_GROUP: string | null;
  WORKCENTERNAME: string | null;
  SPECNAME: string | null;
  EQUIPMENTNAME: string | null;
  PRODUCTLINENAME: string | null;
  PJ_TYPE: string | null;
  CONTAINERNAME: string | null;
  PJ_FUNCTION: string | null;
  PRODUCTNAME: string | null;
  LOSSREASONNAME: string | null;
  LOSSREASON_CODE: string | null;
  REJECTCOMMENT: string | null;
  MOVEIN_QTY: number;
  REJECT_QTY: number;
  STANDBY_QTY: number;
  QTYTOPROCESS_QTY: number;
  INPROCESS_QTY: number;
  PROCESSED_QTY: number;
  REJECT_TOTAL_QTY: number;
  DEFECT_QTY: number;
  REJECT_RATE_PCT: number;
  DEFECT_RATE_PCT: number;
  REJECT_SHARE_PCT: number;
  AFFECTED_WORKORDER_COUNT: number;
}

/** Pagination metadata returned alongside detail items. */
export interface DetailPagination {
  page: number;
  perPage: number;
  total: number;
  totalPages: number;
}

/** Paged detail result. */
export interface DetailResult {
  items: DetailRow[];
  pagination: DetailPagination;
}

/** One item in a Pareto dimension result. */
export interface ParetoItem {
  reason: string;
  metric_value: number;
  MOVEIN_QTY: number;
  REJECT_TOTAL_QTY: number;
  DEFECT_QTY: number;
  count: number;
  pct: number;
  cumPct: number;
}

/** One Pareto dimension aggregate (reason / package / type). */
export interface ParetoDimension {
  items: ParetoItem[];
  dimension: string;
  metric_mode: string;
}

/** All three Pareto dimensions combined. */
export interface BatchParetoResult {
  dimensions: Record<string, ParetoDimension>;
  metric_mode: string;
  pareto_scope: string;
  pareto_display_scope: string;
}

/** Available filter options returned after policy conditions are applied. */
export interface AvailableFilters {
  workcenter_groups: string[];
  packages: string[];
  reasons: string[];
}

/** Full result object from computeView(). */
export interface ComputeViewResult {
  analytics_raw: AnalyticsRawRow[];
  summary: SummaryData;
  detail: DetailResult;
  batch_pareto: BatchParetoResult;
  available_filters: AvailableFilters;
}

/** Policy-level filter flags (mirrors backend reject_cache_sql_runtime.py). */
export interface PolicyFilters {
  includeExcludedScrap?: boolean;
  excludeMaterialScrap?: boolean;
  excludePbDiode?: boolean;
  excludedReasonCodes?: string[];
}

/** Cross-dimension Pareto selections (dimension → selected value list). */
export type ParetoSelections = Record<string, string[]>;

/** Parameters accepted by computeView(). */
export interface ComputeViewParams {
  policyFilters?: PolicyFilters;
  packages?: string[];
  workcenterGroups?: string[];
  reasons?: string[];
  trendDates?: string[];
  metricFilter?: string;
  metricMode?: string;
  paretoScope?: string;
  paretoSelections?: ParetoSelections;
  page?: number;
  perPage?: number;
  detailReason?: string | null;
}

/**
 * Minimal interface for the DuckDB-WASM client object returned by getDuckDBClient().
 * The client originates from core/duckdb-client (JS, not yet migrated to TS).
 */
interface DuckDBClient {
  init(): Promise<void>;
  registerParquet(tableName: string, buffer: ArrayBuffer): Promise<void>;
  sendQuery(sql: string): Promise<Record<string, unknown>[]>;
  destroy(): void;
}

// ── Constants ──────────────────────────────────────────────────────────────────

const TABLE_NAME = 'reject_data';

/** Dimension → column mapping (mirrors dim_to_column in backend). */
const DIM_TO_COLUMN: Record<string, string> = {
  reason: 'LOSSREASONNAME',
  package: 'PRODUCTLINENAME',
  type: 'PJ_TYPE',
};

// ── Helper functions ───────────────────────────────────────────────────────────

function getCsrfToken(): string {
  // TODO: type — querySelector returns Element | null; content is only on HTMLMetaElement
  const meta = document.querySelector('meta[name="csrf-token"]') as HTMLMetaElement | null;
  return meta?.content ?? '';
}

async function fetchParquetBuffer(url: string, timeout = 120000): Promise<ArrayBuffer> {
  const controller = new AbortController();
  const timerId = setTimeout(() => controller.abort(), timeout);
  try {
    const resp = await fetch(url, {
      method: 'GET',
      headers: { 'X-CSRF-Token': getCsrfToken() },
      signal: controller.signal,
    });
    if (!resp.ok) throw new Error(`Spool download failed: HTTP ${resp.status}`);
    return await resp.arrayBuffer();
  } finally {
    clearTimeout(timerId);
  }
}

// ── SQL helpers ───────────────────────────────────────────────────────────────

function qs(val: unknown): string {
  return "'" + String(val ?? '').replace(/'/g, "''") + "'";
}

function qid(name: string): string {
  return '"' + String(name).replace(/"/g, '""') + '"';
}

function normValueExpr(col: string): string {
  const q = qid(col);
  return `CASE WHEN TRIM(COALESCE(CAST(${q} AS VARCHAR), '')) = '' THEN '(未知)' ELSE TRIM(CAST(${q} AS VARCHAR)) END`;
}

interface PolicyConditionParams {
  includeExcludedScrap: boolean;
  excludeMaterialScrap: boolean;
  excludePbDiode: boolean;
  excludedReasonCodes: string[];
}

function buildPolicyConditions({
  includeExcludedScrap,
  excludeMaterialScrap,
  excludePbDiode,
  excludedReasonCodes,
}: PolicyConditionParams): string[] {
  const conditions: string[] = [];

  if (excludeMaterialScrap) {
    conditions.push(
      `UPPER(TRIM(COALESCE(CAST(${qid('SCRAP_OBJECTTYPE')} AS VARCHAR), ''))) <> 'MATERIAL'`,
    );
  }

  if (excludePbDiode) {
    conditions.push(
      `NOT regexp_matches(UPPER(TRIM(COALESCE(CAST(${qid('PRODUCTLINENAME')} AS VARCHAR), ''))), '^PB_')`,
    );
  }

  if (!includeExcludedScrap) {
    if (excludedReasonCodes.length > 0) {
      const codeList = excludedReasonCodes.map((c) => qs(String(c).toUpperCase())).join(', ');
      conditions.push(
        `UPPER(TRIM(COALESCE(CAST(${qid('LOSSREASON_CODE')} AS VARCHAR), ''))) NOT IN (${codeList})`,
      );
      conditions.push(
        `UPPER(TRIM(COALESCE(CAST(${qid('LOSSREASONNAME')} AS VARCHAR), ''))) NOT IN (${codeList})`,
      );
    }
    // Pattern: LOSSREASONNAME must start with 3 digits + underscore
    const nameExpr = `UPPER(TRIM(COALESCE(CAST(${qid('LOSSREASONNAME')} AS VARCHAR), '')))`;
    conditions.push(`regexp_matches(${nameExpr}, '^[0-9]{3}_')`);
    conditions.push(`NOT regexp_matches(${nameExpr}, '^(XXX|ZZZ)_')`);
  }

  return conditions;
}

interface UserConditionParams {
  packages: string[];
  workcenterGroups: string[];
  reasons: string[];
  trendDates: string[];
  metricFilter: string;
}

function buildUserConditions({
  packages,
  workcenterGroups,
  reasons,
  trendDates,
  metricFilter,
}: UserConditionParams): string[] {
  const conditions: string[] = [];

  if (packages?.length) {
    const inList = packages.map(qs).join(', ');
    conditions.push(`${normValueExpr('PRODUCTLINENAME')} IN (${inList})`);
  }

  if (workcenterGroups?.length) {
    const inList = workcenterGroups.map(qs).join(', ');
    conditions.push(`${normValueExpr('WORKCENTER_GROUP')} IN (${inList})`);
  }

  if (reasons?.length) {
    const inList = reasons.map(qs).join(', ');
    conditions.push(`${normValueExpr('LOSSREASONNAME')} IN (${inList})`);
  }

  if (trendDates?.length) {
    const inList = trendDates.map(qs).join(', ');
    conditions.push(`strftime(CAST(${qid('TXN_DAY')} AS DATE), '%Y-%m-%d') IN (${inList})`);
  }

  if (metricFilter === 'reject') {
    conditions.push(`COALESCE(${qid('REJECT_TOTAL_QTY')}, 0) > 0`);
  } else if (metricFilter === 'defect') {
    conditions.push(`COALESCE(${qid('DEFECT_QTY')}, 0) > 0`);
  }

  return conditions;
}

function buildWhereClause(conditions: string[]): string {
  return conditions.length ? 'WHERE ' + conditions.join(' AND ') : '';
}

// ── Sub-view queries ──────────────────────────────────────────────────────────

async function queryAnalyticsRaw(client: DuckDBClient, baseWhere: string): Promise<AnalyticsRawRow[]> {
  const sql = `
    SELECT
      strftime(CAST(${qid('TXN_DAY')} AS DATE), '%Y-%m-%d') AS bucket_date,
      CASE WHEN TRIM(COALESCE(CAST(${qid('LOSSREASONNAME')} AS VARCHAR), '')) = ''
           THEN '(未填寫)'
           ELSE TRIM(CAST(${qid('LOSSREASONNAME')} AS VARCHAR))
      END AS reason,
      SUM(COALESCE(${qid('MOVEIN_QTY')}, 0)) AS MOVEIN_QTY,
      SUM(COALESCE(${qid('REJECT_TOTAL_QTY')}, 0)) AS REJECT_TOTAL_QTY,
      SUM(COALESCE(${qid('DEFECT_QTY')}, 0)) AS DEFECT_QTY,
      COUNT(DISTINCT ${qid('CONTAINERID')}) AS AFFECTED_LOT_COUNT,
      SUM(COALESCE(${qid('AFFECTED_WORKORDER_COUNT')}, 0)) AS AFFECTED_WORKORDER_COUNT
    FROM ${TABLE_NAME}
    ${baseWhere}
    GROUP BY 1, 2
    ORDER BY 1, 2
  `;
  const rows = await client.sendQuery(sql);
  return rows as unknown as AnalyticsRawRow[];
}

function buildSummaryFromAnalytics(rows: AnalyticsRawRow[]): SummaryData {
  let movein = 0, rejectTotal = 0, defect = 0, affectedLot = 0, affectedWo = 0;
  for (const r of rows) {
    movein      += Number(r.MOVEIN_QTY || 0);
    rejectTotal += Number(r.REJECT_TOTAL_QTY || 0);
    defect      += Number(r.DEFECT_QTY || 0);
    affectedLot += Number(r.AFFECTED_LOT_COUNT || 0);
    affectedWo  += Number(r.AFFECTED_WORKORDER_COUNT || 0);
  }
  const totalScrap = rejectTotal + defect;
  return {
    MOVEIN_QTY: movein,
    REJECT_TOTAL_QTY: rejectTotal,
    DEFECT_QTY: defect,
    REJECT_RATE_PCT: movein ? +((rejectTotal / movein * 100).toFixed(4)) : 0,
    DEFECT_RATE_PCT: movein ? +((defect / movein * 100).toFixed(4)) : 0,
    REJECT_SHARE_PCT: totalScrap ? +((rejectTotal / totalScrap * 100).toFixed(4)) : 0,
    AFFECTED_LOT_COUNT: affectedLot,
    AFFECTED_WORKORDER_COUNT: affectedWo,
  };
}

interface QueryDetailParams {
  page: number;
  perPage: number;
  detailReason: string | null;
  paretoSelections: ParetoSelections;
}

async function queryDetail(
  client: DuckDBClient,
  allConditions: string[],
  { page, perPage, detailReason, paretoSelections }: QueryDetailParams,
): Promise<DetailResult> {
  const detailConditions = [...allConditions];

  if (detailReason) {
    detailConditions.push(`${normValueExpr('LOSSREASONNAME')} = ${qs(detailReason)}`);
  }

  // Apply cross-dimension pareto selections to detail filter
  for (const [dim, values] of Object.entries(paretoSelections || {})) {
    if (!values?.length) continue;
    const dimCol = DIM_TO_COLUMN[dim];
    if (!dimCol) continue;
    const inList = values.map(qs).join(', ');
    detailConditions.push(`${normValueExpr(dimCol)} IN (${inList})`);
  }

  const detailWhere = buildWhereClause(detailConditions);

  const countRows = await client.sendQuery(
    `SELECT COUNT(*) AS total FROM ${TABLE_NAME} ${detailWhere}`,
  );
  const total = Number((countRows[0] as Record<string, unknown>)?.total || 0);

  const p  = Math.max(Number(page || 1), 1);
  const pp = Math.min(Math.max(Number(perPage || 20), 1), 200);
  const totalPages = Math.max(Math.ceil(total / pp), 1);
  const offset = (p - 1) * pp;

  const detailCols = [
    'TXN_TIME', 'TXN_DAY', 'TXN_MONTH', 'WORKCENTER_GROUP', 'WORKCENTERNAME',
    'SPECNAME', 'EQUIPMENTNAME', 'PRODUCTLINENAME', 'PJ_TYPE', 'CONTAINERNAME',
    'PJ_FUNCTION', 'PRODUCTNAME', 'LOSSREASONNAME', 'LOSSREASON_CODE', 'REJECTCOMMENT',
    'MOVEIN_QTY', 'REJECT_QTY', 'STANDBY_QTY', 'QTYTOPROCESS_QTY', 'INPROCESS_QTY',
    'PROCESSED_QTY', 'REJECT_TOTAL_QTY', 'DEFECT_QTY', 'REJECT_RATE_PCT',
    'DEFECT_RATE_PCT', 'REJECT_SHARE_PCT', 'AFFECTED_WORKORDER_COUNT',
  ];
  const selectExpr = detailCols.map((c) => qid(c)).join(', ');
  const detailSql = `
    SELECT ${selectExpr}
    FROM ${TABLE_NAME}
    ${detailWhere}
    ORDER BY ${qid('TXN_DAY')} DESC, ${qid('WORKCENTER_GROUP')} ASC, ${qid('WORKCENTERNAME')} ASC,
             ${qid('REJECT_TOTAL_QTY')} DESC, ${qid('CONTAINERNAME')} ASC
    LIMIT ${pp} OFFSET ${offset}
  `;
  const rows = await client.sendQuery(detailSql);

  const items: DetailRow[] = rows.map((row) => {
    const r = row as Record<string, unknown>;
    return {
      TXN_TIME:       r.TXN_TIME  != null ? String(r.TXN_TIME)  : null,
      TXN_DAY:        r.TXN_DAY   != null ? String(r.TXN_DAY).substring(0, 10) : null,
      TXN_MONTH:      r.TXN_MONTH != null ? String(r.TXN_MONTH).trim() : null,
      WORKCENTER_GROUP:  r.WORKCENTER_GROUP  != null ? String(r.WORKCENTER_GROUP).trim() : null,
      WORKCENTERNAME:    r.WORKCENTERNAME    != null ? String(r.WORKCENTERNAME).trim() : null,
      SPECNAME:          r.SPECNAME          != null ? String(r.SPECNAME).trim() : null,
      EQUIPMENTNAME:     r.EQUIPMENTNAME     != null ? String(r.EQUIPMENTNAME).trim() : null,
      PRODUCTLINENAME:   r.PRODUCTLINENAME   != null ? String(r.PRODUCTLINENAME).trim() : null,
      PJ_TYPE:           r.PJ_TYPE           != null ? String(r.PJ_TYPE).trim() : null,
      CONTAINERNAME:     r.CONTAINERNAME     != null ? String(r.CONTAINERNAME).trim() : null,
      PJ_FUNCTION:       r.PJ_FUNCTION       != null ? String(r.PJ_FUNCTION).trim() : null,
      PRODUCTNAME:       r.PRODUCTNAME       != null ? String(r.PRODUCTNAME).trim() : null,
      LOSSREASONNAME:    r.LOSSREASONNAME    != null ? String(r.LOSSREASONNAME).trim() : null,
      LOSSREASON_CODE:   r.LOSSREASON_CODE   != null ? String(r.LOSSREASON_CODE).trim() : null,
      REJECTCOMMENT:     r.REJECTCOMMENT     != null ? String(r.REJECTCOMMENT).trim() : null,
      MOVEIN_QTY:              Number(r.MOVEIN_QTY || 0),
      REJECT_QTY:              Number(r.REJECT_QTY || 0),
      STANDBY_QTY:             Number(r.STANDBY_QTY || 0),
      QTYTOPROCESS_QTY:        Number(r.QTYTOPROCESS_QTY || 0),
      INPROCESS_QTY:           Number(r.INPROCESS_QTY || 0),
      PROCESSED_QTY:           Number(r.PROCESSED_QTY || 0),
      REJECT_TOTAL_QTY:        Number(r.REJECT_TOTAL_QTY || 0),
      DEFECT_QTY:              Number(r.DEFECT_QTY || 0),
      REJECT_RATE_PCT:         +Number(r.REJECT_RATE_PCT || 0).toFixed(4),
      DEFECT_RATE_PCT:         +Number(r.DEFECT_RATE_PCT || 0).toFixed(4),
      REJECT_SHARE_PCT:        +Number(r.REJECT_SHARE_PCT || 0).toFixed(4),
      AFFECTED_WORKORDER_COUNT: Number(r.AFFECTED_WORKORDER_COUNT || 0),
    };
  });

  return {
    items,
    pagination: {
      page: total === 0 ? 1 : p,
      perPage: pp,
      total,
      totalPages,
    },
  };
}

interface QueryBatchParetoParams {
  metricMode: string;
  paretoScope: string;
  paretoSelections: ParetoSelections;
}

async function queryBatchPareto(
  client: DuckDBClient,
  baseConditions: string[],
  { metricMode, paretoScope, paretoSelections }: QueryBatchParetoParams,
): Promise<BatchParetoResult> {
  const metricCol = metricMode === 'defect' ? 'DEFECT_QTY' : 'REJECT_TOTAL_QTY';
  const metricExpr = `COALESCE(${qid(metricCol)}, 0)`;

  const normalizedSelections: ParetoSelections = {};
  for (const [dim, values] of Object.entries(paretoSelections || {})) {
    if (values?.length && DIM_TO_COLUMN[dim]) {
      normalizedSelections[dim] = values;
    }
  }

  const dimensions: Record<string, ParetoDimension> = {};
  for (const [dimension, dimCol] of Object.entries(DIM_TO_COLUMN)) {
    const conditions = [...baseConditions];

    // Cross-dimension pareto selections (exclude current dimension)
    for (const [otherDim, values] of Object.entries(normalizedSelections)) {
      if (otherDim === dimension || !values?.length) continue;
      const otherCol = DIM_TO_COLUMN[otherDim];
      if (!otherCol) continue;
      const inList = values.map(qs).join(', ');
      conditions.push(`${normValueExpr(otherCol)} IN (${inList})`);
    }

    const whereClause = buildWhereClause(conditions);
    const sql = `
      SELECT
        ${normValueExpr(dimCol)} AS dim_value,
        SUM(COALESCE(${qid('MOVEIN_QTY')}, 0)) AS movein_qty,
        SUM(COALESCE(${qid('REJECT_TOTAL_QTY')}, 0)) AS reject_total_qty,
        SUM(COALESCE(${qid('DEFECT_QTY')}, 0)) AS defect_qty,
        COUNT(DISTINCT ${qid('CONTAINERID')}) AS lot_count,
        SUM(${metricExpr}) AS metric_value
      FROM ${TABLE_NAME}
      ${whereClause}
      GROUP BY 1
      HAVING SUM(${metricExpr}) > 0
      ORDER BY metric_value DESC
    `;
    const rows = await client.sendQuery(sql);

    const totalMetric = rows.reduce(
      (sum, r) => sum + Number((r as Record<string, unknown>).metric_value || 0),
      0,
    );
    let items: ParetoItem[] = [];
    if (totalMetric > 0) {
      let cumulative = 0;
      for (const row of rows) {
        const r = row as Record<string, unknown>;
        const mv = Number(r.metric_value || 0);
        const pct = +((mv / totalMetric * 100).toFixed(4));
        cumulative = +(cumulative + pct).toFixed(4);
        items.push({
          reason: String(r.dim_value || '(未知)').trim() || '(未知)',
          metric_value: mv,
          MOVEIN_QTY: Number(r.movein_qty || 0),
          REJECT_TOTAL_QTY: Number(r.reject_total_qty || 0),
          DEFECT_QTY: Number(r.defect_qty || 0),
          count: Number(r.lot_count || 0),
          pct,
          cumPct: cumulative,
        });
      }
    }

    // top80 pareto scope
    if (paretoScope === 'top80' && items.length > 0) {
      const top80 = items.filter((item) => item.cumPct <= 80.0);
      items = top80.length > 0 ? top80 : [items[0]];
    }

    // top20 display limit
    items = items.slice(0, 20);

    const apiMetricMode = metricMode === 'defect' ? 'defect' : 'reject_total';
    dimensions[dimension] = { items, dimension, metric_mode: apiMetricMode };
  }

  const apiMetricMode = metricMode === 'defect' ? 'defect' : 'reject_total';
  return {
    dimensions,
    metric_mode: apiMetricMode,
    pareto_scope: paretoScope,
    pareto_display_scope: 'top20',
  };
}

async function queryAvailableFilters(
  client: DuckDBClient,
  policyConditions: string[],
): Promise<AvailableFilters> {
  const policyWhere = buildWhereClause(policyConditions);
  const result: AvailableFilters = { workcenter_groups: [], packages: [], reasons: [] };

  const wcRows = await client.sendQuery(
    `SELECT DISTINCT TRIM(CAST(${qid('WORKCENTER_GROUP')} AS VARCHAR)) AS v FROM ${TABLE_NAME} ${policyWhere} ORDER BY 1`,
  );
  result.workcenter_groups = [
    ...new Set(wcRows.map((r) => String((r as Record<string, unknown>).v || '').trim()).filter(Boolean)),
  ].sort();

  const pkgRows = await client.sendQuery(
    `SELECT DISTINCT TRIM(CAST(${qid('PRODUCTLINENAME')} AS VARCHAR)) AS v FROM ${TABLE_NAME} ${policyWhere} ORDER BY 1`,
  );
  result.packages = [
    ...new Set(pkgRows.map((r) => String((r as Record<string, unknown>).v || '').trim()).filter(Boolean)),
  ].sort();

  const reasonRows = await client.sendQuery(
    `SELECT DISTINCT TRIM(CAST(${qid('LOSSREASONNAME')} AS VARCHAR)) AS v FROM ${TABLE_NAME} ${policyWhere} ORDER BY 1`,
  );
  result.reasons = [
    ...new Set(reasonRows.map((r) => String((r as Record<string, unknown>).v || '').trim()).filter(Boolean)),
  ].sort();

  return result;
}

// ── Main composable ───────────────────────────────────────────────────────────

export function useRejectHistoryDuckDB() {
  const isActive = ref(false);
  const isLoading = ref(false);
  const error = ref('');
  let _client: DuckDBClient | null = null;
  let _isRegistered = false;

  async function activate(spoolUrl: string): Promise<void> {
    if (!isDuckDBSupported()) {
      throw new Error('DuckDB-WASM not supported in this browser');
    }
    isLoading.value = true;
    error.value = '';
    try {
      // TODO: type — getDuckDBClient() returns a JS object; cast via DuckDBClient interface
      _client = getDuckDBClient() as DuckDBClient;
      await _client.init();

      const buffer = await fetchParquetBuffer(spoolUrl);
      await _client.registerParquet(TABLE_NAME, buffer);
      _isRegistered = true;
      isActive.value = true;
    } catch (err) {
      const e = err as Error;
      error.value = String(e?.message ?? err);
      isActive.value = false;
      throw err;
    } finally {
      isLoading.value = false;
    }
  }

  async function computeView({
    policyFilters = {},
    packages = [],
    workcenterGroups = [],
    reasons = [],
    trendDates = [],
    metricFilter = 'all',
    metricMode = 'reject_total',
    paretoScope = 'top80',
    paretoSelections = {},
    page = 1,
    perPage = 20,
    detailReason = null,
  }: ComputeViewParams = {}): Promise<ComputeViewResult> {
    if (!_isRegistered || !_client) throw new Error('DuckDB not initialised');

    const {
      includeExcludedScrap = false,
      excludeMaterialScrap = true,
      excludePbDiode = true,
      excludedReasonCodes = [],
    } = policyFilters;

    const policyConditions = buildPolicyConditions({
      includeExcludedScrap,
      excludeMaterialScrap,
      excludePbDiode,
      excludedReasonCodes,
    });
    const userConditions = buildUserConditions({
      packages,
      workcenterGroups,
      reasons,
      trendDates,
      metricFilter,
    });
    const allConditions = [...policyConditions, ...userConditions];
    const baseWhere = buildWhereClause(allConditions);

    const [analyticsRaw, detailResult, paretoResult, availableFilters] = await Promise.all([
      queryAnalyticsRaw(_client, baseWhere),
      queryDetail(_client, allConditions, {
        page,
        perPage,
        detailReason: detailReason ?? null,
        paretoSelections,
      }),
      queryBatchPareto(_client, [...policyConditions, ...userConditions], {
        metricMode,
        paretoScope,
        paretoSelections,
      }),
      queryAvailableFilters(_client, policyConditions),
    ]);

    return {
      analytics_raw: analyticsRaw,
      summary: buildSummaryFromAnalytics(analyticsRaw),
      detail: detailResult,
      batch_pareto: paretoResult,
      available_filters: availableFilters,
    };
  }

  function deactivate(): void {
    if (_client) {
      _client.destroy();
      _client = null;
    }
    isActive.value = false;
    isLoading.value = false;
    _isRegistered = false;
  }

  return {
    isActive: readonly(isActive),
    isLoading: readonly(isLoading),
    error: readonly(error),
    activate,
    computeView,
    deactivate,
  };
}
