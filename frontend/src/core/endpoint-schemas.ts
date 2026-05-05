/**
 * Endpoint response schemas for runtime guard validation.
 *
 * Each schema describes the shape of the `data` field (or full envelope)
 * returned by the corresponding API endpoint.
 *
 * Used by guardResponse() in dev-warnings.ts to emit console.warn on shape drift.
 *
 * Dual-layer design:
 *   - Runtime objects (HOLD_OVERVIEW_SUMMARY_SCHEMA etc.) are used by schema-guard.ts
 *   - TypeScript interfaces (IHoldOverviewSummary etc.) provide static type safety
 */

// ---------------------------------------------------------------------------
// TypeScript interfaces (static type layer)
// ---------------------------------------------------------------------------

export interface IHoldOverviewSummary {
  totalLots: number;
  totalQty: number;
  avgAge?: number | null;
  maxAge?: number | null;
  workcenterCount: number;
  dataUpdateDate?: string | null;
}

export interface IHoldOverviewTreemap {
  items: unknown[];
}

export interface IRejectHistorySummary {
  total_lots?: number | null;
  total_qty?: number | null;
}

export interface IRejectHistoryOptions {
  pj_types: unknown[];
}

export interface IProductionHistoryQuery {
  items: unknown[];
}

export interface IProductionHistoryTypeOptions {
  items: unknown[];
}

export interface IProductionHistoryCount {
  count: number;
}

export interface IMaterialTraceSpool {
  items: unknown[];
}

export interface IMaterialTraceQuery {
  query_id?: string | null;
  job_id?: string | null;
}

export interface IAnalyticsAnomalySummary {
  items: unknown[];
  count: number;
}

export interface IEnvelopeMeta {
  timestamp: string;
  app_version?: string | null;
}

// ---------------------------------------------------------------------------
// Runtime schema objects (used by schema-guard.ts at runtime)
// These must be kept in sync with the interfaces above.
// ---------------------------------------------------------------------------

/** Spec type for schema-guard runtime objects */
export type FieldSpec = string | { [key: string]: FieldSpec } | { __array: FieldSpec };

export type SchemaObject = Record<string, FieldSpec>;

// ---------------------------------------------------------------------------
// /api/hold-overview/summary
// ---------------------------------------------------------------------------
export const HOLD_OVERVIEW_SUMMARY_SCHEMA: SchemaObject = {
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
export const HOLD_OVERVIEW_TREEMAP_SCHEMA: SchemaObject = {
  items: 'array',
};

// ---------------------------------------------------------------------------
// /api/reject-history/summary
// ---------------------------------------------------------------------------
export const REJECT_HISTORY_SUMMARY_SCHEMA: SchemaObject = {
  total_lots: 'number?',
  total_qty: 'number?',
};

// ---------------------------------------------------------------------------
// /api/reject-history/options
// ---------------------------------------------------------------------------
export const REJECT_HISTORY_OPTIONS_SCHEMA: SchemaObject = {
  pj_types: 'array',
};

// ---------------------------------------------------------------------------
// /api/production-history/query (sync result path)
// ---------------------------------------------------------------------------
export const PRODUCTION_HISTORY_QUERY_SCHEMA: SchemaObject = {
  items: 'array',
};

// ---------------------------------------------------------------------------
// /api/production-history/type-options
// ---------------------------------------------------------------------------
export const PRODUCTION_HISTORY_TYPE_OPTIONS_SCHEMA: SchemaObject = {
  items: 'array',
};

// ---------------------------------------------------------------------------
// /api/production-history/count
// ---------------------------------------------------------------------------
export const PRODUCTION_HISTORY_COUNT_SCHEMA: SchemaObject = {
  count: 'number',
};

// ---------------------------------------------------------------------------
// /api/material-trace/spool (paged result from spool)
// ---------------------------------------------------------------------------
export const MATERIAL_TRACE_SPOOL_SCHEMA: SchemaObject = {
  items: 'array',
};

// ---------------------------------------------------------------------------
// /api/material-trace/query (async job enqueue)
// ---------------------------------------------------------------------------
export const MATERIAL_TRACE_QUERY_SCHEMA: SchemaObject = {
  query_id: 'string?',
  job_id: 'string?',
};

// ---------------------------------------------------------------------------
// /api/analytics/anomaly-summary
// ---------------------------------------------------------------------------
export const ANALYTICS_ANOMALY_SUMMARY_SCHEMA: SchemaObject = {
  items: 'array',
  count: 'number',
};

// ---------------------------------------------------------------------------
// Envelope meta schema (common to all standard responses)
// ---------------------------------------------------------------------------
export const ENVELOPE_META_SCHEMA: SchemaObject = {
  timestamp: 'string',
  app_version: 'string?',
};

// ---------------------------------------------------------------------------
// Registry: endpoint path → expected data schema
// ---------------------------------------------------------------------------
export const ENDPOINT_SCHEMAS: Record<string, SchemaObject> = {
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
