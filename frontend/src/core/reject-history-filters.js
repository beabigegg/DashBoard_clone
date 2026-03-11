function normalizeText(value) {
  if (value === null || value === undefined) {
    return '';
  }
  return String(value).trim();
}

function normalizeArray(values) {
  if (!Array.isArray(values)) {
    return [];
  }
  const seen = new Set();
  const result = [];
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

function normalizeBoolean(value, fallback = false) {
  if (value === undefined) {
    return fallback;
  }
  return Boolean(value);
}

export const PRIMARY_QUERY_MAX_DAYS = 190;

export function toRejectFilterSnapshot(input = {}) {
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

export function extractWorkcenterGroupValues(options = []) {
  if (!Array.isArray(options)) {
    return [];
  }
  const values = [];
  const seen = new Set();
  for (const option of options) {
    let value = '';
    if (option && typeof option === 'object') {
      value = normalizeText(option.name || option.value || option.label);
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

export function pruneRejectFilterSelections(filters = {}, options = {}) {
  const next = toRejectFilterSnapshot(filters);
  const hasWorkcenterOptions = Array.isArray(options.workcenterGroups);
  const hasPackageOptions = Array.isArray(options.packages);
  const hasReasonOptions = Array.isArray(options.reasons);
  const validWorkcenters = new Set(extractWorkcenterGroupValues(options.workcenterGroups || []));
  const validPackages = new Set(normalizeArray(options.packages));
  const validReasons = new Set(normalizeArray(options.reasons));

  const removed = {
    workcenterGroups: [],
    packages: [],
    reasons: [],
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

export function buildRejectOptionsRequestParams(filters = {}) {
  const next = toRejectFilterSnapshot(filters);
  const params = {
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

export function buildRejectCommonQueryParams(filters = {}, { reasons: extraReasons = [] } = {}) {
  const next = toRejectFilterSnapshot(filters);
  const params = {
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

export function parseMultiLineInput(text) {
  if (!text) return [];
  const tokens = String(text)
    .split(/[\n,]+/)
    .map((s) => s.trim())
    .filter(Boolean)
    .map((s) => s.replace(/\*/g, '%'));
  const seen = new Set();
  const result = [];
  for (const token of tokens) {
    if (!seen.has(token)) {
      seen.add(token);
      result.push(token);
    }
  }
  return result;
}

export function validateDateRange(startDate, endDate) {
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
  const days = Math.floor((endDt - startDt) / dayMs) + 1;
  if (days > PRIMARY_QUERY_MAX_DAYS) {
    return `查詢範圍不可超過 ${PRIMARY_QUERY_MAX_DAYS} 天（約半年）`;
  }
  return '';
}

export function buildViewParams(queryId, {
  supplementaryFilters = {},
  metricFilter = 'all',
  trendDates = [],
  detailReason = '',
  paretoSelections = {},
  page = 1,
  perPage = 50,
  policyFilters = {},
} = {}) {
  const params = { query_id: queryId };
  if (supplementaryFilters.packages?.length > 0) {
    params.packages = supplementaryFilters.packages;
  }
  if (supplementaryFilters.workcenterGroups?.length > 0) {
    params.workcenter_groups = supplementaryFilters.workcenterGroups;
  }
  if (supplementaryFilters.reasons?.length > 0) {
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
  const selectionParamMap = {
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
  params.per_page = perPage || 50;

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
