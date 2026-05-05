/**
 * Barrel re-export for frontend/src/core.
 * All public exports are gathered here so downstream feature apps can import
 * from '@/core' without specifying individual module paths.
 */

// Types (ApiResponse<T>, PendingJobEntry, etc.)
export type { ApiResponse, ApiResponseMeta, ApiErrorPayload, PaginationMeta, PendingJobEntry } from './types.js';

// API layer
export { apiGet, apiPost, apiUpload, ensureMesApiAvailable, _inFlightSize, _clearInFlight } from './api.js';
export type { FetchOptions } from './api.js';

// Unwrap utilities (also re-exports ApiResponse for convenience)
export { unwrapApiResult, unwrapApiData } from './unwrap-api-result.js';

// Datetime
export { formatLogTime } from './datetime.js';

// Compute
export {
  calcOuPct,
  calcAvailabilityPct,
  calcStatusPct,
  calcYieldPct,
  calcOeePct,
  buildResourceKpiFromHours,
} from './compute.js';
export type { ResourceHours, ResourceKpi } from './compute.js';

// Risk score
export { calcRiskScore, calcRiskLevel } from './risk-score.js';
export type { RiskLevel } from './risk-score.js';

// Field contracts
export {
  getPageContract,
  getFieldContractByApiKey,
  getUiHeaders,
  getExportHeaders,
  getContractRegistry,
} from './field-contracts.js';
export type { FieldContract } from './field-contracts.js';

// Endpoint schemas (runtime + static interfaces)
export {
  ENDPOINT_SCHEMAS,
  HOLD_OVERVIEW_SUMMARY_SCHEMA,
  HOLD_OVERVIEW_TREEMAP_SCHEMA,
  REJECT_HISTORY_SUMMARY_SCHEMA,
  REJECT_HISTORY_OPTIONS_SCHEMA,
  PRODUCTION_HISTORY_QUERY_SCHEMA,
  PRODUCTION_HISTORY_TYPE_OPTIONS_SCHEMA,
  PRODUCTION_HISTORY_COUNT_SCHEMA,
  MATERIAL_TRACE_SPOOL_SCHEMA,
  MATERIAL_TRACE_QUERY_SCHEMA,
  ANALYTICS_ANOMALY_SUMMARY_SCHEMA,
  ENVELOPE_META_SCHEMA,
} from './endpoint-schemas.js';
export type {
  IHoldOverviewSummary,
  IHoldOverviewTreemap,
  IRejectHistorySummary,
  IRejectHistoryOptions,
  IProductionHistoryQuery,
  IProductionHistoryTypeOptions,
  IProductionHistoryCount,
  IMaterialTraceSpool,
  IMaterialTraceQuery,
  IAnalyticsAnomalySummary,
  IEnvelopeMeta,
  FieldSpec,
  SchemaObject,
} from './endpoint-schemas.js';

// Schema guard
export { assertShape, _resetWarned } from './schema-guard.js';

// Dev warnings
export {
  detectNaNPagination,
  detectUnknownEnvelope,
  guardResponse,
  detectArrayShape,
  detectSpoolContentType,
  detectMissingSignal,
} from './dev-warnings.js';

// Table tree utilities
export { groupBy, sortBy, toggleTreeState, setTreeStateBulk, escapeHtml, safeText } from './table-tree.js';

// Autocomplete
export {
  debounce,
  buildWipAutocompleteParams,
  fetchWipAutocompleteItems,
  WIP_AUTOCOMPLETE_FIELD_MAP,
} from './autocomplete.js';
export type { WipAutocompleteFilters, WipAutocompleteParams, FetchWipAutocompleteOptions } from './autocomplete.js';

// WIP derive
export {
  normalizeStatusFilter,
  buildWipOverviewQueryParams,
  buildWipDetailQueryParams,
  splitHoldByType,
  prepareParetoData,
} from './wip-derive.js';
export type {
  WipStatusFilterResult,
  WipFilters,
  WipOverviewQueryParams,
  WipDetailQueryOptions,
  WipItem,
  HoldSplit,
  ParetoData,
} from './wip-derive.js';

// Shell navigation
export {
  isPortalShellRuntime,
  toRuntimeRoute,
  navigateToRuntimeRoute,
  replaceRuntimeHistory,
  restoreUrlState,
} from './shell-navigation.js';
export type { ToRuntimeRouteOptions, NavigateOptions } from './shell-navigation.js';

// App version check
export {
  onVersionMismatch,
  appVersionCheck,
  getLastSeenServerVersion,
  getBundleVersion,
  _resetVersionCheck,
} from './app-version-check.js';
export type { AppVersionMeta } from './app-version-check.js';

// WIP navigation state
export {
  storeWipNavigationState,
  loadWipNavigationState,
  clearWipNavigationState,
} from './wip-navigation-state.js';
export type { WipNavigationFilters, WipNavigationState } from './wip-navigation-state.js';

// Reject history filters
export {
  PRIMARY_QUERY_MAX_DAYS,
  toRejectFilterSnapshot,
  extractWorkcenterGroupValues,
  pruneRejectFilterSelections,
  buildRejectOptionsRequestParams,
  buildRejectCommonQueryParams,
  parseMultiLineInput,
  validateDateRange,
  buildViewParams,
} from './reject-history-filters.js';
export type {
  RejectFilterInput,
  RejectFilterSnapshot,
  WorkcenterGroupOption,
  RejectFilterOptions,
  PruneRejectFilterResult,
  RejectOptionsRequestParams,
  RejectCommonQueryParams,
  BuildRejectCommonQueryOptions,
  ViewParamsOptions,
} from './reject-history-filters.js';

// Resource history filters
export {
  toResourceFilterSnapshot,
  deriveResourceFamilyOptions,
  deriveResourceMachineOptions,
  pruneResourceFilterSelections,
  buildResourceHistoryQueryParams,
} from './resource-history-filters.js';
export type {
  ResourceItem,
  ResourceFilterInput,
  ResourceFilterSnapshot,
  MachineOption,
  PruneResourceFilterOptions,
  PruneResourceFilterResult,
  ResourceHistoryQueryParams,
} from './resource-history-filters.js';

// DuckDB client
export { DuckDBClient, getDuckDBClient, isDuckDBSupported, fetchParquetBuffer } from './duckdb-client.js';

// DuckDB activation policy
export { checkLocalComputeEligibility } from './duckdb-activation-policy.js';
export type { LocalComputeEligibilityOptions, LocalComputeEligibilityResult } from './duckdb-activation-policy.js';

// Pending jobs registry
export {
  registerJob,
  deregisterJob,
  getPendingJobs,
  clearAllJobs,
  isJobPending,
} from './pending-jobs-registry.js';

// POST export
export { postExport } from './post-export.js';

