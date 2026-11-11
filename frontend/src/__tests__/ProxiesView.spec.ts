import { http, HttpResponse } from 'msw'
import { flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeAll, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter, type RouteLocationNormalized } from 'vue-router'

import { navEntries } from '../components/nav-meta'
import { messages } from '../locales'
import { server } from '../mocks/server'
import { routes } from '../router'
import { authGuard } from '../router/guards'
import ProxiesView from '../views/ProxiesView.vue'
import { choose, fill, mountView } from './viewHelpers'

type Wrapper = Awaited<ReturnType<typeof mountView>>['wrapper']

// jsdom no implementa showModal/close de <dialog>.
beforeAll(() => {
  Object.assign(HTMLDialogElement.prototype, {
    showModal(this: HTMLDialogElement) {
      this.setAttribute('open', '')
    },
    close(this: HTMLDialogElement) {
      this.removeAttribute('open')
    },
  })
})

const mount = () => mountView(ProxiesView, '/proxies')

/** Clicks the button with that text; `row` picks the list row (0 = first). */
async function click(wrapper: Wrapper, text: string, row?: number): Promise<void> {
  const scope = row === undefined ? wrapper : wrapper.findAll('tbody tr')[row]!
  await scope
    .findAll('button')
    .find((b) => b.text() === text)!
    .trigger('click')
  await flushPromises()
}

// Saving chains two requests (save and reload the list): a single flush is not enough
// on a slow machine, so wait for the notice.
const saved = (w: Wrapper, text: string) =>
  vi.waitFor(() => expect(w.get('[role="status"]').text()).toBe(text))

const rows = (w: Wrapper) => w.findAll('tbody tr').map((r) => r.findAll('td').map((c) => c.text()))

