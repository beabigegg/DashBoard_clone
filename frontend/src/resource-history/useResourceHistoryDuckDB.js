/**
 * useResourceHistoryDuckDB — DuckDB-WASM composable for resource-history.
 *
 * When the server returns spool_download_url + resource_metadata (row_count >= threshold),
 * this composable takes over view computation:
 *   1. Download Parquet from spool URL
 *   2. Register in DuckDB-WASM as 'resource_history_data' table
 *   3. Compute KPI, trend, heatmap, workcenter comparison, and detail locally
 *   4. Serve supplementary filter/granularity changes without calling GET /view
 *
 * SQL logic mirrors resource_dataset_cache.py derivation functions.
 */

import { ref, readonly } from 'vue';
import { getDuckDBClient, fetchParquetBuffer } from '../core/duckdb-client.js';

const TABLE_NAME = 'resource_history_data';

// ── SQL helpers ───────────────────────────────────────────────────────────────

function qid(name) {
  return '"' + String(name).replace(/"/g, '""') + '"';
}

function granularityExpr(col) {
  // Returns a SQL expression that truncates the date column to the given granularity.
  // Returns a closure so it can be used at query time.
  return (granularity) => {
    const q = qid(col);
    switch (granularity) {
      case 'year':  return `strftime(CAST(${q} AS DATE), '%Y')`;
      case 'month': return `strftime(CAST(${q} AS DATE), '%Y-%m')`;
      case 'week':  return `strftime(date_trunc('week', CAST(${q} AS DATE)), '%Y-%m-%d')`;
      default:      return `strftime(CAST(${q} AS DATE), '%Y-%m-%d')`;
    }
  };
}

const datePeriod = granularityExpr('DATA_DATE');

// ── KPI calculations (mirrors Python) ─────────────────────────────────────────

function sf(val, def = 0) {
  const n = Number(val);
  return isNaN(n) ? def : n;
}

function calcOuPct(prd, sby, udt, sdt, egt) {
  const denom = prd + sby + udt + sdt + egt;
  return denom > 0 ? Math.round((prd / denom) * 1000) / 10 : 0;
}

function calcAvailPct(prd, sby, udt, sdt, egt, nst) {
  const num = prd + sby + egt;
  const denom = prd + sby + egt + sdt + udt + nst;
  return denom > 0 ? Math.round((num / denom) * 1000) / 10 : 0;
}

function statusPct(val, total) {
  return total > 0 ? Math.round((val / total) * 1000) / 10 : 0;
}

function buildKpiFromRow(row) {
  const prd = sf(row.prd_hours);
  const sby = sf(row.sby_hours);
  const udt = sf(row.udt_hours);
  const sdt = sf(row.sdt_hours);
  const egt = sf(row.egt_hours);
  const nst = sf(row.nst_hours);
  const total = prd + sby + udt + sdt + egt + nst;
  return {
    ou_pct: calcOuPct(prd, sby, udt, sdt, egt),
    availability_pct: calcAvailPct(prd, sby, udt, sdt, egt, nst),
    prd_hours: Math.round(prd * 10) / 10,
    prd_pct: statusPct(prd, total),
    sby_hours: Math.round(sby * 10) / 10,
    sby_pct: statusPct(sby, total),
    udt_hours: Math.round(udt * 10) / 10,
    udt_pct: statusPct(udt, total),
    sdt_hours: Math.round(sdt * 10) / 10,
    sdt_pct: statusPct(sdt, total),
    egt_hours: Math.round(egt * 10) / 10,
    egt_pct: statusPct(egt, total),
    nst_hours: Math.round(nst * 10) / 10,
    nst_pct: statusPct(nst, total),
    machine_count: sf(row.machine_count, 0),
  };
}

function emptyKpi() {
  return {
    ou_pct: 0, availability_pct: 0,
    prd_hours: 0, prd_pct: 0,
    sby_hours: 0, sby_pct: 0,
    udt_hours: 0, udt_pct: 0,
    sdt_hours: 0, sdt_pct: 0,
    egt_hours: 0, egt_pct: 0,
    nst_hours: 0, nst_pct: 0,
    machine_count: 0,
  };
}

// ── Sub-view queries ──────────────────────────────────────────────────────────

async function queryKpi(client) {
  const sql = `
    SELECT
      SUM(COALESCE(${qid('PRD_HOURS')}, 0)) AS prd_hours,
      SUM(COALESCE(${qid('SBY_HOURS')}, 0)) AS sby_hours,
      SUM(COALESCE(${qid('UDT_HOURS')}, 0)) AS udt_hours,
      SUM(COALESCE(${qid('SDT_HOURS')}, 0)) AS sdt_hours,
      SUM(COALESCE(${qid('EGT_HOURS')}, 0)) AS egt_hours,
      SUM(COALESCE(${qid('NST_HOURS')}, 0)) AS nst_hours,
      COUNT(DISTINCT ${qid('HISTORYID')}) AS machine_count
    FROM ${TABLE_NAME}
  `;
  const rows = await client.sendQuery(sql);
  if (!rows.length) return emptyKpi();
  return buildKpiFromRow(rows[0]);
}

async function queryTrend(client, granularity) {
  const period = datePeriod(granularity);
  const sql = `
    SELECT
      ${period} AS period,
      SUM(COALESCE(${qid('PRD_HOURS')}, 0)) AS prd_hours,
      SUM(COALESCE(${qid('SBY_HOURS')}, 0)) AS sby_hours,
      SUM(COALESCE(${qid('UDT_HOURS')}, 0)) AS udt_hours,
      SUM(COALESCE(${qid('SDT_HOURS')}, 0)) AS sdt_hours,
      SUM(COALESCE(${qid('EGT_HOURS')}, 0)) AS egt_hours,
      SUM(COALESCE(${qid('NST_HOURS')}, 0)) AS nst_hours
    FROM ${TABLE_NAME}
    GROUP BY 1
    ORDER BY 1
  `;
  const rows = await client.sendQuery(sql);
  return rows.map(row => {
    const prd = sf(row.prd_hours);
    const sby = sf(row.sby_hours);
    const udt = sf(row.udt_hours);
    const sdt = sf(row.sdt_hours);
    const egt = sf(row.egt_hours);
    const nst = sf(row.nst_hours);
    return {
      date: String(row.period || ''),
      ou_pct: calcOuPct(prd, sby, udt, sdt, egt),
      availability_pct: calcAvailPct(prd, sby, udt, sdt, egt, nst),
      prd_hours: Math.round(prd * 10) / 10,
      sby_hours: Math.round(sby * 10) / 10,
      udt_hours: Math.round(udt * 10) / 10,
      sdt_hours: Math.round(sdt * 10) / 10,
      egt_hours: Math.round(egt * 10) / 10,
      nst_hours: Math.round(nst * 10) / 10,
    };
  });
}

async function queryByHistoryId(client) {
  // Aggregate by HISTORYID for heatmap, comparison, and detail derivation
  const sql = `
    SELECT
      ${qid('HISTORYID')} AS historyid,
      SUM(COALESCE(${qid('PRD_HOURS')}, 0)) AS prd_hours,
      SUM(COALESCE(${qid('SBY_HOURS')}, 0)) AS sby_hours,
      SUM(COALESCE(${qid('UDT_HOURS')}, 0)) AS udt_hours,
      SUM(COALESCE(${qid('SDT_HOURS')}, 0)) AS sdt_hours,
      SUM(COALESCE(${qid('EGT_HOURS')}, 0)) AS egt_hours,
      SUM(COALESCE(${qid('NST_HOURS')}, 0)) AS nst_hours,
      SUM(COALESCE(${qid('TOTAL_HOURS')}, 0)) AS total_hours
    FROM ${TABLE_NAME}
    GROUP BY ${qid('HISTORYID')}
  `;
  return client.sendQuery(sql);
}

async function queryByHistoryIdAndDate(client, granularity) {
  // Used for heatmap: HISTORYID × period → hours
  const period = datePeriod(granularity);
  const sql = `
    SELECT
      ${qid('HISTORYID')} AS historyid,
      ${period} AS period,
      SUM(COALESCE(${qid('PRD_HOURS')}, 0)) AS prd_hours,
      SUM(COALESCE(${qid('SBY_HOURS')}, 0)) AS sby_hours,
      SUM(COALESCE(${qid('UDT_HOURS')}, 0)) AS udt_hours,
      SUM(COALESCE(${qid('SDT_HOURS')}, 0)) AS sdt_hours,
      SUM(COALESCE(${qid('EGT_HOURS')}, 0)) AS egt_hours
    FROM ${TABLE_NAME}
    GROUP BY ${qid('HISTORYID')}, 2
    ORDER BY ${qid('HISTORYID')}, 2
  `;
  return client.sendQuery(sql);
}

// ── Derivation from raw query rows + resource_metadata ───────────────────────

function deriveHeatmap(heatmapRows, resourceMetadata) {
  // Aggregate by workcenter_group × period
  const wcSeqMap = {};
  const agg = {}; // key: "wc|period"

  for (const row of heatmapRows) {
    const meta = resourceMetadata[String(row.historyid || '')] || {};
    const wc = meta.workcenter || '';
    if (!wc) continue;
    const wcSeq = Number(meta.workcenter_seq ?? 999);
    wcSeqMap[wc] = wcSeq;

    const period = String(row.period || '');
    const key = `${wc}||${period}`;
    if (!agg[key]) agg[key] = { wc, period, prd: 0, sby: 0, udt: 0, sdt: 0, egt: 0 };
    agg[key].prd += sf(row.prd_hours);
    agg[key].sby += sf(row.sby_hours);
    agg[key].udt += sf(row.udt_hours);
    agg[key].sdt += sf(row.sdt_hours);
    agg[key].egt += sf(row.egt_hours);
  }

  const items = Object.values(agg).map(a => ({
    workcenter: a.wc,
    workcenter_seq: wcSeqMap[a.wc] ?? 999,
    date: a.period,
    ou_pct: calcOuPct(a.prd, a.sby, a.udt, a.sdt, a.egt),
  }));

  items.sort((a, b) =>
    a.workcenter_seq - b.workcenter_seq || (a.date < b.date ? -1 : a.date > b.date ? 1 : 0)
  );
  return items;
}

function deriveComparison(byHistoryRows, resourceMetadata) {
  const agg = {}; // wc_group → { prd, sby, udt, sdt, egt, mc }
  for (const row of byHistoryRows) {
    const meta = resourceMetadata[String(row.historyid || '')] || {};
    const wc = meta.workcenter || '';
    if (!wc) continue;
    if (!agg[wc]) agg[wc] = { prd: 0, sby: 0, udt: 0, sdt: 0, egt: 0, mc: 0 };
    agg[wc].prd += sf(row.prd_hours);
    agg[wc].sby += sf(row.sby_hours);
    agg[wc].udt += sf(row.udt_hours);
    agg[wc].sdt += sf(row.sdt_hours);
    agg[wc].egt += sf(row.egt_hours);
    agg[wc].mc += 1;
  }
  const items = Object.entries(agg).map(([wc, d]) => ({
    workcenter: wc,
    ou_pct: calcOuPct(d.prd, d.sby, d.udt, d.sdt, d.egt),
    prd_hours: Math.round(d.prd * 10) / 10,
    machine_count: d.mc,
  }));
  items.sort((a, b) => b.ou_pct - a.ou_pct);
  return items;
}

function deriveDetail(byHistoryRows, resourceMetadata) {
  const data = [];
  for (const row of byHistoryRows) {
    const meta = resourceMetadata[String(row.historyid || '')] || {};
    if (!meta.workcenter) continue;
    const prd = sf(row.prd_hours);
    const sby = sf(row.sby_hours);
    const udt = sf(row.udt_hours);
    const sdt = sf(row.sdt_hours);
    const egt = sf(row.egt_hours);
    const nst = sf(row.nst_hours);
    const total = sf(row.total_hours);
    data.push({
      workcenter: meta.workcenter,
      workcenter_seq: Number(meta.workcenter_seq ?? 999),
      family: meta.family || '',
      resource: meta.resource || '',
      ou_pct: calcOuPct(prd, sby, udt, sdt, egt),
      availability_pct: calcAvailPct(prd, sby, udt, sdt, egt, nst),
      prd_hours: Math.round(prd * 10) / 10,
      prd_pct: statusPct(prd, total),
      sby_hours: Math.round(sby * 10) / 10,
      sby_pct: statusPct(sby, total),
      udt_hours: Math.round(udt * 10) / 10,
      udt_pct: statusPct(udt, total),
      sdt_hours: Math.round(sdt * 10) / 10,
      sdt_pct: statusPct(sdt, total),
      egt_hours: Math.round(egt * 10) / 10,
      egt_pct: statusPct(egt, total),
      nst_hours: Math.round(nst * 10) / 10,
      nst_pct: statusPct(nst, total),
      machine_count: 1,
    });
  }
  data.sort((a, b) =>
    a.workcenter_seq - b.workcenter_seq ||
    (a.family < b.family ? -1 : a.family > b.family ? 1 : 0) ||
    (a.resource < b.resource ? -1 : a.resource > b.resource ? 1 : 0)
  );
  return { data, total: data.length, truncated: false, max_records: null };
}

// ── Main composable ───────────────────────────────────────────────────────────

export function useResourceHistoryDuckDB() {
  const isActive = ref(false);
  const isLoading = ref(false);
  const error = ref('');
  let _client = null;
  let _isRegistered = false;
  let _resourceMetadata = {}; // HISTORYID → { workcenter, workcenter_seq, family, resource }

  /**
   * Activate local compute mode.
   * @param {string} spoolUrl        - Spool Parquet download URL
   * @param {object} resourceMetadata - HISTORYID → dimension mapping from server response
   */
  async function activate(spoolUrl, resourceMetadata) {
    isLoading.value = true;
    error.value = '';
    try {
      _client = getDuckDBClient();
      await _client.init();
      const buffer = await fetchParquetBuffer(spoolUrl);
      await _client.registerParquet(TABLE_NAME, buffer);
      _resourceMetadata = resourceMetadata || {};
      _isRegistered = true;
      isActive.value = true;
    } catch (err) {
      error.value = String(err?.message ?? err);
      isActive.value = false;
      console.warn('[resource-history] DuckDB activation failed:', err);
      throw err;
    } finally {
      isLoading.value = false;
    }
  }

  /**
   * Compute all views locally (mirrors resource_dataset_cache.py derivation).
   * @param {string} granularity - 'day' | 'week' | 'month' | 'year'
   * @returns {{ summary, detail }}
   */
  async function computeView({ granularity = 'day' } = {}) {
    if (!_isRegistered || !_client) throw new Error('DuckDB not initialised');

    const [kpiResult, trendResult, byHistoryResult, heatmapResult] = await Promise.all([
      queryKpi(_client),
      queryTrend(_client, granularity),
      queryByHistoryId(_client),
      queryByHistoryIdAndDate(_client, granularity),
    ]);

    const summary = {
      kpi: kpiResult,
      trend: trendResult,
      heatmap: deriveHeatmap(heatmapResult, _resourceMetadata),
      workcenter_comparison: deriveComparison(byHistoryResult, _resourceMetadata),
    };

    const detail = deriveDetail(byHistoryResult, _resourceMetadata);

    return { summary, detail };
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
    _resourceMetadata = {};
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
