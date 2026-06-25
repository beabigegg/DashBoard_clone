function normalizeText(value: unknown): string {
  if (value === null || value === undefined) {
    return '';
  }
  return String(value).trim();
}

function normalizeArray(values: unknown): string[] {
  if (!Array.isArray(values)) {
    return [];
  }
  const seen = new Set<string>();
  const result: string[] = [];
  for (const item of values) {
    const text = normalizeText(item);
    if (!text || seen.has(text)) {
      continue;
    }
    seen.add(text);
    result.push(text);
  }
  return result;
}

function normalizeBoolean(value: unknown, fallback = false): boolean {
  if (value === undefined) {
    return fallback;
  }
  return Boolean(value);
}

export const PRIMARY_QUERY_MAX_DAYS = 365;

export interface RejectFilterInput {
  startDate?: unknown;
  endDate?: unknown;
  workcenterGroups?: unknown;
  packages?: unknown;
  reasons?: unknown;
  includeExcludedScrap?: unknown;
  excludeMaterialScrap?: unknown;
  excludePbDiode?: unknown;
  paretoTop80?: unknown;
  [key: string]: unknown;
}

export interface RejectFilterSnapshot {
  startDate: string;
  endDate: string;
  workcenterGroups: string[];
  packages: string[];
  reasons: string[];
  includeExcludedScrap: boolean;
  excludeMaterialScrap: boolean;
  excludePbDiode: boolean;
  paretoTop80: boolean;
}

export function toRejectFilterSnapshot(input: RejectFilterInput = {}): RejectFilterSnapshot {
  return {
    startDate: normalizeText(input.startDate),
    endDate: normalizeText(input.endDate),
    workcenterGroups: normalizeArray(input.workcenterGroups),
    packages: normalizeArray(input.packages),
    reasons: normalizeArray(input.reasons),
    includeExcludedScrap: normalizeBoolean(input.includeExcludedScrap, false),
    excludeMaterialScrap: normalizeBoolean(input.excludeMaterialScrap, true),
    excludePbDiode: normalizeBoolean(input.excludePbDiode, true),
    paretoTop80: normalizeBoolean(input.paretoTop80, true),
  };
}

export interface WorkcenterGroupOption {
  name?: string;
  value?: string;
  label?: string;
  [key: string]: unknown;
}

export function extractWorkcenterGroupValues(options: Array<WorkcenterGroupOption | string> = []): string[] {
  if (!Array.isArray(options)) {
    return [];
  }
  const values: string[] = [];
  const seen = new Set<string>();
  for (const option of options) {
    let value = '';
    if (option && typeof option === 'object') {
      const opt = option as WorkcenterGroupOption;
      value = normalizeText(opt.name || opt.value || opt.label);
    } else {
      value = normalizeText(option);
    }
    if (!value || seen.has(value)) {
      continue;
    }
    seen.add(value);
    values.push(value);
  }
  return values;
}

export interface RejectFilterOptions {
  workcenterGroups?: Array<WorkcenterGroupOption | string>;
  packages?: unknown[];
  reasons?: unknown[];
}

export interface PruneRejectFilterResult {
  filters: RejectFilterSnapshot;
  removed: {
    workcenterGroups: string[];
    packages: string[];
    reasons: string[];
  };
  removedCount: number;
}

export function pruneRejectFilterSelections(
  filters: RejectFilterInput = {},
  options: RejectFilterOptions = {}
): PruneRejectFilterResult {
  const next = toRejectFilterSnapshot(filters);
  const hasWorkcenterOptions = Array.isArray(options.workcenterGroups);
  const hasPackageOptions = Array.isArray(options.packages);
  const hasReasonOptions = Array.isArray(options.reasons);
  const validWorkcenters = new Set(extractWorkcenterGroupValues(options.workcenterGroups || []));
  const validPackages = new Set(normalizeArray(options.packages));
  const validReasons = new Set(normalizeArray(options.reasons));

  const removed = {
    workcenterGroups: [] as string[],
    packages: [] as string[],
    reasons: [] as string[],
  };

  if (hasWorkcenterOptions) {
    next.workcenterGroups = next.workcenterGroups.filter((value) => {
      if (validWorkcenters.has(value)) {
        return true;
      }
      removed.workcenterGroups.push(value);
      return false;
    });
  }

  if (hasPackageOptions) {
    next.packages = next.packages.filter((value) => {
      if (validPackages.has(value)) {
        return true;
      }
      removed.packages.push(value);
      return false;
    });
  }

  if (hasReasonOptions) {
    next.reasons = next.reasons.filter((value) => {
      if (validReasons.has(value)) {
        return true;
      }
      removed.reasons.push(value);
      return false;
    });
  }

  return {
    filters: next,
    removed,
    removedCount:
      removed.workcenterGroups.length +
      removed.packages.length +
      removed.reasons.length,
  };
}

export interface RejectOptionsRequestParams {
  start_date: string;
  end_date: string;
  workcenter_groups: string[];
  packages: string[];
  include_excluded_scrap: boolean;
  exclude_material_scrap: boolean;
  exclude_pb_diode: boolean;
  reasons?: string[];
}

export function buildRejectOptionsRequestParams(filters: RejectFilterInput = {}): RejectOptionsRequestParams {
  const next = toRejectFilterSnapshot(filters);
  const params: RejectOptionsRequestParams = {
    start_date: next.startDate,
    end_date: next.endDate,
    workcenter_groups: next.workcenterGroups,
    packages: next.packages,
    include_excluded_scrap: next.includeExcludedScrap,
    exclude_material_scrap: next.excludeMaterialScrap,
    exclude_pb_diode: next.excludePbDiode,
  };
  if (next.reasons.length > 0) {
    params.reasons = next.reasons;
  }
  return params;
}

