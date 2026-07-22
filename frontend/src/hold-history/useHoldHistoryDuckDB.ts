/**
 * useHoldHistoryDuckDB — DuckDB-WASM composable for hold-history.
 *
 * When the server returns spool_download_url + workcenter_mapping (row_count >= threshold),
 * this composable takes over view computation:
 *   1. Download Parquet from spool URL
 *   2. Register in DuckDB-WASM as 'hold_history_data' table
 *   3. Compute trend, reason_pareto, duration, and paginated list locally
 *   4. Serve supplementary filter/pagination changes without calling GET /view
 *
 * SQL logic mirrors hold_dataset_cache.py derivation functions.
 */

import { ref, readonly } from 'vue';
import { getDuckDBClient, fetchParquetBuffer, DuckDBClient } from '../core/duckdb-client';

// ── Types ─────────────────────────────────────────────────────────────────────

/** A single day entry in the trend result. */
export interface TrendDayMetrics {
  holdQty: number;
  newHoldQty: number;
  releaseQty: number;
  futureHoldQty: number;
  repeatQualityHoldQty: number;
}

/** Full trend day row. */
export interface TrendDay {
  date: string;
  quality: TrendDayMetrics;
  non_quality: TrendDayMetrics;
  all: TrendDayMetrics;
}

/** Result of the trend query. */
export interface TrendResult {
  days: TrendDay[];
}

/** One item in the reason pareto result. */
export interface ReasonParetoItem {
  reason: string;
  count: number;
  qty: number;
  pct: number;
  cumPct: number;
}

/** Reason pareto query result. */
export interface ReasonParetoResult {
  items: ReasonParetoItem[];
}

/** One bucket in the duration distribution. */
export interface DurationItem {
  range: string;
  count: number;
  qty: number;
  pct: number;
}

/** Duration query result. */
export interface DurationResult {
  items: DurationItem[];
  avgReleasedHours: number;
  avgOnHoldHours: number;
  maxReleasedHours: number;
  maxOnHoldHours: number;
}

/** Pagination metadata for the list result. */
export interface ListPagination {
  page: number;
  perPage: number;
  total: number;
  totalPages: number;
}

/** One hold/release record in the detail list. */
export interface HoldListItem {
  lotId: string | null;
  workorder: string | null;
  product: string | null;
  workcenter: string | null;
  holdReason: string | null;
  qty: number;
  holdDate: string | null;
  holdEmp: string | null;
  holdComment: string | null;
  releaseDate: string | null;
  releaseEmp: string | null;
  releaseComment: string | null;
  holdHours: number;
  ncr: string | null;
  futureHoldComment: string | null;
}

/** Paged list result. */
export interface ListResult {
  items: HoldListItem[];
  pagination: ListPagination;
}

/** Full result from computeView(). */
export interface ComputeViewResult {
  trend: TrendResult;
  reason_pareto: ReasonParetoResult;
  duration: DurationResult;
  list: ListResult;
}

/** Parameters accepted by computeView(). */
export interface ComputeViewParams {
  startDate: string;
  endDate: string;
  holdType?: string;
  recordTypes?: string[];
  reason?: string | null;
  durationRange?: string | null;
  dayFilter?: string | null;
  page?: number;
  perPage?: number;
  sortCol?: string;
  sortDir?: 'asc' | 'desc';
}

// ── Constants ─────────────────────────────────────────────────────────────────

const TABLE_NAME = 'hold_history_data';

// ── SQL helpers ───────────────────────────────────────────────────────────────

