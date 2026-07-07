import { computed, ref } from 'vue';
import type { Ref, ComputedRef } from 'vue';

export type MessageRole = 'user' | 'ai' | 'error' | 'clarification';

/** Leader-mode (AI_MODE=leader) subtask result — additive backend field. */
export interface AiSubtask {
  goal: string;
  answer: string;
  success: boolean;
}

export interface AiMessage {
  role: MessageRole;
  content: string;
  chartData?: unknown | null;
  queryUsed?: string | null;
  paramsUsed?: unknown | null;
  suggestions?: string[];
  sqlUsed?: string | null;
  toolTrace?: unknown[];
  missingSlots?: string[];
  queryState?: unknown | null;
  subtasks?: AiSubtask[];
}

export interface AiChatComposable {
  messages: Ref<AiMessage[]>;
  isOpen: Ref<boolean>;
  isLoading: Ref<boolean>;
  isRateLimited: Ref<boolean>;
  loadingStepText: Ref<string>;
  canSubmit: ComputedRef<boolean>;
  togglePanel: () => void;
  clearHistory: () => void;
  submitQuestion: (question: string) => Promise<void>;
  submitSuggestion: (text: string) => Promise<void>;
}

/**
 * Composable for AI Chat panel state and API interaction.
 * Each question is an independent query — no conversation history sent to backend.
 */
export function useAiChat(): AiChatComposable {
  const messages: Ref<AiMessage[]> = ref([]);
  const isOpen: Ref<boolean> = ref(false);
  const isLoading: Ref<boolean> = ref(false);
  const isRateLimited: Ref<boolean> = ref(false);
  const loadingStepText: Ref<string> = ref('');
  const conversationId: Ref<string> = ref(createConversationId());

  let rateLimitTimer: ReturnType<typeof setInterval> | null = null;
  let loadingStepTimer: ReturnType<typeof setInterval> | null = null;
  let abortController: AbortController | null = null;
  let activeRequestId = 0;

  const canSubmit: ComputedRef<boolean> = computed(() => !isLoading.value && !isRateLimited.value);

  const _LOADING_STEPS: string[] = [
    '正在分析您的問題...',
    '正在準備查詢...',
    '正在生成報告...',
  ];

  function _startLoadingSteps(): void {
    _clearLoadingSteps();
    let step = 0;
    loadingStepText.value = _LOADING_STEPS[0];
    loadingStepTimer = setInterval(() => {
      step = Math.min(step + 1, _LOADING_STEPS.length - 1);
      loadingStepText.value = _LOADING_STEPS[step];
    }, 3000);
  }

  function _clearLoadingSteps(): void {
    if (loadingStepTimer) {
      clearInterval(loadingStepTimer);
      loadingStepTimer = null;
    }
    loadingStepText.value = '';
  }

  function togglePanel(): void {
    isOpen.value = !isOpen.value;
  }

  function clearHistory(): void {
    messages.value = [];
    conversationId.value = createConversationId();
  }

  async function submitQuestion(question: string): Promise<void> {
    if (!question || !question.trim()) return;

    const trimmed = question.trim();

    if (abortController) {
      abortController.abort();
    }
    const requestId = ++activeRequestId;
    const controller = new AbortController();
    abortController = controller;

    messages.value = [...messages.value, { role: 'user', content: trimmed }];
    isLoading.value = true;
    _startLoadingSteps();

    try {
      const response = await fetch('/api/ai/query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          question: trimmed,
          conversation_id: conversationId.value,
        }),
        signal: controller.signal,
      });

      if (requestId !== activeRequestId) return;

      if (response.status === 429) {
        isRateLimited.value = true;
        messages.value = [
          ...messages.value,
          { role: 'error', content: '請求過於頻繁，請稍候再試。' },
        ];
        startRateLimitCountdown();
        return;
      }

      const payload = await response.json() as {
        error?: { message?: string };
        data?: {
          needs_clarification?: boolean;
          answer?: string;
          chart_data?: unknown;
          query_used?: string;
          params_used?: unknown;
          suggestions?: string[];
          sql_used?: string;
          tool_trace?: unknown[];
          missing_slots?: string[];
          query_state?: unknown;
          subtasks?: AiSubtask[];
        };
        [key: string]: unknown;
      };

      if (requestId !== activeRequestId) return;

      if (!response.ok) {
        const errorMsg = payload?.error?.message || `伺服器錯誤 (${response.status})`;
        messages.value = [...messages.value, { role: 'error', content: errorMsg }];
        return;
      }

      const data = payload.data ?? (payload as unknown as typeof payload.data);
      const isClarification = data?.needs_clarification === true;
      const aiMessage: AiMessage = {
        role: isClarification ? 'clarification' : 'ai',
        content: data?.answer || '',
        chartData: data?.chart_data ?? null,
        queryUsed: data?.query_used ?? null,
        paramsUsed: data?.params_used ?? null,
        suggestions: Array.isArray(data?.suggestions) ? (data.suggestions as string[]) : [],
        sqlUsed: data?.sql_used ?? null,
        toolTrace: Array.isArray(data?.tool_trace) ? (data.tool_trace as unknown[]) : [],
        missingSlots: Array.isArray(data?.missing_slots) ? (data.missing_slots as string[]) : [],
        queryState: data?.query_state ?? null,
        subtasks: Array.isArray(data?.subtasks) ? (data.subtasks as AiSubtask[]) : [],
      };

      if (requestId === activeRequestId) {
        messages.value = [...messages.value, aiMessage];
      }
    } catch (err: unknown) {
      if ((err as Error).name === 'AbortError') return;
      if (requestId !== activeRequestId) return;
      messages.value = [
        ...messages.value,
        { role: 'error', content: (err as Error).message || '網路錯誤，請稍後再試。' },
      ];
    } finally {
      if (requestId === activeRequestId) {
        isLoading.value = false;
        _clearLoadingSteps();
        abortController = null;
      }
    }
  }

  function submitSuggestion(text: string): Promise<void> {
    return submitQuestion(text);
  }

  function startRateLimitCountdown(): void {
    if (rateLimitTimer) clearInterval(rateLimitTimer);
    let remaining = 20;
    rateLimitTimer = setInterval(() => {
      remaining--;
      if (remaining <= 0) {
        clearInterval(rateLimitTimer!);
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

function createConversationId(): string {
  return `ai-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}
