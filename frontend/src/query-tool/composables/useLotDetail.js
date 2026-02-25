import { reactive, ref } from 'vue';

import { apiGet, ensureMesApiAvailable } from '../../core/api.js';
import { exportCsv } from '../utils/csv.js';
import { normalizeText, parseDateTime, uniqueValues, formatDateTime } from '../utils/values.js';

const LOT_SUB_TABS = Object.freeze([
  'history',
  'materials',
  'rejects',
  'holds',
  'jobs',
]);

const ASSOCIATION_TABS = new Set(['materials', 'rejects', 'holds', 'jobs']);

const EXPORT_TYPE_MAP = Object.freeze({
  history: 'lot_history',
  materials: 'lot_materials',
  rejects: 'lot_rejects',
  holds: 'lot_holds',
  jobs: 'lot_jobs',
});

function emptyTabFlags() {
  return {
    history: false,
    materials: false,
    rejects: false,
    holds: false,
    jobs: false,
  };
}

function emptyTabErrors() {
  return {
    workcenterGroups: '',
    history: '',
    materials: '',
    rejects: '',
    holds: '',
    jobs: '',
  };
}

function emptyAssociations() {
  return {
    materials: [],
    rejects: [],
    holds: [],
    jobs: [],
  };
}

function normalizeSubTab(value) {
  const tab = normalizeText(value).toLowerCase();
  return LOT_SUB_TABS.includes(tab) ? tab : 'history';
}

function resolveTimeRangeFromHistory(rows) {
  if (!Array.isArray(rows) || rows.length === 0) {
    return null;
  }

  let minTrackIn = null;
  let maxTrackOut = null;

  rows.forEach((row) => {
    const trackIn = parseDateTime(row?.TRACKINTIMESTAMP || row?.TRACKINTIME);
    const trackOut = parseDateTime(row?.TRACKOUTTIMESTAMP || row?.TRACKOUTTIME);

    if (trackIn && (!minTrackIn || trackIn < minTrackIn)) {
      minTrackIn = trackIn;
    }

    if (trackOut && (!maxTrackOut || trackOut > maxTrackOut)) {
      maxTrackOut = trackOut;
    }

    if (!maxTrackOut && trackIn && (!maxTrackOut || trackIn > maxTrackOut)) {
      maxTrackOut = trackIn;
    }
  });

  if (!minTrackIn || !maxTrackOut) {
    return null;
  }

  return {
    time_start: formatDateTime(minTrackIn),
    time_end: formatDateTime(maxTrackOut),
  };
}

function resolveEquipmentIdFromHistory(rows) {
  if (!Array.isArray(rows) || rows.length === 0) {
    return '';
  }

  for (const row of rows) {
    const equipmentId = normalizeText(row?.EQUIPMENTID || row?.RESOURCEID);
    if (equipmentId) {
      return equipmentId;
    }
  }

  return '';
}

