import { flushPromises } from '@vue/test-utils'
import { http, HttpResponse } from 'msw'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter, type RouteRecordRaw } from 'vue-router'

import type { components } from '../api/schema'
import { POLL_MS } from '../composables/useJobRun'
import { messages } from '../locales'
import { server } from '../mocks/server'
import { routes } from '../router'
import { useSessionStore } from '../stores/session'
import LogView from '../views/log/LogView.vue'
import { render } from './helpers'
import { fill as fillNow } from './viewHelpers'

type JobRun = components['schemas']['JobRun']
type Tree = { [key: string]: string | Tree }

const library: RouteRecordRaw = {
  path: '/library',
  name: 'library',
  component: { render: () => null },
}

/** Mounts the log with a session; `extra` adds routes of other views (e.g. the Library). */
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

async function choose(
  wrapper: Awaited<ReturnType<typeof mountLog>>['wrapper'],
  label: string,
  value: string,
) {
  const field = wrapper.findAll('label').find((l) => l.text() === label)
  await wrapper.get(`#${field?.attributes('for')}`).setValue(value)
  await flushPromises()
}

const job = (fields: Partial<JobRun>): JobRun => ({
  id: 9,
  kind: 'download',
  params: {},
  user: 'demo',
  status: 'running',
  started_at: '2026-01-01T10:00:00Z',
  finished_at: null,
  done: 1,
  total: 4,
  current: '',
  summary: {},
  ...fields,
})

afterEach(() => vi.useRealTimers())

describe('log route', () => {
  it('is in “More” with its label', () => {
    const route = routes.find((r) => r.name === 'log')
    expect(route?.path).toBe('/log')
    expect(route?.meta).toMatchObject({ navLabel: 'log.nav', navGroup: 'more' })
  })

  it('has the same keys in en and es', () => {
    const paths = (tree: Tree, prefix = ''): string[] =>
      Object.entries(tree).flatMap(([k, v]) =>
        typeof v === 'string' ? [`${prefix}${k}`] : paths(v, `${prefix}${k}.`),
      )
    expect(paths(messages.en.log as Tree)).toEqual(paths(messages.es.log as Tree))
  })
})

describe('Activity tab', () => {
  it('is the default tab and lists the entries', async () => {
    const { wrapper } = await mountLog()
    expect(wrapper.get('[aria-current="page"]').text()).toBe('Activity')
    expect(wrapper.text()).toContain('catalog.artist.updated')
    expect(wrapper.text()).toContain('Artist no. 7')
    expect(wrapper.text()).toContain('System')
  })

  it('sends the filters to the API and keeps them in the URL', async () => {
    const seen = record('/api/v1/activity/entries/')
    const { wrapper, router } = await mountLog()
    await fill(wrapper, 'From', '2026-01-01')
    await fill(wrapper, 'To', '2026-01-31')
    await fill(wrapper, 'User', 'demo')
    await fill(wrapper, 'Action', 'blocked')
    await choose(wrapper, 'Object type', 'catalog.track')
    await vi.waitFor(() =>
      expect(seen.at(-1)).toEqual({
        date_from: '2026-01-01',
        date_to: '2026-01-31',
        username: 'demo',
        action: 'blocked',
        object_type: 'catalog.track',
      }),
    )
    expect(router.currentRoute.value.query).toMatchObject({
      username: 'demo',
      object_type: 'catalog.track',
    })
  })

  it('reads the filters from the URL on entry', async () => {
    const seen = record('/api/v1/activity/entries/')
    const { wrapper } = await mountLog('/log?action=import')
    expect(seen[0]).toEqual({ action: 'import' })
    const field = wrapper.findAll('label').find((l) => l.text() === 'Action')
    expect((wrapper.get(`#${field?.attributes('for')}`).element as HTMLInputElement).value).toBe(
      'import',
    )
  })

  it('links to the history in the Library when that view exists', async () => {
    const { wrapper, router } = await mountLog('/log', { extra: [library] })
    const link = wrapper.get('a.history')
    expect(link.text()).toBe('View history')
    expect(router.resolve(link.attributes('href') as string).query).toEqual({
      tab: 'artists',
      id: '7',
      panel: 'history',
    })
  })

  it('does not link without the Library view or for objects outside the library', async () => {
    server.use(
      http.get('/api/v1/activity/entries/', () =>
        HttpResponse.json({
          count: 1,
          results: [
            {
              id: 3,
              created_at: '2026-01-01T10:00:00Z',
              user: 1,
              username: 'demo',
              action: 'proxies.created',
              object_type: 'proxies.proxy',
              object_id: '2',
              detail: {},
            },
            {
              id: 4,
              created_at: '2026-01-01T10:00:00Z',
              user: 1,
              username: 'demo',
              action: 'other.thing',
              object_type: 'other.thing',
              object_id: '5',
              detail: {},
            },
          ],
        }),
      ),
    )
    const { wrapper } = await mountLog('/log', { extra: [library] })
    expect(wrapper.text()).toContain('Proxy no. 2')
    expect(wrapper.text()).toContain('other.thing no. 5')
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
    const [previous, next] = wrapper.findAll('.pager button')
    // “Previous” enables when the answer arrives; on a slow machine, after mounting.
    await vi.waitFor(() => expect(previous.attributes('disabled')).toBeUndefined())
    expect(next.attributes('disabled')).toBeDefined()
    await previous.trigger('click')
    await flushPromises()
    await vi.waitFor(() => expect(seen.at(-1)).toEqual({ page: '1' }))
  })

  it('shows the API error', async () => {
    server.use(http.get('/api/v1/activity/entries/', () => HttpResponse.json({}, { status: 500 })))
    const { wrapper } = await mountLog()
    expect(wrapper.get('[role="alert"]').text()).toBe('The server failed. Please try again later.')
  })
})

