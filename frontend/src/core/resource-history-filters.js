function normalizeText(value) {
  if (value === null || value === undefined) {
    return '';
  }
  return String(value).trim();
}

function normalizeBoolean(value, fallback = false) {
  if (value === undefined) {
    return fallback;
  }
  return Boolean(value);
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

function applyUpstreamResourceFilters(resources, filters) {
  let list = Array.isArray(resources) ? resources : [];
  const groups = new Set(normalizeArray(filters.workcenterGroups));

  if (groups.size > 0) {
    list = list.filter((resource) => groups.has(normalizeText(resource.workcenterGroup)));
  }
  if (filters.isProduction) {
    list = list.filter((resource) => Boolean(resource.isProduction));
  }
  if (filters.isKey) {
    list = list.filter((resource) => Boolean(resource.isKey));
  }
  if (filters.isMonitor) {
    list = list.filter((resource) => Boolean(resource.isMonitor));
  }

  return list;
}

export function toResourceFilterSnapshot(input = {}) {
  return {
    startDate: normalizeText(input.startDate),
    endDate: normalizeText(input.endDate),
    granularity: normalizeText(input.granularity) || 'day',
    workcenterGroups: normalizeArray(input.workcenterGroups),
    families: normalizeArray(input.families),
    machines: normalizeArray(input.machines),
    isProduction: normalizeBoolean(input.isProduction, false),
    isKey: normalizeBoolean(input.isKey, false),
    isMonitor: normalizeBoolean(input.isMonitor, false),
  };
}

export function deriveResourceFamilyOptions(resources = [], filters = {}) {
  const next = toResourceFilterSnapshot(filters);
  const filtered = applyUpstreamResourceFilters(resources, next);
  const families = new Set();
  for (const resource of filtered) {
    const value = normalizeText(resource.family);
    if (value) {
      families.add(value);
    }
  }
  return [...families].sort((left, right) => left.localeCompare(right));
}

export function deriveResourceMachineOptions(resources = [], filters = {}) {
  const next = toResourceFilterSnapshot(filters);
  let filtered = applyUpstreamResourceFilters(resources, next);
  const families = new Set(next.families);
  if (families.size > 0) {
    filtered = filtered.filter((resource) => families.has(normalizeText(resource.family)));
  }

  return filtered
    .map((resource) => ({
      label: normalizeText(resource.name),
      value: normalizeText(resource.id),
    }))
    .filter((option) => option.label && option.value)
    .sort((left, right) => left.label.localeCompare(right.label));
}

export function pruneResourceFilterSelections(filters = {}, { familyOptions = [], machineOptions = [] } = {}) {
  const next = toResourceFilterSnapshot(filters);
  const hasFamilyOptions = Array.isArray(familyOptions);
  const hasMachineOptions = Array.isArray(machineOptions);
  const validFamilies = new Set(normalizeArray(familyOptions));
  const validMachines = new Set(
    (Array.isArray(machineOptions) ? machineOptions : [])
      .map((option) => normalizeText(option?.value))
      .filter(Boolean)
  );

  const removed = {
    families: [],
    machines: [],
  };

  if (hasFamilyOptions) {
    next.families = next.families.filter((value) => {
      if (validFamilies.has(value)) {
        return true;
      }
      removed.families.push(value);
      return false;
    });
  }

  if (hasMachineOptions) {
    next.machines = next.machines.filter((value) => {
      if (validMachines.has(value)) {
        return true;
      }
      removed.machines.push(value);
      return false;
    });
  }

  return {
    filters: next,
    removed,
    removedCount: removed.families.length + removed.machines.length,
  };
}

export function buildResourceHistoryQueryParams(filters = {}) {
  const next = toResourceFilterSnapshot(filters);
  const params = {
    start_date: next.startDate,
    end_date: next.endDate,
    granularity: next.granularity,
    workcenter_groups: next.workcenterGroups,
    families: next.families,
    resource_ids: next.machines,
  };
  if (next.isProduction) {
    params.is_production = '1';
  }
  if (next.isKey) {
    params.is_key = '1';
  }
  if (next.isMonitor) {
    params.is_monitor = '1';
  }
  return params;
}
