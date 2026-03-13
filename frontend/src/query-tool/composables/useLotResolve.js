import { computed, reactive, ref } from 'vue';

import { apiPost, ensureMesApiAvailable } from '../../core/api.js';
import { parseInputValues } from '../utils/values.js';

const INPUT_TYPE_OPTIONS = Object.freeze([
  { value: 'wafer_lot', label: 'Wafer LOT' },
  { value: 'lot_id', label: 'LOT ID' },
  { value: 'serial_number', label: '流水號' },
  { value: 'work_order', label: '工單' },
  { value: 'gd_work_order', label: 'GD 工單' },
  { value: 'gd_lot_id', label: 'GD LOT ID' },
]);

const INPUT_LIMITS = Object.freeze({
  wafer_lot: 100,
  lot_id: 100,
  serial_number: 100,
  work_order: 30,
  gd_work_order: 100,
  gd_lot_id: 100,
});

function normalizeInputType(value) {
  const text = String(value || '').trim();
  if (INPUT_LIMITS[text]) {
    return text;
  }
  return 'lot_id';
}

function normalizeAllowedTypes(input) {
  const values = Array.isArray(input)
    ? input.map((item) => String(item || '').trim()).filter(Boolean)
    : [];
  const filtered = values.filter((value) => Boolean(INPUT_LIMITS[value]));
  if (filtered.length === 0) {
    return ['wafer_lot', 'lot_id', 'serial_number', 'work_order', 'gd_work_order', 'gd_lot_id'];
  }
  return filtered;
}

export function useLotResolve(initial = {}) {
  ensureMesApiAvailable();

  const allowedTypes = normalizeAllowedTypes(initial.allowedTypes);
  const optionPool = INPUT_TYPE_OPTIONS.filter((option) => allowedTypes.includes(option.value));
  const defaultType = optionPool[0]?.value || 'lot_id';

  const inputType = ref(normalizeInputType(initial.inputType));
  if (!allowedTypes.includes(inputType.value)) {
    inputType.value = defaultType;
  }
  const inputText = ref(String(initial.inputText || ''));

  const resolvedLots = ref([]);
  const notFound = ref([]);
  const expansionInfo = ref({});

  const errorMessage = ref('');
  const successMessage = ref('');

  const loading = reactive({
    resolving: false,
  });

  const inputTypeOptions = optionPool;
  const inputValues = computed(() => parseInputValues(inputText.value));
  const inputLimit = computed(() => INPUT_LIMITS[inputType.value] || INPUT_LIMITS.lot_id);

  function clearMessages() {
    errorMessage.value = '';
    successMessage.value = '';
  }

  function clearResults() {
    resolvedLots.value = [];
    notFound.value = [];
    expansionInfo.value = {};
  }

  function reset() {
    inputText.value = '';
    clearMessages();
    clearResults();
  }

  function setInputType(nextType) {
    const normalized = normalizeInputType(nextType);
    inputType.value = allowedTypes.includes(normalized) ? normalized : defaultType;
  }

  function setInputText(text) {
    inputText.value = String(text || '');
  }

  function validateInput(values) {
    if (values.length === 0) {
      const labels = inputTypeOptions
        .map((option) => option.label)
        .filter(Boolean)
        .join('/');
      return labels ? `請輸入 ${labels} 條件` : '請輸入查詢條件';
    }

    const limit = INPUT_LIMITS[inputType.value] || INPUT_LIMITS.lot_id;
    if (values.length > limit) {
      return `輸入數量超過上限 (${limit} 筆)`;
    }

    return '';
  }

  async function resolveLots() {
    const values = inputValues.value;
    const validationMessage = validateInput(values);

    if (validationMessage) {
      errorMessage.value = validationMessage;
      return {
        ok: false,
        reason: 'validation',
      };
    }

    clearMessages();
    clearResults();
    loading.resolving = true;

    try {
      const payload = await apiPost(
        '/api/query-tool/resolve',
        {
          input_type: inputType.value,
          values,
        },
        { timeout: 360000, silent: true },
      );

      const inner = payload?.data || {};
      resolvedLots.value = Array.isArray(inner?.data) ? inner.data : [];
      notFound.value = Array.isArray(inner?.not_found) ? inner.not_found : [];
      expansionInfo.value = inner?.expansion_info || {};

      successMessage.value = `解析完成：${resolvedLots.value.length} 筆，未命中 ${notFound.value.length} 筆`;

      return {
        ok: true,
        resolvedLots: resolvedLots.value,
        notFound: notFound.value,
      };
    } catch (error) {
      errorMessage.value = error?.message || '解析失敗';
      return {
        ok: false,
        reason: 'request',
      };
    } finally {
      loading.resolving = false;
    }
  }

  return {
    inputType,
    inputText,
    inputTypeOptions,
    inputValues,
    inputLimit,
    resolvedLots,
    notFound,
    expansionInfo,
    loading,
    errorMessage,
    successMessage,
    clearMessages,
    clearResults,
    reset,
    setInputType,
    setInputText,
    resolveLots,
  };
}
