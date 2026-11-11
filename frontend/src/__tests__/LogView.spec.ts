import { flushPromises } from '@vue/test-utils'
import { http, HttpResponse } from 'msw'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter, type RouteRecordRaw } from 'vue-router'

import { messages } from '../locales'
import { server } from '../mocks/server'
import { routes } from '../router'
import { useSessionStore } from '../stores/session'
import LogView from '../views/log/LogView.vue'
import { render } from './helpers'
import { fill as fillNow } from './viewHelpers'

type Tree = { [key: string]: string | Tree }

const library: RouteRecordRaw = {
  path: '/library',
  name: 'library',
  component: { render: () => null },
}

/** Mounts the activity page with a session; `extra` adds routes of other views (e.g. the Library). */
async function mountLog(path = '/log', { extra = [] as RouteRecordRaw[] } = {}) {
  const pinia = createPinia()
  setActivePinia(pinia)
  await useSessionStore(pinia).fetchMe()
  const router = createRouter({ history: createMemoryHistory(), routes: [...routes, ...extra] })
  await router.push(path)
  await router.isReady()
  const wrapper = render(LogView, { global: { plugins: [pinia, router] } })
  await flushPromises()
  return { wrapper, router }
}

/** Records the query of every request to `path` and answers with `results`. */
function record(path: string, results: unknown[] = []) {
  const seen: Record<string, string>[] = []
  server.use(
    http.get(path, ({ request }) => {
      seen.push(Object.fromEntries(new URL(request.url).searchParams))
      return HttpResponse.json({ count: 60, next: 'x', previous: null, results })
    }),
  )
  return seen
}

/** Fills a field and waits for the URL to change, as someone typing field by field would. */
async function fill(
  wrapper: Awaited<ReturnType<typeof mountLog>>['wrapper'],
  label: string,
  value: string,
) {
  await fillNow(wrapper, label, value)
  await flushPromises()
}

afterEach(() => vi.useRealTimers())

const entry = (fields: Record<string, unknown>) => ({
  id: 3,
  created_at: '2026-01-01T10:00:00Z',
  user: 1,
  username: 'demo',
  action: 'proxies.created',
  object_type: '',
  object_id: '',
  detail: {},
  ...fields,
})

describe('activity route', () => {
  it('is in “More” with its label', () => {
    const route = routes.find((r) => r.name === 'log')
    expect(route?.path).toBe('/log')
    expect(route?.meta).toMatchObject({ navLabel: 'log.nav', navGroup: 'more' })
    expect((messages.en.log as Tree).nav).toBe('Activity')
    expect((messages.es.log as Tree).nav).toBe('Actividad')
  })

  it('has the same keys in en and es', () => {
    const paths = (tree: Tree, prefix = ''): string[] =>
      Object.entries(tree).flatMap(([k, v]) =>
        typeof v === 'string' ? [`${prefix}${k}`] : paths(v, `${prefix}${k}.`),
      )
    expect(paths(messages.en.log as Tree)).toEqual(paths(messages.es.log as Tree))
  })
})

