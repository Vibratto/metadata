import { flushPromises } from '@vue/test-utils'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it, onTestFinished, vi } from 'vitest'

import type { components } from '../api/schema'
import { POLL_MS } from '../composables/useJobRun'
import { messages } from '../locales'
import { server } from '../mocks/server'
import watchHandlers, { watches } from '../mocks/handlers/watches'
import WatchForm from '../views/watches/WatchForm.vue'
import WatchesView from '../views/watches/WatchesView.vue'
import WatchView from '../views/watches/WatchView.vue'
import { render } from './helpers'
import { choose, fill, mountView } from './viewHelpers'

type JobRun = components['schemas']['JobRun']

// Other views also mock `catalog/artists/` with their own data: here the watches ones win.
beforeEach(() => server.use(...watchHandlers))

// Unanswered MSW requests: a single `flushPromises` round is not enough on a slow machine
// (navigation, request and response chained), so wait until none is left.
let inflight = 0
server.events.on('request:start', () => void inflight++)
server.events.on('response:mocked', () => void inflight--)

/**
 * Waits for in-flight requests to finish and the result to render. A request may start a
 * few ticks after the click (navigation, watcher), so two rounds in a row without any are required.
 */
async function settle(): Promise<void> {
  for (let idle = 0; idle < 2;) {
    await flushPromises()
    await new Promise((resolve) => setTimeout(resolve, 10))
    idle = inflight > 0 ? 0 : idle + 1
  }
}

async function mount(...args: Parameters<typeof mountView>) {
  const ctx = await mountView(...args)
  await settle()
  return ctx
}

type Wrapper = Awaited<ReturnType<typeof mountView>>['wrapper']

function button(wrapper: Wrapper, text: string) {
  const found = wrapper
    .findAll('button')
    .find((b) => b.text() === text || b.attributes('aria-label') === text)
  if (!found) throw new Error(`No “${text}” button`)
  return found
}

/** Records the body of every `method` request to the API; the default mock answers. */
function capture(method: string) {
  const bodies: unknown[] = []
  const listener = ({ request }: { request: Request }) => {
    if (request.method === method)
      void request
        .clone()
        .json()
        .catch(() => null)
        .then((b) => bodies.push(b))
  }
  server.events.on('request:start', listener)
  onTestFinished(() => server.events.removeListener('request:start', listener))
  return bodies
}

/** Answers the save request with `reply`. */
function captureSave(method: 'post' | 'patch', reply: () => Response) {
  const bodies: unknown[] = []
  const path = method === 'post' ? '/api/v1/watches/' : '/api/v1/watches/:id/'
  server.use(
    http[method](path, async ({ request }) => {
      bodies.push(await request.json())
      return reply()
    }),
  )
  return bodies
}

