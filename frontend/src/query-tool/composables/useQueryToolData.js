import { computed, reactive, ref } from 'vue';

import { apiGet, apiPost, ensureMesApiAvailable } from '../../core/api.js';
import { replaceRuntimeHistory } from '../../core/shell-navigation.js';

ensureMesApiAvailable();

function toDateString(date) {
  return date.toISOString().slice(0, 10);
}

function parseArrayQuery(params, key) {
  const repeated = params.getAll(key).map((item) => String(item || '').trim()).filter(Boolean);
  if (repeated.length > 0) {
    return repeated;
  }
  return String(params.get(key) || '')
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean);
}

function buildBatchQueryString(state) {
  const params = new URLSearchParams();
  if (state.inputType) params.set('input_type', state.inputType);
  if (state.selectedContainerId) params.set('container_id', state.selectedContainerId);
  if (state.associationType) params.set('association_type', state.associationType);
  state.selectedWorkcenterGroups.forEach((item) => params.append('workcenter_groups', item));
  return params.toString();
}

function buildEquipmentQueryString(state) {
  const params = new URLSearchParams();
  state.selectedEquipmentIds.forEach((item) => params.append('equipment_ids', item));
  if (state.startDate) params.set('start_date', state.startDate);
  if (state.endDate) params.set('end_date', state.endDate);
  if (state.equipmentQueryType) params.set('query_type', state.equipmentQueryType);
  return params.toString();
}

function mapEquipmentExportType(queryType) {
  const normalized = String(queryType || '').trim();
  const mapping = {
    status_hours: 'equipment_status_hours',
    lots: 'equipment_lots',
    materials: 'equipment_materials',
    rejects: 'equipment_rejects',
    jobs: 'equipment_jobs',
  };
  return mapping[normalized] || null;
}

function mapAssociationExportType(associationType) {
  const normalized = String(associationType || '').trim();
  const mapping = {
    materials: 'lot_materials',
    rejects: 'lot_rejects',
    holds: 'lot_holds',
    splits: 'lot_splits',
    jobs: 'lot_jobs',
  };
  return mapping[normalized] || null;
}