function qs(val: unknown): string {
  return "'" + String(val ?? '').replace(/'/g, "''") + "'";
}

function qid(name: string): string {
  return '"' + String(name).replace(/"/g, '""') + '"';
}

function sf(val: unknown, def = 0): number {
  const n = Number(val);
  return isNaN(n) ? def : n;
}

/** Cast unknown[] from sendQuery to an indexable row array. */
function toRows(rows: unknown[]): Record<string, unknown>[] {
  return rows as Record<string, unknown>[];
}

// ── Record-type & hold-type filter conditions ─────────────────────────────────

function buildRecordTypeConditions(
  recordTypes: string[] | undefined,
  startDate: string,
  endDate: string,
): string {
  const types = new Set((recordTypes || ['new']).map((t) => String(t).toLowerCase()));
  const parts: string[] = [];

  if (types.has('new') || types.size === 3) {
    // "new" = HOLD_DAY falls within the query date range
    parts.push(
      `(CAST(${qid('HOLD_DAY')} AS DATE) >= DATE ${qs(startDate)} AND CAST(${qid('HOLD_DAY')} AS DATE) <= DATE ${qs(endDate)})`,
    );
  }
  if (types.has('on_hold')) {
    parts.push(`${qid('RELEASETXNDATE')} IS NULL`);
  }
  if (types.has('released')) {
    parts.push(`${qid('RELEASETXNDATE')} IS NOT NULL`);
  }

  if (!parts.length) return '1=1';
  return parts.join(' OR ');
}

function buildHoldTypeCondition(holdType: string): string | null {
  if (holdType === 'quality') return `${qid('HOLD_TYPE')} = 'quality'`;
  if (holdType === 'non-quality') return `${qid('HOLD_TYPE')} = 'non-quality'`;
  return null; // 'all' — no filter
}

function buildDurationCondition(durationRange: string | null | undefined): string | null {
  const h = qid('HOLD_HOURS');
  if (durationRange === '<4h')   return `${h} < 4`;
  if (durationRange === '4-24h') return `${h} >= 4 AND ${h} < 24`;
  if (durationRange === '1-3d')  return `${h} >= 24 AND ${h} < 72`;
  if (durationRange === '>3d')   return `${h} >= 72`;
  return null;
}

/**
 * Build a WHERE clause fragment for the Daily Trend click-to-filter feature.
 * dayFilter is "YYYY-MM-DD:new" or "YYYY-MM-DD:release"; mirrors the exact
 * column references/predicates queryTrend() uses for newHoldQty/releaseQty
 * so the filtered result matches the bar the user clicked.
 */
export function buildDayFilterCondition(dayFilter: string | null | undefined): string | null {
  if (!dayFilter) return null;
  const parts = String(dayFilter).split(':');
  if (parts.length !== 2) return null;
  const [dayStr, dayType] = parts;
  if (!/^\d{4}-\d{2}-\d{2}$/.test(dayStr)) return null;
  if (dayType === 'new') {
    return `(CAST(${qid('HOLD_DAY')} AS DATE) = DATE ${qs(dayStr)} AND ${qid('RN_HOLD_DAY')} = 1)`;
  }
  if (dayType === 'release') {
    return `CAST(${qid('RELEASE_DAY')} AS DATE) = DATE ${qs(dayStr)}`;
  }
  return null;
}

interface BaseConditionParams {
  holdType: string;
  recordTypes?: string[];
  startDate: string;
  endDate: string;
}

function buildBaseConditions({ holdType, recordTypes, startDate, endDate }: BaseConditionParams): string[] {
  const conditions: string[] = [
    `(${buildRecordTypeConditions(recordTypes, startDate, endDate)})`,
  ];
  const ht = buildHoldTypeCondition(holdType);
  if (ht) conditions.push(ht);
  return conditions;
}

function buildWhere(conditions: string[]): string {
  return conditions.length ? 'WHERE ' + conditions.join(' AND ') : '';
}

// ── Trend query ───────────────────────────────────────────────────────────────

async function queryTrend(
  client: DuckDBClient,
  startDate: string,
  endDate: string,
): Promise<TrendResult> {
  // Use a cross join with date series; compute 3 hold_type variants in one pass.
  // This mirrors _derive_trend() in hold_dataset_cache.py.
  const sql = `
    SELECT
      strftime(d.d, '%Y-%m-%d') AS date,
      SUM(CASE WHEN ${qid('HOLD_TYPE')} = 'quality'     AND CAST(${qid('HOLD_DAY')} AS DATE) <= d.d AND (${qid('RELEASE_DAY')} IS NULL OR CAST(${qid('RELEASE_DAY')} AS DATE) > d.d) THEN ${qid('QTY')} ELSE 0 END) AS quality_holdQty,
      SUM(CASE WHEN ${qid('HOLD_TYPE')} = 'non-quality' AND CAST(${qid('HOLD_DAY')} AS DATE) <= d.d AND (${qid('RELEASE_DAY')} IS NULL OR CAST(${qid('RELEASE_DAY')} AS DATE) > d.d) THEN ${qid('QTY')} ELSE 0 END) AS non_quality_holdQty,
      SUM(CASE WHEN CAST(${qid('HOLD_DAY')} AS DATE) <= d.d AND (${qid('RELEASE_DAY')} IS NULL OR CAST(${qid('RELEASE_DAY')} AS DATE) > d.d) THEN ${qid('QTY')} ELSE 0 END) AS all_holdQty,
      SUM(CASE WHEN ${qid('HOLD_TYPE')} = 'quality'     AND CAST(${qid('HOLD_DAY')} AS DATE) = d.d AND ${qid('RN_HOLD_DAY')} = 1 THEN ${qid('QTY')} ELSE 0 END) AS quality_newHoldQty,
      SUM(CASE WHEN ${qid('HOLD_TYPE')} = 'non-quality' AND CAST(${qid('HOLD_DAY')} AS DATE) = d.d AND ${qid('RN_HOLD_DAY')} = 1 THEN ${qid('QTY')} ELSE 0 END) AS non_quality_newHoldQty,
      SUM(CASE WHEN CAST(${qid('HOLD_DAY')} AS DATE) = d.d AND ${qid('RN_HOLD_DAY')} = 1 THEN ${qid('QTY')} ELSE 0 END) AS all_newHoldQty,
      SUM(CASE WHEN ${qid('HOLD_TYPE')} = 'quality'     AND CAST(${qid('RELEASE_DAY')} AS DATE) = d.d THEN ${qid('QTY')} ELSE 0 END) AS quality_releaseQty,
      SUM(CASE WHEN ${qid('HOLD_TYPE')} = 'non-quality' AND CAST(${qid('RELEASE_DAY')} AS DATE) = d.d THEN ${qid('QTY')} ELSE 0 END) AS non_quality_releaseQty,
      SUM(CASE WHEN CAST(${qid('RELEASE_DAY')} AS DATE) = d.d THEN ${qid('QTY')} ELSE 0 END) AS all_releaseQty,
      SUM(CASE WHEN ${qid('HOLD_TYPE')} = 'quality'     AND CAST(${qid('HOLD_DAY')} AS DATE) = d.d AND ${qid('IS_FUTURE_HOLD')} = 1 AND ${qid('FUTURE_HOLD_FLAG')} = 1 THEN ${qid('QTY')} ELSE 0 END) AS quality_futureHoldQty,
      SUM(CASE WHEN ${qid('HOLD_TYPE')} = 'non-quality' AND CAST(${qid('HOLD_DAY')} AS DATE) = d.d AND ${qid('IS_FUTURE_HOLD')} = 1 AND ${qid('FUTURE_HOLD_FLAG')} = 1 THEN ${qid('QTY')} ELSE 0 END) AS non_quality_futureHoldQty,
      SUM(CASE WHEN CAST(${qid('HOLD_DAY')} AS DATE) = d.d AND ${qid('IS_FUTURE_HOLD')} = 1 AND ${qid('FUTURE_HOLD_FLAG')} = 1 THEN ${qid('QTY')} ELSE 0 END) AS all_futureHoldQty,
      SUM(CASE WHEN ${qid('HOLD_TYPE')} = 'quality' AND CAST(${qid('HOLD_DAY')} AS DATE) = d.d AND ${qid('RN_FUTURE_REASON')} > 1 THEN ${qid('QTY')} ELSE 0 END) AS repeatQualityHoldQty
    FROM generate_series(DATE ${qs(startDate)}, DATE ${qs(endDate)}, INTERVAL 1 DAY) t(d)
    CROSS JOIN ${TABLE_NAME} f
    GROUP BY d.d
    ORDER BY d.d
  `;
  const rows = toRows(await client.sendQuery(sql));
  const days: TrendDay[] = rows.map((row) => ({
    date: String(row.date || ''),
    quality: {
      holdQty: sf(row.quality_holdQty),
      newHoldQty: sf(row.quality_newHoldQty),
      releaseQty: sf(row.quality_releaseQty),
      futureHoldQty: sf(row.quality_futureHoldQty),
      repeatQualityHoldQty: sf(row.repeatQualityHoldQty),
    },
    non_quality: {
      holdQty: sf(row.non_quality_holdQty),
      newHoldQty: sf(row.non_quality_newHoldQty),
      releaseQty: sf(row.non_quality_releaseQty),
      futureHoldQty: sf(row.non_quality_futureHoldQty),
      repeatQualityHoldQty: 0,
    },
    all: {
      holdQty: sf(row.all_holdQty),
      newHoldQty: sf(row.all_newHoldQty),
      releaseQty: sf(row.all_releaseQty),
      futureHoldQty: sf(row.all_futureHoldQty),
      repeatQualityHoldQty: sf(row.repeatQualityHoldQty),
    },
  }));
  return { days };
}

// ── Reason pareto query ───────────────────────────────────────────────────────

async function queryReasonPareto(
  client: DuckDBClient,
  baseConditions: string[],
): Promise<ReasonParetoResult> {
  const where = buildWhere(baseConditions);
  const sql = `
    SELECT
      COALESCE(TRIM(CAST(${qid('HOLDREASONNAME')} AS VARCHAR)), '') AS reason,
      COUNT(*) AS cnt,
      SUM(COALESCE(${qid('QTY')}, 0)) AS qty
    FROM ${TABLE_NAME}
    ${where}
    GROUP BY reason
    HAVING SUM(COALESCE(${qid('QTY')}, 0)) > 0
    ORDER BY qty DESC
  `;
  const rows = toRows(await client.sendQuery(sql));
  const total = rows.reduce((sum, r) => sum + sf(r.qty), 0);
  let cumulative = 0;
  const items: ReasonParetoItem[] = rows.map((row) => {
    const qty = sf(row.qty);
    const pct = total > 0 ? Math.round((qty / total * 100) * 100) / 100 : 0;
    cumulative = Math.round((cumulative + pct) * 100) / 100;
    return {
      reason: String(row.reason || '').trim() || '(未填寫)',
      count: sf(row.cnt),
      qty,
      pct,
      cumPct: cumulative,
    };
  });
  return { items };
}

// ── Duration distribution query ───────────────────────────────────────────────

async function queryDuration(
  client: DuckDBClient,
  baseConditions: string[],
): Promise<DurationResult> {
  const bucketConditions = [...baseConditions, `${qid('RELEASETXNDATE')} IS NOT NULL`];
  const bucketWhere = buildWhere(bucketConditions);
  const bucketSql = `
    SELECT
      CASE
        WHEN ${qid('HOLD_HOURS')} < 4  THEN '<4h'
        WHEN ${qid('HOLD_HOURS')} < 24 THEN '4-24h'
        WHEN ${qid('HOLD_HOURS')} < 72 THEN '1-3d'
        ELSE '>3d'
      END AS range,
      COUNT(*) AS cnt,
      SUM(COALESCE(${qid('QTY')}, 0)) AS qty
    FROM ${TABLE_NAME}
    ${bucketWhere}
    GROUP BY range
  `;

  const releasedConditions = [...baseConditions, `${qid('RELEASETXNDATE')} IS NOT NULL`];
  const releasedWhere = buildWhere(releasedConditions);
  const releasedSql = `
    SELECT
      ROUND(AVG(${qid('HOLD_HOURS')}), 2) AS avg_released_hours,
      ROUND(MAX(${qid('HOLD_HOURS')}), 2) AS max_released_hours
    FROM ${TABLE_NAME}
    ${releasedWhere}
  `;

  const onHoldConditions = [...baseConditions, `${qid('RELEASETXNDATE')} IS NULL`];
  const onHoldWhere = buildWhere(onHoldConditions);
  const onHoldSql = `
    SELECT
      ROUND(AVG(${qid('HOLD_HOURS')}), 2) AS avg_on_hold_hours,
      ROUND(MAX(${qid('HOLD_HOURS')}), 2) AS max_on_hold_hours
    FROM ${TABLE_NAME}
    ${onHoldWhere}
  `;

  const [rawRows, rawReleasedRows, rawOnHoldRows] = await Promise.all([
    client.sendQuery(bucketSql),
    client.sendQuery(releasedSql),
    client.sendQuery(onHoldSql),
  ]);
  const rows = toRows(rawRows);
  const releasedRows = toRows(rawReleasedRows);
  const onHoldRows = toRows(rawOnHoldRows);

  const total = rows.reduce((sum, r) => sum + sf(r.qty), 0);
  const orderMap: Record<string, number> = { '<4h': 0, '4-24h': 1, '1-3d': 2, '>3d': 3 };
  rows.sort((a, b) => (orderMap[String(a.range)] ?? 9) - (orderMap[String(b.range)] ?? 9));
  const items: DurationItem[] = rows.map((row) => ({
    range: String(row.range || ''),
    count: sf(row.cnt),
    qty: sf(row.qty),
    pct: total > 0 ? Math.round((sf(row.qty) / total * 100) * 100) / 100 : 0,
  }));

  const rel = releasedRows[0] || {};
  const oh = onHoldRows[0] || {};

  return {
    items,
    avgReleasedHours: Math.round(sf(rel.avg_released_hours) * 100) / 100,
    avgOnHoldHours: Math.round(sf(oh.avg_on_hold_hours) * 100) / 100,
    maxReleasedHours: Math.round(sf(rel.max_released_hours) * 100) / 100,
    maxOnHoldHours: Math.round(sf(oh.max_on_hold_hours) * 100) / 100,
  };
}

// ── Paginated list query ──────────────────────────────────────────────────────

// Column whitelist: frontend camelCase → DuckDB column name
const SORT_COL_WHITELIST: Record<string, string> = {
  lotId: 'LOT_ID',
  workorder: 'PJ_WORKORDER',
  product: 'PRODUCTNAME',
  package: 'PACKAGE',
  workcenter: 'WORKCENTERNAME',
  holdReason: 'HOLDREASONNAME',
  qty: 'QTY',
  holdDate: 'HOLDTXNDATE',
  holdEmp: 'HOLDEMP',
  holdComment: 'HOLDCOMMENTS',
  releaseDate: 'RELEASETXNDATE',
  releaseEmp: 'RELEASEEMP',
  releaseComment: 'RELEASECOMMENTS',
  holdHours: 'HOLD_HOURS',
  ncr: 'NCRID',
  futureHoldComment: 'FUTUREHOLDCOMMENTS',
};

interface QueryListParams {
  reason?: string | null;
  durationRange?: string | null;
  page: number;
  perPage: number;
  wcMapping: Record<string, string>;
  sortCol?: string;
  sortDir?: 'asc' | 'desc';
}

async function queryList(
  client: DuckDBClient,
  baseConditions: string[],
  { reason, durationRange, page, perPage, wcMapping, sortCol, sortDir }: QueryListParams,
): Promise<ListResult> {
  const listConditions = [...baseConditions];

  if (reason) {
    listConditions.push(`TRIM(CAST(${qid('HOLDREASONNAME')} AS VARCHAR)) = ${qs(reason.trim())}`);
  }
  const dur = buildDurationCondition(durationRange);
  if (dur) listConditions.push(dur);

  const where = buildWhere(listConditions);

  const p = Math.max(Number(page || 1), 1);
  const pp = Math.min(Math.max(Number(perPage || 20), 1), 200);
  const offset = (p - 1) * pp;

  const [rawCountRows, rawItemRows] = await Promise.all([
    client.sendQuery(`SELECT COUNT(*) AS total FROM ${TABLE_NAME} ${where}`),
    client.sendQuery(`
      SELECT
        ${qid('LOT_ID')}, ${qid('PJ_WORKORDER')}, ${qid('PRODUCTNAME')}, ${qid('WORKCENTERNAME')},
        ${qid('HOLDREASONNAME')}, ${qid('QTY')}, ${qid('HOLDTXNDATE')}, ${qid('HOLDEMP')},
        ${qid('HOLDCOMMENTS')}, ${qid('RELEASETXNDATE')}, ${qid('RELEASEEMP')},
        ${qid('RELEASECOMMENTS')}, ${qid('HOLD_HOURS')}, ${qid('NCRID')}, ${qid('FUTUREHOLDCOMMENTS')}
      FROM ${TABLE_NAME}
      ${where}
      ORDER BY ${qid(SORT_COL_WHITELIST[sortCol ?? ''] ?? 'HOLDTXNDATE')} ${(sortDir ?? 'desc').toUpperCase() === 'ASC' ? 'ASC' : 'DESC'}
      LIMIT ${pp} OFFSET ${offset}
    `),
  ]);
  const countRows = toRows(rawCountRows);
  const itemRows = toRows(rawItemRows);

  const total = sf(countRows[0]?.total, 0);
  const totalPages = Math.max(Math.ceil(total / pp), 1);

  const items: HoldListItem[] = itemRows.map((row) => {
    const r = row;
    const wcName = String(r.WORKCENTERNAME || '').trim();
    const workcenter = wcMapping[wcName] || wcName || null;
    const holdDate = r.HOLDTXNDATE != null ? String(r.HOLDTXNDATE) : null;
    const releaseDate = r.RELEASETXNDATE != null ? String(r.RELEASETXNDATE) : null;
    return {
      lotId: String(r.LOT_ID || '').trim() || null,
      workorder: String(r.PJ_WORKORDER || '').trim() || null,
      product: String(r.PRODUCTNAME || '').trim() || null,
      workcenter,
      holdReason: String(r.HOLDREASONNAME || '').trim() || null,
      qty: sf(r.QTY),
      holdDate,
      holdEmp: String(r.HOLDEMP || '').trim() || null,
      holdComment: String(r.HOLDCOMMENTS || '').trim() || null,
      releaseDate,
      releaseEmp: String(r.RELEASEEMP || '').trim() || null,
      releaseComment: String(r.RELEASECOMMENTS || '').trim() || null,
      holdHours: Math.round(sf(r.HOLD_HOURS) * 100) / 100,
      ncr: String(r.NCRID || '').trim() || null,
      futureHoldComment: String(r.FUTUREHOLDCOMMENTS || '').trim() || null,
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

// ── Main composable ───────────────────────────────────────────────────────────

export function useHoldHistoryDuckDB() {
  const isActive = ref(false);
  const isLoading = ref(false);
  const error = ref('');
  let _client: DuckDBClient | null = null;
  let _isRegistered = false;
  let _wcMapping: Record<string, string> = {}; // WORKCENTERNAME → wc_group

  /**
   * Activate local compute mode.
   * @param spoolUrl - Spool Parquet download URL
   * @param wcMapping - WORKCENTERNAME → wc_group from server response
   */
  async function activate(spoolUrl: string, wcMapping: Record<string, string>): Promise<void> {
    isLoading.value = true;
    error.value = '';
    try {
      _client = getDuckDBClient();
      await _client.init();
      const buffer = await fetchParquetBuffer(spoolUrl);
      await _client.registerParquet(TABLE_NAME, buffer);
      _wcMapping = wcMapping || {};
      _isRegistered = true;
      isActive.value = true;
    } catch (err) {
      const e = err as Error;
      error.value = String(e?.message ?? err);
      isActive.value = false;
      console.warn('[hold-history] DuckDB activation failed:', err);
      throw err;
    } finally {
      isLoading.value = false;
    }
  }

  /**
   * Compute all views locally (mirrors hold_dataset_cache.py derivation).
   * Trend is always full-range; pareto/duration/list apply holdType + recordType filters.
   */
  async function computeView({
    startDate,
    endDate,
    holdType = 'quality',
    recordTypes = ['new'],
    reason = null,
    durationRange = null,
    dayFilter = null,
    page = 1,
    perPage = 20,
    sortCol,
    sortDir,
  }: ComputeViewParams): Promise<ComputeViewResult> {
    if (!_isRegistered || !_client) throw new Error('DuckDB not initialised');

    // Trend: full DF (no record_type/reason/duration/day filter — all hold_types, full range)
    const trendPromise = queryTrend(_client, startDate, endDate);

    // Base conditions for pareto, duration, list (record_type + hold_type)
    const baseConditions = buildBaseConditions({ holdType, recordTypes, startDate, endDate });

    // Daily Trend click-to-filter: additive day condition for pareto/list only
    // (never trend — it's the source of the bars being clicked; never duration — out of scope)
    const dayCond = buildDayFilterCondition(dayFilter);
    const conditionsWithDay = dayCond ? [...baseConditions, dayCond] : baseConditions;

    const [trend, reasonPareto, duration, list] = await Promise.all([
      trendPromise,
      queryReasonPareto(_client, conditionsWithDay),
      queryDuration(_client, baseConditions),
      queryList(_client, conditionsWithDay, {
        reason,
        durationRange,
        page,
        perPage,
        wcMapping: _wcMapping,
        sortCol,
        sortDir,
      }),
    ]);

    return { trend, reason_pareto: reasonPareto, duration, list };
  }

  /** Tear down local mode and release DuckDB resources. */
  function deactivate(): void {
    if (_client) {
      _client.destroy();
      _client = null;
    }
    isActive.value = false;
    isLoading.value = false;
    _isRegistered = false;
    _wcMapping = {};
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