describe('WatchesView', () => {
  it('shows each watch as a card with artists, interval and status', async () => {
    const { wrapper } = await mount(WatchesView, '/watches')
    const rows = wrapper.findAll('.watch-card').map((r) => r.text())
    expect(wrapper.get('.watch-card a').attributes('href')).toBe('/watches/1')
    expect(rows[0]).toContain('Urban')
    expect(rows[0]).toContain('Bad Bunny, Rauw Alejandro')
    expect(rows[0]).toContain('24 hours')
    expect(rows[0]).toContain('Active')
    expect(rows[1]).toContain('Paused · Automatic download')
    expect(wrapper.find('nav').exists()).toBe(false)
  })

  it('changes page with the URL query', async () => {
    server.use(
      http.get('/api/v1/watches/', ({ request }) => {
        const page = new URL(request.url).searchParams.get('page') ?? '1'
        return HttpResponse.json({
          count: 51,
          next: page === '1' ? 'x?page=2' : null,
          previous: page === '1' ? null : 'x',
          results: page === '1' ? watches : [{ ...watches[0], id: 9, interval_hours: 1 }],
        })
      }),
    )
    const { wrapper, router } = await mount(WatchesView, '/watches')
    expect(button(wrapper, 'Previous').attributes('disabled')).toBeDefined()
    await button(wrapper, 'Next').trigger('click')
    await settle()
    expect(router.currentRoute.value.query.page).toBe('2')
    expect(wrapper.text()).toContain('1 hour')
    await button(wrapper, 'Previous').trigger('click')
    await settle()
    expect(router.currentRoute.value.query.page).toBe('1')
  })

  it('filters by status, automatic download, artist, search and ordering, and keeps it in the URL', async () => {
    const seen: Record<string, string>[] = []
    server.events.on('request:start', ({ request }) => {
      const url = new URL(request.url)
      if (url.pathname === '/api/v1/watches/') seen.push(Object.fromEntries(url.searchParams))
    })
    onTestFinished(() => void server.events.removeAllListeners())
    const { wrapper, router } = await mount(WatchesView, '/watches')
    await fill(wrapper, 'Search', 'urb')
    await choose(wrapper, 'Status', 'Active')
    await choose(wrapper, 'Sort by', 'Name (Z-A)')
    await wrapper.get('form').trigger('submit')
    await settle()
    expect(router.currentRoute.value.query).toEqual({
      search: 'urb',
      enabled: 'true',
      ordering: '-name',
    })
    await vi.waitFor(() =>
      expect(seen.at(-1)).toEqual({ search: 'urb', enabled: 'true', ordering: '-name' }),
    )
    expect(wrapper.get('.active-filters').text()).toContain('Status: Active')
    await button(wrapper, 'Remove all').trigger('click')
    await settle()
    expect(router.currentRoute.value.query).toEqual({ search: 'urb', ordering: '-name' })
  })

  it('picks the artist of the watch with the searchable picker', async () => {
    const { wrapper, router } = await mount(WatchesView, '/watches')
    await wrapper.get('input[role="combobox"]').trigger('focus')
    await vi.waitFor(() =>
      expect(wrapper.findAll('.combo [role="option"]').length).toBeGreaterThan(0),
    )
    await wrapper.get('.combo [role="option"]').trigger('mousedown')
    await settle()
    await vi.waitFor(() => expect(router.currentRoute.value.query.artist).toBeDefined())
  })

  it('shows the API error', async () => {
    server.use(http.get('/api/v1/watches/', () => new HttpResponse(null, { status: 500 })))
    const { wrapper } = await mount(WatchesView, '/watches')
    expect(wrapper.get('[role="alert"]').text()).toBe('The server failed. Please try again later.')
  })
})

