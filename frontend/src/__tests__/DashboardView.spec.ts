import { http, HttpResponse } from 'msw'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { server } from '../mocks/server'
import DashboardView from '../views/DashboardView.vue'
import { mountView } from './viewHelpers'

const page = (results: unknown[]) => HttpResponse.json({ count: results.length, results })

afterEach(() => vi.useRealTimers())

// MSW answers arrive after several real network ticks, so wait for the result instead of
// counting ticks (in CI, which is slower, a single flushPromises is not enough).
describe('DashboardView', () => {
  it('shows the library summary', async () => {
    const { wrapper } = await mountView(DashboardView, '/dashboard')
    await vi.waitFor(() =>
      expect(wrapper.findAll('dl div').map((d) => d.text())).toEqual([
        'Artists12',
        'Albums48',
        'Recordings498',
        'Tracks530',
        'Downloaded211',
      ]),
    )
  })

  it('greets the user by time of day', async () => {
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date(2026, 10, 2, 9, 0))
    const morning = (await mountView(DashboardView, '/dashboard')).wrapper
    expect(morning.get('h1').text()).toBe('Good morning, demo')
    vi.setSystemTime(new Date(2026, 10, 2, 16, 0))
    expect((await mountView(DashboardView, '/dashboard')).wrapper.get('h1').text()).toBe(
      'Good afternoon, demo',
    )
    vi.setSystemTime(new Date(2026, 10, 2, 22, 0))
    expect((await mountView(DashboardView, '/dashboard')).wrapper.get('h1').text()).toBe(
      'Good evening, demo',
    )
  })

  it('shows recent activity and links to the Log', async () => {
    const { wrapper } = await mountView(DashboardView, '/dashboard')
    const recent = () => wrapper.get('.recent')
    await vi.waitFor(() => expect(recent().findAll('li')).toHaveLength(2))
    expect(recent().get('h2').text()).toBe('Recent activity')
    expect(recent().findAll('li')[0]!.text()).toContain('catalog.artist.updated')
    expect(recent().findAll('li')[0]!.text()).toContain('demo')
    expect(recent().findAll('li')[1]!.text()).toContain('System')
    expect(recent().get('a').attributes('href')).toBe('/log')
  })

  it('shows at most the last five actions', async () => {
    const entry = (id: number) => ({
      id,
      created_at: '2026-01-01T10:00:00Z',
      user: null,
      username: '',
      action: `accion.${id}`,
      object_type: '',
      object_id: '',
      detail: {},
    })
    server.use(http.get('/api/v1/activity/entries/', () => page([1, 2, 3, 4, 5, 6, 7].map(entry))))
    const { wrapper } = await mountView(DashboardView, '/dashboard')
    await vi.waitFor(() => expect(wrapper.findAll('.recent li')).toHaveLength(5))
  })

  it('lists only running jobs, with their progress', async () => {
    const { wrapper } = await mountView(DashboardView, '/dashboard')
    await vi.waitFor(() => expect(wrapper.findAll('.jobs li')).toHaveLength(1))
    const item = wrapper.get('.jobs li')
    expect(item.text()).toContain('Import')
    expect(item.text()).toContain('Daft Punk')
    expect(wrapper.get('[role="progressbar"]').attributes('aria-valuenow')).toBe('40')
  })

  it('uses the kind as is when it has no translation', async () => {
    server.use(
      http.get('/api/v1/jobs/runs/', () =>
        page([{ id: 9, kind: 'raro', status: 'running', done: 0, total: 0, current: '' }]),
      ),
    )
    const { wrapper } = await mountView(DashboardView, '/dashboard')
    await vi.waitFor(() => expect(wrapper.get('.jobs li').text()).toContain('raro'))
  })

  it('says no jobs are running', async () => {
    server.use(http.get('/api/v1/jobs/runs/', () => page([])))
    const { wrapper } = await mountView(DashboardView, '/dashboard')
    await vi.waitFor(() => expect(wrapper.text()).toContain('No jobs are running.'))
  })

  it('shows the error if the summary fails and carries on with the jobs', async () => {
    server.use(http.get('/api/v1/catalog/summary/', () => new HttpResponse(null, { status: 500 })))
    const { wrapper } = await mountView(DashboardView, '/dashboard')
    await vi.waitFor(() => expect(wrapper.findAll('.jobs li')).toHaveLength(1))
    await vi.waitFor(() =>
      expect(wrapper.get('[role="alert"]').text()).toBe(
        'The server failed. Please try again later.',
      ),
    )
    expect(wrapper.find('dl').exists()).toBe(false)
  })

  it('refreshes the jobs every few seconds and stops on unmount', async () => {
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
    let calls = 0
    server.use(
      http.get('/api/v1/jobs/runs/', () => {
        calls += 1
        return page([])
      }),
    )
    const { wrapper } = await mountView(DashboardView, '/dashboard')
    await vi.waitFor(() => expect(calls).toBe(1))
    await vi.advanceTimersByTimeAsync(5000)
    await vi.waitFor(() => expect(calls).toBe(2))
    wrapper.unmount()
    await vi.advanceTimersByTimeAsync(10000)
    expect(calls).toBe(2)
  })

  it('a refresh failure is shown and cleared once it works again', async () => {
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
    server.use(http.get('/api/v1/jobs/runs/', () => HttpResponse.error()))
    const { wrapper } = await mountView(DashboardView, '/dashboard')
    await vi.waitFor(() => expect(wrapper.find('[role="alert"]').exists()).toBe(true))
    server.use(http.get('/api/v1/jobs/runs/', () => page([])))
    await vi.advanceTimersByTimeAsync(5000)
    await vi.waitFor(() => expect(wrapper.find('[role="alert"]').exists()).toBe(false))
  })

  describe('recommended next step', () => {
    const summary = (data: object) =>
      server.use(http.get('/api/v1/catalog/summary/', () => HttpResponse.json(data)))
    const next = async (jobs = false) => {
      if (!jobs) server.use(http.get('/api/v1/jobs/runs/', () => page([])))
      const { wrapper } = await mountView(DashboardView, '/dashboard')
      await vi.waitFor(() => expect(wrapper.find('.next-step').exists()).toBe(true))
      return wrapper.get('.next-step')
    }

    it('with an empty library it guides to importing artists or a folder (first run)', async () => {
      summary({ artists: 0, albums: 0, recordings: 0, tracks: 0, downloaded: 0 })
      const step = await next()
      expect(step.text()).toContain('Your library is empty')
      const hrefs = step.findAll('a').map((a) => a.attributes('href'))
      expect(hrefs).toEqual(['/import', '/import/folder'])
    })

    it('with tracks left to download it suggests downloading', async () => {
      const step = await next()
      expect(step.text()).toContain('319')
      expect(step.get('a').attributes('href')).toBe('/download')
    })

    it('with everything downloaded it suggests watching new releases', async () => {
      summary({ artists: 1, albums: 1, recordings: 0, tracks: 5, downloaded: 5 })
      const step = await next()
      expect(step.get('a').attributes('href')).toBe('/watches')
    })

    it('with running jobs it asks to wait and suggests nothing else', async () => {
      summary({ artists: 0, albums: 0, recordings: 0, tracks: 0, downloaded: 0 })
      const step = await next(true)
      expect(step.text()).toContain('Wait for them to finish')
      expect(step.find('a').exists()).toBe(false)
    })
  })
})
