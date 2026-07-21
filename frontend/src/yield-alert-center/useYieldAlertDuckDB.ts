/**
 * useYieldAlertDuckDB — DuckDB-WASM composable for yield-alert-center.
 *
 * When the server returns spool_download_url (total_row_count >= 5000),
 * this composable takes over view computation from the server:
 *   1. Download Parquet from spool URL
 *   2. Register into DuckDB-WASM
 *   3. Execute sub-view SQL locally (summary / trend / heatmap / station /
 *      package / alerts)
 *   4. Handle filter / sort / page changes without calling /view API
 *
 * SQL logic mirrors yield_alert_sql_runtime.py exactly.
 */

import { ref, readonly, type Ref } from 'vue';
import { getDuckDBClient, isDuckDBSupported, type DuckDBClient } from '../core/duckdb-client';
import { calcRiskScore, calcRiskLevel, type RiskLevel } from '../core/risk-score';

function getCsrfToken(): string {
  return document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') ?? '';
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

// ── Internal constants ────────────────────────────────────────────────────────

const TABLE_NAME = 'yield_alert_data';

const TX_DEDUP_COLS = [
  'DATE_BUCKET', 'WORKORDER',
  'DEPARTMENT_NAME', 'DEPARTMENT_GROUP', 'PROCESS_CATEGORY',
  'LINE_NAME', 'PACKAGE_NAME', 'TYPE_NAME', 'FUNCTION_NAME', 'OPERATION_TEXT',
];

const DEPT_SEQ_MAP: Record<string, number> = {
  '切割': 0, '焊接_DB': 1, '焊接_WB': 2, '成型': 3, '去膠': 4, '水吹砂': 5,
  '電鍍': 6, '移印': 7, '切彎腳': 8, 'TMTT': 9, '品檢': 10, 'FQC': 11,
};

// ── Internal types ────────────────────────────────────────────────────────────

interface SummaryResult {
  transaction_qty: number;
  scrap_qty: number;
  yield_pct: number;
}

interface TrendItem {
  date_bucket: string;
  transaction_qty: number;
  scrap_qty: number;
  yield_pct: number;
}

interface HeatmapItem {
  station: string;
  station_seq: number;
  date: string;
  transaction_qty: number;
  scrap_qty: number;
  yield_pct: number;
}

interface StationItem {
  station: string;
  station_seq: number;
  transaction_qty: number;
  scrap_qty: number;
  yield_pct: number;
}

interface PackageItem {
  package: string;
  transaction_qty: number;
  scrap_qty: number;
  yield_pct: number;
}

interface AlertItem {
  date_bucket: string;
  workorder: string;
  source_code: string | null;
  reason_code: string;
  reason_name: string;
  department: string;
  process_category: string;
  line: string;
  package: string;
  type: string;
  function: string;
  operation: string;
  transaction_qty: number;
  scrap_qty: number;
  yield_pct: number;
  scrap_rate_pct: number;
  risk_score: number;
  risk_level: RiskLevel;
  match_status: string;
  fallback_reason: null;
  reject_total_qty: number;
}

interface AlertsResult {
  items: AlertItem[];
  pagination: { page: number; per_page: number; total: number; total_pages: number };
  quality: null;
  sort: { sort_by: string; sort_dir: string };
}

interface FilterOptions {
  [key: string]: string[];
}

interface ComputeViewParams {
  filters: Record<string, unknown>;
  granularity: string;
  riskThreshold: number;
  minScrapQty: number;
  sortBy: string;
  sortDir: string;
  page: number;
  perPage: number;
  excludedTokens?: string[];
}

interface WhereParams {
  deptWhere: string;
  reasonWhere: string;
}

interface TrendWhereParams extends WhereParams {
  granularity: string;
}

interface AlertQueryParams {
  fullWhere: string;
  reasonWhere: string;
  riskThreshold: number;
  minScrapQty: number;
  sortBy: string;
  sortDir: string;
  page: number;
  perPage: number;
}

// ── SQL helpers ───────────────────────────────────────────────────────────────

function qs(val: unknown): string {
  // Quote a string value for embedding in SQL (single-quote escape)
  return "'" + String(val ?? '').replace(/'/g, "''") + "'";
}

function qid(name: string): string {
  return '"' + String(name).replace(/"/g, '""') + '"';
}

function granularityExpr(granularity: string, col = 'DATE_BUCKET'): string {
  const c = qid(col);
  switch (granularity) {
    case 'week':  return `strftime(date_trunc('week', CAST(${c} AS DATE)), '%Y-%m-%d')`;
    case 'month': return `strftime(CAST(${c} AS DATE), '%Y-%m')`;
    case 'year':  return `strftime(CAST(${c} AS DATE), '%Y')`;
    default:      return `CAST(${c} AS VARCHAR)`;   // day
  }
}

function buildDimensionWhere(filters: Record<string, unknown>, deptProcOnly = false): string {
  const conditions = [];

  // departments: selections may be canonical DEPARTMENT_GROUP labels OR raw
  // DEPARTMENT_NAME values (workcenter_groups filter-options are sourced from
  // DISTINCT DEPARTMENT_NAME — see queryFilterOptions below, mirroring
  // yield_alert_sql_runtime.py's _query_filter_options). Match either domain
  // directly, or via the DEPARTMENT_NAME -> DEPARTMENT_GROUP mapping already
  // present in this row's own data, so a raw name selection still resolves
  // to the group it actually belongs to.
  const deptValues = (filters.departments || []).filter(v => String(v).trim());
  if (deptValues.length) {
    const inList = deptValues.map(v => qs(v)).join(', ');
    conditions.push(
      `(${qid('DEPARTMENT_GROUP')} IN (${inList}) OR ${qid('DEPARTMENT_GROUP')} IN (` +
      `SELECT DISTINCT ${qid('DEPARTMENT_GROUP')} FROM ${qid(TABLE_NAME)} WHERE ${qid('DEPARTMENT_NAME')} IN (${inList})))`
    );
  }

  const colMap: Record<string, string> = { process_category: 'PROCESS_CATEGORY' };
  if (!deptProcOnly) {
    Object.assign(colMap, {
      lines: 'LINE_NAME', packages: 'PACKAGE_NAME',
      types: 'TYPE_NAME', functions: 'FUNCTION_NAME',
    });
  }
  for (const [key, col] of Object.entries(colMap)) {
    const values = (filters[key] || []).filter(v => String(v).trim());
    if (!values.length) continue;
    const inList = values.map(v => qs(v)).join(', ');
    conditions.push(`${qid(col)} IN (${inList})`);
  }
  return conditions.length ? conditions.join(' AND ') : '';
}

function buildReasonExclusionWhere(excludedTokens: string[] = []): string {
  // Always exclude UNMAPPED_REASON from scrap aggregation; include reversals (SCRAP_QTY < 0)
  const parts = [`${qid('REASON_CODE')} <> 'UNMAPPED_REASON'`];
  if (excludedTokens.length) {
    const inList = excludedTokens.map(t => qs(t.toUpperCase())).join(', ');
    parts.push(`${qid('REASON_CODE')} NOT IN (${inList})`);
    parts.push(`${qid('REASON_RAW_UPPER')} NOT IN (${inList})`);
    parts.push(`${qid('REASON_NAME_UPPER')} NOT IN (${inList})`);
  }
  const excl = parts.join(' AND ');
  return `((${excl}) OR ${qid('SCRAP_QTY')} < 0)`;
}

function sf(val: unknown, def = 0): number {
  const n = Number(val);
  return isNaN(n) ? def : n;
}

// ── Sub-view queries ──────────────────────────────────────────────────────────

async function querySummary(client: DuckDBClient, { deptWhere, reasonWhere }: WhereParams): Promise<SummaryResult> {
  const txDedup = TX_DEDUP_COLS.map(c => qid(c)).join(', ');
  const deptClause = deptWhere ? `WHERE ${deptWhere}` : '';
  const scrapClause = deptWhere
    ? `WHERE ${deptWhere} AND ${reasonWhere}`
    : `WHERE ${reasonWhere}`;

  const sql = `
    SELECT
      (SELECT COALESCE(SUM(TRANSACTION_QTY), 0)
       FROM (
           SELECT SUM(${qid('TRANSACTION_QTY')}) AS TRANSACTION_QTY
           FROM ${qid(TABLE_NAME)}
           ${deptClause}
           GROUP BY ${txDedup}
       )
      ) AS transaction_qty,
      (SELECT COALESCE(SUM(${qid('SCRAP_QTY')}), 0)
       FROM ${qid(TABLE_NAME)}
       ${scrapClause}
      ) AS scrap_qty
  `;
  const rows = await client.sendQuery(sql) as Array<Record<string, unknown>>;
  const tx = sf((rows[0] as Record<string, unknown>)?.transaction_qty);
  const sc = sf((rows[0] as Record<string, unknown>)?.scrap_qty);
  return {
    transaction_qty: Math.round(tx * 10000) / 10000,
    scrap_qty: Math.round(sc * 10000) / 10000,
    yield_pct: tx <= 0 ? 100 : Math.round((1 - sc / tx) * 100 * 10000) / 10000,
  };
}

async function queryTrend(client: DuckDBClient, { granularity, deptWhere, reasonWhere }: TrendWhereParams): Promise<TrendItem[]> {
  const txDedup = TX_DEDUP_COLS.map(c => qid(c)).join(', ');
  const bucket = granularityExpr(granularity);
  const deptClause = deptWhere ? `WHERE ${deptWhere}` : '';
  const scrapClause = deptWhere
    ? `WHERE ${deptWhere} AND ${reasonWhere}`
    : `WHERE ${reasonWhere}`;

  // Step 1: per-station TX (deduped per workorder+station) for each date bucket.
  const txPerStationSql = `
    SELECT ${bucket} AS bucket, ${qid('DEPARTMENT_GROUP')},
           SUM(TRANSACTION_QTY) AS station_tx
    FROM (
        SELECT ${bucket} AS DATE_BUCKET,
               ${qid('DEPARTMENT_GROUP')},
               SUM(${qid('TRANSACTION_QTY')}) AS TRANSACTION_QTY
        FROM ${qid(TABLE_NAME)}
        ${deptClause}
        GROUP BY ${txDedup}
    )
    GROUP BY 1, 2
  `;
  // Step 2: per-station scrap (reason-filtered) for each date bucket.
  const scPerStationSql = `
    SELECT ${bucket} AS bucket, ${qid('DEPARTMENT_GROUP')},
           SUM(${qid('SCRAP_QTY')}) AS station_sc
    FROM ${qid(TABLE_NAME)}
    ${scrapClause}
    GROUP BY 1, 2
  `;
  const [txStRows, scStRows] = await Promise.all([
    client.sendQuery(txPerStationSql) as Promise<Array<Record<string, unknown>>>,
    client.sendQuery(scPerStationSql) as Promise<Array<Record<string, unknown>>>,
  ]);

  // Per-station scrap lookup: "bucket::dept" -> sc
  const scStMap: Record<string, number> = {};
  for (const r of scStRows) scStMap[`${r.bucket}::${r.DEPARTMENT_GROUP}`] = sf(r.station_sc);

  // Aggregate per date: FPY = PRODUCT(per-station yield), Input = SUM(SCRAP) / (1 - FPY)
  type DayAgg = { fpy: number; totalSc: number; totalTx: number };
  const dayMap: Record<string, DayAgg> = {};
  for (const r of txStRows) {
    const b = String(r.bucket);
    const dept = String(r.DEPARTMENT_GROUP ?? '');
    const stTx = sf(r.station_tx);
    const stSc = scStMap[`${b}::${dept}`] ?? 0;
    const stYield = stTx > 0 ? Math.max((stTx - stSc) / stTx, 1e-6) : 1;
    if (!dayMap[b]) dayMap[b] = { fpy: 1, totalSc: 0, totalTx: 0 };
    dayMap[b].fpy *= stYield;
    dayMap[b].totalSc += stSc;
    dayMap[b].totalTx += stTx;
  }

  const buckets = Object.keys(dayMap).sort();
  return buckets.map(b => {
    const { fpy, totalSc, totalTx } = dayMap[b];
    // Multi-station: INPUT = SUM(SCRAP) / (1 - FPY)
    const denom = 1 - fpy;
    const inputQty = denom > 1e-9 ? totalSc / denom : totalTx;
    return {
      date_bucket: b,
      transaction_qty: Math.round(inputQty * 10000) / 10000,
      scrap_qty: Math.round(totalSc * 10000) / 10000,
      yield_pct: Math.round(fpy * 100 * 10000) / 10000,
    };
  });
}

async function queryHeatmap(client: DuckDBClient, { granularity, deptWhere, reasonWhere }: TrendWhereParams): Promise<HeatmapItem[]> {
  const txDedup = TX_DEDUP_COLS.map(c => qid(c)).join(', ');
  const bucket = granularityExpr(granularity);
  const deptClause = deptWhere ? `WHERE ${deptWhere}` : '';
  const scrapClause = deptWhere
    ? `WHERE ${deptWhere} AND ${reasonWhere}`
    : `WHERE ${reasonWhere}`;

  const txSql = `
    SELECT ${bucket} AS bucket, ${qid('DEPARTMENT_GROUP')}, SUM(TRANSACTION_QTY) AS tx_qty
    FROM (
        SELECT ${bucket} AS DATE_BUCKET, ${qid('DEPARTMENT_GROUP')},
               SUM(${qid('TRANSACTION_QTY')}) AS TRANSACTION_QTY
        FROM ${qid(TABLE_NAME)}
        ${deptClause}
        GROUP BY ${txDedup}
    )
    GROUP BY 1, 2
  `;
  const scSql = `
    SELECT ${bucket} AS bucket, ${qid('DEPARTMENT_GROUP')}, SUM(${qid('SCRAP_QTY')}) AS sc_qty
    FROM ${qid(TABLE_NAME)}
    ${scrapClause}
    GROUP BY 1, 2
  `;
  const [txRows, scRows] = await Promise.all([
    client.sendQuery(txSql) as Promise<Array<Record<string, unknown>>>,
    client.sendQuery(scSql) as Promise<Array<Record<string, unknown>>>,
  ]);
  const txMap: Record<string, number> = {};
  for (const r of txRows) txMap[`${r.bucket}::${r.DEPARTMENT_GROUP}`] = sf(r.tx_qty);
  const scMap: Record<string, number> = {};
  for (const r of scRows) scMap[`${r.bucket}::${r.DEPARTMENT_GROUP}`] = sf(r.sc_qty);
  const allKeys = new Set([...Object.keys(txMap), ...Object.keys(scMap)]);
  const result = [];
  for (const key of allKeys) {
    const [b, dept] = key.split('::');
    const tx = txMap[key] ?? 0;
    const sc = scMap[key] ?? 0;
    result.push({
      station: dept || '',
      station_seq: DEPT_SEQ_MAP[dept] ?? 999,
      date: b,
      transaction_qty: Math.round(tx * 10000) / 10000,
      scrap_qty: Math.round(sc * 10000) / 10000,
      yield_pct: tx <= 0 ? 100 : Math.round((1 - sc / tx) * 100 * 10000) / 10000,
    });
  }
  result.sort((a, b) => a.station_seq - b.station_seq || a.date.localeCompare(b.date));
  return result;
}

async function queryStationSummary(client: DuckDBClient, { deptWhere, reasonWhere }: WhereParams): Promise<StationItem[]> {
  const txDedup = TX_DEDUP_COLS.map(c => qid(c)).join(', ');
  const deptClause = deptWhere ? `WHERE ${deptWhere}` : '';
  const scrapClause = deptWhere
    ? `WHERE ${deptWhere} AND ${reasonWhere}`
    : `WHERE ${reasonWhere}`;

  const txSql = `
    SELECT ${qid('DEPARTMENT_GROUP')}, SUM(TRANSACTION_QTY) AS tx_qty
    FROM (
        SELECT ${qid('DEPARTMENT_GROUP')}, SUM(${qid('TRANSACTION_QTY')}) AS TRANSACTION_QTY
        FROM ${qid(TABLE_NAME)}
        ${deptClause}
        GROUP BY ${txDedup}
    ) GROUP BY 1
  `;
  const scSql = `
    SELECT ${qid('DEPARTMENT_GROUP')}, SUM(${qid('SCRAP_QTY')}) AS sc_qty
    FROM ${qid(TABLE_NAME)} ${scrapClause} GROUP BY 1
  `;
  const [txRows, scRows] = await Promise.all([
    client.sendQuery(txSql) as Promise<Array<Record<string, unknown>>>,
    client.sendQuery(scSql) as Promise<Array<Record<string, unknown>>>,
  ]);
  const txMap = Object.fromEntries(txRows.map(r => [String(r.DEPARTMENT_GROUP || ''), sf(r.tx_qty)]));
  const scMap = Object.fromEntries(scRows.map(r => [String(r.DEPARTMENT_GROUP || ''), sf(r.sc_qty)]));
  const depts = new Set([...Object.keys(txMap), ...Object.keys(scMap)]);
  const result = [];
  for (const dept of depts) {
    const tx = txMap[dept] ?? 0;
    const sc = scMap[dept] ?? 0;
    result.push({
      station: dept,
      station_seq: DEPT_SEQ_MAP[dept] ?? 999,
      transaction_qty: Math.round(tx * 10000) / 10000,
      scrap_qty: Math.round(sc * 10000) / 10000,
      yield_pct: tx <= 0 ? 100 : Math.round((1 - sc / tx) * 100 * 10000) / 10000,
    });
  }
  result.sort((a, b) => a.yield_pct - b.yield_pct || a.station_seq - b.station_seq);
  return result;
}

async function queryPackageSummary(client: DuckDBClient, { deptWhere, reasonWhere }: WhereParams): Promise<PackageItem[]> {
  const txDedup = TX_DEDUP_COLS.map(c => qid(c)).join(', ');
  const deptClause = deptWhere ? `WHERE ${deptWhere}` : '';
  const scrapClause = deptWhere
    ? `WHERE ${deptWhere} AND ${reasonWhere}`
    : `WHERE ${reasonWhere}`;

  const txSql = `
    SELECT ${qid('PACKAGE_NAME')}, SUM(TRANSACTION_QTY) AS tx_qty
    FROM (
        SELECT ${qid('PACKAGE_NAME')}, SUM(${qid('TRANSACTION_QTY')}) AS TRANSACTION_QTY
        FROM ${qid(TABLE_NAME)} ${deptClause} GROUP BY ${txDedup}
    ) GROUP BY 1
  `;
  const scSql = `
    SELECT ${qid('PACKAGE_NAME')}, SUM(${qid('SCRAP_QTY')}) AS sc_qty
    FROM ${qid(TABLE_NAME)} ${scrapClause} GROUP BY 1
  `;
  const [txRows, scRows] = await Promise.all([
    client.sendQuery(txSql) as Promise<Array<Record<string, unknown>>>,
    client.sendQuery(scSql) as Promise<Array<Record<string, unknown>>>,
  ]);
  const txMap = Object.fromEntries(txRows.map(r => [String(r.PACKAGE_NAME || ''), sf(r.tx_qty)]));
  const scMap = Object.fromEntries(scRows.map(r => [String(r.PACKAGE_NAME || ''), sf(r.sc_qty)]));
  const pkgs = new Set([...Object.keys(txMap), ...Object.keys(scMap)]);
  const result = [];
  for (const pkg of pkgs) {
    const tx = txMap[pkg] ?? 0;
    const sc = scMap[pkg] ?? 0;
    result.push({
      package: pkg,
      transaction_qty: Math.round(tx * 10000) / 10000,
      scrap_qty: Math.round(sc * 10000) / 10000,
      yield_pct: tx <= 0 ? 100 : Math.round((1 - sc / tx) * 100 * 10000) / 10000,
    });
  }
  result.sort((a, b) => b.scrap_qty - a.scrap_qty || a.yield_pct - b.yield_pct);
  return result;
}

async function queryAlerts(client: DuckDBClient, { fullWhere, reasonWhere, riskThreshold, minScrapQty, sortBy, sortDir, page, perPage }: AlertQueryParams): Promise<AlertsResult> {
  const th = sf(riskThreshold, 98);
  const minSc = sf(minScrapQty, 1);

  const combinedWhere = fullWhere
    ? `WHERE ${fullWhere} AND ${reasonWhere} AND ${qid('SCRAP_QTY')} <> 0`
    : `WHERE ${reasonWhere} AND ${qid('SCRAP_QTY')} <> 0`;

  // tx_lookup WHERE: dimension filters only (no reason exclusion, no SCRAP_QTY filter)
  const txWhere = fullWhere ? `WHERE ${fullWhere}` : '';

  const groupByCols = [
    'DATE_BUCKET', 'WORKORDER', 'SOURCE_CODE', 'REASON_CODE', 'REASON_NAME',
    'DEPARTMENT_GROUP', 'PROCESS_CATEGORY', 'LINE_NAME', 'PACKAGE_NAME',
    'TYPE_NAME', 'FUNCTION_NAME', 'OPERATION_TEXT',
  ].map(c => qid(c)).join(', ');

  const txJoinCols = [
    'DATE_BUCKET', 'WORKORDER',
    'DEPARTMENT_GROUP', 'PROCESS_CATEGORY',
    'LINE_NAME', 'PACKAGE_NAME', 'TYPE_NAME', 'FUNCTION_NAME', 'OPERATION_TEXT',
  ];
  const txGroupBy = txJoinCols.map(c => qid(c)).join(', ');
  const txJoinOn = txJoinCols.map(c => `ag.${qid(c)} IS NOT DISTINCT FROM tx.${qid(c)}`).join(' AND ');

  // Get all alert groups with computed risk score
  // tx_lookup computes TRANSACTION_QTY from ALL rows (including move-only),
  // then joins to scrap-only alert_groups for accurate yield calculation.
  const allSql = `
    WITH tx_lookup AS (
      SELECT
        ${txGroupBy},
        SUM(${qid('TRANSACTION_QTY')}) AS transaction_qty
      FROM ${qid(TABLE_NAME)}
      ${txWhere}
      GROUP BY ${txGroupBy}
    ),
    alert_groups AS (
      SELECT
        ${qid('DATE_BUCKET')},
        ${qid('WORKORDER')},
        ${qid('SOURCE_CODE')},
        ${qid('REASON_CODE')},
        ${qid('REASON_NAME')},
        ${qid('DEPARTMENT_GROUP')},
        ${qid('PROCESS_CATEGORY')},
        ${qid('LINE_NAME')},
        ${qid('PACKAGE_NAME')},
        ${qid('TYPE_NAME')},
        ${qid('FUNCTION_NAME')},
        ${qid('OPERATION_TEXT')},
        SUM(${qid('SCRAP_QTY')}) AS scrap_qty
      FROM ${qid(TABLE_NAME)}
      ${combinedWhere}
      GROUP BY ${groupByCols}
    ),
    alert_with_tx AS (
      SELECT ag.*, COALESCE(tx.transaction_qty, 0) AS transaction_qty
      FROM alert_groups ag
      LEFT JOIN tx_lookup tx ON ${txJoinOn}
    )
    SELECT *,
      CASE WHEN transaction_qty <= 0 THEN 100.0
           ELSE ROUND((1 - scrap_qty / transaction_qty) * 100, 4)
      END AS yield_pct,
      CASE WHEN transaction_qty <= 0 THEN 100.0
           ELSE ROUND((1 - scrap_qty / transaction_qty) * 100, 4)
      END AS yield_pct_raw
    FROM alert_with_tx
    WHERE NOT (
      CASE WHEN transaction_qty <= 0 THEN 100.0
           ELSE ROUND((1 - scrap_qty / transaction_qty) * 100, 4)
      END >= ${th} AND scrap_qty < ${minSc}
    )
  `;

  const allRows = await client.sendQuery(allSql) as Array<Record<string, unknown>>;

  // Apply risk score & level in JS (mirrors backend formula)
  const enriched = allRows.map(r => {
    const tx = sf(r.transaction_qty);
    const sc = sf(r.scrap_qty);
    const yp = tx <= 0 ? 100 : Math.round((1 - sc / tx) * 100 * 10000) / 10000;
    const rs = calcRiskScore(yp, sc, th);
    const rl = calcRiskLevel(yp, sc, th);
    return {
      date_bucket: String(r.DATE_BUCKET || ''),
      workorder: String(r.WORKORDER || '').trim(),
      source_code: r.SOURCE_CODE != null ? String(r.SOURCE_CODE).trim() : null,
      reason_code: String(r.REASON_CODE || '').trim(),
      reason_name: String(r.REASON_NAME || '').trim(),
      department: String(r.DEPARTMENT_GROUP || '(NA)'),
      process_category: String(r.PROCESS_CATEGORY || 'OTHER'),
      line: String(r.LINE_NAME || '(NA)'),
      package: String(r.PACKAGE_NAME || '(NA)'),
      type: String(r.TYPE_NAME || '(NA)'),
      function: String(r.FUNCTION_NAME || '(NA)'),
      operation: String(r.OPERATION_TEXT || '-1'),
      transaction_qty: Math.round(tx * 10000) / 10000,
      scrap_qty: Math.round(sc * 10000) / 10000,
      yield_pct: yp,
      scrap_rate_pct: tx <= 0 ? 0 : Math.round((sc / tx) * 100 * 10000) / 10000,
      risk_score: rs,
      risk_level: rl,
      match_status: 'none',
      fallback_reason: null,
      reject_total_qty: 0,
    };
  });

  // Sort
  const SORT_COL_MAP: Record<string, string> = {
    date_bucket: 'date_bucket', workorder: 'workorder', reason_code: 'reason_code',
    department: 'department', source_code: 'source_code',
    package: 'package', type: 'type', transaction_qty: 'transaction_qty',
    scrap_qty: 'scrap_qty', yield_pct: 'yield_pct', risk_score: 'risk_score',
  };
  const sortField = SORT_COL_MAP[sortBy] || 'date_bucket';
  const dir = sortDir === 'asc' ? 1 : -1;
  enriched.sort((a, b) => {
    const av = (a as Record<string, unknown>)[sortField];
    const bv = (b as Record<string, unknown>)[sortField];
    if (av == null && bv == null) return 0;
    if (av == null) return 1;   // nulls sort last
    if (bv == null) return -1;
    if (typeof av === 'number' && typeof bv === 'number') return dir * (av - bv);
    return dir * String(av).localeCompare(String(bv));
  });

  const total = enriched.length;
  const totalPages = Math.max(1, Math.ceil(total / perPage));
  const normalizedPage = Math.min(Math.max(1, page), totalPages);
  const offset = (normalizedPage - 1) * perPage;
  const items = enriched.slice(offset, offset + perPage);

  return {
    items,
    pagination: { page: normalizedPage, per_page: perPage, total, total_pages: totalPages },
    quality: null,
    sort: { sort_by: sortBy, sort_dir: sortDir },
  };
}

async function queryFilterOptions(client: DuckDBClient): Promise<FilterOptions> {
  const options: FilterOptions = {};
  const colKeyMap = [
    ['lines', 'LINE_NAME'], ['packages', 'PACKAGE_NAME'],
    ['types', 'TYPE_NAME'], ['functions', 'FUNCTION_NAME'],
  ];
  const exclude = new Set(['(NA)', '-1', '']);
  for (const [key, col] of colKeyMap) {
    const sql = `
      SELECT DISTINCT CAST(${qid(col)} AS VARCHAR) AS v
      FROM ${qid(TABLE_NAME)}
      WHERE ${qid(col)} IS NOT NULL ORDER BY 1
    `;
    const rows = await client.sendQuery(sql) as Array<Record<string, unknown>>;
    options[key] = rows.map(r => String(r.v)).filter(v => v.trim() && !exclude.has(v)).sort();
  }
  const pcSql = `
    SELECT DISTINCT CAST(${qid('PROCESS_CATEGORY')} AS VARCHAR) AS v
    FROM ${qid(TABLE_NAME)} WHERE ${qid('PROCESS_CATEGORY')} IS NOT NULL ORDER BY 1
  `;
  const pcRows = await client.sendQuery(pcSql) as Array<Record<string, unknown>>;
  options.process_categories = pcRows.map(r => String(r.v)).filter(v => v && v !== 'OTHER').sort();

  // workcenter_groups: raw DEPARTMENT_NAME distinct values (§3.16.5/§3.16.6) —
  // NOT DEPARTMENT_GROUP (that column feeds the unrelated `departments` filter-apply key
  // via buildDimensionWhere). Mirrors server-side _query_filter_options() for WASM parity.
  const wgSql = `
    SELECT DISTINCT CAST(${qid('DEPARTMENT_NAME')} AS VARCHAR) AS v
    FROM ${qid(TABLE_NAME)}
    WHERE ${qid('DEPARTMENT_NAME')} IS NOT NULL ORDER BY 1
  `;
  const wgRows = await client.sendQuery(wgSql) as Array<Record<string, unknown>>;
  options.workcenter_groups = wgRows.map(r => String(r.v)).filter(v => v.trim() && !exclude.has(v)).sort();

  return options;
}

// ── Main composable ───────────────────────────────────────────────────────────

export function useYieldAlertDuckDB() {
  const isActive: Ref<boolean> = ref(false);
  const isLoading: Ref<boolean> = ref(false);
  const error: Ref<string> = ref('');
  let _client: DuckDBClient | null = null;
  let _isRegistered = false;

  async function activate(spoolUrl: string): Promise<void> {
    if (!isDuckDBSupported()) {
      throw new Error('DuckDB-WASM not supported in this browser');
    }
    isLoading.value = true;
    error.value = '';
    try {
      _client = getDuckDBClient();
      await _client.init();

      // Download Parquet from spool URL
      const buffer = await fetchParquetBuffer(spoolUrl);

      await _client.registerParquet(TABLE_NAME, buffer);
      _isRegistered = true;
      isActive.value = true;
    } catch (err) {
      error.value = String((err as Error)?.message ?? err);
      isActive.value = false;
      throw err;
    } finally {
      isLoading.value = false;
    }
  }

  async function computeView({ filters, granularity, riskThreshold, minScrapQty, sortBy, sortDir, page, perPage, excludedTokens = [] }: ComputeViewParams): Promise<{
    summary: SummaryResult;
    trend: { items: TrendItem[]; granularity: string };
    heatmap: { items: HeatmapItem[]; granularity: string };
    station_summary: { items: StationItem[] };
    package_summary: { items: PackageItem[] };
    alerts: AlertsResult;
    filter_options: FilterOptions;
  }> {
    if (!_isRegistered || !_client) throw new Error('DuckDB not initialised');

    const fullWhere = buildDimensionWhere(filters, false);
    const reasonWhere = buildReasonExclusionWhere(excludedTokens);

    const [summaryResult, trendItems, heatmapItems, stationItems, packageItems, alertsResult, filterOptions] = await Promise.all([
      querySummary(_client, { deptWhere: fullWhere, reasonWhere }),
      queryTrend(_client, { granularity, deptWhere: fullWhere, reasonWhere }),
      queryHeatmap(_client, { granularity, deptWhere: fullWhere, reasonWhere }),
      queryStationSummary(_client, { deptWhere: fullWhere, reasonWhere }),
      queryPackageSummary(_client, { deptWhere: fullWhere, reasonWhere }),
      queryAlerts(_client, { fullWhere, reasonWhere, riskThreshold, minScrapQty, sortBy, sortDir, page, perPage }),
      queryFilterOptions(_client),
    ]);

    return {
      summary: summaryResult,
      trend: { items: trendItems, granularity },
      heatmap: { items: heatmapItems, granularity },
      station_summary: { items: stationItems },
      package_summary: { items: packageItems },
      alerts: alertsResult,
      filter_options: filterOptions,
    };
  }

  function deactivate() {
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