describe('WatchForm, in the dialogs of the list and the detail', () => {
  it('searches library artists by itself once typing stops', async () => {
    const { wrapper } = await mount(WatchesView, '/watches?new=1')
    await wrapper.get('form[name="artist-search"] input').setValue('r')
    await vi.waitFor(() => expect(button(wrapper, 'Add Rosalía')).toBeTruthy())
  })

  it('creates with artists searched in the library, in order', async () => {
    const bodies = capture('POST')
    // The old link to the form's page opens the dialog on the list.
    const { wrapper, router } = await mount(WatchesView, '/watches/new')
    expect(router.currentRoute.value.fullPath).toBe('/watches?new=1')
    expect(wrapper.get('dialog[open] h2').text()).toBe('New release watch')
    expect(wrapper.text()).toContain('No artists yet.')

    await fill(wrapper, 'Name', 'Mis novedades')
    await fill(wrapper, 'Interval in hours', '6')
    await wrapper.findAll('dialog[open] input[type="checkbox"]')[0]?.setValue(true)
    await fill(wrapper, 'Search the catalogue', 'r')
    await wrapper.get('form[name="artist-search"]').trigger('submit')
    await settle()
    await button(wrapper, 'Add Rosalía').trigger('click')
    await button(wrapper, 'Add Rauw Alejandro').trigger('click')
    expect(wrapper.text()).toContain('No catalogue artist matches.')
    await button(wrapper, 'Move Rauw Alejandro up').trigger('click')

    await wrapper.get('form[name="watch"]').trigger('submit')
    await settle()
    expect(bodies).toEqual([
      {
        name: 'Mis novedades',
        interval_hours: 6,
        auto_download: true,
        enabled: true,
        artist_ids: [3, 1],
      },
    ])
    // Saved: the dialog closes and the list stays, without the query that opened it.
    expect(wrapper.find('dialog[open]').exists()).toBe(false)
    expect(router.currentRoute.value.fullPath).toBe('/watches')
  })

  it('does not offer artists already chosen and allows moving down and removing', async () => {
    const bodies = capture('PATCH')
    // The old link to the edit page opens the dialog on the detail.
    const { wrapper, router } = await mount(WatchView, '/watches/1/edit')
    expect(router.currentRoute.value.fullPath).toBe('/watches/1?edit=1')
    expect(wrapper.get('dialog[open] h2').text()).toBe('Edit “Urban”')
    expect(wrapper.findAll('.artists__chosen li').map((li) => li.text().split(/\s/)[0])).toEqual([
      'Bad',
      'Rauw',
    ])
    expect(button(wrapper, 'Move Bad Bunny up').attributes('disabled')).toBeDefined()
    expect(button(wrapper, 'Move Rauw Alejandro down').attributes('disabled')).toBeDefined()

    await wrapper.get('form[name="artist-search"]').trigger('submit')
    await settle()
    expect(wrapper.findAll('.artists__results li').map((li) => li.text())).toEqual(['Add Rosalía'])

    await button(wrapper, 'Move Bad Bunny down').trigger('click')
    await button(wrapper, 'Remove Bad Bunny').trigger('click')
    await wrapper.findAll('dialog[open] input[type="checkbox"]')[1]?.setValue(false)
    await wrapper.get('form[name="watch"]').trigger('submit')
    await settle()
    expect(bodies).toEqual([
      { name: 'Urban', interval_hours: 24, auto_download: false, enabled: false, artist_ids: [3] },
    ])
    expect(wrapper.find('dialog[open]').exists()).toBe(false)
    expect(router.currentRoute.value.fullPath).toBe('/watches/1')
  })

  it('shows each validation error on its field and the rest above', async () => {
    captureSave('post', () =>
      HttpResponse.json(
        {
          name: ['A watch with this name already exists.'],
          interval_hours: ['Ensure this value is greater than or equal to 1.'],
          artist_ids: ['Some artist does not exist.'],
          non_field_errors: ['Something else.'],
        },
        { status: 400 },
      ),
    )
    const { wrapper } = await mount(WatchesView, '/watches?new=1')
    await wrapper.get('form[name="watch"]').trigger('submit')
    await settle()
    const errors = wrapper.findAll('.field__error').map((p) => p.text())
    expect(errors).toEqual([
      'A watch with this name already exists.',
      'Ensure this value is greater than or equal to 1.',
    ])
    expect(wrapper.get('.artists__error').text()).toBe('Some artist does not exist.')
    expect(wrapper.get('dialog[open] .alert').text()).toBe('Something else.')
  })

  it('a 400 with only field errors sets no general alert', async () => {
    captureSave('post', () => HttpResponse.json({ name: ['Required.'] }, { status: 400 }))
    const { wrapper } = await mount(WatchesView, '/watches?new=1')
    await wrapper.get('form[name="watch"]').trigger('submit')
    await settle()
    expect(wrapper.get('.field__error').text()).toBe('Required.')
    expect(wrapper.find('dialog[open] .alert').exists()).toBe(false)
  })

  it('other failures go to the general alert', async () => {
    captureSave('post', () => new HttpResponse(null, { status: 500 }))
    const { wrapper } = await mount(WatchesView, '/watches?new=1')
    await wrapper.get('form[name="watch"]').trigger('submit')
    await settle()
    expect(wrapper.get('dialog[open] .alert').text()).toBe(
      'The server failed. Please try again later.',
    )
    expect(wrapper.find('.field__error').exists()).toBe(false)
  })

  it('warns if it cannot load the watch or search artists', async () => {
    server.use(
      http.get('/api/v1/watches/:id/', () => new HttpResponse(null, { status: 404 })),
      http.get('/api/v1/catalog/artists/', () => new HttpResponse(null, { status: 500 })),
    )
    const wrapper = render(WatchForm, { props: { watchId: 5 } })
    await settle()
    expect(wrapper.get('.alert').text()).toBe('We could not find what you were looking for.')
    await wrapper.get('form[name="artist-search"]').trigger('submit')
    await settle()
    expect(wrapper.get('.alert').text()).toBe('The server failed. Please try again later.')
  })
})

