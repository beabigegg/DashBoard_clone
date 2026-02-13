import { reactive, ref } from 'vue';

import { apiGet, ensureMesApiAvailable } from '../../core/api.js';
import { exportCsv } from '../utils/csv.js';
import { normalizeText, parseDateTime, uniqueValues, formatDateTime } from '../utils/values.js';

const LOT_SUB_TABS = Object.freeze([
  'history',
  'materials',
  'rejects',
  'holds',
  'splits',
  'jobs',
]);

const ASSOCIATION_TABS = new Set(['materials', 'rejects', 'holds', 'splits', 'jobs']);

const EXPORT_TYPE_MAP = Object.freeze({
  history: 'lot_history',
  materials: 'lot_materials',
  rejects: 'lot_rejects',
  holds: 'lot_holds',
  splits: 'lot_splits',
  jobs: 'lot_jobs',
});

function emptyTabFlags() {
  return {
    history: false,
    materials: false,
    rejects: false,
    holds: false,
    splits: false,
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
    splits: '',
    jobs: '',
  };
}

function emptyAssociations() {
  return {
    materials: [],
    rejects: [],
    holds: [],
    splits: [],
    jobs: [],
  };
}

function normalizeSubTab(value) {
  const tab = normalizeText(value).toLowerCase();
  return LOT_SUB_TABS.includes(tab) ? tab : 'history';
}

function flattenSplitPayload(payload) {
  if (Array.isArray(payload?.data)) {
    return payload.data;
  }

  const productionHistory = Array.isArray(payload?.production_history)
    ? payload.production_history.map((item) => ({
      RECORD_TYPE: 'PRODUCTION_HISTORY',
      ...item,
    }))
    : [];

  const serialRows = Array.isArray(payload?.serial_numbers)
    ? payload.serial_numbers.flatMap((item) => {
      const serialNumber = item?.serial_number || '';
      const totalGoodDie = item?.total_good_die || null;
      const lots = Array.isArray(item?.lots) ? item.lots : [];

      return lots.map((lot) => ({
        RECORD_TYPE: 'SERIAL_MAPPING',
        SERIAL_NUMBER: serialNumber,
        TOTAL_GOOD_DIE: totalGoodDie,
        LOT_ID: lot?.lot_id || '',
        WORK_ORDER: lot?.work_order || '',
        COMBINE_RATIO: lot?.combine_ratio,
        COMBINE_RATIO_PCT: lot?.combine_ratio_pct || '',
        GOOD_DIE_QTY: lot?.good_die_qty,
        ORIGINAL_START_DATE: lot?.original_start_date,
      }));
    })
    : [];

  return [...productionHistory, ...serialRows];
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
    splits: false,
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
        timeout: 60000,
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
      const results = await Promise.allSettled(
        cids.map((cid) => {
          const params = new URLSearchParams();
          params.set('container_id', cid);
          if (selectedWorkcenterGroups.value.length > 0) {
            params.set('workcenter_groups', selectedWorkcenterGroups.value.join(','));
          }
          return apiGet(`/api/query-tool/lot-history?${params.toString()}`, {
            timeout: 60000,
            silent: true,
          });
        }),
      );

      const allRows = [];
      const failedCids = [];
      results.forEach((result, index) => {
        if (result.status === 'fulfilled') {
          const rows = Array.isArray(result.value?.data) ? result.value.data : [];
          allRows.push(...rows);
        } else {
          failedCids.push(cids[index]);
        }
      });

      historyRows.value = allRows;
      loaded.history = true;

      if (failedCids.length > 0) {
        errors.history = `部分節點歷程載入失敗：${failedCids.join(', ')}`;
      }

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
          timeout: 120000,
          silent: true,
        });

        associationRows[associationType] = Array.isArray(payload?.data) ? payload.data : [];
      } else {
        // Non-jobs tabs: load in parallel for all selected CIDs
        const results = await Promise.allSettled(
          cids.map((cid) => {
            const params = new URLSearchParams();
            params.set('container_id', cid);
            params.set('type', associationType);
            return apiGet(`/api/query-tool/lot-associations?${params.toString()}`, {
              timeout: 120000,
              silent: true,
            });
          }),
        );

        const allRows = [];
        results.forEach((result) => {
          if (result.status === 'fulfilled') {
            const rows = associationType === 'splits'
              ? flattenSplitPayload(result.value)
              : (Array.isArray(result.value?.data) ? result.value.data : []);
            allRows.push(...rows);
          }
        });
        associationRows[associationType] = allRows;
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
    const containerId = selectedContainerId.value;

    if (!exportType || !containerId) {
      return false;
    }

    exporting[normalized] = true;
    errors[normalized] = '';

    try {
      const params = {
        container_id: containerId,
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
