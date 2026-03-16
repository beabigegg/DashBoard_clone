import { reactive, ref, watch, toRaw } from 'vue';
import { useRequestGuard } from './useRequestGuard.js';
import { useUrlSync } from './useUrlSync.js';

/**
 * Configuration-driven filter state management composable.
 *
 * @param {Object} config
 * @param {Object} config.fields - { [name]: { trigger: 'immediate'|'draft-apply', initial, options? } }
 * @param {Array}  config.dependencies - [{ when, then, action: 'reload-options'|'clear'|'reset', value?, debounce? }]
 * @param {Object} config.pagination - { resetOn: ['*'] | string[] }
 * @param {Object} config.urlSync - { enabled: boolean }
 * @param {Function} config.onFetch - callback when committed state changes (for immediate / apply)
 * @param {Function} config.onPrimaryQuery - callback for two-phase primary query
 * @param {Function} config.onViewRefresh - callback for two-phase supplementary refresh
 * @param {Function} [config.onLoadOptions] - async (fieldName, committed) => string[] | {label,value}[]
 */
export function useFilterOrchestrator(config) {
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
  const committed = reactive({});
  const draft = reactive({});
  const options = reactive({});
  const pagination = reactive({ page: 1 });

  for (const [name, def] of Object.entries(fieldDefs)) {
    const urlVal = urlState[name];
    const initial = urlVal !== undefined ? urlVal : (def.initial !== undefined ? def.initial : null);
    committed[name] = initial;
    draft[name] = initial;
    options[name] = def.options || [];
  }

  // Debounce timers
  const debounceTimers = {};

  function scheduleAction(dep, changedField) {
    const delay = dep.debounce || 0;
    const key = `${dep.when}->${dep.then?.join(',')}`;
    clearTimeout(debounceTimers[key]);
    debounceTimers[key] = setTimeout(() => {
      executeDependencyAction(dep, changedField);
    }, delay);
  }

  function executeDependencyAction(dep, _changedField) {
    const targets = Array.isArray(dep.then) ? dep.then : [dep.then];
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

  function triggerDependencies(changedField) {
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

  function resetPaginationIfNeeded(changedField) {
    const resetOn = paginationConfig.resetOn || [];
    if (resetOn.includes('*') || resetOn.includes(changedField)) {
      pagination.page = 1;
    }
  }

  function syncUrlIfEnabled() {
    if (urlSyncConfig.enabled) {
      syncToUrl(toRaw(committed));
    }
  }

  /**
   * Update a field value. For immediate fields, also updates committed and triggers fetch.
   * For draft-apply fields, only updates draft.
   */
  function updateField(name, value) {
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
  function applyDraft() {
    const changedFields = [];
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
  function resetAll() {
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
  function setPage(page) {
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
