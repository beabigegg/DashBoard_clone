// @vitest-environment jsdom
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import PagesManagementPanel from '../components/PagesManagementPanel.vue'

describe('PagesManagementPanel — aria-pressed reflects toggle state', () => {
  it('status_toggle_aria_pressed_true_when_released', () => {
    const wrapper = mount(PagesManagementPanel, {
      props: {
        pages: [{ route: '/wip', name: 'WIP Overview', status: 'released' }],
      },
    })
    const btn = wrapper.find('button.status-badge')
    expect(btn.exists()).toBe(true)
    expect(btn.attributes('aria-pressed')).toBe('true')
  })

  it('status_toggle_aria_pressed_false_when_dev', () => {
    const wrapper = mount(PagesManagementPanel, {
      props: {
        pages: [{ route: '/wip', name: 'WIP Overview', status: 'dev' }],
      },
    })
    const btn = wrapper.find('button.status-badge')
    expect(btn.exists()).toBe(true)
    expect(btn.attributes('aria-pressed')).toBe('false')
  })
})
