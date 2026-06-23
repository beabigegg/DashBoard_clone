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
  location?: unknown;
  family?: unknown;
  packageGroup?: unknown;
  isProduction?: unknown;
  isKey?: unknown;
  isMonitor?: unknown;
  name?: unknown;
  id?: unknown;
  [key: string]: unknown;
}

// ── Internal cross-filter helper ──────────────────────────────────────────────
// For each dimension's option list, apply ALL other filters but exclude the
// dimension's own key so the list stays open to the user's next selection.
function applyFiltersExcluding(
  resources: ResourceItem[],
  filters: ResourceFilterSnapshot,
  exclude: Set<string>
): ResourceItem[] {
  let list = Array.isArray(resources) ? resources : [];

  if (!exclude.has('workcenterGroups')) {
    const groups = new Set(normalizeArray(filters.workcenterGroups));
    if (groups.size > 0) {
      list = list.filter((r) => groups.has(normalizeText(r.workcenterGroup)));
    }
  }
  if (!exclude.has('locations')) {
    const locs = new Set(normalizeArray(filters.locations));
    if (locs.size > 0) {
      list = list.filter((r) => locs.has(normalizeText(r.location)));
    }
  }
  if (!exclude.has('families')) {
    const fams = new Set(normalizeArray(filters.families));
    if (fams.size > 0) {
      list = list.filter((r) => fams.has(normalizeText(r.family)));
    }
  }
  if (!exclude.has('machines')) {
    const machs = new Set(normalizeArray(filters.machines));
    if (machs.size > 0) {
      list = list.filter((r) => machs.has(normalizeText(r.id)));
    }
  }
  if (!exclude.has('packageGroups')) {
    const pkgs = new Set(normalizeArray(filters.packageGroups));
    if (pkgs.size > 0) {
      list = list.filter((r) => pkgs.has(normalizeText(r.packageGroup)));
    }
  }
  if (filters.isProduction) list = list.filter((r) => Boolean(r.isProduction));
  if (filters.isKey) list = list.filter((r) => Boolean(r.isKey));
  if (filters.isMonitor) list = list.filter((r) => Boolean(r.isMonitor));

  return list;
}

export interface ResourceFilterInput {
  startDate?: unknown;
  endDate?: unknown;
  granularity?: unknown;
  workcenterGroups?: unknown;
  locations?: unknown;
  families?: unknown;
  machines?: unknown;
  packageGroups?: unknown;
  isProduction?: unknown;
  isKey?: unknown;
  isMonitor?: unknown;
  [key: string]: unknown;
}

export interface ResourceFilterSnapshot {
  startDate: string;
  endDate: string;
  granularity: string;
  workcenterGroups: string[];
  locations: string[];
  families: string[];
  machines: string[];
  packageGroups: string[];
  isProduction: boolean;
  isKey: boolean;
  isMonitor: boolean;
}

export function toResourceFilterSnapshot(input: ResourceFilterInput = {}): ResourceFilterSnapshot {
  return {
    startDate: normalizeText(input.startDate),
    endDate: normalizeText(input.endDate),
    granularity: normalizeText(input.granularity) || 'day',
    workcenterGroups: normalizeArray(input.workcenterGroups),
    locations: normalizeArray(input.locations),
    families: normalizeArray(input.families),
    machines: normalizeArray(input.machines),
    packageGroups: normalizeArray(input.packageGroups),
    isProduction: normalizeBoolean(input.isProduction, false),
    isKey: normalizeBoolean(input.isKey, false),
    isMonitor: normalizeBoolean(input.isMonitor, false),
  };
}

// ── Cross-filter option derivers (each excludes its own dimension) ────────────

export function deriveWorkcenterGroupOptions(
  resources: ResourceItem[] = [],
  filters: ResourceFilterInput = {}
): string[] {
  const next = toResourceFilterSnapshot(filters);
  const filtered = applyFiltersExcluding(resources, next, new Set(['workcenterGroups']));
  const values = new Set<string>();
  for (const r of filtered) {
    const v = normalizeText(r.workcenterGroup);
    if (v) values.add(v);
  }
  return [...values].sort((a, b) => a.localeCompare(b));
}

export function deriveLocationOptions(
  resources: ResourceItem[] = [],
  filters: ResourceFilterInput = {}
): string[] {
  const next = toResourceFilterSnapshot(filters);
  const filtered = applyFiltersExcluding(resources, next, new Set(['locations']));
  const values = new Set<string>();
  for (const r of filtered) {
    const v = normalizeText(r.location);
    if (v) values.add(v);
  }
  return [...values].sort((a, b) => a.localeCompare(b));
}

export function deriveResourceFamilyOptions(
  resources: ResourceItem[] = [],
  filters: ResourceFilterInput = {}
): string[] {
  const next = toResourceFilterSnapshot(filters);
  const filtered = applyFiltersExcluding(resources, next, new Set(['families']));
  const values = new Set<string>();
  for (const r of filtered) {
    const v = normalizeText(r.family);
    if (v) values.add(v);
  }
  return [...values].sort((a, b) => a.localeCompare(b));
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
  const filtered = applyFiltersExcluding(resources, next, new Set(['machines']));
  return filtered
    .map((r) => ({
      label: normalizeText(r.name),
      value: normalizeText(r.id),
    }))
    .filter((o) => o.label && o.value)
    .sort((a, b) => a.label.localeCompare(b.label));
}

export function derivePackageGroupOptions(
  resources: ResourceItem[] = [],
  filters: ResourceFilterInput = {}
): string[] {
  const next = toResourceFilterSnapshot(filters);
  const filtered = applyFiltersExcluding(resources, next, new Set(['packageGroups']));
  const values = new Set<string>();
  for (const r of filtered) {
    const v = normalizeText(r.packageGroup);
    if (v) values.add(v);
  }
  return [...values].sort((a, b) => a.localeCompare(b));
}

// ── Prune selections that are no longer valid after upstream change ───────────

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
  locations?: string[];
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
  if (next.locations.length > 0) {
    params.locations = next.locations;
  }
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
