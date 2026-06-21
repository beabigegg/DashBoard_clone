/**
 * E2E tests: AI query panel (AI 助手)
 *
 * Scenarios covered — real user query flows:
 *   trigger visible    — ai_query_enabled:true → .ai-chat-trigger appears
 *   trigger hidden     — ai_query_enabled:false → no trigger
 *   open / close       — click trigger → panel opens; click X → closes
 *   empty state        — panel shows hint text before any query
 *   happy path query   — type question → send → user bubble → loading → AI answer
 *   clarification      — AI returns needs_clarification → clarification bubble + suggestion chips
 *   suggestion click   — click chip re-submits that question → new answer appears
 *   API error          — 500 response → .ai-msg-error bubble visible
 *   rate limit 429     — 429 response → error bubble + input disabled
 *   clear history      — 清除紀錄 → messages cleared, empty state returns
 *   keyboard submit    — Enter key submits question
 *
 * Network strategy:
 *   All mocked. Navigate to /portal-shell with ai_query_enabled:true in nav mock.
 *   AI panel is rendered by the portal-shell; no specific page route needed.
 */

import { test, expect, type Page } from '@playwright/test';

const BASE_URL = process.env.E2E_BASE_URL || 'http://127.0.0.1:8080';
const SHELL_URL = `${BASE_URL}/portal-shell`;

// ---------------------------------------------------------------------------
// Navigation mock helpers
// ---------------------------------------------------------------------------

function buildNavMock(aiEnabled: boolean) {
  return {
    drawers: [
      {
        id: 'reports',
        name: '即時報表',
        order: 1,
        admin_only: false,
        pages: [
          { route: '/hold-overview', name: 'Hold 即時概況', status: 'released', order: 1 },
        ],
      },
    ],
    is_admin: false,
    admin_links: { logout: '/api/auth/logout' },
    portal_spa_enabled: false,
    features: { ai_query_enabled: aiEnabled },
    diagnostics: {
      filtered_drawers: 0,
      filtered_pages: 0,
      invalid_drawers: 0,
      invalid_pages: 0,
      contract_mismatch_routes: [],
    },
  };
}

async function setupPortalMocks(page: Page, aiEnabled: boolean): Promise<void> {
  await page.route('**/*', (route) => route.continue());
  await page.route('**/api/auth/me**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ success: true, data: { name: 'Tester', role: 'user', is_admin: false } }),
    }),
  );
  await page.route('**/api/portal/navigation**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(buildNavMock(aiEnabled)),
    }),
  );
  await page.route('**/api/auth/heartbeat**', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ok: true }) }),
  );
}

async function gotoShell(page: Page): Promise<void> {
  await page.goto(SHELL_URL, { timeout: 30_000 }).catch(() => {});
  // Wait for shell navigation to finish bootstrapping
  await page.waitForSelector('nav', { timeout: 20_000 });
}

async function openAiPanel(page: Page): Promise<void> {
  await page.locator('button[aria-label="開啟 AI 助手"]').click();
  await page.waitForSelector('.ai-chat-panel', { timeout: 5_000 });
}

// ---------------------------------------------------------------------------
// Tests — visibility
// ---------------------------------------------------------------------------

test('test_trigger_visible_when_ai_enabled', async ({ page }) => {
  await setupPortalMocks(page, true);
  await gotoShell(page);
  await expect(page.locator('button[aria-label="開啟 AI 助手"]')).toBeVisible({ timeout: 10_000 });
});

test('test_trigger_hidden_when_ai_disabled', async ({ page }) => {
  await setupPortalMocks(page, false);
  await gotoShell(page);
  // Give the shell time to fully initialize
  await page.waitForTimeout(2_000);
  await expect(page.locator('button[aria-label="開啟 AI 助手"]')).toBeHidden();
});

// ---------------------------------------------------------------------------
// Tests — panel open / close
// ---------------------------------------------------------------------------

test('test_panel_opens_and_shows_empty_state', async ({ page }) => {
  await setupPortalMocks(page, true);
  await gotoShell(page);

  await openAiPanel(page);

  // Panel visible with header
  await expect(page.locator('.ai-chat-panel')).toBeVisible();
  const panelText = await page.locator('.ai-chat-panel').textContent();
  expect(panelText).toContain('AI 助手');

  // Empty state hint shown
  await expect(page.locator('.ai-chat-empty')).toBeVisible();
  const emptyText = await page.locator('.ai-chat-empty').textContent();
  expect(emptyText).toContain('請輸入您的問題');
});

