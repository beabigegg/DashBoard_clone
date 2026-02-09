<script setup>
import { computed, ref, watch } from 'vue';

import { apiGet } from '../../core/api.js';

const props = defineProps({
  lotId: {
    type: String,
    default: '',
  },
});

const emit = defineEmits(['close']);

const loading = ref(false);
const errorMessage = ref('');
const detail = ref(null);

function unwrapApiResult(result, fallbackMessage) {
  if (result?.success) {
    return result.data;
  }
  if (result?.success === false) {
    throw new Error(result.error || fallbackMessage);
  }
  if (result?.data !== undefined) {
    return result.data;
  }
  return result;
}

async function loadLotDetail(lotId) {
  if (!lotId) {
    detail.value = null;
    return;
  }

  loading.value = true;
  errorMessage.value = '';

  try {
    const result = await apiGet(`/api/wip/lot/${encodeURIComponent(lotId)}`, {
      timeout: 60000,
    });
    detail.value = unwrapApiResult(result, 'Failed to fetch lot detail');
  } catch (error) {
    detail.value = null;
    errorMessage.value = error?.message || '載入失敗';
  } finally {
    loading.value = false;
  }
}

watch(
  () => props.lotId,
  (lotId) => {
    if (!lotId) {
      detail.value = null;
      return;
    }
    void loadLotDetail(lotId);
  },
  { immediate: true }
);

const labels = computed(() => detail.value?.fieldLabels || {});

function getLabel(key) {
  return labels.value[key] || key;
}

function formatNumber(value) {
  if (value === null || value === undefined || value === '') {
    return '-';
  }
  return Number.isFinite(Number(value)) ? Number(value).toLocaleString('zh-TW') : String(value);
}

function fieldValue(key) {
  const value = detail.value?.[key];
  if (value === null || value === undefined || value === '') {
    return '-';
  }
  if (typeof value === 'number') {
    return formatNumber(value);
  }
  return String(value);
}

function fieldClass(key) {
  if (key !== 'wipStatus') {
    return '';
  }

  const status = String(detail.value?.[key] || '').toLowerCase();
  return `status-${status}`;
}

function hasHoldSection() {
  return detail.value?.wipStatus === 'HOLD' || Number(detail.value?.holdCount || 0) > 0;
}

const basicFields = ['lotId', 'workorder', 'wipStatus', 'status', 'qty', 'qty2', 'ageByDays', 'priority'];
const productFields = ['product', 'productLine', 'packageLef', 'pjType', 'pjFunction', 'bop', 'dateCode', 'produceRegion'];
const processFields = ['workcenterGroup', 'workcenter', 'spec', 'specSequence', 'workflow', 'equipment', 'equipmentCount', 'location'];
const materialFields = ['waferLotId', 'waferPn', 'waferLotPrefix', 'leadframeName', 'leadframeOption', 'compoundName', 'dieConsumption', 'uts'];
const holdFields = ['holdReason', 'holdCount', 'holdEmp', 'holdDept', 'holdComment', 'releaseTime', 'releaseEmp', 'releaseComment'];
const ncrFields = ['ncrId', 'ncrDate'];
const commentFields = ['comment', 'commentDate', 'commentEmp', 'futureHoldComment'];
const otherFields = ['owner', 'startDate', 'tmttRemaining', 'dataUpdateDate'];
</script>

<template>
  <section v-if="lotId" class="lot-detail-panel show">
    <div class="lot-detail-header">
      <div class="lot-detail-title">
        Lot Detail -
        <span class="lot-id">{{ lotId }}</span>
      </div>
      <button type="button" class="lot-detail-close" @click="emit('close')">Close</button>
    </div>

    <div class="lot-detail-content">
      <div v-if="loading" class="lot-detail-loading">
        <span class="loading-spinner"></span>
        Loading...
      </div>

      <div v-else-if="errorMessage" class="lot-detail-loading error">{{ errorMessage }}</div>

      <div v-else-if="detail" class="lot-detail-grid">
        <div class="lot-detail-section">
          <div class="lot-detail-section-title">基本資訊</div>
          <div v-for="field in basicFields" :key="field" class="lot-detail-field">
            <span class="lot-detail-label">{{ getLabel(field) }}</span>
            <span class="lot-detail-value" :class="fieldClass(field)">{{ fieldValue(field) }}</span>
          </div>
        </div>

        <div class="lot-detail-section">
          <div class="lot-detail-section-title">產品資訊</div>
          <div v-for="field in productFields" :key="field" class="lot-detail-field">
            <span class="lot-detail-label">{{ getLabel(field) }}</span>
            <span class="lot-detail-value">{{ fieldValue(field) }}</span>
          </div>
        </div>

        <div class="lot-detail-section">
          <div class="lot-detail-section-title">製程資訊</div>
          <div v-for="field in processFields" :key="field" class="lot-detail-field">
            <span class="lot-detail-label">{{ getLabel(field) }}</span>
            <span class="lot-detail-value">{{ fieldValue(field) }}</span>
          </div>
        </div>

        <div class="lot-detail-section">
          <div class="lot-detail-section-title">物料資訊</div>
          <div v-for="field in materialFields" :key="field" class="lot-detail-field">
            <span class="lot-detail-label">{{ getLabel(field) }}</span>
            <span class="lot-detail-value">{{ fieldValue(field) }}</span>
          </div>
        </div>

        <div v-if="hasHoldSection()" class="lot-detail-section">
          <div class="lot-detail-section-title">Hold 資訊</div>
          <div v-for="field in holdFields" :key="field" class="lot-detail-field">
            <span class="lot-detail-label">{{ getLabel(field) }}</span>
            <span class="lot-detail-value">{{ fieldValue(field) }}</span>
          </div>
        </div>

        <div v-if="detail.ncrId" class="lot-detail-section">
          <div class="lot-detail-section-title">NCR 資訊</div>
          <div v-for="field in ncrFields" :key="field" class="lot-detail-field">
            <span class="lot-detail-label">{{ getLabel(field) }}</span>
            <span class="lot-detail-value">{{ fieldValue(field) }}</span>
          </div>
        </div>

        <div class="lot-detail-section">
          <div class="lot-detail-section-title">備註資訊</div>
          <div v-for="field in commentFields" :key="field" class="lot-detail-field">
            <span class="lot-detail-label">{{ getLabel(field) }}</span>
            <span class="lot-detail-value">{{ fieldValue(field) }}</span>
          </div>
        </div>

        <div class="lot-detail-section">
          <div class="lot-detail-section-title">其他資訊</div>
          <div v-for="field in otherFields" :key="field" class="lot-detail-field">
            <span class="lot-detail-label">{{ getLabel(field) }}</span>
            <span class="lot-detail-value">{{ fieldValue(field) }}</span>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>
