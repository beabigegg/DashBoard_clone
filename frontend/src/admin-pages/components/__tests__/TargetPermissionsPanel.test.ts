// @vitest-environment jsdom
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import TargetPermissionsPanel from '../TargetPermissionsPanel.vue'

describe('TargetPermissionsPanel — renders whitelist and toggles', () => {
  it('renders empty state when no permissions granted', () => {
    const wrapper = mount(TargetPermissionsPanel, { props: { permissions: [] } })
    expect(wrapper.find('[data-testid="pa-permissions-empty"]').exists()).toBe(true)
  })

  it('renders a row per permission with aria-pressed reflecting can_edit_targets', () => {
    const wrapper = mount(TargetPermissionsPanel, {
      props: {
        permissions: [
          { user_identifier: 'alice', can_edit_targets: true, granted_at: '2026-01-01', granted_by: 'admin' },
          { user_identifier: 'bob', can_edit_targets: false, granted_at: '2026-01-02', granted_by: 'admin' },
        ],
      },
    })
    const toggles = wrapper.findAll('[data-testid="pa-permissions-toggle"]')
    expect(toggles).toHaveLength(2)
    expect(toggles[0].attributes('aria-pressed')).toBe('true')
    expect(toggles[1].attributes('aria-pressed')).toBe('false')
  })

  it('emits toggle with the flipped value when clicking a row toggle', async () => {
    const wrapper = mount(TargetPermissionsPanel, {
      props: {
        permissions: [
          { user_identifier: 'alice', can_edit_targets: true, granted_at: '2026-01-01', granted_by: 'admin' },
        ],
      },
    })
    await wrapper.find('[data-testid="pa-permissions-toggle"]').trigger('click')
    expect(wrapper.emitted('toggle')).toEqual([['alice', false]])
  })

  it('emits grantNew with the trimmed input value', async () => {
    const wrapper = mount(TargetPermissionsPanel, { props: { permissions: [] } })
    const input = wrapper.find('[data-testid="pa-permissions-new-user-input"]')
    await input.setValue('  charlie  ')
    await wrapper.find('[data-testid="pa-permissions-new-user-btn"]').trigger('click')
    expect(wrapper.emitted('grantNew')).toEqual([['charlie']])
  })

  it('does not emit grantNew when input is empty', async () => {
    const wrapper = mount(TargetPermissionsPanel, { props: { permissions: [] } })
    await wrapper.find('[data-testid="pa-permissions-new-user-btn"]').trigger('click')
    expect(wrapper.emitted('grantNew')).toBeUndefined()
  })
})
