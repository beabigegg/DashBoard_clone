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

function edgeKey(fromCid, toCid) {
  const from = normalizeText(fromCid);
  const to = normalizeText(toCid);
  if (!from || !to) {
    return '';
  }
  return `${from}->${to}`;
}

export function useLotLineage(initial = {}) {
  ensureMesApiAvailable();

  const lineageMap = reactive(new Map());
  const nameMap = reactive(new Map());
  const nodeMetaMap = reactive(new Map());
  const edgeTypeMap = reactive(new Map());
  const graphEdges = ref([]);
  const leafSerials = reactive(new Map());
  const expandedNodes = ref(new Set());
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

  function getSerials(containerId) {
    const id = normalizeText(containerId);
    return id ? (leafSerials.get(id) || []) : [];
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

  function isExpanded(containerId) {
    const id = normalizeText(containerId);
    return id ? expandedNodes.value.has(id) : false;
  }

  function isSelected(containerId) {
    return normalizeText(containerId) === selectedContainerId.value;
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

  const lineageLoading = computed(() => {
    for (const entry of lineageMap.values()) {
      if (entry.loading) {
        return true;
      }
    }
    return false;
  });

  function collapseAll() {
    expandedNodes.value = new Set();
  }

  async function requestLineageWithRetry(containerIds) {
    let attempt = 0;

    while (attempt <= MAX_429_RETRY) {
      try {
        const envelope = await apiPost(
          '/api/trace/lineage',
          {
            profile: 'query_tool',
            container_ids: containerIds,
          },
          { timeout: 360000, silent: true },
        );
        return envelope?.data || {};
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

  function populateForwardTree(payload) {
    const childrenMapData = payload?.children_map;
    const rootsList = payload?.roots || [];
    const serialsData = payload?.leaf_serials || {};
    const names = payload?.names;
    const typedNodes = payload?.nodes;
    const typedEdges = payload?.edges;

    // Merge name mapping
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

    // Store leaf serial numbers
    Object.entries(serialsData).forEach(([cid, serials]) => {
      const id = normalizeText(cid);
      if (id && Array.isArray(serials)) {
        leafSerials.set(id, serials);
      }
    });

    // Populate children_map for all nodes
    if (childrenMapData && typeof childrenMapData === 'object') {
      // First pass: set children for all parent nodes
      Object.entries(childrenMapData).forEach(([parentId, childIds]) => {
        const normalized = normalizeText(parentId);
        if (!normalized) {
          return;
        }
        patchEntry(normalized, {
          children: uniqueValues(childIds || []),
          loading: false,
          fetched: true,
          error: '',
          lastUpdatedAt: Date.now(),
        });
      });

      // Second pass: mark leaf nodes (appear as children but not as parents)
      const allChildCids = new Set();
      Object.values(childrenMapData).forEach((childIds) => {
        (childIds || []).forEach((c) => {
          const nc = normalizeText(c);
          if (nc) {
            allChildCids.add(nc);
          }
        });
      });
      allChildCids.forEach((childCid) => {
        if (!childrenMapData[childCid] && !getEntry(childCid).fetched) {
          patchEntry(childCid, {
            children: [],
            loading: false,
            fetched: true,
            error: '',
            lastUpdatedAt: Date.now(),
          });
        }
      });

      // Also mark roots as fetched
      rootsList.forEach((rootCid) => {
        const id = normalizeText(rootCid);
        if (id && !getEntry(id).fetched) {
          patchEntry(id, {
            children: uniqueValues(childrenMapData[rootCid] || []),
            loading: false,
            fetched: true,
            error: '',
            lastUpdatedAt: Date.now(),
          });
        }
      });
    }

    // Update tree roots
    treeRoots.value = rootsList.map((r) => normalizeText(r)).filter(Boolean);
  }

  async function fetchLineage(containerIds, { force = false } = {}) {
    const ids = (Array.isArray(containerIds) ? containerIds : [containerIds])
      .map((c) => normalizeText(c))
      .filter(Boolean);

    if (ids.length === 0) {
      return null;
    }

    // Check if all already fetched (for single-node requests)
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

          populateForwardTree(payload);
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
              error: error?.message || '血緣查詢失敗',
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

  function expandNode(containerId) {
    const id = normalizeText(containerId);
    if (!id) {
      return;
    }

    const next = new Set(expandedNodes.value);
    next.add(id);
    expandedNodes.value = next;
  }

  function collapseNode(containerId) {
    const id = normalizeText(containerId);
    if (!id) {
      return;
    }

    const next = new Set(expandedNodes.value);
    next.delete(id);
    expandedNodes.value = next;
  }

  function toggleNode(containerId) {
    const id = normalizeText(containerId);
    if (!id) {
      return;
    }

    if (expandedNodes.value.has(id)) {
      collapseNode(id);
      return;
    }

    expandNode(id);
  }

  function expandAll() {
    const expanded = new Set();

    function walk(nodeId) {
      const id = normalizeText(nodeId);
      if (!id || expanded.has(id)) {
        return;
      }
      const entry = getEntry(id);
      if (entry.children && entry.children.length > 0) {
        expanded.add(id);
        entry.children.forEach((childId) => walk(childId));
      }
    }

    treeRoots.value.forEach((rootId) => walk(rootId));
    expandedNodes.value = expanded;
  }

  function resetLineageState() {
    generation += 1;
    semaphore.clear();
    inFlight.clear();
    lineageMap.clear();
    nameMap.clear();
    nodeMetaMap.clear();
    edgeTypeMap.clear();
    graphEdges.value = [];
    leafSerials.clear();
    expandedNodes.value = new Set();
    selectedContainerIds.value = [];
    treeRoots.value = [];
  }

  async function primeResolvedLots(lots = []) {
    resetLineageState();

    rootRows.value = Array.isArray(lots) ? [...lots] : [];
    rootContainerIds.value = rootRows.value
      .map((row) => extractContainerId(row))
      .filter(Boolean);

    // Seed name map from resolve data
    rootRows.value.forEach((row) => {
      const cid = extractContainerId(row);
      const name = normalizeText(row?.lot_id || row?.CONTAINERNAME || row?.input_value);
      if (cid && name) {
        nameMap.set(cid, name);
      }
    });

    if (rootContainerIds.value.length > 0 && !selectedContainerId.value) {
      selectedContainerId.value = rootContainerIds.value[0];
    }

    rootContainerIds.value.forEach((containerId) => {
      patchEntry(containerId, { loading: true });
    });

    // Send all seed CIDs in a single request for forward tree
    await fetchLineage(rootContainerIds.value);
  }

  function clearSelection() {
    selectedContainerId.value = '';
    selectedContainerIds.value = [];
  }

  return {
    lineageMap,
    nameMap,
    nodeMetaMap,
    edgeTypeMap,
    graphEdges,
    leafSerials,
    expandedNodes,
    selectedContainerId,
    selectedContainerIds,
    lineageLoading,
    rootRows,
    rootContainerIds,
    treeRoots,
    getEntry,
    getChildren,
    getSerials,
    getSubtreeCids,
    isExpanded,
    isSelected,
    selectNode,
    setSelectedNodes,
    fetchLineage,
    expandNode,
    collapseNode,
    toggleNode,
    expandAll,
    collapseAll,
    primeResolvedLots,
    resetLineageState,
    clearSelection,
    extractContainerId,
  };
}
