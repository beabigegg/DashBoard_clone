// @vitest-environment jsdom
import { describe, it, expect, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { defineComponent } from 'vue'

// Mock portal-shell navigation manifest (external JS module)
vi.mock('../../portal-shell/navigationManifest.js', () => ({
  routes: {},
}))

// Mock shared-ui PageHeader component
vi.mock('../../shared-ui/components/PageHeader.vue', () => ({
  default: defineComponent({
    name: 'PageHeader',
    props: ['title', 'refreshing'],
    emits: ['refresh'],
    template: '<div class="page-header-stub"><slot name="subtitle" /></div>',
  }),
}))

// Mock PagesManagementPanel so App.test stays unit-scope
vi.mock('../components/PagesManagementPanel.vue', () => ({
  default: defineComponent({
    name: 'PagesManagementPanel',
    props: ['pages'],
    emits: ['update'],
    template: '<div class="pages-panel-stub" />',
  }),
}))

// Mock apiGet to reject so we can trigger the error path
vi.mock('../../core/api', () => ({
  apiGet: vi.fn().mockRejectedValue(new Error('網路錯誤')),
}))

import App from '../App.vue'

describe('App — load-error panel exposes role="alert"', () => {
  it('load_error_panel_has_role_alert', async () => {
    const wrapper = mount(App, { attachTo: document.body })
    // Wait for onMounted async flow to complete (apiGet rejects → errorMessage set)
    await flushPromises()
    const errorPanel = wrapper.find('.error-panel')
    expect(errorPanel.exists()).toBe(true)
    expect(errorPanel.attributes('role')).toBe('alert')
  })
})
