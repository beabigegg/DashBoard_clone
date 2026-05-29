function normalizeText(value: unknown): string {
  if (value === null || value === undefined) {
    return '';
  }
  return String(value).trim();
}

function normalizeBoolean(value: unknown, fallback = false): boolean {
  if (value === undefined) {
    return fallback;
  }
  return Boolean(value);
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

export interface ResourceItem {
  workcenterGroup?: unknown;
  family?: unknown;
  isProduction?: unknown;
  isKey?: unknown;
  isMonitor?: unknown;
  name?: unknown;
  id?: unknown;
  [key: string]: unknown;
}

function applyUpstreamResourceFilters(
  resources: ResourceItem[],
  filters: ResourceFilterSnapshot
): ResourceItem[] {
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

export interface ResourceFilterInput {
  startDate?: unknown;
  endDate?: unknown;
  granularity?: unknown;
  workcenterGroups?: unknown;
  families?: unknown;
  machines?: unknown;
  isProduction?: unknown;
  isKey?: unknown;
  isMonitor?: unknown;
  packageGroups?: unknown;
  [key: string]: unknown;
}

export interface ResourceFilterSnapshot {
  startDate: string;
  endDate: string;
  granularity: string;
  workcenterGroups: string[];
  families: string[];
  machines: string[];
  isProduction: boolean;
  isKey: boolean;
  isMonitor: boolean;
  packageGroups: string[];
}

export function toResourceFilterSnapshot(input: ResourceFilterInput = {}): ResourceFilterSnapshot {
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
    packageGroups: normalizeArray(input.packageGroups),
  };
}

export function deriveResourceFamilyOptions(
  resources: ResourceItem[] = [],
  filters: ResourceFilterInput = {}
): string[] {
  const next = toResourceFilterSnapshot(filters);
  const filtered = applyUpstreamResourceFilters(resources, next);
  const families = new Set<string>();
  for (const resource of filtered) {
    const value = normalizeText(resource.family);
    if (value) {
      families.add(value);
    }
  }
  return [...families].sort((left, right) => left.localeCompare(right));
}

export interface MachineOption {
  label: string;
  value: string;
}

export function deriveResourceMachineOptions(
  resources: ResourceItem[] = [],
  filters: ResourceFilterInput = {}
): MachineOption[] {
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

export interface PruneResourceFilterOptions {
  familyOptions?: unknown[];
  machineOptions?: MachineOption[];
}

export interface PruneResourceFilterResult {
  filters: ResourceFilterSnapshot;
  removed: {
    families: string[];
    machines: string[];
  };
  removedCount: number;
}

export function pruneResourceFilterSelections(
  filters: ResourceFilterInput = {},
  { familyOptions = [], machineOptions = [] }: PruneResourceFilterOptions = {}
): PruneResourceFilterResult {
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
    families: [] as string[],
    machines: [] as string[],
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

export interface ResourceHistoryQueryParams {
  start_date: string;
  end_date: string;
  granularity: string;
  workcenter_groups: string[];
  families: string[];
  resource_ids: string[];
  is_production?: string;
  is_key?: string;
  is_monitor?: string;
  package_groups?: string[];
}

export function buildResourceHistoryQueryParams(
  filters: ResourceFilterInput = {}
): ResourceHistoryQueryParams {
  const next = toResourceFilterSnapshot(filters);
  const params: ResourceHistoryQueryParams = {
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
  if (next.packageGroups.length > 0) {
    params.package_groups = next.packageGroups;
  }
  return params;
}
