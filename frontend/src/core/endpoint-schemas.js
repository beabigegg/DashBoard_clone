/**
 * Endpoint response schemas for runtime guard validation.
 *
 * Each schema describes the shape of the `data` field (or full envelope)
 * returned by the corresponding API endpoint.
 *
 * Used by guardResponse() in dev-warnings.js to emit console.warn on shape drift.
 */

// ---------------------------------------------------------------------------
// /api/hold-overview/summary
// ---------------------------------------------------------------------------
export const HOLD_OVERVIEW_SUMMARY_SCHEMA = {
  totalLots: 'number',
  totalQty: 'number',
  avgAge: 'number?',
  maxAge: 'number?',
  workcenterCount: 'number',
  dataUpdateDate: 'string?',
};

// ---------------------------------------------------------------------------
// /api/hold-overview/treemap
// ---------------------------------------------------------------------------
export const HOLD_OVERVIEW_TREEMAP_SCHEMA = {
  items: 'array',
};

// ---------------------------------------------------------------------------
// /api/reject-history/summary
// ---------------------------------------------------------------------------
export const REJECT_HISTORY_SUMMARY_SCHEMA = {
  total_lots: 'number?',
  total_qty: 'number?',
};

// ---------------------------------------------------------------------------
// /api/reject-history/options
// ---------------------------------------------------------------------------
export const REJECT_HISTORY_OPTIONS_SCHEMA = {
  pj_types: 'array',
};

// ---------------------------------------------------------------------------
// /api/production-history/query (sync result path)
// ---------------------------------------------------------------------------
export const PRODUCTION_HISTORY_QUERY_SCHEMA = {
  items: 'array',
};

// ---------------------------------------------------------------------------
// /api/production-history/type-options
// ---------------------------------------------------------------------------
export const PRODUCTION_HISTORY_TYPE_OPTIONS_SCHEMA = {
  items: 'array',
};

// ---------------------------------------------------------------------------
// /api/production-history/count
// ---------------------------------------------------------------------------
export const PRODUCTION_HISTORY_COUNT_SCHEMA = {
  count: 'number',
};

// ---------------------------------------------------------------------------
// /api/material-trace/spool (paged result from spool)
// ---------------------------------------------------------------------------
export const MATERIAL_TRACE_SPOOL_SCHEMA = {
  items: 'array',
};

// ---------------------------------------------------------------------------
// /api/material-trace/query (async job enqueue)
// ---------------------------------------------------------------------------
export const MATERIAL_TRACE_QUERY_SCHEMA = {
  query_id: 'string?',
  job_id: 'string?',
};

// ---------------------------------------------------------------------------
// /api/analytics/anomaly-summary
// ---------------------------------------------------------------------------
export const ANALYTICS_ANOMALY_SUMMARY_SCHEMA = {
  items: 'array',
  count: 'number',
};

// ---------------------------------------------------------------------------
// Envelope meta schema (common to all standard responses)
// ---------------------------------------------------------------------------
export const ENVELOPE_META_SCHEMA = {
  timestamp: 'string',
  app_version: 'string?',
};

// ---------------------------------------------------------------------------
// Registry: endpoint path → expected data schema
// ---------------------------------------------------------------------------
export const ENDPOINT_SCHEMAS = {
  '/api/hold-overview/summary': HOLD_OVERVIEW_SUMMARY_SCHEMA,
  '/api/hold-overview/treemap': HOLD_OVERVIEW_TREEMAP_SCHEMA,
  '/api/reject-history/summary': REJECT_HISTORY_SUMMARY_SCHEMA,
  '/api/reject-history/options': REJECT_HISTORY_OPTIONS_SCHEMA,
  '/api/production-history/query': PRODUCTION_HISTORY_QUERY_SCHEMA,
  '/api/production-history/type-options': PRODUCTION_HISTORY_TYPE_OPTIONS_SCHEMA,
  '/api/production-history/count': PRODUCTION_HISTORY_COUNT_SCHEMA,
  '/api/material-trace/spool': MATERIAL_TRACE_SPOOL_SCHEMA,
  '/api/material-trace/query': MATERIAL_TRACE_QUERY_SCHEMA,
  '/api/analytics/anomaly-summary': ANALYTICS_ANOMALY_SUMMARY_SCHEMA,
};