export function useQueryToolData() {
  const loading = reactive({
    resolving: false,
    history: false,
    association: false,
    equipment: false,
    exporting: false,
    bootstrapping: false,
  });

  const errorMessage = ref('');
  const successMessage = ref('');

  const batch = reactive({
    inputType: 'lot_id',
    inputText: '',
    resolvedLots: [],
    selectedContainerId: '',
    selectedWorkcenterGroups: [],
    workcenterGroups: [],
    lotHistoryRows: [],
    associationType: 'materials',
    associationRows: [],
  });

  const equipment = reactive({
    options: [],
    selectedEquipmentIds: [],
    startDate: '',
    endDate: '',
    equipmentQueryType: 'status_hours',
    rows: [],
  });

  const resolvedColumns = computed(() => Object.keys(batch.resolvedLots[0] || {}));
  const historyColumns = computed(() => Object.keys(batch.lotHistoryRows[0] || {}));
  const associationColumns = computed(() => Object.keys(batch.associationRows[0] || {}));
  const equipmentColumns = computed(() => Object.keys(equipment.rows[0] || {}));

  const selectedEquipmentNames = computed(() => {
    const selectedSet = new Set(equipment.selectedEquipmentIds);
    return equipment.options
      .filter((item) => selectedSet.has(item.RESOURCEID))
      .map((item) => item.RESOURCENAME)
      .filter(Boolean);
  });

  function hydrateFromUrl() {
    const params = new URLSearchParams(window.location.search);
    batch.inputType = String(params.get('input_type') || 'lot_id').trim() || 'lot_id';
    batch.selectedContainerId = String(params.get('container_id') || '').trim();
    batch.associationType = String(params.get('association_type') || 'materials').trim() || 'materials';
    batch.selectedWorkcenterGroups = parseArrayQuery(params, 'workcenter_groups');

    equipment.selectedEquipmentIds = parseArrayQuery(params, 'equipment_ids');
    equipment.startDate = String(params.get('start_date') || '').trim();
    equipment.endDate = String(params.get('end_date') || '').trim();
    equipment.equipmentQueryType = String(params.get('query_type') || 'status_hours').trim() || 'status_hours';
  }

  function resetEquipmentDateRange() {
    const end = new Date();
    const start = new Date();
    start.setDate(start.getDate() - 30);
    equipment.startDate = toDateString(start);
    equipment.endDate = toDateString(end);
  }

  function syncBatchUrlState() {
    const query = buildBatchQueryString(batch);
    replaceRuntimeHistory(query ? `/query-tool?${query}` : '/query-tool');
  }

  function syncEquipmentUrlState() {
    const query = buildEquipmentQueryString(equipment);
    replaceRuntimeHistory(query ? `/query-tool?${query}` : '/query-tool');
  }

  function parseBatchInputValues() {
    return String(batch.inputText || '')
      .split(/[\n,]/)
      .map((item) => item.trim())
      .filter(Boolean);
  }

  async function loadEquipmentOptions() {
    try {
      const payload = await apiGet('/api/query-tool/equipment-list', { timeout: 60000, silent: true });
      equipment.options = Array.isArray(payload?.data) ? payload.data : [];
    } catch (error) {
      errorMessage.value = error?.message || '載入設備選單失敗';
      equipment.options = [];
    }
  }

  async function loadWorkcenterGroups() {
    try {
      const payload = await apiGet('/api/query-tool/workcenter-groups', { timeout: 60000, silent: true });
      batch.workcenterGroups = Array.isArray(payload?.data) ? payload.data : [];
    } catch {
      batch.workcenterGroups = [];
    }
  }

  async function bootstrap() {
    loading.bootstrapping = true;
    errorMessage.value = '';
    await Promise.all([loadEquipmentOptions(), loadWorkcenterGroups()]);
    loading.bootstrapping = false;
  }

  async function resolveLots() {
    const values = parseBatchInputValues();
    if (values.length === 0) {
      errorMessage.value = '請輸入 LOT/流水號/工單條件';
      return false;
    }
    loading.resolving = true;
    errorMessage.value = '';
    successMessage.value = '';
    batch.selectedContainerId = '';
    batch.lotHistoryRows = [];
    batch.associationRows = [];
    syncBatchUrlState();
    try {
      const payload = await apiPost(
        '/api/query-tool/resolve',
        {
          input_type: batch.inputType,
          values,
        },
        { timeout: 60000, silent: true },
      );
      batch.resolvedLots = Array.isArray(payload?.data) ? payload.data : [];
      const notFound = Array.isArray(payload?.not_found) ? payload.not_found : [];
      successMessage.value = `解析完成：${batch.resolvedLots.length} 筆，未命中 ${notFound.length} 筆`;
      return true;
    } catch (error) {
      errorMessage.value = error?.message || '解析失敗';
      batch.resolvedLots = [];
      return false;
    } finally {
      loading.resolving = false;
    }
  }

  async function loadLotHistory(containerId) {
    const id = String(containerId || '').trim();
    if (!id) {
      return false;
    }
    loading.history = true;
    errorMessage.value = '';
    batch.selectedContainerId = id;
    syncBatchUrlState();
    try {
      const params = new URLSearchParams();
      params.set('container_id', id);
      batch.selectedWorkcenterGroups.forEach((item) => params.append('workcenter_groups', item));
      const payload = await apiGet(`/api/query-tool/lot-history?${params.toString()}`, {
        timeout: 60000,
        silent: true,
      });
      batch.lotHistoryRows = Array.isArray(payload?.data) ? payload.data : [];
      return true;
    } catch (error) {
      errorMessage.value = error?.message || '查詢 LOT 歷程失敗';
      batch.lotHistoryRows = [];
      return false;
    } finally {
      loading.history = false;
    }
  }

  async function loadAssociations() {
    if (!batch.selectedContainerId) {
      errorMessage.value = '請先選擇一筆 CONTAINERID';
      return false;
    }
    loading.association = true;
    errorMessage.value = '';
    syncBatchUrlState();
    try {
      const params = new URLSearchParams({
        container_id: batch.selectedContainerId,
        type: batch.associationType,
      });
      const payload = await apiGet(`/api/query-tool/lot-associations?${params.toString()}`, {
        timeout: 60000,
        silent: true,
      });
      batch.associationRows = Array.isArray(payload?.data) ? payload.data : [];
      return true;
    } catch (error) {
      errorMessage.value = error?.message || '查詢關聯資料失敗';
      batch.associationRows = [];
      return false;
    } finally {
      loading.association = false;
    }
  }

  async function queryEquipmentPeriod() {
    if (equipment.selectedEquipmentIds.length === 0) {
      errorMessage.value = '請選擇至少一台設備';
      return false;
    }
    if (!equipment.startDate || !equipment.endDate) {
      errorMessage.value = '請指定設備查詢日期範圍';
      return false;
    }
    loading.equipment = true;
    errorMessage.value = '';
    successMessage.value = '';
    syncEquipmentUrlState();
    try {
      const payload = await apiPost(
        '/api/query-tool/equipment-period',
        {
          equipment_ids: equipment.selectedEquipmentIds,
          equipment_names: selectedEquipmentNames.value,
          start_date: equipment.startDate,
          end_date: equipment.endDate,
          query_type: equipment.equipmentQueryType,
        },
        { timeout: 120000, silent: true },
      );
      equipment.rows = Array.isArray(payload?.data) ? payload.data : [];
      successMessage.value = `設備查詢完成：${equipment.rows.length} 筆`;
      return true;
    } catch (error) {
      errorMessage.value = error?.message || '設備查詢失敗';
      equipment.rows = [];
      return false;
    } finally {
      loading.equipment = false;
    }
  }

  async function exportCurrentCsv() {
    loading.exporting = true;
    errorMessage.value = '';
    successMessage.value = '';

    let exportType = null;
    let params = {};

    if (equipment.rows.length > 0) {
      exportType = mapEquipmentExportType(equipment.equipmentQueryType);
      params = {
        equipment_ids: equipment.selectedEquipmentIds,
        equipment_names: selectedEquipmentNames.value,
        start_date: equipment.startDate,
        end_date: equipment.endDate,
      };
    } else if (batch.selectedContainerId && batch.associationRows.length > 0) {
      exportType = mapAssociationExportType(batch.associationType);
      params = {
        container_id: batch.selectedContainerId,
      };
    } else if (batch.selectedContainerId && batch.lotHistoryRows.length > 0) {
      exportType = 'lot_history';
      params = {
        container_id: batch.selectedContainerId,
      };
    }

    if (!exportType) {
      loading.exporting = false;
      errorMessage.value = '無可匯出的查詢結果';
      return false;
    }

    try {
      const response = await fetch('/api/query-tool/export-csv', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          export_type: exportType,
          params,
        }),
      });

      if (!response.ok) {
        let message = `匯出失敗 (${response.status})`;
        try {
          const payload = await response.json();
          message = payload?.error || payload?.message || message;
        } catch {
          // ignore parse error
        }
        throw new Error(message);
      }

      const blob = await response.blob();
      const href = window.URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = href;
      anchor.download = `${exportType}.csv`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.URL.revokeObjectURL(href);
      successMessage.value = `CSV 匯出成功：${exportType}`;
      return true;
    } catch (error) {
      errorMessage.value = error?.message || '匯出失敗';
      return false;
    } finally {
      loading.exporting = false;
    }
  }

  return {
    loading,
    errorMessage,
    successMessage,
    batch,
    equipment,
    resolvedColumns,
    historyColumns,
    associationColumns,
    equipmentColumns,
    hydrateFromUrl,
    resetEquipmentDateRange,
    bootstrap,
    resolveLots,
    loadLotHistory,
    loadAssociations,
    queryEquipmentPeriod,
    exportCurrentCsv,
  };
}