test('test_panel_closes_on_x_button', async ({ page }) => {
  await setupPortalMocks(page, true);
  await gotoShell(page);

  await openAiPanel(page);
  await expect(page.locator('.ai-chat-panel')).toBeVisible();

  await page.locator('.ai-chat-btn-close').click();
  await expect(page.locator('.ai-chat-panel')).toBeHidden({ timeout: 3_000 });
});

// ---------------------------------------------------------------------------
// Tests — real user query flows
// ---------------------------------------------------------------------------

test('test_question_submit_shows_user_bubble_then_ai_answer', async ({ page }) => {
  await setupPortalMocks(page, true);

  // Mock AI query — returns a plain answer
  await page.route('**/api/ai/query**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        data: {
          answer: '最近 7 天 WB 線不良率為 0.8%，比上週改善 0.1%。',
          needs_clarification: false,
          suggestions: [],
          chart_data: null,
          query_used: 'yield_trend',
        },
      }),
    }),
  );

  await gotoShell(page);
  await openAiPanel(page);

  // Type question and submit
  await page.locator('.ai-chat-textarea').fill('WB 線最近 7 天不良率如何？');
  await page.locator('.ai-chat-btn-send').click();

  // User bubble appears immediately
  const userBubble = page.locator('.ai-chat-msg--user .ai-msg-user');
  await expect(userBubble).toBeVisible({ timeout: 5_000 });
  expect(await userBubble.textContent()).toContain('WB 線最近 7 天不良率如何？');

  // AI answer appears after API response
  const aiAnswer = page.locator('.ai-chat-msg--ai .ai-msg-ai');
  await expect(aiAnswer).toBeVisible({ timeout: 10_000 });
  expect(await aiAnswer.textContent()).toContain('0.8%');

  // Textarea cleared after submission
  expect(await page.locator('.ai-chat-textarea').inputValue()).toBe('');
});

test('test_loading_indicator_shown_during_query', async ({ page }) => {
  await setupPortalMocks(page, true);

  // Slow API — gives us time to observe loading state
  await page.route('**/api/ai/query**', async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 1_500));
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ data: { answer: '查詢完成', needs_clarification: false } }),
    });
  });

  await gotoShell(page);
  await openAiPanel(page);

  await page.locator('.ai-chat-textarea').fill('設備稼動率？');
  await page.locator('.ai-chat-btn-send').click();

  // Loading dots visible while waiting
  await expect(page.locator('.ai-typing-indicator')).toBeVisible({ timeout: 3_000 });

  // Answer eventually appears
  await expect(page.locator('.ai-chat-msg--ai .ai-msg-ai')).toBeVisible({ timeout: 10_000 });
});

test('test_clarification_response_shows_suggestion_chips', async ({ page }) => {
  await setupPortalMocks(page, true);

  await page.route('**/api/ai/query**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        data: {
          answer: '請問您想查詢哪條線的不良率？',
          needs_clarification: true,
          suggestions: ['WB 線', 'DA 線', '全部線別'],
          chart_data: null,
        },
      }),
    }),
  );

  await gotoShell(page);
  await openAiPanel(page);

  await page.locator('.ai-chat-textarea').fill('不良率是多少？');
  await page.locator('.ai-chat-btn-send').click();

  // Clarification bubble appears
  const clarification = page.locator('.ai-chat-msg--clarification');
  await expect(clarification).toBeVisible({ timeout: 10_000 });
  expect(await clarification.textContent()).toContain('請問您想查詢哪條線的不良率？');

  // Suggestion chips render
  const chips = page.locator('.ai-suggestion-chip');
  await expect(chips.first()).toBeVisible({ timeout: 5_000 });
  const chipTexts = await chips.allTextContents();
  expect(chipTexts).toContain('WB 線');
  expect(chipTexts).toContain('DA 線');
});

test('test_clicking_suggestion_chip_submits_follow_up', async ({ page }) => {
  await setupPortalMocks(page, true);

  let callCount = 0;
  await page.route('**/api/ai/query**', async (route) => {
    callCount++;
    if (callCount === 1) {
      // First call → clarification
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          data: {
            answer: '請問您想查詢哪條線？',
            needs_clarification: true,
            suggestions: ['WB 線', 'DA 線'],
          },
        }),
      });
    } else {
      // Second call (after chip click) → real answer
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          data: {
            answer: 'WB 線本週不良率 0.8%。',
            needs_clarification: false,
            suggestions: [],
          },
        }),
      });
    }
  });

  await gotoShell(page);
  await openAiPanel(page);

  await page.locator('.ai-chat-textarea').fill('不良率？');
  await page.locator('.ai-chat-btn-send').click();

  // Wait for suggestion chips
  await expect(page.locator('.ai-suggestion-chip').first()).toBeVisible({ timeout: 10_000 });

  // Click "WB 線" chip
  await page.locator('.ai-suggestion-chip', { hasText: 'WB 線' }).click();

  // Follow-up answer appears
  const answers = page.locator('.ai-chat-msg--ai .ai-msg-ai');
  await expect(answers.last()).toContainText('WB 線本週不良率 0.8%', { timeout: 10_000 });
});

