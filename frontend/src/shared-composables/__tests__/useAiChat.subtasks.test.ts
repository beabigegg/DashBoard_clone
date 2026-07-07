/**
 * Unit tests for useAiChat — leader-mode `subtasks` field parsing
 *
 * Change: ai-leader-subagent
 * - subtasks array in response data is parsed onto the AI message
 * - missing / non-array subtasks degrade to []
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { useAiChat } from '../useAiChat';

function mockFetchResponse(data: Record<string, unknown>): void {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ data }),
    }),
  );
}

describe('useAiChat subtasks parsing', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it('parses leader-mode subtasks onto the AI message', async () => {
    mockFetchResponse({
      answer: '綜合回答',
      chart_data: null,
      query_used: 'wip_hold_summary',
      subtasks: [
        { goal: '查詢近 7 天不良率趨勢', answer: '不良率 2.1%', success: true },
        { goal: '查詢目前 Hold 摘要', answer: '（子任務執行失敗：timeout）', success: false },
      ],
    });

    const chat = useAiChat();
    await chat.submitQuestion('DB 不良率和 Hold 狀況');

    const aiMsg = chat.messages.value[chat.messages.value.length - 1];
    expect(aiMsg.role).toBe('ai');
    expect(aiMsg.subtasks).toHaveLength(2);
    expect(aiMsg.subtasks?.[0]).toEqual({
      goal: '查詢近 7 天不良率趨勢',
      answer: '不良率 2.1%',
      success: true,
    });
    expect(aiMsg.subtasks?.[1].success).toBe(false);
  });

  it('defaults subtasks to [] when the field is absent (non-leader modes)', async () => {
    mockFetchResponse({
      answer: '一般回答',
      chart_data: null,
      query_used: 'text2sql',
    });

    const chat = useAiChat();
    await chat.submitQuestion('今天不良率');

    const aiMsg = chat.messages.value[chat.messages.value.length - 1];
    expect(aiMsg.subtasks).toEqual([]);
  });

  it('defaults subtasks to [] when the field is not an array', async () => {
    mockFetchResponse({
      answer: '回答',
      subtasks: 'not-an-array',
    });

    const chat = useAiChat();
    await chat.submitQuestion('查詢');

    const aiMsg = chat.messages.value[chat.messages.value.length - 1];
    expect(aiMsg.subtasks).toEqual([]);
  });

  it('keeps the latest request loading state when a previous request is aborted', async () => {
    vi.useRealTimers();
    let resolveSecond: ((value: unknown) => void) | undefined;

    const fetchMock = vi.fn()
      .mockImplementationOnce((_url: string, init?: RequestInit) => new Promise((_resolve, reject) => {
        init?.signal?.addEventListener(
          'abort',
          () => reject(new DOMException('Aborted', 'AbortError')),
          { once: true },
        );
      }))
      .mockImplementationOnce(() => new Promise((resolve) => {
        resolveSecond = resolve;
      }));
    vi.stubGlobal('fetch', fetchMock);

    const chat = useAiChat();
    const first = chat.submitQuestion('第一個問題');
    const second = chat.submitQuestion('第二個問題');

    await first;
    expect(chat.isLoading.value).toBe(true);

    resolveSecond?.({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ data: { answer: '第二個回答' } }),
    });
    await second;

    expect(chat.isLoading.value).toBe(false);
    expect(chat.messages.value.at(-1)).toMatchObject({ role: 'ai', content: '第二個回答' });
  });
});
