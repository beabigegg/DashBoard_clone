import { computed, reactive, ref } from 'vue';

import { apiPost, ensureMesApiAvailable } from '../../core/api.js';
import { parseInputValues } from '../utils/values.js';

const INPUT_TYPE_OPTIONS = Object.freeze([
  { value: 'lot_id', label: 'LOT ID' },
  { value: 'serial_number', label: '流水號' },
  { value: 'work_order', label: '工單' },
]);

const INPUT_LIMITS = Object.freeze({
  lot_id: 50,
  serial_number: 50,
  work_order: 10,
});

function normalizeInputType(value) {
  const text = String(value || '').trim();
  if (INPUT_LIMITS[text]) {
    return text;
  }
  return 'lot_id';
}

export function useLotResolve(initial = {}) {
  ensureMesApiAvailable();

  const inputType = ref(normalizeInputType(initial.inputType));
  const inputText = ref(String(initial.inputText || ''));

  const resolvedLots = ref([]);
  const notFound = ref([]);
  const expansionInfo = ref({});

  const errorMessage = ref('');
  const successMessage = ref('');

  const loading = reactive({
    resolving: false,
  });

  const inputTypeOptions = INPUT_TYPE_OPTIONS;
  const inputValues = computed(() => parseInputValues(inputText.value));
  const inputLimit = computed(() => INPUT_LIMITS[inputType.value] || 50);

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
    inputType.value = normalizeInputType(nextType);
  }

  function setInputText(text) {
    inputText.value = String(text || '');
  }

  function validateInput(values) {
    if (values.length === 0) {
      return '請輸入 LOT/流水號/工單條件';
    }

    const limit = INPUT_LIMITS[inputType.value] || 50;
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
        { timeout: 60000, silent: true },
      );

      resolvedLots.value = Array.isArray(payload?.data) ? payload.data : [];
      notFound.value = Array.isArray(payload?.not_found) ? payload.not_found : [];
      expansionInfo.value = payload?.expansion_info || {};

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