export function useLotDetail(initial = {}) {
  ensureMesApiAvailable();

  const selectedContainerId = ref(normalizeText(initial.selectedContainerId));
  const selectedContainerIds = ref(
    initial.selectedContainerId ? [normalizeText(initial.selectedContainerId)] : [],
  );
  const activeSubTab = ref(normalizeSubTab(initial.activeSubTab));

  const workcenterGroups = ref([]);
  const selectedWorkcenterGroups = ref(uniqueValues(initial.workcenterGroups || []));

  const historyRows = ref([]);
  const associationRows = reactive(emptyAssociations());

  const loading = reactive({
    workcenterGroups: false,
    history: false,
    materials: false,
    rejects: false,
    holds: false,
    jobs: false,
  });

  const loaded = reactive(emptyTabFlags());
  const exporting = reactive(emptyTabFlags());
  const errors = reactive(emptyTabErrors());

  function clearTabData() {
    historyRows.value = [];
    const nextAssociations = emptyAssociations();
    Object.keys(nextAssociations).forEach((key) => {
      associationRows[key] = nextAssociations[key];
    });

    const nextLoaded = emptyTabFlags();
    Object.keys(nextLoaded).forEach((key) => {
      loaded[key] = nextLoaded[key];
      exporting[key] = false;
      errors[key] = '';
    });
  }

  function getActiveCids() {
    if (selectedContainerIds.value.length > 0) {
      return selectedContainerIds.value;
    }
    const single = selectedContainerId.value;
    return single ? [single] : [];
  }

  async function loadWorkcenterGroups() {
    loading.workcenterGroups = true;
    errors.workcenterGroups = '';

    try {
      const payload = await apiGet('/api/query-tool/workcenter-groups', {
        timeout: 360000,
        silent: true,
      });

      workcenterGroups.value = Array.isArray(payload?.data) ? payload.data : [];
      return true;
    } catch (error) {
      errors.workcenterGroups = error?.message || '載入站點群組失敗';
      workcenterGroups.value = [];
      return false;
    } finally {
      loading.workcenterGroups = false;
    }
  }

  async function loadHistory({ force = false } = {}) {
    const cids = getActiveCids();
    if (cids.length === 0) {
      return false;
    }

    if (!force && loaded.history) {
      return true;
    }

    loading.history = true;
    errors.history = '';

    try {
      const params = new URLSearchParams();
      // Batch mode: send all CIDs in one request
      if (cids.length > 1) {
        params.set('container_ids', cids.join(','));
      } else {
        params.set('container_id', cids[0]);
      }
      if (selectedWorkcenterGroups.value.length > 0) {
        params.set('workcenter_groups', selectedWorkcenterGroups.value.join(','));
      }

      const payload = await apiGet(`/api/query-tool/lot-history?${params.toString()}`, {
        timeout: 360000,
        silent: true,
      });

      historyRows.value = Array.isArray(payload?.data) ? payload.data : [];
      loaded.history = true;
      return true;
    } catch (error) {
      errors.history = error?.message || '載入 LOT 歷程失敗';
      historyRows.value = [];
      return false;
    } finally {
      loading.history = false;
    }
  }

  async function loadAssociation(tab, { force = false, silentError = false } = {}) {
    const associationType = normalizeSubTab(tab);
    if (!ASSOCIATION_TABS.has(associationType)) {
      return false;
    }

    const cids = getActiveCids();
    if (cids.length === 0) {
      return false;
    }

    if (!force && loaded[associationType]) {
      return true;
    }

    loading[associationType] = true;
    if (!silentError) {
      errors[associationType] = '';
    }

    try {
      if (associationType === 'jobs') {
        // Jobs derive equipment/time from merged history — use first CID as anchor
        if (historyRows.value.length === 0) {
          await loadHistory();
        }

        const equipmentId = resolveEquipmentIdFromHistory(historyRows.value);
        const timeRange = resolveTimeRangeFromHistory(historyRows.value);

        if (!equipmentId || !timeRange?.time_start || !timeRange?.time_end) {
          throw new Error('無法從 LOT 歷程推導 JOB 查詢條件，請先確認歷程資料');
        }

        const params = new URLSearchParams();
        params.set('container_id', cids[0]);
        params.set('type', associationType);
        params.set('equipment_id', equipmentId);
        params.set('time_start', timeRange.time_start);
        params.set('time_end', timeRange.time_end);

        const payload = await apiGet(`/api/query-tool/lot-associations?${params.toString()}`, {
          timeout: 360000,
          silent: true,
        });

        associationRows[associationType] = Array.isArray(payload?.data) ? payload.data : [];
      } else {
        // Non-jobs tabs: batch all CIDs into a single request
        const params = new URLSearchParams();
        if (cids.length > 1) {
          params.set('container_ids', cids.join(','));
        } else {
          params.set('container_id', cids[0]);
        }
        params.set('type', associationType);

        const payload = await apiGet(`/api/query-tool/lot-associations?${params.toString()}`, {
          timeout: 360000,
          silent: true,
        });

        associationRows[associationType] = Array.isArray(payload?.data) ? payload.data : [];
      }

      loaded[associationType] = true;
      return true;
    } catch (error) {
      associationRows[associationType] = [];
      if (!silentError) {
        errors[associationType] = error?.message || '載入關聯資料失敗';
      }
      return false;
    } finally {
      loading[associationType] = false;
    }
  }

  async function ensureActiveSubTabData() {
    if (activeSubTab.value === 'history') {
      const historyOk = await loadHistory();
      if (historyOk) {
        // History timeline uses hold/material events as marker sources.
        await Promise.allSettled([
          loadAssociation('holds', { silentError: true }),
          loadAssociation('materials', { silentError: true }),
        ]);
      }
      return historyOk;
    }

    return loadAssociation(activeSubTab.value);
  }

  async function setActiveSubTab(tab) {
    activeSubTab.value = normalizeSubTab(tab);
    return ensureActiveSubTabData();
  }

  async function setSelectedContainerId(containerId) {
    const nextId = normalizeText(containerId);
    selectedContainerIds.value = nextId ? [nextId] : [];

    if (nextId === selectedContainerId.value) {
      return ensureActiveSubTabData();
    }

    selectedContainerId.value = nextId;
    clearTabData();

    if (!nextId) {
      return false;
    }

    return ensureActiveSubTabData();
  }

  async function setSelectedContainerIds(cids) {
    const normalized = uniqueValues(
      (Array.isArray(cids) ? cids : []).map(normalizeText).filter(Boolean),
    );
    selectedContainerIds.value = normalized;
    selectedContainerId.value = normalized[0] || '';
    clearTabData();

    if (normalized.length === 0) {
      return false;
    }

    return ensureActiveSubTabData();
  }

  async function setSelectedWorkcenterGroups(groups) {
    selectedWorkcenterGroups.value = uniqueValues(groups || []);

    if (!selectedContainerId.value) {
      return false;
    }

    loaded.history = false;
    return loadHistory({ force: true });
  }

  function getRowsByTab(tab) {
    const normalized = normalizeSubTab(tab);
    if (normalized === 'history') {
      return historyRows.value;
    }
    if (!ASSOCIATION_TABS.has(normalized)) {
      return [];
    }
    return associationRows[normalized] || [];
  }

  async function exportSubTab(tab) {
    const normalized = normalizeSubTab(tab);
    const exportType = EXPORT_TYPE_MAP[normalized];
    const cids = getActiveCids();

    if (!exportType || cids.length === 0) {
      return false;
    }

    exporting[normalized] = true;
    errors[normalized] = '';

    try {
      const params = {
        container_ids: cids,
      };

      if (normalized === 'jobs') {
        if (historyRows.value.length === 0) {
          await loadHistory();
        }
        const equipmentId = resolveEquipmentIdFromHistory(historyRows.value);
        const timeRange = resolveTimeRangeFromHistory(historyRows.value);
        if (!equipmentId || !timeRange?.time_start || !timeRange?.time_end) {
          throw new Error('無法取得 JOB 匯出所需條件');
        }
        params.equipment_id = equipmentId;
        params.time_start = timeRange.time_start;
        params.time_end = timeRange.time_end;
      }

      await exportCsv({
        exportType,
        params,
      });

      return true;
    } catch (error) {
      errors[normalized] = error?.message || '匯出失敗';
      return false;
    } finally {
      exporting[normalized] = false;
    }
  }

  return {
    lotSubTabs: LOT_SUB_TABS,
    selectedContainerId,
    selectedContainerIds,
    activeSubTab,
    workcenterGroups,
    selectedWorkcenterGroups,
    historyRows,
    associationRows,
    loading,
    loaded,
    exporting,
    errors,
    loadWorkcenterGroups,
    loadHistory,
    loadAssociation,
    ensureActiveSubTabData,
    setActiveSubTab,
    setSelectedContainerId,
    setSelectedContainerIds,
    setSelectedWorkcenterGroups,
    getRowsByTab,
    exportSubTab,
    clearTabData,
  };
}
