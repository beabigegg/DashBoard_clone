import { computed, ref } from 'vue';

/**
 * Composable for AI Chat panel state and API interaction.
 * Each question is an independent query — no conversation history sent to backend.
 */
export function useAiChat() {
  const messages = ref([]);
  const isOpen = ref(false);
  const isLoading = ref(false);
  const isRateLimited = ref(false);
  const loadingStepText = ref('');

  let rateLimitTimer = null;
  let loadingStepTimer = null;
  let abortController = null;

  const canSubmit = computed(() => !isLoading.value && !isRateLimited.value);

  const _LOADING_STEPS = [
    '正在分析您的問題...',
    '正在準備查詢...',
    '正在生成報告...',
  ];

  function _startLoadingSteps() {
    let step = 0;
    loadingStepText.value = _LOADING_STEPS[0];
    loadingStepTimer = setInterval(() => {
      step = Math.min(step + 1, _LOADING_STEPS.length - 1);
      loadingStepText.value = _LOADING_STEPS[step];
    }, 3000);
  }

  function _clearLoadingSteps() {
    if (loadingStepTimer) {
      clearInterval(loadingStepTimer);
      loadingStepTimer = null;
    }
    loadingStepText.value = '';
  }

  function togglePanel() {
    isOpen.value = !isOpen.value;
  }

  function clearHistory() {
    messages.value = [];
  }

  async function submitQuestion(question) {
    if (!question || !question.trim()) return;

    const trimmed = question.trim();

    if (abortController) {
      abortController.abort();
    }
    abortController = new AbortController();

    messages.value = [...messages.value, { role: 'user', content: trimmed }];
    isLoading.value = true;
    _startLoadingSteps();

    try {
      const response = await fetch('/api/ai/query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: trimmed }),
        signal: abortController.signal,
      });

      if (response.status === 429) {
        isRateLimited.value = true;
        messages.value = [
          ...messages.value,
          { role: 'error', content: '請求過於頻繁，請稍候再試。' },
        ];
        startRateLimitCountdown();
        return;
      }

      const payload = await response.json();

      if (!response.ok) {
        const errorMsg = payload?.error?.message || `伺服器錯誤 (${response.status})`;
        messages.value = [...messages.value, { role: 'error', content: errorMsg }];
        return;
      }

      const data = payload.data || payload;
      const aiMessage = {
        role: 'ai',
        content: data.answer || '',
        chartData: data.chart_data ?? null,
        queryUsed: data.query_used ?? null,
        paramsUsed: data.params_used ?? null,
        suggestions: Array.isArray(data.suggestions) ? data.suggestions : [],
      };

      messages.value = [...messages.value, aiMessage];
    } catch (err) {
      if (err.name === 'AbortError') return;
      messages.value = [
        ...messages.value,
        { role: 'error', content: err.message || '網路錯誤，請稍後再試。' },
      ];
    } finally {
      isLoading.value = false;
      _clearLoadingSteps();
      abortController = null;
    }
  }

  function submitSuggestion(text) {
    return submitQuestion(text);
  }

  function startRateLimitCountdown() {
    if (rateLimitTimer) clearInterval(rateLimitTimer);
    let remaining = 20;
    rateLimitTimer = setInterval(() => {
      remaining--;
      if (remaining <= 0) {
        clearInterval(rateLimitTimer);
        rateLimitTimer = null;
        isRateLimited.value = false;
      }
    }, 1000);
  }

  return {
    messages,
    isOpen,
    isLoading,
    isRateLimited,
    loadingStepText,
    canSubmit,
    togglePanel,
    clearHistory,
    submitQuestion,
    submitSuggestion,
  };
}
