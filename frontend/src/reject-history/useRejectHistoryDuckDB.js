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
import { getDuckDBClient, isDuckDBSupported } from '../core/duckdb-client.js';

function getCsrfToken() {
  return document.querySelector('meta[name="csrf-token"]')?.content || '';
}

async function fetchParquetBuffer(url, timeout = 120000) {
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

// ── Constants ──────────────────────────────────────────────────────────────────

const TABLE_NAME = 'reject_data';

// Dimension → column mapping (mirrors dim_to_column in backend)
const DIM_TO_COLUMN = {
  reason: 'LOSSREASONNAME',
  package: 'PRODUCTLINENAME',
  type: 'PJ_TYPE',
};

// ── SQL helpers ───────────────────────────────────────────────────────────────

function qs(val) {
  return "'" + String(val ?? '').replace(/'/g, "''") + "'";
}

function qid(name) {
  return '"' + String(name).replace(/"/g, '""') + '"';
}

function normValueExpr(col) {
  const q = qid(col);
  return `CASE WHEN TRIM(COALESCE(CAST(${q} AS VARCHAR), '')) = '' THEN '(未知)' ELSE TRIM(CAST(${q} AS VARCHAR)) END`;
}

function buildPolicyConditions({ includeExcludedScrap, excludeMaterialScrap, excludePbDiode, excludedReasonCodes = [] }) {
  const conditions = [];

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
      const codeList = excludedReasonCodes.map(c => qs(String(c).toUpperCase())).join(', ');
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

function buildUserConditions({ packages, workcenterGroups, reasons, trendDates, metricFilter }) {
  const conditions = [];

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

function buildWhereClause(conditions) {
  return conditions.length ? 'WHERE ' + conditions.join(' AND ') : '';
}

// ── Sub-view queries ──────────────────────────────────────────────────────────

async function queryAnalyticsRaw(client, baseWhere) {
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
  return client.sendQuery(sql);
}

function buildSummaryFromAnalytics(rows) {
  let movein = 0, rejectTotal = 0, defect = 0, affectedLot = 0, affectedWo = 0;
  for (const r of rows) {
    movein     += Number(r.MOVEIN_QTY || 0);
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

async function queryDetail(client, allConditions, { page, perPage, detailReason, paretoSelections }) {
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
  const total = Number(countRows[0]?.total || 0);

  const p  = Math.max(Number(page || 1), 1);
  const pp = Math.min(Math.max(Number(perPage || 50), 1), 200);
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
  const selectExpr = detailCols.map(c => qid(c)).join(', ');
  const detailSql = `
    SELECT ${selectExpr}
    FROM ${TABLE_NAME}
    ${detailWhere}
    ORDER BY ${qid('TXN_DAY')} DESC, ${qid('WORKCENTER_GROUP')} ASC, ${qid('WORKCENTERNAME')} ASC,
             ${qid('REJECT_TOTAL_QTY')} DESC, ${qid('CONTAINERNAME')} ASC
    LIMIT ${pp} OFFSET ${offset}
  `;
  const rows = await client.sendQuery(detailSql);

  const items = rows.map(row => ({
    TXN_TIME: row.TXN_TIME != null ? String(row.TXN_TIME) : null,
    TXN_DAY: row.TXN_DAY != null ? String(row.TXN_DAY).substring(0, 10) : null,
    TXN_MONTH: row.TXN_MONTH != null ? String(row.TXN_MONTH).trim() : null,
    WORKCENTER_GROUP: row.WORKCENTER_GROUP != null ? String(row.WORKCENTER_GROUP).trim() : null,
    WORKCENTERNAME: row.WORKCENTERNAME != null ? String(row.WORKCENTERNAME).trim() : null,
    SPECNAME: row.SPECNAME != null ? String(row.SPECNAME).trim() : null,
    EQUIPMENTNAME: row.EQUIPMENTNAME != null ? String(row.EQUIPMENTNAME).trim() : null,
    PRODUCTLINENAME: row.PRODUCTLINENAME != null ? String(row.PRODUCTLINENAME).trim() : null,
    PJ_TYPE: row.PJ_TYPE != null ? String(row.PJ_TYPE).trim() : null,
    CONTAINERNAME: row.CONTAINERNAME != null ? String(row.CONTAINERNAME).trim() : null,
    PJ_FUNCTION: row.PJ_FUNCTION != null ? String(row.PJ_FUNCTION).trim() : null,
    PRODUCTNAME: row.PRODUCTNAME != null ? String(row.PRODUCTNAME).trim() : null,
    LOSSREASONNAME: row.LOSSREASONNAME != null ? String(row.LOSSREASONNAME).trim() : null,
    LOSSREASON_CODE: row.LOSSREASON_CODE != null ? String(row.LOSSREASON_CODE).trim() : null,
    REJECTCOMMENT: row.REJECTCOMMENT != null ? String(row.REJECTCOMMENT).trim() : null,
    MOVEIN_QTY: Number(row.MOVEIN_QTY || 0),
    REJECT_QTY: Number(row.REJECT_QTY || 0),
    STANDBY_QTY: Number(row.STANDBY_QTY || 0),
    QTYTOPROCESS_QTY: Number(row.QTYTOPROCESS_QTY || 0),
    INPROCESS_QTY: Number(row.INPROCESS_QTY || 0),
    PROCESSED_QTY: Number(row.PROCESSED_QTY || 0),
    REJECT_TOTAL_QTY: Number(row.REJECT_TOTAL_QTY || 0),
    DEFECT_QTY: Number(row.DEFECT_QTY || 0),
    REJECT_RATE_PCT: +Number(row.REJECT_RATE_PCT || 0).toFixed(4),
    DEFECT_RATE_PCT: +Number(row.DEFECT_RATE_PCT || 0).toFixed(4),
    REJECT_SHARE_PCT: +Number(row.REJECT_SHARE_PCT || 0).toFixed(4),
    AFFECTED_WORKORDER_COUNT: Number(row.AFFECTED_WORKORDER_COUNT || 0),
  }));

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

async function queryBatchPareto(client, baseConditions, { metricMode, paretoScope, paretoSelections }) {
  const metricCol = metricMode === 'defect' ? 'DEFECT_QTY' : 'REJECT_TOTAL_QTY';
  const metricExpr = `COALESCE(${qid(metricCol)}, 0)`;

  const normalizedSelections = {};
  for (const [dim, values] of Object.entries(paretoSelections || {})) {
    if (values?.length && DIM_TO_COLUMN[dim]) {
      normalizedSelections[dim] = values;
    }
  }

  const dimensions = {};
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

    const totalMetric = rows.reduce((sum, r) => sum + Number(r.metric_value || 0), 0);
    let items = [];
    if (totalMetric > 0) {
      let cumulative = 0;
      for (const row of rows) {
        const mv = Number(row.metric_value || 0);
        const pct = +((mv / totalMetric * 100).toFixed(4));
        cumulative = +(cumulative + pct).toFixed(4);
        items.push({
          reason: String(row.dim_value || '(未知)').trim() || '(未知)',
          metric_value: mv,
          MOVEIN_QTY: Number(row.movein_qty || 0),
          REJECT_TOTAL_QTY: Number(row.reject_total_qty || 0),
          DEFECT_QTY: Number(row.defect_qty || 0),
          count: Number(row.lot_count || 0),
          pct,
          cumPct: cumulative,
        });
      }
    }

    // top80 pareto scope
    if (paretoScope === 'top80' && items.length > 0) {
      const top80 = items.filter(item => item.cumPct <= 80.0);
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

async function queryAvailableFilters(client, policyConditions) {
  const policyWhere = buildWhereClause(policyConditions);
  const result = { workcenter_groups: [], packages: [], reasons: [] };

  const wcRows = await client.sendQuery(
    `SELECT DISTINCT TRIM(CAST(${qid('WORKCENTER_GROUP')} AS VARCHAR)) AS v FROM ${TABLE_NAME} ${policyWhere} ORDER BY 1`,
  );
  result.workcenter_groups = [...new Set(wcRows.map(r => String(r.v || '').trim()).filter(Boolean))].sort();

  const pkgRows = await client.sendQuery(
    `SELECT DISTINCT TRIM(CAST(${qid('PRODUCTLINENAME')} AS VARCHAR)) AS v FROM ${TABLE_NAME} ${policyWhere} ORDER BY 1`,
  );
  result.packages = [...new Set(pkgRows.map(r => String(r.v || '').trim()).filter(Boolean))].sort();

  const reasonRows = await client.sendQuery(
    `SELECT DISTINCT TRIM(CAST(${qid('LOSSREASONNAME')} AS VARCHAR)) AS v FROM ${TABLE_NAME} ${policyWhere} ORDER BY 1`,
  );
  result.reasons = [...new Set(reasonRows.map(r => String(r.v || '').trim()).filter(Boolean))].sort();

  return result;
}

// ── Main composable ───────────────────────────────────────────────────────────

export function useRejectHistoryDuckDB() {
  const isActive = ref(false);
  const isLoading = ref(false);
  const error = ref('');
  let _client = null;
  let _isRegistered = false;

  async function activate(spoolUrl) {
    if (!isDuckDBSupported()) {
      throw new Error('DuckDB-WASM not supported in this browser');
    }
    isLoading.value = true;
    error.value = '';
    try {
      _client = getDuckDBClient();
      await _client.init();

      const buffer = await fetchParquetBuffer(spoolUrl);
      await _client.registerParquet(TABLE_NAME, buffer);
      _isRegistered = true;
      isActive.value = true;
    } catch (err) {
      error.value = String(err?.message ?? err);
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
    perPage = 50,
    detailReason = null,
  } = {}) {
    if (!_isRegistered || !_client) throw new Error('DuckDB not initialised');

    const {
      includeExcludedScrap = false,
      excludeMaterialScrap = true,
      excludePbDiode = true,
      excludedReasonCodes = [],
    } = policyFilters;

    const policyConditions = buildPolicyConditions({ includeExcludedScrap, excludeMaterialScrap, excludePbDiode, excludedReasonCodes });
    const userConditions = buildUserConditions({ packages, workcenterGroups, reasons, trendDates, metricFilter });
    const allConditions = [...policyConditions, ...userConditions];
    const baseWhere = buildWhereClause(allConditions);

    const [analyticsRaw, detailResult, paretoResult, availableFilters] = await Promise.all([
      queryAnalyticsRaw(_client, baseWhere),
      queryDetail(_client, allConditions, { page, perPage, detailReason, paretoSelections }),
      queryBatchPareto(_client, [...policyConditions, ...userConditions], { metricMode, paretoScope, paretoSelections }),
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