export interface RejectCommonQueryParams extends RejectOptionsRequestParams {
  reasons?: string[];
}

export interface BuildRejectCommonQueryOptions {
  reasons?: unknown[];
}

export function buildRejectCommonQueryParams(
  filters: RejectFilterInput = {},
  { reasons: extraReasons = [] }: BuildRejectCommonQueryOptions = {}
): RejectCommonQueryParams {
  const next = toRejectFilterSnapshot(filters);
  const params: RejectCommonQueryParams = {
    start_date: next.startDate,
    end_date: next.endDate,
    workcenter_groups: next.workcenterGroups,
    packages: next.packages,
    include_excluded_scrap: next.includeExcludedScrap,
    exclude_material_scrap: next.excludeMaterialScrap,
    exclude_pb_diode: next.excludePbDiode,
  };
  const merged = normalizeArray([...next.reasons, ...normalizeArray(extraReasons)]);
  if (merged.length > 0) {
    params.reasons = merged;
  }
  return params;
}

export function parseMultiLineInput(text: string | null | undefined): string[] {
  if (!text) return [];
  const tokens = String(text)
    .split(/[\n,]+/)
    .map((s) => s.trim())
    .filter(Boolean)
    .map((s) => s.replace(/\*/g, '%'));
  const seen = new Set<string>();
  const result: string[] = [];
  for (const token of tokens) {
    if (!seen.has(token)) {
      seen.add(token);
      result.push(token);
    }
  }
  return result;
}

export function validateDateRange(startDate: unknown, endDate: unknown): string {
  const start = normalizeText(startDate);
  const end = normalizeText(endDate);
  if (!start || !end) {
    return '請先設定開始與結束日期';
  }

  const startDt = new Date(`${start}T00:00:00`);
  const endDt = new Date(`${end}T00:00:00`);
  if (Number.isNaN(startDt.getTime()) || Number.isNaN(endDt.getTime())) {
    return '日期格式不正確';
  }
  if (endDt < startDt) {
    return '結束日期必須大於起始日期';
  }
  const dayMs = 24 * 60 * 60 * 1000;
  const days = Math.floor((endDt.getTime() - startDt.getTime()) / dayMs) + 1;
  if (days > PRIMARY_QUERY_MAX_DAYS) {
    return `查詢範圍不可超過 ${PRIMARY_QUERY_MAX_DAYS} 天（約一年）`;
  }
  return '';
}

export interface ViewParamsOptions {
  supplementaryFilters?: {
    packages?: string[];
    workcenterGroups?: string[];
    reasons?: string[];
    [key: string]: unknown;
  };
  metricFilter?: string;
  trendDates?: unknown[];
  detailReason?: string;
  paretoSelections?: {
    reason?: unknown;
    package?: unknown;
    type?: unknown;
    [key: string]: unknown;
  };
  page?: number;
  perPage?: number;
  sortCol?: string;
  sortDir?: 'asc' | 'desc';
  policyFilters?: {
    includeExcludedScrap?: boolean;
    excludeMaterialScrap?: boolean;
    excludePbDiode?: boolean;
    [key: string]: unknown;
  };
}

export function buildViewParams(
  queryId: string,
  {
    supplementaryFilters = {},
    metricFilter = 'all',
    trendDates = [],
    detailReason = '',
    paretoSelections = {},
    page = 1,
    perPage = 20,
    sortCol = '',
    sortDir = 'asc' as 'asc' | 'desc',
    policyFilters = {},
  }: ViewParamsOptions = {}
): Record<string, unknown> {
  const params: Record<string, unknown> = { query_id: queryId };
  if (supplementaryFilters.packages && supplementaryFilters.packages.length > 0) {
    params.packages = supplementaryFilters.packages;
  }
  if (supplementaryFilters.workcenterGroups && supplementaryFilters.workcenterGroups.length > 0) {
    params.workcenter_groups = supplementaryFilters.workcenterGroups;
  }
  if (supplementaryFilters.reasons && supplementaryFilters.reasons.length > 0) {
    params.reasons = supplementaryFilters.reasons;
  }
  if (metricFilter && metricFilter !== 'all') {
    params.metric_filter = metricFilter;
  }
  if (trendDates?.length > 0) {
    params.trend_dates = trendDates;
  }
  if (detailReason) {
    params.detail_reason = detailReason;
  }
  const selectionParamMap: Record<string, string> = {
    reason: 'sel_reason',
    package: 'sel_package',
    type: 'sel_type',
  };
  for (const [dimension, paramName] of Object.entries(selectionParamMap)) {
    const normalizedValues = normalizeArray(paretoSelections?.[dimension]);
    if (normalizedValues.length > 0) {
      params[paramName] = normalizedValues;
    }
  }
  params.page = page || 1;
  params.per_page = perPage || 20;
  if (sortCol) {
    params.sort_col = sortCol;
    params.sort_dir = sortDir || 'asc';
  }

  // Policy filters (applied in-memory on cached data)
  if (policyFilters.includeExcludedScrap) {
    params.include_excluded_scrap = 'true';
  }
  if (policyFilters.excludeMaterialScrap === false) {
    params.exclude_material_scrap = 'false';
  }
  if (policyFilters.excludePbDiode === false) {
    params.exclude_pb_diode = 'false';
  }
  return params;
}
