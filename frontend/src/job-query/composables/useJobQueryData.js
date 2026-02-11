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

function buildQueryString(filters) {
  const params = new URLSearchParams();
  filters.resourceIds.forEach((resourceId) => params.append('resource_ids', resourceId));
  if (filters.startDate) {
    params.set('start_date', filters.startDate);
  }
  if (filters.endDate) {
    params.set('end_date', filters.endDate);
  }
  if (filters.searchText) {
    params.set('search', filters.searchText);
  }
  return params.toString();
}

function buildStatusTone(status) {
  const text = String(status || '').trim().toLowerCase();
  if (!text) {
    return 'neutral';
  }
  if (['complete', 'completed', 'done', 'closed', 'finish'].some((keyword) => text.includes(keyword))) {
    return 'success';
  }
  if (['open', 'pending', 'queue', 'wait', 'hold', 'in progress'].some((keyword) => text.includes(keyword))) {
    return 'warning';
  }
  if (['cancel', 'abort', 'fail', 'error'].some((keyword) => text.includes(keyword))) {
    return 'danger';
  }
  return 'neutral';
}

export function useJobQueryData() {
  const resources = ref([]);
  const loadingResources = ref(false);
  const loadingJobs = ref(false);
  const loadingTxn = ref(false);
  const exporting = ref(false);

  const errorMessage = ref('');
  const exportMessage = ref('');

  const filters = reactive({
    resourceIds: [],
    startDate: '',
    endDate: '',
    searchText: '',
  });

  const jobs = ref([]);
  const selectedJobId = ref('');
  const txnRows = ref([]);

  const filteredResources = computed(() => {
    const query = String(filters.searchText || '').trim().toLowerCase();
    if (!query) {
      return resources.value;
    }
    return resources.value.filter((item) => {
      const resourceName = String(item.RESOURCENAME || '').toLowerCase();
      const workcenter = String(item.WORKCENTERNAME || '').toLowerCase();
      const family = String(item.RESOURCEFAMILYNAME || '').toLowerCase();
      return resourceName.includes(query) || workcenter.includes(query) || family.includes(query);
    });
  });

  const selectedResourceCount = computed(() => filters.resourceIds.length);

  const jobsColumns = computed(() => {
    const row = jobs.value[0] || {};
    return Object.keys(row);
  });

  const txnColumns = computed(() => {
    const row = txnRows.value[0] || {};
    return Object.keys(row);
  });

  function resetDateRangeToLast90Days() {
    const today = new Date();
    const start = new Date(today);
    start.setDate(start.getDate() - 90);
    filters.startDate = toDateString(start);
    filters.endDate = toDateString(today);
  }

  function hydrateFiltersFromUrl() {
    const params = new URLSearchParams(window.location.search);
    const resourceIds = parseArrayQuery(params, 'resource_ids');
    const startDate = String(params.get('start_date') || '').trim();
    const endDate = String(params.get('end_date') || '').trim();
    const searchText = String(params.get('search') || '').trim();

    filters.resourceIds = resourceIds;
    filters.startDate = startDate;
    filters.endDate = endDate;
    filters.searchText = searchText;
  }

  function syncUrlState() {
    const query = buildQueryString(filters);
    const nextUrl = query ? `/job-query?${query}` : '/job-query';
    replaceRuntimeHistory(nextUrl);
  }

  function toggleResource(resourceId) {
    const id = String(resourceId || '').trim();
    if (!id) {
      return;
    }
    if (filters.resourceIds.includes(id)) {
      filters.resourceIds = filters.resourceIds.filter((item) => item !== id);
      return;
    }
    filters.resourceIds = [...filters.resourceIds, id];
  }

  function validateInputs() {
    if (filters.resourceIds.length === 0) {
      return '請選擇至少一台設備';
    }
    if (!filters.startDate || !filters.endDate) {
      return '請指定日期範圍';
    }

    const start = new Date(filters.startDate);
    const end = new Date(filters.endDate);
    if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) {
      return '日期格式錯誤';
    }
    if (end < start) {
      return '結束日期不可早於起始日期';
    }
    const days = (end.getTime() - start.getTime()) / (1000 * 60 * 60 * 24);
    if (days > 365) {
      return '日期範圍不可超過 365 天';
    }
    return '';
  }

  async function loadResources() {
    loadingResources.value = true;
    errorMessage.value = '';
    try {
      const payload = await apiGet('/api/job-query/resources', { timeout: 60000, silent: true });
      resources.value = Array.isArray(payload?.data) ? payload.data : [];
    } catch (error) {
      errorMessage.value = error?.message || '載入設備清單失敗';
      resources.value = [];
    } finally {
      loadingResources.value = false;
    }
  }

  async function queryJobs() {
    const validationError = validateInputs();
    if (validationError) {
      errorMessage.value = validationError;
      return false;
    }

    loadingJobs.value = true;
    errorMessage.value = '';
    exportMessage.value = '';
    syncUrlState();
    selectedJobId.value = '';
    txnRows.value = [];

    try {
      const payload = await apiPost(
        '/api/job-query/jobs',
        {
          resource_ids: filters.resourceIds,
          start_date: filters.startDate,
          end_date: filters.endDate,
        },
        { timeout: 60000, silent: true },
      );
      jobs.value = Array.isArray(payload?.data) ? payload.data : [];
      return true;
    } catch (error) {
      errorMessage.value = error?.message || '查詢失敗';
      jobs.value = [];
      return false;
    } finally {
      loadingJobs.value = false;
    }
  }

  async function loadTxn(jobId) {
    const id = String(jobId || '').trim();
    if (!id) {
      return;
    }
    loadingTxn.value = true;
    selectedJobId.value = id;
    errorMessage.value = '';
    try {
      const payload = await apiGet(`/api/job-query/txn/${encodeURIComponent(id)}`, {
        timeout: 60000,
        silent: true,
      });
      txnRows.value = Array.isArray(payload?.data) ? payload.data : [];
    } catch (error) {
      errorMessage.value = error?.message || '載入交易歷程失敗';
      txnRows.value = [];
    } finally {
      loadingTxn.value = false;
    }
  }

  async function exportCsv() {
    const validationError = validateInputs();
    if (validationError) {
      errorMessage.value = validationError;
      return false;
    }
    exporting.value = true;
    errorMessage.value = '';
    exportMessage.value = '';

    try {
      const response = await fetch('/api/job-query/export', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          resource_ids: filters.resourceIds,
          start_date: filters.startDate,
          end_date: filters.endDate,
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
      anchor.download = `job-query-${filters.startDate}-to-${filters.endDate}.csv`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.URL.revokeObjectURL(href);

      exportMessage.value = 'CSV 匯出成功';
      return true;
    } catch (error) {
      errorMessage.value = error?.message || '匯出失敗';
      return false;
    } finally {
      exporting.value = false;
    }
  }

  function getStatusTone(status) {
    return buildStatusTone(status);
  }

  return {
    resources,
    loadingResources,
    loadingJobs,
    loadingTxn,
    exporting,
    errorMessage,
    exportMessage,
    filters,
    jobs,
    jobsColumns,
    selectedJobId,
    txnRows,
    txnColumns,
    filteredResources,
    selectedResourceCount,
    resetDateRangeToLast90Days,
    hydrateFiltersFromUrl,
    loadResources,
    toggleResource,
    queryJobs,
    loadTxn,
    exportCsv,
    getStatusTone,
  };
}