describe('API errors', () => {
  it.each([
    ['jobs', '/api/v1/jobs/runs/'],
    ['technical', '/api/v1/activity/logs/'],
  ])('the %s tab shows the error of its list', async (tab, path) => {
    server.use(http.get(path, () => HttpResponse.json({}, { status: 500 })))
    const { wrapper } = await mountLog(`/log?tab=${tab}`)
    expect(wrapper.get('[role="alert"]').text()).toBe('The server failed. Please try again later.')
  })
})

describe('Jobs tab', () => {
  it('lists the runs and sends their filters', async () => {
    const seen = record('/api/v1/jobs/runs/', [job({})])
    const { wrapper, router } = await mountLog('/log?tab=jobs')
    expect(wrapper.get('[aria-current="page"]').text()).toBe('Jobs')
    expect(wrapper.text()).toContain('Download')
    expect(wrapper.text()).toContain('1 / 4')
    await choose(wrapper, 'Job type', 'import')
    await choose(wrapper, 'Status', 'failed')
    await fill(wrapper, 'From', '2026-01-01T00:00')
    await fill(wrapper, 'To', '2026-01-02T00:00')
    await flushPromises()
    await vi.waitFor(() =>
      expect(seen.at(-1)).toEqual({
        kind: 'import',
        status: 'failed',
        started_after: '2026-01-01T00:00',
        started_before: '2026-01-02T00:00',
      }),
    )
    expect(router.currentRoute.value.query.tab).toBe('jobs')
  })

  it('shows the kind as is when it has no translation', async () => {
    record('/api/v1/jobs/runs/', [job({ kind: 'library_restore', status: 'pending', total: 0 })])
    const { wrapper } = await mountLog('/log?tab=jobs')
    expect(wrapper.text()).toContain('library_restore')
    // Without a total there is no progress to show yet.
    expect(wrapper.find('td[data-label="Progress"]').text()).toBe('')
  })

  it('opens the detail and refreshes it while the job is running', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
    record('/api/v1/jobs/runs/', [job({})])
    // The first answer is the one from opening it; the second, the first poll.
    const states = [
      job({ done: 1 }),
      job({ done: 1 }),
      job({ done: 3 }),
      job({ status: 'succeeded', done: 4 }),
    ]
    let calls = 0
    server.use(
      http.get('/api/v1/jobs/runs/9/', () => HttpResponse.json(states[Math.min(calls++, 3)])),
      http.get('/api/v1/jobs/runs/9/lines/', () => HttpResponse.json([])),
    )
    const { wrapper, router } = await mountLog('/log?tab=jobs')
    await wrapper.get('a.detail').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query.run).toBe('9')
    expect(wrapper.get('.run h2').text()).toBe('Job no. 9')
    await vi.waitFor(() => expect(wrapper.get('.job__status').text()).toContain('1 / 4'))
    await vi.advanceTimersByTimeAsync(POLL_MS)
    await vi.waitFor(() => expect(wrapper.get('.job__status').text()).toContain('3 / 4'))
    await vi.advanceTimersByTimeAsync(POLL_MS)
    await vi.waitFor(() => expect(wrapper.get('.job__status').text()).toContain('Finished'))
    await vi.advanceTimersByTimeAsync(POLL_MS * 3)
    expect(calls).toBe(4)

    await wrapper.get('.run button').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query.run).toBeUndefined()
    expect(wrapper.find('.run').exists()).toBe(false)
  })
})

describe('Technical logs tab', () => {
  it('lists the logs with level and expandable trace, and sends their filters', async () => {
    const { wrapper } = await mountLog('/log?tab=technical')
    expect(wrapper.get('[aria-current="page"]').text()).toBe('Technical logs')
    expect(wrapper.text()).toContain('Error')
    expect(wrapper.get('details summary').text()).toBe('Trace')
    expect(wrapper.findAll('details')).toHaveLength(1)

    const seen = record('/api/v1/activity/logs/')
    await choose(wrapper, 'Minimum level', '40')
    await fill(wrapper, 'Module', 'catalog')
    await fill(wrapper, 'Job number', '5')
    await fill(wrapper, 'Search the message', 'yt-dlp')
    await fill(wrapper, 'From', '2026-01-01')
    await fill(wrapper, 'To', '2026-01-02')
    await flushPromises()
    await vi.waitFor(() =>
      expect(seen.at(-1)).toEqual({
        min_level: '40',
        module: 'catalog',
        task: '5',
        search: 'yt-dlp',
        date_from: '2026-01-01',
        date_to: '2026-01-02',
      }),
    )
  })

  it('switching tab drops the filters of the previous one', async () => {
    const { wrapper, router } = await mountLog('/log?tab=technical&module=jobs')
    const link = wrapper.findAll('.tabs a').find((a) => a.text() === 'Activity')
    await link?.trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query).toEqual({ tab: 'activity' })
  })

  it('shows a nameless level by its number', async () => {
    record('/api/v1/activity/logs/', [
      {
        id: 1,
        created_at: '2026-01-01T10:00:00Z',
        level: 0,
        logger_name: 'x',
        msg: 'm',
        trace: null,
      },
    ])
    const { wrapper } = await mountLog('/log?tab=technical')
    expect(wrapper.get('td[data-label="Level"]').text()).toBe('0')
  })
})
