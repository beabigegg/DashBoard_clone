import { computed, reactive, ref } from 'vue';

import { apiGet, apiPost, ensureMesApiAvailable } from '../../core/api.js';
import { pollJobUntilComplete } from '../../shared-composables/useAsyncJobPolling.js';
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

function edgeKey(fromCid, toCid) {
  const from = normalizeText(fromCid);
  const to = normalizeText(toCid);
  if (!from || !to) {
    return '';
  }
  return `${from}->${to}`;
}

function collectAncestors(parentMap, startCid) {
  const start = normalizeText(startCid);
  if (!start) {
    return new Set();
  }

  const visited = new Set();
  const stack = [start];

  while (stack.length > 0) {
    const current = stack.pop();
    const parents = Array.isArray(parentMap?.[current]) ? parentMap[current] : [];
    parents.forEach((parentId) => {
      const parent = normalizeText(parentId);
      if (!parent || visited.has(parent)) {
        return;
      }
      visited.add(parent);
      stack.push(parent);
    });
  }

  return visited;
}

export function useReverseLineage(initial = {}) {
  ensureMesApiAvailable();

  const lineageMap = reactive(new Map());
  const nameMap = reactive(new Map());
  const nodeMetaMap = reactive(new Map());
  const edgeTypeMap = reactive(new Map());
  const graphEdges = ref([]);
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
        const envelope = await apiPost(
          '/api/trace/lineage',
          {
            profile: 'query_tool_reverse',
            container_ids: containerIds,
          },
          { timeout: 360000, silent: true },
        );
        const payload = envelope?.data || {};
        if (payload?.async === true && payload?.status_url) {
          await pollJobUntilComplete(payload.status_url);
          const resultEnvelope = await apiGet(`${payload.status_url}/result`, {
            timeout: 360000,
            silent: true,
          });
          return resultEnvelope?.data || {};
        }
        return payload;
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

  function deriveDisplayRoots(candidateRoots, parentMap) {
    const roots = uniqueValues((candidateRoots || []).map((cid) => normalizeText(cid)).filter(Boolean));
    if (roots.length <= 1) {
      return roots;
    }

    const candidateSet = new Set(roots);
    const groupedRoots = [];
    const groupsByInput = new Map();
    const assigned = new Set();

    // Keep reduction within each query input token to avoid cross-token interference.
    rootRows.value.forEach((row) => {
      const cid = extractContainerId(row);
      if (!candidateSet.has(cid)) {
        return;
      }

      const inputToken = normalizeText(row?.input_value || row?.inputValue || row?.INPUT_VALUE);
      const key = inputToken || `__${cid}`;

      if (!groupsByInput.has(key)) {
        groupsByInput.set(key, []);
        groupedRoots.push(groupsByInput.get(key));
      }

      const group = groupsByInput.get(key);
      if (!group.includes(cid)) {
        group.push(cid);
        assigned.add(cid);
      }
    });

    // Roots not found in rootRows still need a standalone group.
    roots.forEach((cid) => {
      if (assigned.has(cid)) {
        return;
      }
      groupedRoots.push([cid]);
    });

    const reduced = [];

    groupedRoots.forEach((group) => {
      if (group.length <= 1) {
        const only = group[0];
        if (only && !reduced.includes(only)) {
          reduced.push(only);
        }
        return;
      }

      const ancestorCache = new Map();
      const getAncestors = (cid) => {
        if (!ancestorCache.has(cid)) {
          ancestorCache.set(cid, collectAncestors(parentMap, cid));
        }
        return ancestorCache.get(cid);
      };

      const kept = group.filter((cid) => !group.some((otherCid) => (
        otherCid !== cid && getAncestors(otherCid).has(cid)
      )));

      const finalGroup = kept.length > 0 ? kept : group;
      finalGroup.forEach((cid) => {
        if (cid && !reduced.includes(cid)) {
          reduced.push(cid);
        }
      });
    });

    return reduced;
  }

  function populateReverseTree(payload, requestedRoots = []) {
    const parentMap = normalizeParentMap(payload);
    const names = payload?.names;
    const typedNodes = payload?.nodes;
    const typedEdges = payload?.edges;

    if (names && typeof names === 'object') {
      Object.entries(names).forEach(([cid, name]) => {
        if (cid && name) {
          nameMap.set(normalizeText(cid), String(name));
        }
      });
    }

    if (typedNodes && typeof typedNodes === 'object') {
      Object.entries(typedNodes).forEach(([cid, node]) => {
        const normalizedCid = normalizeText(cid);
        if (!normalizedCid || !node || typeof node !== 'object') {
          return;
        }
        nodeMetaMap.set(normalizedCid, node);
        const displayName = normalizeText(node.container_name);
        if (displayName) {
          nameMap.set(normalizedCid, displayName);
        }
      });
    }

    edgeTypeMap.clear();
    const normalizedEdges = [];
    if (Array.isArray(typedEdges)) {
      typedEdges.forEach((edge) => {
        if (!edge || typeof edge !== 'object') {
          return;
        }
        const from = normalizeText(edge.from_cid);
        const to = normalizeText(edge.to_cid);
        const key = edgeKey(from, to);
        const type = normalizeText(edge.edge_type);
        if (key && type) {
          edgeTypeMap.set(key, type);
          normalizedEdges.push({ from_cid: from, to_cid: to, edge_type: type });
        }
      });
    }
    graphEdges.value = normalizedEdges;

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

    treeRoots.value = deriveDisplayRoots(roots, parentMap);
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
    nodeMetaMap.clear();
    edgeTypeMap.clear();
    graphEdges.value = [];
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
    nodeMetaMap,
    edgeTypeMap,
    graphEdges,
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