describe('Activity', () => {
  it('tells each entry as a sentence, never as a code', async () => {
    const { wrapper } = await mountLog()
    expect(wrapper.get('h1').text()).toBe('Activity')
    expect(wrapper.text()).toContain('Edited an album')
    expect(wrapper.text()).toContain('Download finished. Tracks downloaded: 3')
    expect(wrapper.text()).not.toContain('catalog.')
    expect(wrapper.find('.tabs').exists()).toBe(false)
  })

  it('uses a generic sentence for an action it does not know', async () => {
    server.use(
      http.get('/api/v1/activity/entries/', () =>
        HttpResponse.json({ count: 1, results: [entry({ action: 'other.thing' })] }),
      ),
    )
    const { wrapper } = await mountLog()
    expect(wrapper.text()).toContain('Change in the library')
    expect(wrapper.text()).not.toContain('other.thing')
  })

  it('sends the dates to the API and keeps them in the URL', async () => {
    const seen = record('/api/v1/activity/entries/')
    const { wrapper, router } = await mountLog()
    await fill(wrapper, 'From', '2026-01-01')
    await fill(wrapper, 'To', '2026-01-31')
    await vi.waitFor(() =>
      expect(seen.at(-1)).toEqual({ date_from: '2026-01-01', date_to: '2026-01-31' }),
    )
    expect(router.currentRoute.value.query).toMatchObject({ date_from: '2026-01-01' })
  })

  it('reads the dates from the URL on entry', async () => {
    const seen = record('/api/v1/activity/entries/')
    const { wrapper } = await mountLog('/log?date_from=2026-01-01')
    expect(seen[0]).toEqual({ date_from: '2026-01-01' })
    const field = wrapper.findAll('label').find((l) => l.text() === 'From')
    expect((wrapper.get(`#${field?.attributes('for')}`).element as HTMLInputElement).value).toBe(
      '2026-01-01',
    )
  })

  it('links to the history in the Library when that view exists', async () => {
    const { wrapper, router } = await mountLog('/log', { extra: [library] })
    const link = wrapper.get('a.history')
    expect(link.text()).toBe('View history')
    expect(router.resolve(link.attributes('href') as string).query).toEqual({
      tab: 'albums',
      id: '7',
      panel: 'history',
    })
  })

  it('does not link for objects outside the library', async () => {
    server.use(
      http.get('/api/v1/activity/entries/', () =>
        HttpResponse.json({
          count: 1,
          results: [entry({ object_type: 'proxies.proxy', object_id: '2' })],
        }),
      ),
    )
    const { wrapper } = await mountLog('/log', { extra: [library] })
    expect(wrapper.text()).toContain('Added a proxy')
    expect(wrapper.find('a.history').exists()).toBe(false)
  })

  it('does not link while the Library view does not exist', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/log', name: 'log', component: LogView }],
    })
    await router.push('/log')
    const wrapper = render(LogView, { global: { plugins: [pinia, router] } })
    await flushPromises()
    await vi.waitFor(() => expect(wrapper.text()).toContain('Edited an album'))
    expect(wrapper.find('a.history').exists()).toBe(false)
  })

  it('changes page', async () => {
    const seen = record('/api/v1/activity/entries/')
    const { wrapper } = await mountLog()
    expect(wrapper.text()).toContain('Page 1 · 60 in total')
    const [previous, next] = wrapper.findAll('.pager button')
    expect(previous.attributes('disabled')).toBeDefined()
    await next.trigger('click')
    await flushPromises()
    await vi.waitFor(() => expect(seen.at(-1)).toEqual({ page: '2' }))
  })

  it('goes back to the previous page', async () => {
    const seen: Record<string, string>[] = []
    server.use(
      http.get('/api/v1/activity/entries/', ({ request }) => {
        seen.push(Object.fromEntries(new URL(request.url).searchParams))
        return HttpResponse.json({ count: 60, next: null, previous: 'x', results: [] })
      }),
    )
    const { wrapper } = await mountLog('/log?page=2')
    // The pager appears when the answer arrives; on a slow machine, after mounting.
    await vi.waitFor(() => expect(wrapper.findAll('.pager button')).toHaveLength(2))
    const [previous, next] = wrapper.findAll('.pager button')
    expect(previous.attributes('disabled')).toBeUndefined()
    expect(next.attributes('disabled')).toBeDefined()
    await previous.trigger('click')
    await flushPromises()
    await vi.waitFor(() => expect(seen.at(-1)).toEqual({ page: '1' }))
  })

  it('shows no pager when everything fits on one page', async () => {
    server.use(
      http.get('/api/v1/activity/entries/', () =>
        HttpResponse.json({ count: 0, next: null, previous: null, results: [] }),
      ),
    )
    const { wrapper } = await mountLog()
    expect(wrapper.find('.pager').exists()).toBe(false)
  })

  it('shows the API error', async () => {
    server.use(http.get('/api/v1/activity/entries/', () => HttpResponse.json({}, { status: 500 })))
    const { wrapper } = await mountLog()
    expect(wrapper.get('[role="alert"]').text()).toBe('The server failed. Please try again later.')
  })
})
