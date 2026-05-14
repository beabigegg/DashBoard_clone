import { computed, reactive, ref } from 'vue';

import { apiGet, apiPost, ensureMesApiAvailable } from '../../core/api';
import { pollJobUntilComplete } from '../../shared-composables/useAsyncJobPolling';
import { normalizeText, uniqueValues } from '../utils/values';

interface LineageEntry {
  children: string[];
  loading: boolean;
  error: string;
  fetched: boolean;
  lastUpdatedAt: number;
}

interface LineageInitial {
  selectedContainerId?: string;
}

interface SemaphoreItem {
  task: () => Promise<unknown>;
  resolve: (value: unknown) => void;
  reject: (reason?: unknown) => void;
}

const MAX_CONCURRENCY = 3;
const MAX_429_RETRY = 3;

function emptyLineageEntry(): LineageEntry {
  return {
    children: [],
    loading: false,
    error: '',
    fetched: false,
    lastUpdatedAt: 0,
  };
}

function extractContainerId(row: unknown): string {
  if (!row || typeof row !== 'object') {
    return '';
  }
  const r = row as Record<string, unknown>;
  return normalizeText(r.container_id || r.CONTAINERID || r.containerId);
}

function createSemaphore(maxConcurrency: number) {
  const queue: SemaphoreItem[] = [];
  let active = 0;

  function pump() {
    if (active >= maxConcurrency || queue.length === 0) {
      return;
    }

    const item = queue.shift();
    if (!item) {
      return;
    }
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
    schedule(task: () => Promise<unknown>): Promise<unknown> {
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

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function edgeKey(fromCid: unknown, toCid: unknown): string {
  const from = normalizeText(fromCid);
  const to = normalizeText(toCid);
  if (!from || !to) {
    return '';
  }
  return `${from}->${to}`;
}

function collectAncestors(parentMap: Record<string, string[]>, startCid: unknown): Set<string> {
  const start = normalizeText(startCid);
  if (!start) {
    return new Set<string>();
  }

  const visited = new Set<string>();
  const stack = [start];

  while (stack.length > 0) {
    const current = stack.pop();
    if (!current) {
      continue;
    }
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

export function useReverseLineage(initial: LineageInitial = {}) {
  ensureMesApiAvailable();

  const lineageMap = reactive(new Map());
  const nameMap = reactive(new Map());
  const nodeMetaMap = reactive(new Map());
  const edgeTypeMap = reactive(new Map());
  const graphEdges = ref<Array<{ from_cid: string; to_cid: string; edge_type: string }>>([]);
  const leafSerials = reactive(new Map());
  const selectedContainerId = ref(normalizeText(initial.selectedContainerId));
  const selectedContainerIds = ref(
    initial.selectedContainerId ? [normalizeText(initial.selectedContainerId)] : [],
  );
  const rootRows = ref<Record<string, unknown>[]>([]);
  const rootContainerIds = ref<string[]>([]);
  const treeRoots = ref<string[]>([]);

  const inFlight = new Map<string, Promise<LineageEntry | null>>();
  const semaphore = createSemaphore(MAX_CONCURRENCY);
  let generation = 0;

  function ensureEntry(containerId: unknown): LineageEntry | null {
    const id = normalizeText(containerId);
    if (!id) {
      return null;
    }

    if (!lineageMap.has(id)) {
      lineageMap.set(id, emptyLineageEntry());
    }

    return lineageMap.get(id);
  }

  function patchEntry(containerId: unknown, patch: Partial<LineageEntry>): void {
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

  function getEntry(containerId: unknown): LineageEntry {
    const id = normalizeText(containerId);
    if (!id) {
      return emptyLineageEntry();
    }
    return lineageMap.get(id) || emptyLineageEntry();
  }

  function getChildren(containerId: unknown): string[] {
    const entry = getEntry(containerId);
    return Array.isArray(entry.children) ? entry.children : [];
  }

  function getSubtreeCids(containerId: unknown): string[] {
    const id = normalizeText(containerId);
    if (!id) {
      return [];
    }
    const result: string[] = [];
    const visited = new Set<string>();
    function walk(nodeId: string): void {
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

  function selectNode(containerId: unknown): void {
    const id = normalizeText(containerId);
    selectedContainerId.value = id;
    if (id && !selectedContainerIds.value.includes(id)) {
      selectedContainerIds.value = [id];
    }
  }

  function setSelectedNodes(cids: unknown[]): void {
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

  async function requestLineageWithRetry(containerIds: string[]): Promise<Record<string, unknown> | null> {
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
        const payload = (envelope as Record<string, unknown>)?.data as Record<string, unknown> || {};
        if (payload?.async === true && payload?.status_url) {
          await pollJobUntilComplete(payload.status_url as string);
          const resultEnvelope = await apiGet(`${payload.status_url}/result`, {
            timeout: 360000,
            silent: true,
          });
          return (resultEnvelope as Record<string, unknown>)?.data as Record<string, unknown> || {};
        }
        return payload;
      } catch (error) {
        const err = error as Record<string, unknown>;
        const status = Number(err?.status || 0);
        if (status !== 429 || attempt >= MAX_429_RETRY) {
          throw error;
        }

        const retryAfter = Number(err?.retryAfterSeconds || 0);
        const fallbackSeconds = 2 ** attempt;
        const waitSeconds = Math.max(1, Math.min(30, retryAfter || fallbackSeconds));
        await sleep(waitSeconds * 1000);
        attempt += 1;
      }
    }

    return null;
  }

  function normalizeParentMap(payload: Record<string, unknown> | null): Record<string, string[]> {
    const parentMapData = payload?.parent_map;
    if (!parentMapData || typeof parentMapData !== 'object') {
      return {};
    }

    const normalized: Record<string, string[]> = {};
    Object.entries(parentMapData as Record<string, unknown>).forEach(([childId, parentIds]) => {
      const child = normalizeText(childId);
      if (!child) {
        return;
      }
      const values = Array.isArray(parentIds) ? parentIds : [];
      normalized[child] = uniqueValues(values.map((parentId: unknown) => normalizeText(parentId)));
    });
    return normalized;
  }

  function deriveDisplayRoots(candidateRoots: string[], parentMap: Record<string, string[]>): string[] {
    const roots = uniqueValues((candidateRoots || []).map((cid) => normalizeText(cid)).filter(Boolean));
    if (roots.length <= 1) {
      return roots;
    }

    const candidateSet = new Set(roots);
    const groupedRoots: string[][] = [];
    const groupsByInput = new Map<string, string[]>();
    const assigned = new Set<string>();

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
        groupedRoots.push(groupsByInput.get(key) as string[]);
      }

      const group = groupsByInput.get(key) as string[];
      if (!group.includes(cid)) {
        group.push(cid);
        assigned.add(cid);
      }
    });

    // Roots not found in rootRows still need a standalone group.
    roots.forEach((cid: string) => {
      if (assigned.has(cid)) {
        return;
      }
      groupedRoots.push([cid]);
    });

    const reduced: string[] = [];

    groupedRoots.forEach((group: string[]) => {
      if (group.length <= 1) {
        const only = group[0];
        if (only && !reduced.includes(only)) {
          reduced.push(only);
        }
        return;
      }

      const ancestorCache = new Map<string, Set<string>>();
      const getAncestors = (cid: string): Set<string> => {
        if (!ancestorCache.has(cid)) {
          ancestorCache.set(cid, collectAncestors(parentMap, cid));
        }
        return ancestorCache.get(cid) as Set<string>;
      };

      const kept = group.filter((cid: string) => !group.some((otherCid: string) => (
        otherCid !== cid && getAncestors(otherCid).has(cid)
      )));

      const finalGroup = kept.length > 0 ? kept : group;
      finalGroup.forEach((cid: string) => {
        if (cid && !reduced.includes(cid)) {
          reduced.push(cid);
        }
      });
    });

    return reduced;
  }

  function populateReverseTree(payload: Record<string, unknown> | null, requestedRoots: string[] = []): void {
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
    const normalizedEdges: Array<{ from_cid: string; to_cid: string; edge_type: string }> = [];
    if (Array.isArray(typedEdges)) {
      typedEdges.forEach((edge: unknown) => {
        if (!edge || typeof edge !== 'object') {
          return;
        }
        const e = edge as Record<string, unknown>;
        const from = normalizeText(e.from_cid);
        const to = normalizeText(e.to_cid);
        const key = edgeKey(from, to);
        const type = normalizeText(e.edge_type);
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

    const allParentIds = new Set<string>();
    Object.values(parentMap).forEach((parentIds) => {
      (parentIds || []).forEach((parentId: string) => {
        const normalized = normalizeText(parentId);
        if (normalized) {
          allParentIds.add(normalized);
        }
      });
    });

    allParentIds.forEach((parentId: string) => {
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

    const roots: string[] = ((Array.isArray(payload?.roots) ? payload?.roots : requestedRoots) || [])
      .map((cid: unknown) => normalizeText(cid))
      .filter(Boolean) as string[];

    roots.forEach((cid: string) => {
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

  async function fetchLineage(containerIds: unknown[] | unknown, { force = false }: { force?: boolean } = {}): Promise<LineageEntry | null> {
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
      return inFlight.get(cacheKey) ?? null;
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
              error: (error as Error)?.message || '反向血緣查詢失敗',
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
      }) as Promise<LineageEntry | null>;

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

  async function primeResolvedLots(rows: Record<string, unknown>[]): Promise<void> {
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
