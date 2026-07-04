// @vitest-environment jsdom
/**
 * Unit tests for AiChatMessage.vue — leader-mode subtask results block
 *
 * Change: ai-leader-subagent
 * - subtasks present → collapsible「子任務結果」block with per-subtask
 *   goal, answer, and success/failure badge
 * - subtasks absent/empty → block not rendered (non-leader modes unaffected)
 */

import { describe, it, expect, vi } from 'vitest';
import { mount } from '@vue/test-utils';
import { defineComponent } from 'vue';
import AiChatMessage from '../AiChatMessage.vue';

// Stub AiChartRenderer — it pulls in echarts, which is irrelevant here.
vi.mock('../AiChartRenderer.vue', () => ({
  default: defineComponent({
    name: 'AiChartRenderer',
    template: '<div class="ai-chart-renderer-stub" />',
  }),
}));

interface TestMessage {
  role: 'user' | 'ai' | 'clarification' | 'error' | 'loading';
  content?: string;
  subtasks?: Array<{ goal: string; answer: string; success: boolean }>;
}

function mountAiMessage(message: TestMessage) {
  return mount(AiChatMessage, { props: { message } });
}

describe('AiChatMessage subtasks block', () => {
  it('renders goal, answer, and status badge for each subtask', () => {
    const wrapper = mountAiMessage({
      role: 'ai',
      content: '綜合回答',
      subtasks: [
        { goal: '查詢近 7 天不良率趨勢', answer: '不良率 2.1%', success: true },
        { goal: '查詢目前 Hold 摘要', answer: '（子任務執行失敗：timeout）', success: false },
      ],
    });

    const summary = wrapper.findAll('.ai-sql-summary').map((s) => s.text());
    expect(summary.some((t) => t.includes('子任務結果 (2)'))).toBe(true);

    const items = wrapper.findAll('.ai-subtask-item');
    expect(items).toHaveLength(2);
    expect(items[0].find('.ai-subtask-goal').text()).toBe('查詢近 7 天不良率趨勢');
    expect(items[0].find('.ai-subtask-answer').text()).toBe('不良率 2.1%');
    expect(items[0].find('.shared-status-badge').text()).toBe('成功');
    expect(items[0].find('.shared-status-badge').classes()).toContain('tone-success');
    expect(items[1].find('.shared-status-badge').text()).toBe('失敗');
    expect(items[1].find('.shared-status-badge').classes()).toContain('tone-danger');
  });

  it('does not render the block when subtasks is empty', () => {
    const wrapper = mountAiMessage({
      role: 'ai',
      content: '一般回答',
      subtasks: [],
    });

    expect(wrapper.find('.ai-subtask-item').exists()).toBe(false);
    expect(wrapper.text()).not.toContain('子任務結果');
  });

  it('does not render the block when subtasks is absent (non-leader modes)', () => {
    const wrapper = mountAiMessage({
      role: 'ai',
      content: '一般回答',
    });

    expect(wrapper.find('.ai-subtask-item').exists()).toBe(false);
  });
});