describe('ProxiesView', () => {
  it('lists the proxies with their status, counters and last use', async () => {
    const { wrapper } = await mount()
    const [first, second] = rows(wrapper)
    expect(first?.slice(0, 4)).toEqual(['http://proxy.example:3128', 'Enabled', '42', '3'])
    expect(first?.[4]).not.toBe('Never')
    expect(second?.slice(1, 5)).toEqual(['Disabled', '0', '0', 'Never'])
    expect([first?.[5], second?.[5]]).toEqual(['IPv4', 'IPv6'])
  })

  it('shows the error if it cannot load the list', async () => {
    server.use(http.get('/api/v1/proxies/', () => new HttpResponse(null, { status: 500 })))
    const { wrapper } = await mount()
    expect(wrapper.get('[role="alert"]').text()).toBe('The server failed. Please try again later.')
  })

  it('adds a proxy and reloads the list', async () => {
    let sent: unknown
    server.use(
      http.post('/api/v1/proxies/', async ({ request }) => {
        sent = await request.json()
        return HttpResponse.json({}, { status: 201 })
      }),
    )
    const { wrapper } = await mount()
    await click(wrapper, 'Add proxy')
    expect(wrapper.find('dialog[open] h2').text()).toBe('New proxy')
    await fill(wrapper, 'Address (http, https, socks5 or socks5h)', 'https://nuevo.example:8080')
    await wrapper.get('form[name="proxy"]').trigger('submit')
    await flushPromises()
    expect(sent).toEqual({ url: 'https://nuevo.example:8080', ip_version: 'ipv4', enabled: true })
    expect(wrapper.find('dialog[open]').exists()).toBe(false)
    await saved(wrapper, 'Proxy added.')
  })

  it('closes the dialogs without saving or deleting', async () => {
    const { wrapper } = await mount()
    await click(wrapper, 'Add proxy')
    await click(wrapper.findAll('dialog')[0] as unknown as Wrapper, 'Close')
    await click(wrapper, 'Delete', 0)
    await click(wrapper.findAll('dialog')[1] as unknown as Wrapper, 'Close')
    expect(wrapper.find('dialog[open]').exists()).toBe(false)
    expect(rows(wrapper)).toHaveLength(2)
  })

  it('adds an IPv6 proxy', async () => {
    let sent: unknown
    server.use(
      http.post('/api/v1/proxies/', async ({ request }) => {
        sent = await request.json()
        return HttpResponse.json({}, { status: 201 })
      }),
    )
    const { wrapper } = await mount()
    await click(wrapper, 'Add proxy')
    await fill(wrapper, 'Address (http, https, socks5 or socks5h)', 'http://[2001:db8::1]:3128')
    await choose(wrapper, 'IP version', 'IPv6')
    await wrapper.get('form[name="proxy"]').trigger('submit')
    await flushPromises()
    expect(sent).toEqual({ url: 'http://[2001:db8::1]:3128', ip_version: 'ipv6', enabled: true })
    await saved(wrapper, 'Proxy added.')
  })

  it('adds a disabled proxy', async () => {
    const { wrapper } = await mount()
    await click(wrapper, 'Add proxy')
    await fill(wrapper, 'Address (http, https, socks5 or socks5h)', 'socks5h://other.example:1080')
    await wrapper.get('form[name="proxy"] input[type="checkbox"]').setValue(false)
    await wrapper.get('form[name="proxy"]').trigger('submit')
    await flushPromises()
    await saved(wrapper, 'Proxy added.')
  })

  it('edits a proxy with its data preloaded', async () => {
    let sent: unknown
    server.use(
      http.patch('/api/v1/proxies/2/', async ({ request }) => {
        sent = await request.json()
        return HttpResponse.json({})
      }),
    )
    const { wrapper } = await mount()
    await click(wrapper, 'Edit', 1)
    expect(wrapper.find('dialog[open] h2').text()).toBe('Edit proxy')
    const input = wrapper.get('form[name="proxy"] input[type="url"]')
    expect((input.element as HTMLInputElement).value).toBe('socks5://socks.example:1080')
    await wrapper.get('form[name="proxy"] input[type="checkbox"]').setValue(true)
    await wrapper.get('form[name="proxy"]').trigger('submit')
    await flushPromises()
    expect(sent).toEqual({ url: 'socks5://socks.example:1080', ip_version: 'ipv6', enabled: true })
    await saved(wrapper, 'Proxy saved.')
  })

  it('shows the validation error next to the address and keeps the form open', async () => {
    server.use(
      http.post('/api/v1/proxies/', () =>
        HttpResponse.json({ url: ['Use a proxy with a valid scheme.'] }, { status: 400 }),
      ),
    )
    const { wrapper } = await mount()
    await click(wrapper, 'Add proxy')
    await wrapper.get('form[name="proxy"]').trigger('submit')
    await flushPromises()
    expect(wrapper.get('.field__error').text()).toBe('Use a proxy with a valid scheme.')
    expect(wrapper.get('input[type="url"]').attributes('aria-invalid')).toBe('true')
    expect(wrapper.find('dialog[open]').exists()).toBe(true)
  })

  it("shows in the form an error that is not the address's", async () => {
    server.use(http.post('/api/v1/proxies/', () => new HttpResponse(null, { status: 403 })))
    const { wrapper } = await mount()
    await click(wrapper, 'Add proxy')
    await wrapper.get('form[name="proxy"]').trigger('submit')
    await flushPromises()
    expect(wrapper.get('form [role="alert"]').text()).toBe('You are not allowed to do this.')
    expect(wrapper.find('.field__error').exists()).toBe(false)
  })

  it('activa y desactiva un proxy', async () => {
    const { wrapper } = await mount()
    await click(wrapper, 'Disable', 0)
    expect(rows(wrapper)[0]?.[1]).toBe('Disabled')
    await click(wrapper, 'Enable', 1)
    expect(rows(wrapper)[1]?.[1]).toBe('Enabled')
    await saved(wrapper, 'Proxy saved.')
  })

  it('deletes a proxy after confirming', async () => {
    const { wrapper } = await mount()
    await click(wrapper, 'Delete', 0)
    const dialog = wrapper.get('dialog[open]')
    expect(dialog.text()).toContain('Delete http://proxy.example:3128?')
    await click(wrapper.findAll('dialog')[1] as unknown as Wrapper, 'Delete')
    expect(rows(wrapper).map((r) => r[0])).toEqual(['socks5://socks.example:1080'])
    expect(wrapper.find('dialog[open]').exists()).toBe(false)
    expect(wrapper.get('[role="status"]').text()).toBe('Proxy deleted.')
  })

  it('shows the error if it cannot delete', async () => {
    server.use(http.delete('/api/v1/proxies/:id/', () => new HttpResponse(null, { status: 404 })))
    const { wrapper } = await mount()
    await click(wrapper, 'Delete', 0)
    await click(wrapper.findAll('dialog')[1] as unknown as Wrapper, 'Delete')
    expect(rows(wrapper)).toHaveLength(2)
    expect(wrapper.get('[role="alert"]').text()).toBe(
      'We could not find what you were looking for.',
    )
  })

  it('reports a successful connection test', async () => {
    const { wrapper } = await mount()
    await click(wrapper, 'Test', 0)
    expect(wrapper.get('[role="status"]').text()).toBe(
      'http://proxy.example:3128 works (HTTP 200).',
    )
  })

  it('reports a failed test as an error, with or without an answer', async () => {
    server.use(
      http.post('/api/v1/proxies/:id/check/', () =>
        HttpResponse.json({ ok: false, status_code: 407 }),
      ),
    )
    const { wrapper } = await mount()
    await click(wrapper, 'Test', 0)
    expect(wrapper.get('[role="alert"]').text()).toBe(
      'http://proxy.example:3128 responds with an error (HTTP 407).',
    )
    expect(wrapper.find('[role="status"]').exists()).toBe(false)
    server.use(
      http.post('/api/v1/proxies/:id/check/', () =>
        HttpResponse.json({ ok: false, status_code: null }),
      ),
    )
    await click(wrapper, 'Test', 1)
    expect(wrapper.get('[role="alert"]').text()).toBe(
      'socks5://socks.example:1080 does not respond.',
    )
  })

  it('adds several pasted proxies and shows the summary and the rejected lines', async () => {
    let sent: unknown
    server.use(
      http.post('/api/v1/proxies/bulk/', async ({ request }) => {
        sent = await request.json()
        return HttpResponse.json({
          created: 2,
          duplicates: [{ line: 3 }],
          invalid: [{ line: 4, reason: 'missing_port' }],
        })
      }),
    )
    const { wrapper } = await mount()
    await click(wrapper, 'Add several')
    expect(wrapper.find('dialog[open] h2').text()).toBe('Add several proxies')
    const text = 'a.example:80\nb.example:81\na.example:80\nc.example'
    await fill(wrapper, 'Proxy list (one per line)', text)
    await choose(wrapper, 'IP type for all lines', 'IPv6')
    await wrapper.get('form[name="bulk"] input[type="checkbox"]').setValue(false)
    await wrapper.get('form[name="bulk"]').trigger('submit')
    await flushPromises()
    expect(sent).toEqual({ text, ip_version: 'ipv6', default_scheme: 'http', enabled: false })
    const dialog = wrapper.get('dialog[open]')
    expect(dialog.text()).toContain('Added: 2 · Duplicates: 1 · Invalid: 1')
    expect(dialog.text()).toContain('Line 4: The port is missing.')
  })

  it('reloads the table after adding several', async () => {
    const extra = {
      id: 9,
      url: 'http://nuevo.example:80',
      ip_version: 'ipv4',
      enabled: true,
      success_count: 0,
      failure_count: 0,
      last_used_at: null,
      last_failed_at: null,
      created_at: '2026-10-30T12:00:00Z',
    }
    let added = false
    server.use(
      http.get('/api/v1/proxies/', () => HttpResponse.json(added ? [extra] : [])),
      http.post('/api/v1/proxies/bulk/', () => {
        added = true
        return HttpResponse.json({ created: 1, duplicates: [], invalid: [] })
      }),
    )
    const { wrapper } = await mount()
    expect(rows(wrapper)).toHaveLength(0)
    await click(wrapper, 'Add several')
    await fill(wrapper, 'Proxy list (one per line)', 'nuevo.example:80')
    await wrapper.get('form[name="bulk"]').trigger('submit')
    await flushPromises()
    expect(rows(wrapper).map((r) => r[0])).toEqual(['http://nuevo.example:80'])
  })

  it('shows the reasons and keeps the dialog open if no line is valid', async () => {
    server.use(
      http.post('/api/v1/proxies/bulk/', () =>
        HttpResponse.json(
          {
            created: 0,
            duplicates: [],
            invalid: [
              { line: 1, reason: 'scheme_not_allowed' },
              { line: 2, reason: 'missing_host' },
            ],
          },
          { status: 400 },
        ),
      ),
    )
    const { wrapper } = await mount()
    await click(wrapper, 'Add several')
    await fill(wrapper, 'Proxy list (one per line)', 'ftp://a.example:21\nhttp://:80')
    await wrapper.get('form[name="bulk"]').trigger('submit')
    await flushPromises()
    const dialog = wrapper.get('dialog[open]')
    expect(dialog.text()).toContain('Line 1: The scheme is not allowed.')
    expect(dialog.text()).toContain('Line 2: The host is missing.')
  })

  it('shows the API error in the dialog, such as exceeding the line limit', async () => {
    server.use(
      http.post('/api/v1/proxies/bulk/', () =>
        HttpResponse.json({ text: ['There are more than 1000 lines.'] }, { status: 400 }),
      ),
    )
    const { wrapper } = await mount()
    await click(wrapper, 'Add several')
    await fill(wrapper, 'Proxy list (one per line)', 'a.example:80')
    await wrapper.get('form[name="bulk"]').trigger('submit')
    await flushPromises()
    expect(wrapper.get('form[name="bulk"] [role="alert"]').text()).toBe(
      'There are more than 1000 lines.',
    )
    expect(wrapper.find('dialog[open]').exists()).toBe(true)
  })

  it('has the same texts in English and Spanish', () => {
    const keys = (tree: object, prefix = ''): string[] =>
      Object.entries(tree).flatMap(([k, v]) =>
        typeof v === 'string' ? [`${prefix}${k}`] : keys(v as object, `${prefix}${k}.`),
      )
    expect(keys(messages.en.proxies as object)).toEqual(keys(messages.es.proxies as object))
  })
})

describe('proxies route', () => {
  it('is in the administration section of “More”', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const router = createRouter({ history: createMemoryHistory(), routes })
    const proxies = router.resolve({ name: 'proxies' })
    expect(proxies.meta).toMatchObject({ navGroup: 'more', navSection: 'admin' })
    const admin = navEntries(router.getRoutes()).sections.find((s) => s.key === 'admin')!
    expect(admin.routes.map((e) => e.name)).toContain('proxies')
    expect(await authGuard(proxies as RouteLocationNormalized)).toBe(true)
  })
})