// ---------------------------------------------------------------------------
// Tests — error scenarios (使用者仍需看到有意義的回饋)
// ---------------------------------------------------------------------------

test('test_api_500_shows_error_bubble', async ({ page }) => {
  await setupPortalMocks(page, true);

  await page.route('**/api/ai/query**', (route) =>
    route.fulfill({
      status: 500,
      contentType: 'application/json',
      body: JSON.stringify({ error: { message: '查詢服務暫時無法使用，請稍後再試。' } }),
    }),
  );

  await gotoShell(page);
  await openAiPanel(page);

  await page.locator('.ai-chat-textarea').fill('有多少 lot 在 hold？');
  await page.locator('.ai-chat-btn-send').click();

  // Error bubble with message visible (not just silent failure)
  const errorBubble = page.locator('.ai-chat-msg--error .ai-msg-error');
  await expect(errorBubble).toBeVisible({ timeout: 10_000 });
  expect(await errorBubble.textContent()).toContain('查詢服務暫時無法使用');

  // Input should be re-enabled so user can retry
  await expect(page.locator('.ai-chat-textarea')).toBeEnabled({ timeout: 3_000 });
});

test('test_rate_limit_429_shows_error_and_disables_input', async ({ page }) => {
  await setupPortalMocks(page, true);

  await page.route('**/api/ai/query**', (route) =>
    route.fulfill({ status: 429, contentType: 'application/json',
      body: JSON.stringify({ error: { message: 'Too many requests' } }) }),
  );

  await gotoShell(page);
  await openAiPanel(page);

  await page.locator('.ai-chat-textarea').fill('查詢設備稼動率');
  await page.locator('.ai-chat-btn-send').click();

  // Error bubble about rate limit
  const errorBubble = page.locator('.ai-chat-msg--error .ai-msg-error');
  await expect(errorBubble).toBeVisible({ timeout: 10_000 });
  expect(await errorBubble.textContent()).toContain('請稍候');

  // Input disabled while rate-limited (notice text appears in place of textarea)
  await expect(page.locator('.ai-chat-input-notice')).toBeVisible({ timeout: 3_000 });
});

// ---------------------------------------------------------------------------
// Tests — clear history
// ---------------------------------------------------------------------------

test('test_clear_history_resets_to_empty_state', async ({ page }) => {
  await setupPortalMocks(page, true);

  await page.route('**/api/ai/query**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ data: { answer: '回答在這裡', needs_clarification: false } }),
    }),
  );

  await gotoShell(page);
  await openAiPanel(page);

  // Submit a question to produce messages
  await page.locator('.ai-chat-textarea').fill('測試問題');
  await page.locator('.ai-chat-btn-send').click();
  await expect(page.locator('.ai-chat-msg--ai .ai-msg-ai')).toBeVisible({ timeout: 10_000 });

  // Clear history
  await page.locator('.ai-chat-btn-reset').click();

  // Back to empty state
  await expect(page.locator('.ai-chat-empty')).toBeVisible({ timeout: 5_000 });
  const msgCount = await page.locator('.ai-chat-msg').count();
  expect(msgCount).toBe(0);
});

// ---------------------------------------------------------------------------
// Tests — keyboard accessibility
// ---------------------------------------------------------------------------

test('test_enter_key_submits_question', async ({ page }) => {
  await setupPortalMocks(page, true);

  await page.route('**/api/ai/query**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ data: { answer: '鍵盤送出成功', needs_clarification: false } }),
    }),
  );

  await gotoShell(page);
  await openAiPanel(page);

  await page.locator('.ai-chat-textarea').fill('按 Enter 送出');
  await page.keyboard.press('Enter');

  // User bubble and answer appear without clicking send button
  await expect(page.locator('.ai-chat-msg--user .ai-msg-user')).toBeVisible({ timeout: 5_000 });
  await expect(page.locator('.ai-chat-msg--ai .ai-msg-ai')).toBeVisible({ timeout: 10_000 });
  expect(await page.locator('.ai-chat-msg--ai .ai-msg-ai').textContent()).toContain('鍵盤送出成功');
});