describe('the watch dialogs', () => {
  it('“New watch” opens the form, and closing it creates nothing', async () => {
    const bodies = capture('POST')
    const { wrapper, router } = await mount(WatchesView, '/watches')
    expect(wrapper.find('dialog[open]').exists()).toBe(false)
    expect(wrapper.find('form[name="watch"]').exists()).toBe(false)
    await button(wrapper, 'New watch').trigger('click')
    expect(wrapper.get('dialog[open] h2').text()).toBe('New release watch')
    await fill(wrapper, 'Name', 'Half typed')
    await wrapper.get('dialog[open] .dialog__actions button').trigger('click')
    await settle()
    expect(wrapper.find('dialog[open]').exists()).toBe(false)
    expect(bodies).toEqual([])
    // Opening it again starts from an empty form.
    await button(wrapper, 'New watch').trigger('click')
    expect((wrapper.get('form[name="watch"] input').element as HTMLInputElement).value).toBe('')
    expect(router.currentRoute.value.fullPath).toBe('/watches')
  })

  it('closing the dialog opened by an old link removes the query that opened it', async () => {
    const { wrapper, router } = await mount(WatchesView, '/watches?new=1&search=urb')
    await wrapper.get('dialog[open] .dialog__actions button').trigger('click')
    await settle()
    expect(router.currentRoute.value.fullPath).toBe('/watches?search=urb')
  })

  it('“Edit” on the detail opens the form and the page shows what was saved', async () => {
    server.use(
      http.patch('/api/v1/watches/:id/', async ({ request }) =>
        HttpResponse.json({ ...watches[0], ...((await request.json()) as object) }),
      ),
    )
    const { wrapper } = await mount(WatchView, '/watches/1')
    expect(wrapper.find('form[name="watch"]').exists()).toBe(false)
    await button(wrapper, 'Edit').trigger('click')
    await settle()
    await fill(wrapper, 'Name', 'Urban hits')
    await wrapper.get('form[name="watch"]').trigger('submit')
    await settle()
    expect(wrapper.find('dialog[open]').exists()).toBe(false)
    expect(wrapper.get('h1').text()).toBe('Urban hits')
  })
})

