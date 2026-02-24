import { reactive, ref } from 'vue';

import { apiPost, ensureMesApiAvailable } from '../core/api.js';

ensureMesApiAvailable();

const DEFAULT_STAGE_TIMEOUT_MS = 60000;
const PROFILE_DOMAINS = Object.freeze({
  query_tool: ['history', 'materials', 'rejects', 'holds', 'jobs'],
  mid_section_defect: ['upstream_history'],
  mid_section_defect_forward: ['upstream_history', 'downstream_rejects'],
});

function stageKey(stageName) {
  if (stageName === 'seed-resolve') return 'seed';
  if (stageName === 'lineage') return 'lineage';
  return 'events';
}

function normalizeSeedContainerIds(seedPayload) {
  const rows = Array.isArray(seedPayload?.seeds) ? seedPayload.seeds : [];
  const seen = new Set();
  const containerIds = [];
  rows.forEach((row) => {
    const id = String(row?.container_id || '').trim();
    if (!id || seen.has(id)) {
      return;
    }
    seen.add(id);
    containerIds.push(id);
  });
  return containerIds;
}

function collectAllContainerIds(seedContainerIds, lineagePayload, direction) {
  const seen = new Set(seedContainerIds);
  const merged = [...seedContainerIds];

  if (direction === 'forward') {
    const childrenMap = lineagePayload?.children_map || {};
    const queue = [...seedContainerIds];
    while (queue.length > 0) {
      const current = queue.shift();
      const children = childrenMap[current];
      if (!Array.isArray(children)) continue;
      for (const child of children) {
        const id = String(child || '').trim();
        if (!id || seen.has(id)) continue;
        seen.add(id);
        merged.push(id);
        queue.push(id);
      }
    }
  } else {
    const ancestors = lineagePayload?.ancestors || {};
    Object.values(ancestors).forEach((values) => {
      if (!Array.isArray(values)) {
        return;
      }
      values.forEach((value) => {
        const id = String(value || '').trim();
        if (!id || seen.has(id)) {
          return;
        }
        seen.add(id);
        merged.push(id);
      });
    });
  }

  return merged;
}

export function useTraceProgress({ profile } = {}) {
  const current_stage = ref(null);
  const completed_stages = ref([]);
  const is_running = ref(false);

  const stage_results = reactive({
    seed: null,
    lineage: null,
    events: null,
  });

  const stage_errors = reactive({
    seed: null,
    lineage: null,
    events: null,
  });

  let activeController = null;

  function reset() {
    completed_stages.value = [];
    current_stage.value = null;
    stage_results.seed = null;
    stage_results.lineage = null;
    stage_results.events = null;
    stage_errors.seed = null;
    stage_errors.lineage = null;
    stage_errors.events = null;
  }

  function abort() {
    if (activeController) {
      activeController.abort();
      activeController = null;
    }
  }

  async function execute(params = {}) {
    const direction = params.direction || 'backward';
    const domainKey = profile === 'mid_section_defect' && direction === 'forward'
      ? 'mid_section_defect_forward'
      : profile;
    const domains = PROFILE_DOMAINS[domainKey];
    if (!domains) {
      throw new Error(`Unsupported trace profile: ${profile}`);
    }

    abort();
    reset();
    is_running.value = true;

    const controller = new AbortController();
    activeController = controller;

    try {
      current_stage.value = 'seed-resolve';
      const seedPayload = await apiPost(
        '/api/trace/seed-resolve',
        { profile, params },
        { timeout: DEFAULT_STAGE_TIMEOUT_MS, signal: controller.signal },
      );
      stage_results.seed = seedPayload;
      completed_stages.value = [...completed_stages.value, 'seed-resolve'];

      const seedContainerIds = normalizeSeedContainerIds(seedPayload);
      if (seedContainerIds.length === 0) {
        return stage_results;
      }

      current_stage.value = 'lineage';
      const lineagePayload = await apiPost(
        '/api/trace/lineage',
        {
          profile,
          container_ids: seedContainerIds,
          cache_key: seedPayload?.cache_key || null,
          params,
        },
        { timeout: DEFAULT_STAGE_TIMEOUT_MS, signal: controller.signal },
      );
      stage_results.lineage = lineagePayload;
      completed_stages.value = [...completed_stages.value, 'lineage'];

      const allContainerIds = collectAllContainerIds(seedContainerIds, lineagePayload, direction);
      current_stage.value = 'events';
      const eventsPayload = await apiPost(
        '/api/trace/events',
        {
          profile,
          container_ids: allContainerIds,
          domains,
          cache_key: seedPayload?.cache_key || null,
          params,
          seed_container_ids: seedContainerIds,
          lineage: {
            ancestors: lineagePayload?.ancestors || {},
            children_map: lineagePayload?.children_map || {},
          },
        },
        { timeout: DEFAULT_STAGE_TIMEOUT_MS, signal: controller.signal },
      );
      stage_results.events = eventsPayload;
      completed_stages.value = [...completed_stages.value, 'events'];
      return stage_results;
    } catch (error) {
      if (error?.name === 'AbortError') {
        return stage_results;
      }
      const key = stageKey(current_stage.value);
      stage_errors[key] = {
        code: error?.errorCode || null,
        message: error?.message || '追溯查詢失敗',
      };
      return stage_results;
    } finally {
      if (activeController === controller) {
        activeController = null;
      }
      current_stage.value = null;
      is_running.value = false;
    }
  }

  return {
    current_stage,
    completed_stages,
    stage_results,
    stage_errors,
    is_running,
    execute,
    reset,
    abort,
  };
}
