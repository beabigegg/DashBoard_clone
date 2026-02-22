import { computed, reactive, ref } from 'vue';

import { apiPost, ensureMesApiAvailable } from '../../core/api.js';
import { normalizeText, uniqueValues } from '../utils/values.js';

const MAX_CONCURRENCY = 3;
const MAX_429_RETRY = 3;

function emptyLineageEntry() {
  return {
    children: [],
    loading: false,
    error: '',
    fetched: false,
    lastUpdatedAt: 0,
  };
}

function extractContainerId(row) {
  if (!row || typeof row !== 'object') {
    return '';
  }
  return normalizeText(row.container_id || row.CONTAINERID || row.containerId);
}

function createSemaphore(maxConcurrency) {
  const queue = [];
  let active = 0;

  function pump() {
    if (active >= maxConcurrency || queue.length === 0) {
      return;
    }

    const item = queue.shift();
    active += 1;

    Promise.resolve()
      .then(item.task)
      .then(item.resolve)
      .catch(item.reject)
      .finally(() => {
        active = Math.max(0, active - 1);
        pump();
      });
  }

  return {
    schedule(task) {
      return new Promise((resolve, reject) => {
        queue.push({ task, resolve, reject });
        pump();
      });
    },
    clear() {
      queue.length = 0;
    },
  };
}