describe('WatchView', () => {
  it('shows the data and the check history', async () => {
    const { wrapper } = await mount(WatchView, '/watches/1')
    expect(wrapper.get('h1').text()).toBe('Urban')
    expect(wrapper.text()).toContain('Active · 24 hours')
    expect(wrapper.text()).toContain('Bad Bunny, Rauw Alejandro')
    const rows = wrapper.findAll('tbody tr').map((r) => r.text())
    expect(rows[0]).toContain('Failed')
    expect(rows[0]).toContain('YouTube Music did not answer')
    expect(rows[1]).toContain('Succeeded')
    expect(rows[0]).toContain(new Date('2026-01-03T10:01:00Z').toLocaleString('en'))
  })

  it('pages the history', async () => {
    server.use(
      http.get('/api/v1/watches/2/runs/', ({ request }) => {
        const first = !new URL(request.url).searchParams.has('page')
        return HttpResponse.json({
          count: 60,
          next: first ? 'x?page=2' : null,
          previous: first ? null : 'x',
          results: [],
        })
      }),
    )
    const { wrapper, router } = await mount(WatchView, '/watches/2')
    expect(wrapper.text()).toContain('Paused · 6 hours · Automatic download')
    await button(wrapper, 'Next').trigger('click')
    await settle()
    expect(router.currentRoute.value.query.page).toBe('2')
    await button(wrapper, 'Previous').trigger('click')
    await settle()
    expect(router.currentRoute.value.query.page).toBe('1')
  })

  it('checks now and reloads the history when done', async () => {
    const launched: unknown[] = []
    let runsCalls = 0
    const job = (status: JobRun['status']): JobRun => ({
      id: 8,
      kind: 'watch_check',
      params: { watch_id: 1 },
      user: 'demo',
      status,
      started_at: '2026-01-01T10:00:00Z',
      finished_at: null,
      done: 0,
      total: 1,
      current: 'Urban',
      summary: {},
    })
    let detail = 0
    server.use(
      http.post('/api/v1/jobs/runs/', async ({ request }) => {
        launched.push(await request.json())
        return HttpResponse.json(job('pending'), { status: 201 })
      }),
      http.get('/api/v1/jobs/runs/8/', () =>
        HttpResponse.json(job(detail++ ? 'succeeded' : 'running')),
      ),
      http.get('/api/v1/watches/1/runs/', () => {
        runsCalls += 1
        return HttpResponse.json({ count: 0, next: null, previous: null, results: [] })
      }),
    )
    const { wrapper } = await mount(WatchView, '/watches/1')
    await button(wrapper, 'Check now').trigger('click')
    // Real time: the poll turns to “Finished” on the next cycle (POLL_MS).
    await vi.waitFor(() => expect(wrapper.text()).toContain('Running'))
    expect(launched).toEqual([{ kind: 'watch_check', params: { watch_id: 1 } }])
    expect(button(wrapper, 'Check now').attributes('disabled')).toBeDefined()
    expect(runsCalls).toBe(1)
    await vi.waitFor(() => expect(runsCalls).toBe(2), { timeout: POLL_MS * 3 })
    expect(wrapper.text()).toContain('Finished')
  })

  it('deletes after confirming and goes back to the list', async () => {
    const deletes = capture('DELETE')
    const { wrapper, router } = await mount(WatchView, '/watches/1')
    await button(wrapper, 'Delete').trigger('click')
    expect(wrapper.get('dialog').attributes('open')).toBeDefined()
    expect(wrapper.get('dialog').text()).toContain('Delete “Urban”?')
    await button(wrapper, 'Close').trigger('click')
    expect(wrapper.get('dialog').attributes('open')).toBeUndefined()
    await button(wrapper, 'Delete').trigger('click')
    await button(wrapper, 'Yes, delete').trigger('click')
    await settle()
    expect(deletes).toHaveLength(1)
    expect(router.currentRoute.value.name).toBe('watches')
  })

  it('shows why it cannot be deleted', async () => {
    server.use(
      http.delete('/api/v1/watches/1/', () =>
        HttpResponse.json(
          { detail: 'The watch has recorded checks and cannot be deleted.' },
          { status: 409 },
        ),
      ),
    )
    const { wrapper, router } = await mount(WatchView, '/watches/1')
    await button(wrapper, 'Delete').trigger('click')
    await button(wrapper, 'Yes, delete').trigger('click')
    await settle()
    expect(wrapper.get('.alert').text()).toContain('cannot be deleted')
    expect(router.currentRoute.value.name).toBe('watch')
  })

  it('warns if it cannot load the history', async () => {
    server.use(http.get('/api/v1/watches/1/runs/', () => new HttpResponse(null, { status: 500 })))
    const { wrapper } = await mount(WatchView, '/watches/1')
    expect(wrapper.get('.alert').text()).toBe('The server failed. Please try again later.')
  })

  it('warns if the watch does not exist', async () => {
    const { wrapper } = await mount(WatchView, '/watches/99')
    expect(wrapper.get('.alert').text()).toBe('Not found.')
    expect(wrapper.find('h1').exists()).toBe(false)
  })
})

describe('textos de Novedades', () => {
  type Tree = { [key: string]: string | Tree }
  const paths = (tree: Tree, prefix = ''): string[] =>
    Object.entries(tree).flatMap(([k, v]) =>
      typeof v === 'string' ? [`${prefix}${k}`] : paths(v, `${prefix}${k}.`),
    )

  it('have the same keys in en and es', () => {
    expect(paths(messages.en.watches as Tree)).toEqual(paths(messages.es.watches as Tree))
  })
})
