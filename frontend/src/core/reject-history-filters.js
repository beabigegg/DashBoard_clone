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

export function toRejectFilterSnapshot(input = {}) {
  return {
    startDate: normalizeText(input.startDate),
    endDate: normalizeText(input.endDate),
    workcenterGroups: normalizeArray(input.workcenterGroups),
    packages: normalizeArray(input.packages),
    reason: normalizeText(input.reason),
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
    reason: '',
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

  if (next.reason && hasReasonOptions && !validReasons.has(next.reason)) {
    removed.reason = next.reason;
    next.reason = '';
  }

  return {
    filters: next,
    removed,
    removedCount:
      removed.workcenterGroups.length +
      removed.packages.length +
      (removed.reason ? 1 : 0),
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
  if (next.reason) {
    params.reason = next.reason;
  }
  return params;
}

export function buildRejectCommonQueryParams(filters = {}, { reason = '' } = {}) {
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
  const effectiveReason = normalizeText(reason) || next.reason;
  if (effectiveReason) {
    params.reasons = [effectiveReason];
  }
  return params;
}
