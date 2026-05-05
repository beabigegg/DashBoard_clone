import { reactive, ref, watch, toRaw } from 'vue';
import { useRequestGuard } from './useRequestGuard.js';
import { useUrlSync } from './useUrlSync.js';

export type FieldTrigger = 'immediate' | 'draft-apply';
export type DependencyAction = 'reload-options' | 'clear' | 'reset';

export interface FieldDefinition {
  trigger?: FieldTrigger;
  initial?: unknown;
  options?: unknown[];
}

export interface FieldDependency {
  when: string;
  then?: string | string[];
  action: DependencyAction;
  value?: unknown;
  debounce?: number;
}

export interface PaginationConfig {
  resetOn?: string[];
}

export interface UrlSyncConfig {
  enabled: boolean;
}

export interface FilterOrchestratorConfig {
  fields?: Record<string, FieldDefinition>;
  dependencies?: FieldDependency[];
  pagination?: PaginationConfig;
  urlSync?: UrlSyncConfig;
  onFetch?: (committed: Record<string, unknown>) => void;
  onPrimaryQuery?: (committed: Record<string, unknown>) => void;
  onViewRefresh?: (committed: Record<string, unknown>) => void;
  onLoadOptions?: (fieldName: string, committed: Record<string, unknown>) => Promise<unknown[]>;
}

export interface FilterOrchestratorComposable {
  committed: Record<string, unknown>;
  draft: Record<string, unknown>;
  options: Record<string, unknown[]>;
  pagination: { page: number };
  updateField: (name: string, value: unknown) => void;
  applyDraft: () => void;
  resetAll: () => void;
  setPage: (page: number) => void;
}

/**
 * Configuration-driven filter state management composable.
 */
export function useFilterOrchestrator(config: FilterOrchestratorConfig): FilterOrchestratorComposable {
  const {
    fields: fieldDefs = {},
    dependencies = [],
    pagination: paginationConfig = {},
    urlSync: urlSyncConfig = { enabled: false },
    onFetch,
    onPrimaryQuery,
    onViewRefresh,
    onLoadOptions,
  } = config;

  const { nextRequestId, isStaleRequest } = useRequestGuard();
  const { syncToUrl, readFromUrl } = useUrlSync();

  // Initialize from URL if sync enabled
  const urlState = urlSyncConfig.enabled ? readFromUrl() : {};

  // Build committed and draft from field definitions
  const committed = reactive<Record<string, unknown>>({});
  const draft = reactive<Record<string, unknown>>({});
  const options = reactive<Record<string, unknown[]>>({});
  const pagination = reactive<{ page: number }>({ page: 1 });

  for (const [name, def] of Object.entries(fieldDefs)) {
    const urlVal = urlState[name];
    const initial = urlVal !== undefined ? urlVal : (def.initial !== undefined ? def.initial : null);
    committed[name] = initial;
    draft[name] = initial;
    options[name] = (def.options || []) as unknown[];
  }

  // Debounce timers
  const debounceTimers: Record<string, ReturnType<typeof setTimeout>> = {};

  function scheduleAction(dep: FieldDependency, changedField: string): void {
    const delay = dep.debounce || 0;
    const thenKey = Array.isArray(dep.then) ? dep.then.join(',') : dep.then;
    const key = `${dep.when}->${thenKey}`;
    clearTimeout(debounceTimers[key]);
    debounceTimers[key] = setTimeout(() => {
      executeDependencyAction(dep, changedField);
    }, delay);
  }

  function executeDependencyAction(dep: FieldDependency, _changedField: string): void {
    const targets = Array.isArray(dep.then) ? dep.then : [dep.then as string];
    for (const target of targets) {
      if (!(target in fieldDefs)) continue;
      if (dep.action === 'clear') {
        const initial = fieldDefs[target]?.initial;
        committed[target] = initial !== undefined ? initial : null;
        draft[target] = committed[target];
      } else if (dep.action === 'reset') {
        const val = dep.value !== undefined ? dep.value : fieldDefs[target]?.initial;
        committed[target] = val !== undefined ? val : null;
        draft[target] = committed[target];
      } else if (dep.action === 'reload-options' && onLoadOptions) {
        onLoadOptions(target, toRaw(committed)).then((result) => {
          options[target] = result || [];
        });
      }
    }
  }

  function triggerDependencies(changedField: string): void {
    for (const dep of dependencies) {
      if (dep.when === changedField) {
        if (dep.debounce) {
          scheduleAction(dep, changedField);
        } else {
          executeDependencyAction(dep, changedField);
        }
      }
    }
  }

  function resetPaginationIfNeeded(changedField: string): void {
    const resetOn = paginationConfig.resetOn || [];
    if (resetOn.includes('*') || resetOn.includes(changedField)) {
      pagination.page = 1;
    }
  }

  function syncUrlIfEnabled(): void {
    if (urlSyncConfig.enabled) {
      syncToUrl(toRaw(committed));
    }
  }

  /**
   * Update a field value. For immediate fields, also updates committed and triggers fetch.
   * For draft-apply fields, only updates draft.
   */
  function updateField(name: string, value: unknown): void {
    const def = fieldDefs[name];
    if (!def) return;

    draft[name] = value;

    if (def.trigger === 'immediate') {
      committed[name] = value;
      triggerDependencies(name);
      resetPaginationIfNeeded(name);
      syncUrlIfEnabled();
      if (onFetch) onFetch(toRaw(committed));
      else if (onViewRefresh) onViewRefresh(toRaw(committed));
    }
    // draft-apply: just update draft, no fetch
  }

  /**
   * Apply all draft values to committed and trigger fetch.
   */
  function applyDraft(): void {
    const changedFields: string[] = [];
    let hasDraftApplyChange = false;
    for (const name of Object.keys(fieldDefs)) {
      if (draft[name] !== committed[name]) {
        changedFields.push(name);
        if (fieldDefs[name]?.trigger === 'draft-apply') {
          hasDraftApplyChange = true;
        }
      }
      committed[name] = draft[name];
    }
    for (const name of changedFields) {
      triggerDependencies(name);
    }
    resetPaginationIfNeeded('*');
    pagination.page = 1;
    syncUrlIfEnabled();
    // When draft-apply fields changed, use onPrimaryQuery (full re-query);
    // otherwise fall back to onFetch (supplementary refresh from cache).
    if (hasDraftApplyChange && onPrimaryQuery) {
      onPrimaryQuery(toRaw(committed));
    } else if (onFetch) {
      onFetch(toRaw(committed));
    } else if (onPrimaryQuery) {
      onPrimaryQuery(toRaw(committed));
    }
  }

  /**
   * Reset all fields to their initial values.
   */
  function resetAll(): void {
    for (const [name, def] of Object.entries(fieldDefs)) {
      const initial = def.initial !== undefined ? def.initial : null;
      committed[name] = initial;
      draft[name] = initial;
    }
    pagination.page = 1;
    syncUrlIfEnabled();
  }

  /**
   * Set pagination page.
   */
  function setPage(page: number): void {
    pagination.page = page;
    syncUrlIfEnabled();
  }

  return {
    committed,
    draft,
    options,
    pagination,
    updateField,
    applyDraft,
    resetAll,
    setPage,
  };
}