function sleep(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

export function useReverseLineage(initial = {}) {
  ensureMesApiAvailable();

  const lineageMap = reactive(new Map());
  const nameMap = reactive(new Map());
  const leafSerials = reactive(new Map());
  const selectedContainerId = ref(normalizeText(initial.selectedContainerId));
  const selectedContainerIds = ref(
    initial.selectedContainerId ? [normalizeText(initial.selectedContainerId)] : [],
  );
  const rootRows = ref([]);
  const rootContainerIds = ref([]);
  const treeRoots = ref([]);

  const inFlight = new Map();
  const semaphore = createSemaphore(MAX_CONCURRENCY);
  let generation = 0;

  function ensureEntry(containerId) {
    const id = normalizeText(containerId);
    if (!id) {
      return null;
    }

    if (!lineageMap.has(id)) {
      lineageMap.set(id, emptyLineageEntry());
    }

    return lineageMap.get(id);
  }

  function patchEntry(containerId, patch) {
    const id = normalizeText(containerId);
    if (!id) {
      return;
    }

    const previous = ensureEntry(id) || emptyLineageEntry();
    lineageMap.set(id, {
      ...previous,
      ...patch,
    });
  }

  function getEntry(containerId) {
    const id = normalizeText(containerId);
    if (!id) {
      return emptyLineageEntry();
    }
    return lineageMap.get(id) || emptyLineageEntry();
  }

  function getChildren(containerId) {
    const entry = getEntry(containerId);
    return Array.isArray(entry.children) ? entry.children : [];
  }

  function getSubtreeCids(containerId) {
    const id = normalizeText(containerId);
    if (!id) {
      return [];
    }
    const result = [];
    const visited = new Set();
    function walk(nodeId) {
      if (!nodeId || visited.has(nodeId)) {
        return;
      }
      visited.add(nodeId);
      result.push(nodeId);
      getChildren(nodeId).forEach(walk);
    }
    walk(id);
    return result;
  }

  function selectNode(containerId) {
    const id = normalizeText(containerId);
    selectedContainerId.value = id;
    if (id && !selectedContainerIds.value.includes(id)) {
      selectedContainerIds.value = [id];
    }
  }

  function setSelectedNodes(cids) {
    const normalized = (Array.isArray(cids) ? cids : [])
      .map(normalizeText)
      .filter(Boolean);
    selectedContainerIds.value = uniqueValues(normalized);
    selectedContainerId.value = normalized[0] || '';
  }

  function clearSelection() {
    selectedContainerId.value = '';
    selectedContainerIds.value = [];
  }

  const lineageLoading = computed(() => {
    for (const entry of lineageMap.values()) {
      if (entry.loading) {
        return true;
      }
    }
    return false;
  });

  async function requestLineageWithRetry(containerIds) {
    let attempt = 0;

    while (attempt <= MAX_429_RETRY) {
      try {
        return await apiPost(
          '/api/trace/lineage',
          {
            profile: 'query_tool_reverse',
            container_ids: containerIds,
          },
          { timeout: 60000, silent: true },
        );
      } catch (error) {
        const status = Number(error?.status || 0);
        if (status !== 429 || attempt >= MAX_429_RETRY) {
          throw error;
        }

        const retryAfter = Number(error?.retryAfterSeconds || 0);
        const fallbackSeconds = 2 ** attempt;
        const waitSeconds = Math.max(1, Math.min(30, retryAfter || fallbackSeconds));
        await sleep(waitSeconds * 1000);
        attempt += 1;
      }
    }

    return null;
  }

  function normalizeParentMap(payload) {
    const parentMapData = payload?.parent_map;
    if (!parentMapData || typeof parentMapData !== 'object') {
      return {};
    }

    const normalized = {};
    Object.entries(parentMapData).forEach(([childId, parentIds]) => {
      const child = normalizeText(childId);
      if (!child) {
        return;
      }
      const values = Array.isArray(parentIds) ? parentIds : [];
      normalized[child] = uniqueValues(values.map((parentId) => normalizeText(parentId)));
    });
    return normalized;
  }

  function populateReverseTree(payload, requestedRoots = []) {
    const parentMap = normalizeParentMap(payload);
    const names = payload?.names;

    if (names && typeof names === 'object') {
      Object.entries(names).forEach(([cid, name]) => {
        if (cid && name) {
          nameMap.set(normalizeText(cid), String(name));
        }
      });
    }

    Object.entries(parentMap).forEach(([childId, parentIds]) => {
      patchEntry(childId, {
        children: uniqueValues(parentIds || []),
        loading: false,
        fetched: true,
        error: '',
        lastUpdatedAt: Date.now(),
      });
    });

    const allParentIds = new Set();
    Object.values(parentMap).forEach((parentIds) => {
      (parentIds || []).forEach((parentId) => {
        const normalized = normalizeText(parentId);
        if (normalized) {
          allParentIds.add(normalized);
        }
      });
    });

    allParentIds.forEach((parentId) => {
      if (!parentMap[parentId] && !getEntry(parentId).fetched) {
        patchEntry(parentId, {
          children: [],
          loading: false,
          fetched: true,
          error: '',
          lastUpdatedAt: Date.now(),
        });
      }
    });

    const roots = (payload?.roots || requestedRoots || [])
      .map((cid) => normalizeText(cid))
      .filter(Boolean);

    roots.forEach((cid) => {
      if (!getEntry(cid).fetched) {
        patchEntry(cid, {
          children: uniqueValues(parentMap[cid] || []),
          loading: false,
          fetched: true,
          error: '',
          lastUpdatedAt: Date.now(),
        });
      }
    });

    treeRoots.value = roots;
  }

  async function fetchLineage(containerIds, { force = false } = {}) {
    const ids = (Array.isArray(containerIds) ? containerIds : [containerIds])
      .map((c) => normalizeText(c))
      .filter(Boolean);

    if (ids.length === 0) {
      return null;
    }

    if (!force && ids.length === 1) {
      const existing = getEntry(ids[0]);
      if (existing.fetched) {
        return existing;
      }
    }

    const cacheKey = [...ids].sort().join(',');
    if (inFlight.has(cacheKey)) {
      return inFlight.get(cacheKey);
    }

    const runGeneration = generation;
    ids.forEach((id) => {
      patchEntry(id, { loading: true, error: '' });
    });

    const promise = semaphore
      .schedule(async () => {
        try {
          const payload = await requestLineageWithRetry(ids);
          if (runGeneration !== generation) {
            return null;
          }

          populateReverseTree(payload, ids);
          return ids.length === 1 ? getEntry(ids[0]) : null;
        } catch (error) {
          if (runGeneration !== generation) {
            return null;
          }

          ids.forEach((id) => {
            patchEntry(id, {
              children: [],
              loading: false,
              fetched: true,
              error: error?.message || '反向血緣查詢失敗',
              lastUpdatedAt: Date.now(),
            });
          });
          return ids.length === 1 ? getEntry(ids[0]) : null;
        } finally {
          inFlight.delete(cacheKey);
        }
      })
      .catch((error) => {
        inFlight.delete(cacheKey);
        throw error;
      });

    inFlight.set(cacheKey, promise);
    return promise;
  }

  function resetLineageState() {
    generation += 1;
    inFlight.clear();
    semaphore.clear();
    lineageMap.clear();
    nameMap.clear();
    leafSerials.clear();
    rootRows.value = [];
    rootContainerIds.value = [];
    treeRoots.value = [];
    clearSelection();
  }

  async function primeResolvedLots(rows) {
    resetLineageState();
    rootRows.value = Array.isArray(rows) ? [...rows] : [];

    const ids = uniqueValues(rootRows.value.map((row) => extractContainerId(row)).filter(Boolean));
    rootContainerIds.value = ids;
    if (ids.length === 0) {
      return;
    }
    await fetchLineage(ids, { force: true });
  }

  return {
    lineageMap,
    nameMap,
    leafSerials,
    selectedContainerId,
    selectedContainerIds,
    rootRows,
    rootContainerIds,
    treeRoots,
    lineageLoading,
    selectNode,
    setSelectedNodes,
    clearSelection,
    getSubtreeCids,
    fetchLineage,
    resetLineageState,
    primeResolvedLots,
  };
}
