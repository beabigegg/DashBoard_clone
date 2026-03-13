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
import { getDuckDBClient, fetchParquetBuffer } from '../core/duckdb-client.js';

const TABLE_NAME = 'hold_history_data';

// ── SQL helpers ───────────────────────────────────────────────────────────────

function qs(val) {
  return "'" + String(val ?? '').replace(/'/g, "''") + "'";
}

function qid(name) {
  return '"' + String(name).replace(/"/g, '""') + '"';
}

function sf(val, def = 0) {
  const n = Number(val);
  return isNaN(n) ? def : n;
}

// ── Record-type & hold-type filter conditions ─────────────────────────────────

function buildRecordTypeConditions(recordTypes, startDate, endDate) {
  // recordTypes is an array like ['new'], ['on_hold'], ['new', 'released'], etc.
  const types = new Set((recordTypes || ['new']).map(t => String(t).toLowerCase()));
  const parts = [];

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

function buildHoldTypeCondition(holdType) {
  if (holdType === 'quality') return `${qid('HOLD_TYPE')} = 'quality'`;
  if (holdType === 'non-quality') return `${qid('HOLD_TYPE')} = 'non-quality'`;
  return null; // 'all' — no filter
}

function buildDurationCondition(durationRange) {
  const h = qid('HOLD_HOURS');
  if (durationRange === '<4h')    return `${h} < 4`;
  if (durationRange === '4-24h')  return `${h} >= 4 AND ${h} < 24`;
  if (durationRange === '1-3d')   return `${h} >= 24 AND ${h} < 72`;
  if (durationRange === '>3d')    return `${h} >= 72`;
  return null;
}

function buildBaseConditions({ holdType, recordTypes, startDate, endDate }) {
  const conditions = [`(${buildRecordTypeConditions(recordTypes, startDate, endDate)})`];
  const ht = buildHoldTypeCondition(holdType);
  if (ht) conditions.push(ht);
  return conditions;
}

function buildWhere(conditions) {
  return conditions.length ? 'WHERE ' + conditions.join(' AND ') : '';
}

// ── Trend query ───────────────────────────────────────────────────────────────

async function queryTrend(client, startDate, endDate) {
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
      SUM(CASE WHEN CAST(${qid('HOLD_DAY')} AS DATE) = d.d AND ${qid('IS_FUTURE_HOLD')} = 1 AND ${qid('FUTURE_HOLD_FLAG')} = 1 THEN ${qid('QTY')} ELSE 0 END) AS all_futureHoldQty
    FROM generate_series(DATE ${qs(startDate)}, DATE ${qs(endDate)}, INTERVAL 1 DAY) t(d)
    CROSS JOIN ${TABLE_NAME} f
    GROUP BY d.d
    ORDER BY d.d
  `;
  const rows = await client.sendQuery(sql);
  const days = rows.map(row => ({
    date: String(row.date || ''),
    quality: {
      holdQty: sf(row.quality_holdQty),
      newHoldQty: sf(row.quality_newHoldQty),
      releaseQty: sf(row.quality_releaseQty),
      futureHoldQty: sf(row.quality_futureHoldQty),
    },
    non_quality: {
      holdQty: sf(row.non_quality_holdQty),
      newHoldQty: sf(row.non_quality_newHoldQty),
      releaseQty: sf(row.non_quality_releaseQty),
      futureHoldQty: sf(row.non_quality_futureHoldQty),
    },
    all: {
      holdQty: sf(row.all_holdQty),
      newHoldQty: sf(row.all_newHoldQty),
      releaseQty: sf(row.all_releaseQty),
      futureHoldQty: sf(row.all_futureHoldQty),
    },
  }));
  return { days };
}

// ── Reason pareto query ───────────────────────────────────────────────────────

async function queryReasonPareto(client, baseConditions) {
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
  const rows = await client.sendQuery(sql);
  const total = rows.reduce((sum, r) => sum + sf(r.qty), 0);
  let cumulative = 0;
  const items = rows.map(row => {
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

async function queryDuration(client, baseConditions) {
  const releaseConditions = [...baseConditions, `${qid('RELEASETXNDATE')} IS NOT NULL`];
  const where = buildWhere(releaseConditions);
  const sql = `
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
    ${where}
    GROUP BY range
  `;
  const rows = await client.sendQuery(sql);
  const total = rows.reduce((sum, r) => sum + sf(r.qty), 0);
  // Return in canonical order
  const orderMap = { '<4h': 0, '4-24h': 1, '1-3d': 2, '>3d': 3 };
  rows.sort((a, b) => (orderMap[a.range] ?? 9) - (orderMap[b.range] ?? 9));
  const items = rows.map(row => ({
    range: String(row.range || ''),
    count: sf(row.cnt),
    qty: sf(row.qty),
    pct: total > 0 ? Math.round((sf(row.qty) / total * 100) * 100) / 100 : 0,
  }));
  return { items };
}

// ── Paginated list query ──────────────────────────────────────────────────────

async function queryList(client, baseConditions, { reason, durationRange, page, perPage, wcMapping }) {
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

  const [countRows, itemRows] = await Promise.all([
    client.sendQuery(`SELECT COUNT(*) AS total FROM ${TABLE_NAME} ${where}`),
    client.sendQuery(`
      SELECT
        ${qid('LOT_ID')}, ${qid('PJ_WORKORDER')}, ${qid('PRODUCTNAME')}, ${qid('WORKCENTERNAME')},
        ${qid('HOLDREASONNAME')}, ${qid('QTY')}, ${qid('HOLDTXNDATE')}, ${qid('HOLDEMP')},
        ${qid('HOLDCOMMENTS')}, ${qid('RELEASETXNDATE')}, ${qid('RELEASEEMP')},
        ${qid('RELEASECOMMENTS')}, ${qid('HOLD_HOURS')}, ${qid('NCRID')}, ${qid('FUTUREHOLDCOMMENTS')}
      FROM ${TABLE_NAME}
      ${where}
      ORDER BY ${qid('HOLDTXNDATE')} DESC
      LIMIT ${pp} OFFSET ${offset}
    `),
  ]);

  const total = sf(countRows[0]?.total, 0);
  const totalPages = Math.max(Math.ceil(total / pp), 1);

  const items = itemRows.map(row => {
    const wcName = String(row.WORKCENTERNAME || '').trim();
    const workcenter = wcMapping[wcName] || wcName || null;
    const holdDate = row.HOLDTXNDATE != null ? String(row.HOLDTXNDATE) : null;
    const releaseDate = row.RELEASETXNDATE != null ? String(row.RELEASETXNDATE) : null;
    return {
      lotId: String(row.LOT_ID || '').trim() || null,
      workorder: String(row.PJ_WORKORDER || '').trim() || null,
      product: String(row.PRODUCTNAME || '').trim() || null,
      workcenter,
      holdReason: String(row.HOLDREASONNAME || '').trim() || null,
      qty: sf(row.QTY),
      holdDate,
      holdEmp: String(row.HOLDEMP || '').trim() || null,
      holdComment: String(row.HOLDCOMMENTS || '').trim() || null,
      releaseDate,
      releaseEmp: String(row.RELEASEEMP || '').trim() || null,
      releaseComment: String(row.RELEASECOMMENTS || '').trim() || null,
      holdHours: Math.round(sf(row.HOLD_HOURS) * 100) / 100,
      ncr: String(row.NCRID || '').trim() || null,
      futureHoldComment: String(row.FUTUREHOLDCOMMENTS || '').trim() || null,
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
  let _client = null;
  let _isRegistered = false;
  let _wcMapping = {}; // WORKCENTERNAME → wc_group

  /**
   * Activate local compute mode.
   * @param {string} spoolUrl       - Spool Parquet download URL
   * @param {object} wcMapping      - WORKCENTERNAME → wc_group from server response
   */
  async function activate(spoolUrl, wcMapping) {
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
      error.value = String(err?.message ?? err);
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
   *
   * @param {object} opts
   * @param {string}   opts.startDate      - Query start date (YYYY-MM-DD)
   * @param {string}   opts.endDate        - Query end date (YYYY-MM-DD)
   * @param {string}   opts.holdType       - 'quality' | 'non-quality' | 'all'
   * @param {string[]} opts.recordTypes    - e.g. ['new'] or ['on_hold', 'released']
   * @param {string}   [opts.reason]       - Optional reason filter for list
   * @param {string}   [opts.durationRange]- Optional duration bucket for list
   * @param {number}   [opts.page=1]       - List page
   * @param {number}   [opts.perPage=20]   - List page size
   * @returns {{ trend, reason_pareto, duration, list }}
   */
  async function computeView({
    startDate,
    endDate,
    holdType = 'quality',
    recordTypes = ['new'],
    reason = null,
    durationRange = null,
    page = 1,
    perPage = 20,
  } = {}) {
    if (!_isRegistered || !_client) throw new Error('DuckDB not initialised');

    // Trend: full DF (no record_type/reason/duration — all hold_types)
    const trendPromise = queryTrend(_client, startDate, endDate);

    // Base conditions for pareto, duration, list (record_type + hold_type)
    const baseConditions = buildBaseConditions({ holdType, recordTypes, startDate, endDate });

    const [trend, reasonPareto, duration, list] = await Promise.all([
      trendPromise,
      queryReasonPareto(_client, baseConditions),
      queryDuration(_client, baseConditions),
      queryList(_client, baseConditions, { reason, durationRange, page, perPage, wcMapping: _wcMapping }),
    ]);

    return { trend, reason_pareto: reasonPareto, duration, list };
  }

  /** Tear down local mode and release DuckDB resources. */
  function deactivate() {
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
