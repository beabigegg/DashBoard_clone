// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const { mockStore } = vi.hoisted(() => ({
  mockStore: {
    permissions: [] as unknown[],
    shouldFailLoad: false,
    pendingGet: null as Promise<{ data: unknown[] }> | null,
  },
}))

vi.mock('../../../core/api.js', () => ({
  apiGet: async () => {
    if (mockStore.pendingGet) return mockStore.pendingGet
    if (mockStore.shouldFailLoad) throw new Error('load failed')
    return { data: mockStore.permissions }
  },
}))

// @ts-expect-error — JS SFC
import PermissionsTab from '../PermissionsTab.vue'

function mountTab(permissions: unknown[] = []) {
  mockStore.permissions = permissions
  mockStore.shouldFailLoad = false
  mockStore.pendingGet = null
  return mount(PermissionsTab, { attachTo: document.body })
}

const ROW_ALICE = { user_identifier: 'alice', can_edit_targets: true, granted_at: '2026-01-01', granted_by: 'admin' }
const ROW_BOB = { user_identifier: 'bob', can_edit_targets: false, granted_at: '2026-01-02', granted_by: 'admin' }

describe('PermissionsTab — fetch + render (AC-1/AC-2)', () => {
  let fetchMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    document.body.innerHTML = ''
    fetchMock = vi.fn(async () => ({
      ok: true,
      json: async () => ({ success: true, data: null }),
    })) as unknown as ReturnType<typeof vi.fn>
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('mounts and renders the permissions fetched from GET', async () => {
    const w = mountTab([ROW_ALICE, ROW_BOB])
    await flushPromises()
    const toggles = w.findAll('[data-testid="pa-permissions-toggle"]')
    expect(toggles).toHaveLength(2)
  })

  it('renders empty state when no permissions granted', async () => {
    const w = mountTab([])
    await flushPromises()
    expect(w.find('[data-testid="pa-permissions-empty"]').exists()).toBe(true)
  })

  it('shows a loading indicator (not the false empty-state) while the initial fetch is pending', async () => {
    let resolveGet: (value: { data: unknown[] }) => void = () => {}
    mockStore.pendingGet = new Promise((resolve) => {
      resolveGet = resolve
    })
    const w = mount(PermissionsTab, { attachTo: document.body })
    await w.vm.$nextTick()

    expect(w.find('[data-testid="loading-state"]').exists()).toBe(true)
    expect(w.find('[data-testid="pa-permissions-empty"]').exists()).toBe(false)

    mockStore.pendingGet = null
    resolveGet({ data: [] })
    await flushPromises()

    expect(w.find('[data-testid="loading-state"]').exists()).toBe(false)
    expect(w.find('[data-testid="pa-permissions-empty"]').exists()).toBe(true)
  })

  it('shows an error banner when the initial load fails', async () => {
    mockStore.shouldFailLoad = true
    const w = mount(PermissionsTab, { attachTo: document.body })
    await new Promise((r) => setTimeout(r, 0))
    await flushPromises()
    expect(w.find('[data-testid="error-banner"]').text()).toContain('load failed')
  })
})

describe('PermissionsTab — toggle/grantNew round-trip (AC-3)', () => {
  let fetchMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    document.body.innerHTML = ''
    fetchMock = vi.fn(async () => ({
      ok: true,
      json: async () => ({ success: true, data: { user_identifier: 'alice', can_edit_targets: false } }),
    })) as unknown as ReturnType<typeof vi.fn>
    vi.stubGlobal('fetch', fetchMock)
    vi.stubGlobal('alert', vi.fn())
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('toggling a row PUTs to the permission endpoint and refetches', async () => {
    mockStore.permissions = [ROW_ALICE]
    const w = mountTab([ROW_ALICE])
    await flushPromises()

    await w.find('[data-testid="pa-permissions-toggle"]').trigger('click')
    await flushPromises()

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url, options] = fetchMock.mock.calls[0]
    expect(url).toBe('/admin/api/production-achievement/permissions/alice')
    expect(options.method).toBe('PUT')
    expect(JSON.parse(options.body)).toEqual({ can_edit_targets: false })
  })

  it('granting a new user PUTs can_edit_targets true for the trimmed identifier', async () => {
    mockStore.permissions = []
    const w = mountTab([])
    await flushPromises()

    const input = w.find('[data-testid="pa-permissions-new-user-input"]')
    await input.setValue('  charlie  ')
    await w.find('[data-testid="pa-permissions-new-user-btn"]').trigger('click')
    await flushPromises()

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url, options] = fetchMock.mock.calls[0]
    expect(url).toBe('/admin/api/production-achievement/permissions/charlie')
    expect(options.method).toBe('PUT')
    expect(JSON.parse(options.body)).toEqual({ can_edit_targets: true })
  })

  it('alerts and still refetches when the PUT fails', async () => {
    fetchMock.mockImplementation(async () => ({
      ok: false,
      status: 500,
      json: async () => ({ success: false, error: 'boom' }),
    }))
    mockStore.permissions = [ROW_ALICE]
    const w = mountTab([ROW_ALICE])
    await flushPromises()

    await w.find('[data-testid="pa-permissions-toggle"]').trigger('click')
    await flushPromises()

    expect(window.alert).toHaveBeenCalled()
  })
})

describe('PermissionsTab — refresh() exposed for tab-switch convention (AC-1)', () => {
  it('exposes a refresh() method callable by the parent App.vue', async () => {
    mockStore.permissions = [ROW_ALICE]
    const w = mountTab([ROW_ALICE])
    await w.vm.$nextTick()
    await (w.vm as unknown as { refresh: () => Promise<void> }).refresh()
    await w.vm.$nextTick()
    expect(w.findAll('[data-testid="pa-permissions-toggle"]')).toHaveLength(1)
  })
})
