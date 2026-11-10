import { http, HttpResponse } from 'msw'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { messages } from '../locales'
import libraryHandlers from '../mocks/handlers/library'
import { server } from '../mocks/server'
import { routes } from '../router'
import LibraryView from '../views/library/LibraryView.vue'
import { duration } from '../views/library/kinds'
import { trackRequests } from './settle'
import { choose, chosen, fill, mountView } from './viewHelpers'

type Tree = { [key: string]: string | Tree }

function paths(tree: Tree, prefix = ''): string[] {
  return Object.entries(tree).flatMap(([k, v]) =>
    typeof v === 'string' ? [`${prefix}${k}`] : paths(v, `${prefix}${k}.`),
  )
}

/** Records the query of every request to the given list. */
function spy(kind: string): Record<string, string>[] {
  const seen: Record<string, string>[] = []
  server.events.on('request:start', ({ request }) => {
    const url = new URL(request.url)
    if (url.pathname === `/api/v1/catalog/${kind}/`) seen.push(Object.fromEntries(url.searchParams))
  })
  return seen
}

const button = (wrapper: Awaited<ReturnType<typeof mountView>>['wrapper'], text: string) =>
  wrapper.findAll('button').find((b) => b.text() === text)!

describe('LibraryView', () => {
  // Other areas (Download) also mock the library lists: here the Library ones win.
  let settle: () => Promise<void>
  beforeEach(() => {
    server.use(...libraryHandlers)
    settle = trackRequests()
  })

  async function mount(path: string) {
    const ctx = await mountView(LibraryView, path)
    await settle()
    return ctx
  }

  afterEach(() => server.events.removeAllListeners())

  it('is in the main navigation', () => {
    const route = routes.find((r) => r.name === 'library')!
    expect(route.meta).toMatchObject({ navLabel: 'library.nav', navGroup: 'main' })
  })

  it('has the same texts in English and Spanish', () => {
    const es = paths(messages.es.library as Tree)
    expect(paths(messages.en.library as Tree)).toEqual(es)
  })

  it('opens the artists tab by default, with a link to each page', async () => {
    const seen = spy('artists')
    const { wrapper } = await mount('/library?tab=other')
    expect(seen).toEqual([{ profile_only: 'false' }])
    expect(wrapper.get('[aria-current="page"]').text()).toBe('Artists')
    const link = wrapper.findAll('a').find((a) => a.text() === 'Daft Punk')!
    expect(link.attributes('href')).toBe('/library/artists/1')
    // Everything fits on one page: no pager.
    expect(wrapper.find('.library-list__pages').exists()).toBe(false)
  })

  it('switches tab and shows artists, duration and whether it is downloaded', async () => {
    const { wrapper, router } = await mount('/library')
    await wrapper
      .findAll('a')
      .find((a) => a.text() === 'Tracks')!
      .trigger('click')
    await settle()
    await vi.waitFor(() => expect(router.currentRoute.value.query).toEqual({ tab: 'tracks' }))
    await vi.waitFor(() => expect(wrapper.findAll('tbody tr')).toHaveLength(2))
    const rows = wrapper.findAll('tbody tr').map((r) => r.findAll('td').map((c) => c.text()))
    expect(rows[0]).toEqual(['Get Lucky', 'Daft Punk, Pharrell Williams', '6:09', 'Yes', 'Preview'])
    expect(rows[1]?.[3]).toBe('No')
  })

  it('shows albums as covers, with their artist and year', async () => {
    const { wrapper } = await mount('/library?tab=albums')
    const card = wrapper.get('.covers li')
    expect(card.get('img').attributes('src')).toBe('https://example.com/ram.jpg')
    expect(card.get('a').text()).toBe('Random Access Memories')
    expect(card.get('a').attributes('href')).toBe('/library/albums/10')
    expect(card.text()).toContain('Daft Punk · 2013')
  })

  it('shows artists as round photos (initials when there is no photo)', async () => {
    const { wrapper } = await mount('/library')
    const card = wrapper.get('.covers li')
    expect(card.get('.cover').classes()).toContain('cover--round')
    expect(card.get('.cover').text()).toBe('DP')
  })

  it('tracks stay in a list, with their columns', async () => {
    const { wrapper } = await mount('/library?tab=tracks')
    expect(wrapper.find('.covers').exists()).toBe(false)
    expect(wrapper.find('table').exists()).toBe(true)
  })

  it('lists one row per recording, except inside an album', async () => {
    const seen: Record<string, string>[] = []
    server.use(
      http.get('/api/v1/catalog/tracks/', ({ request }) => {
        seen.push(Object.fromEntries(new URL(request.url).searchParams))
        return HttpResponse.json({ count: 0, next: null, previous: null, results: [] })
      }),
    )
    await mount('/library?tab=tracks')
    await mount('/library?tab=tracks&album=10')
    await vi.waitFor(() => expect(seen).toHaveLength(2))
    expect(seen[0]).toEqual({ one_per_recording: 'true' })
    expect(seen[1]).toEqual({ album: '10' })
  })

  it('marks the tracks whose recording is on other albums', async () => {
    const { wrapper } = await mount('/library?tab=tracks')
    expect(wrapper.findAll('.library-list__also').map((c) => c.text())).toEqual([
      'On 2 other albums',
    ])
  })

  it('every track has “Preview”, which opens the modal with the video', async () => {
    server.use(
      http.get('/api/v1/catalog/tracks/:id/video/', () =>
        HttpResponse.json({ video_id: 'abcdefghijk', embed_url: 'https://e/embed/a' }),
      ),
    )
    const { wrapper } = await mount('/library?tab=tracks')
    const buttons = wrapper.findAll('table button[aria-label^="Preview"]')
    expect(buttons.length).toBe(wrapper.findAll('tbody tr').length)
    expect(buttons[0]!.attributes('aria-label')).toBe('Preview: Get Lucky')
    await buttons[0]!.trigger('click')
    await vi.waitFor(() =>
      expect(wrapper.get('dialog[open] iframe').attributes('src')).toBe('https://e/embed/a'),
    )
    await button(wrapper, 'Close').trigger('click')
    expect(wrapper.find('iframe').exists()).toBe(false)
  })

  it('albums and artists have no preview', async () => {
    for (const tab of ['albums', 'artists']) {
      const { wrapper } = await mount(`/library?tab=${tab}`)
      expect(wrapper.find('[aria-label^="Preview"]').exists()).toBe(false)
    }
  })

  it('tracks show their album cover, or initials when there is none', async () => {
    const { wrapper } = await mount('/library?tab=tracks')
    const covers = wrapper.findAll('table .cover')
    expect(covers.length).toBeGreaterThan(1)
    expect(covers[0]!.get('img').attributes('src')).toBe('https://example.com/ram.jpg')
    expect(covers[1]!.find('img').exists()).toBe(false)
    expect(covers[1]!.text()).not.toBe('')
  })

  it('applies search, ordering and years of the albums', async () => {
    const seen = spy('albums')
    const { wrapper, router } = await mount('/library?tab=albums')
    await fill(wrapper, 'Search', 'random')
    await fill(wrapper, 'Year from', '2010')
    await fill(wrapper, 'Year to', '2020')
    await choose(wrapper, 'Sort by', 'Year (newest first)')
    expect(chosen(wrapper, 'Sort by')).toBe('Year (newest first)')
    await wrapper.get('form').trigger('submit')
    await settle()
    await vi.waitFor(() =>
      expect(router.currentRoute.value.query).toEqual({
        tab: 'albums',
        search: 'random',
        ordering: '-year',
        year_from: '2010',
        year_to: '2020',
      }),
    )
    await vi.waitFor(() =>
      expect(seen.at(-1)).toEqual({
        search: 'random',
        ordering: '-year',
        year_from: '2010',
        year_to: '2020',
      }),
    )
  })

  it('filters tracks by download and restores the filters from the URL', async () => {
    const seen = spy('tracks')
    const { wrapper, router } = await mount('/library?tab=tracks&search=get')
    expect((wrapper.get('input').element as HTMLInputElement).value).toBe('get')
    await choose(wrapper, 'Downloaded', 'No')
    await wrapper.get('form').trigger('submit')
    await settle()
    await vi.waitFor(() =>
      expect(router.currentRoute.value.query).toMatchObject({ downloaded: 'false', search: 'get' }),
    )
    await vi.waitFor(() =>
      expect(seen.at(-1)).toEqual({
        one_per_recording: 'true',
        search: 'get',
        downloaded: 'false',
      }),
    )
  })

  it('searches by itself once typing stops, and the “x” restores the full list', async () => {
    const seen = spy('tracks')
    const { wrapper, router } = await mount('/library?tab=tracks')
    await wrapper.get('input[type="search"]').setValue('get')
    expect(router.currentRoute.value.query.search).toBeUndefined()
    await vi.waitFor(() => expect(router.currentRoute.value.query.search).toBe('get'))
    await vi.waitFor(() => expect(seen.at(-1)).toMatchObject({ search: 'get' }))
    await wrapper.get('button[aria-label="Clear search"]').trigger('click')
    await vi.waitFor(() => expect(router.currentRoute.value.query.search).toBeUndefined())
    await vi.waitFor(() => expect(seen.at(-1)).not.toHaveProperty('search'))
  })

  it('shows the album filter as a chip with its name and removes it', async () => {
    const { wrapper, router } = await mount('/library?tab=tracks&album=10')
    await vi.waitFor(() =>
      expect(wrapper.get('.active-filters').text()).toContain('Album: Random Access Memories'),
    )
    await wrapper.get('.active-filters .chip button').trigger('click')
    await settle()
    await vi.waitFor(() => expect(router.currentRoute.value.query).toEqual({ tab: 'tracks' }))
    expect(wrapper.find('.active-filters').exists()).toBe(false)
  })

  it('picks an artist in the album picker: URL, request and page 1', async () => {
    const seen = spy('albums')
    const { wrapper, router } = await mount('/library?tab=albums&page=3')
    const combo = wrapper.get('input[role="combobox"]')
    await combo.trigger('focus')
    await vi.waitFor(() => expect(wrapper.findAll('.combo [role="option"]')).toHaveLength(2))
    await wrapper.findAll('.combo [role="option"]')[1]!.trigger('mousedown')
    await settle()
    await vi.waitFor(() =>
      expect(router.currentRoute.value.query).toEqual({ tab: 'albums', artist: '2' }),
    )
    await vi.waitFor(() => expect(seen.at(-1)).toEqual({ artist: '2' }))
    await vi.waitFor(() =>
      expect(wrapper.get('.active-filters').text()).toContain('Artist: Pharrell Williams'),
    )
  })

  it('combines simple filters and keeps them in the URL', async () => {
    const seen = spy('albums')
    const { wrapper, router } = await mount('/library?tab=albums')
    await fill(wrapper, 'Year from', '2010')
    await choose(wrapper, 'Type', 'Single')
    await wrapper.get('form').trigger('submit')
    await settle()
    await vi.waitFor(() =>
      expect(router.currentRoute.value.query).toEqual({
        tab: 'albums',
        record_type: 'single',
        year_from: '2010',
      }),
    )
    await vi.waitFor(() =>
      expect(seen.at(-1)).toEqual({ record_type: 'single', year_from: '2010' }),
    )
    expect(wrapper.get('.active-filters').text()).toContain('Type: Single')
    expect(wrapper.get('.active-filters').text()).toContain('Year from: 2010')
  })

  it('“Remove all” leaves the list without filters and on page 1', async () => {
    const { wrapper, router } = await mount(
      '/library?tab=albums&artist=1&year_from=2010&page=2&search=ra',
    )
    await vi.waitFor(() => expect(wrapper.find('.active-filters').exists()).toBe(true))
    await button(wrapper, 'Remove all').trigger('click')
    await settle()
    await vi.waitFor(() =>
      expect(router.currentRoute.value.query).toEqual({ tab: 'albums', search: 'ra' }),
    )
  })

  it("the artist of an album or track leads to that artist's albums", async () => {
    const albums = await mount('/library?tab=albums')
    const link = albums.wrapper.findAll('a').find((a) => a.classes().includes('covers__artist'))!
    expect(link.text()).toBe('Daft Punk')
    expect(link.attributes('href')).toBe('/library?tab=albums&artist=1')
    const tracks = await mount('/library?tab=tracks')
    const row = tracks.wrapper.findAll('tbody tr')[0]!
    expect(row.findAll('a').map((a) => a.attributes('href'))).toContain(
      '/library?tab=albums&artist=2',
    )
  })

  it('the Related tab lists the saved profiles with their audience', async () => {
    const seen = spy('artists')
    const { wrapper } = await mount('/library?tab=related')
    expect(seen).toEqual([{ profile_only: 'true' }])
    expect(wrapper.get('[aria-current="page"]').text()).toBe('Related')
    expect(wrapper.text()).toContain('Only their profile is saved')
    const cards = wrapper.findAll('.covers li')
    expect(cards.map((c) => c.get('a').text())).toEqual(['Justice', 'Kavinsky'])
    expect(cards[0]!.text()).toContain('4.8M monthly listeners')
    expect(cards[1]!.text()).toContain('310K subscribers')
    expect(cards[0]!.text()).not.toContain('pending')
  })

  it('every related artist can be imported, and the big ones are marked as suggested', async () => {
    const { wrapper } = await mount('/library?tab=related')
    const cards = wrapper.findAll('.covers li')
    expect(cards.map((c) => c.get('button').text())).toEqual([
      'Import discography',
      'Import discography',
    ])
    expect(cards.map((c) => c.find('.chip').exists())).toEqual([true, false])
    expect(cards[0]!.get('.chip').text()).toBe('Suggested')
    expect(cards[0]!.get('button').classes()).toContain('btn--primary')
    expect(cards[1]!.get('button').classes()).toContain('btn--secondary')
  })

  it('asks before importing and does nothing when the dialog is closed', async () => {
    let posts = 0
    server.use(http.post('/api/v1/jobs/runs/', () => (posts++, HttpResponse.json({}))))
    const { wrapper } = await mount('/library?tab=related')
    expect(wrapper.find('dialog[open]').exists()).toBe(false)
    await wrapper.get('.covers li button').trigger('click')
    const dialog = wrapper.get('dialog[open]')
    expect(dialog.get('h2').text()).toBe('Import discography')
    expect(dialog.text()).toContain('Import every album, single and track of Justice?')
    await button(wrapper, 'Close').trigger('click')
    await settle()
    expect(wrapper.find('dialog[open]').exists()).toBe(false)
    expect(posts).toBe(0)
  })

  it('artists already in the library can have their discography updated', async () => {
    let body: unknown
    server.use(
      http.post('/api/v1/jobs/runs/', async ({ request }) => {
        body = await request.json()
        return HttpResponse.json({ id: 6, kind: 'import', status: 'succeeded' }, { status: 201 })
      }),
    )
    const { wrapper } = await mount('/library?tab=artists')
    const card = wrapper.findAll('.covers li')[0]!
    expect(card.get('button').text()).toBe('Update discography')
    expect(card.find('.chip').exists()).toBe(false)
    await card.get('button').trigger('click')
    const dialog = wrapper.get('dialog[open]')
    expect(dialog.text()).toContain('Look for new releases of Daft Punk')
    await dialog.get('.btn--primary').trigger('click')
    await vi.waitFor(() =>
      expect(body).toEqual({
        kind: 'import',
        params: { artist_ids: ['UCdaftpunk0000000000000a'] },
      }),
    )
    expect(wrapper.find('dialog[open]').exists()).toBe(false)
  })

  it('imports a related artist and reloads the list when the job ends', async () => {
    const run = { id: 5, kind: 'import', status: 'running', done: 0, total: 1, current: '' }
    let body: unknown
    server.use(
      http.post('/api/v1/jobs/runs/', async ({ request }) => {
        body = await request.json()
        return HttpResponse.json(run, { status: 201 })
      }),
      http.get('/api/v1/jobs/runs/5/', () =>
        HttpResponse.json({ ...run, status: 'succeeded', done: 1 }),
      ),
      http.get('/api/v1/jobs/runs/5/lines/', () => HttpResponse.json([])),
    )
    const seen = spy('artists')
    const { wrapper } = await mount('/library?tab=related')
    await wrapper.get('.covers li button').trigger('click')
    await wrapper.get('dialog[open] .btn--primary').trigger('click')
    await vi.waitFor(() => expect(wrapper.get('.job__status').text()).toContain('Finished'))
    expect(body).toEqual({ kind: 'import', params: { artist_ids: ['UCjustice00000000000000b'] } })
    await vi.waitFor(() => expect(seen).toHaveLength(2))
  })

  it('the artist filter of albums and tracks only offers artists with music', async () => {
    const seen = spy('artists')
    const { wrapper } = await mount('/library?tab=albums')
    await wrapper.get('input[role="combobox"]').trigger('focus')
    await vi.waitFor(() => expect(wrapper.findAll('.combo [role="option"]')).toHaveLength(2))
    expect(seen.at(-1)).toMatchObject({ profile_only: 'false' })
  })

  it('shows the track and pending counts', async () => {
    const { wrapper } = await mount('/library')
    expect(wrapper.get('.covers li').text()).toContain('2 tracks · 1 pending')
  })

  it('pages forwards and backwards', async () => {
    server.use(
      http.get('/api/v1/catalog/artists/', ({ request }) => {
        const page = Number(new URL(request.url).searchParams.get('page') ?? 1)
        return HttpResponse.json({
          count: 60,
          next: page === 1 ? 'x?page=2' : null,
          previous: page === 2 ? 'x?page=1' : null,
          results: [{ id: page, name: `Artist ${page}`, image_url: '' }],
        })
      }),
    )
    const { wrapper, router } = await mount('/library')
    expect(button(wrapper, 'Previous').attributes('disabled')).toBeDefined()
    await button(wrapper, 'Next').trigger('click')
    await settle()
    await vi.waitFor(() => expect(router.currentRoute.value.query.page).toBe('2'))
    await vi.waitFor(() => expect(wrapper.text()).toContain('Artist 2'))
    expect(button(wrapper, 'Next').attributes('disabled')).toBeDefined()
    await button(wrapper, 'Previous').trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Artist 1'))
    await vi.waitFor(() => expect(router.currentRoute.value.query.page).toBe('1'))
  })

  it('says it is loading and shows the API error', async () => {
    let release!: () => void
    const gate = new Promise<void>((r) => (release = r))
    server.use(
      http.get('/api/v1/catalog/artists/', async () => {
        await gate
        return new HttpResponse(null, { status: 500 })
      }),
    )
    const { wrapper } = await mountView(LibraryView, '/library')
    expect(wrapper.get('[role="status"]').text()).toBe('Loading…')
    release()
    await settle()
    expect(wrapper.get('[role="alert"]').text()).toBe('The server failed. Please try again later.')
    expect(wrapper.find('[role="status"]').exists()).toBe(false)
  })

  it.each([
    ['/library?tab=tracks&id=100&panel=history', '/library/tracks/100#history'],
    ['/library?tab=albums&id=10', '/library/albums/10'],
    ['/library?tab=other&id=10', '/library?tab=other&id=10'],
    ['/library?tab=albums&id=x', '/library?tab=albums&id=x'],
  ])('takes the link %s to the item page when it names an item', async (from, to) => {
    const { router } = await mount('/dashboard')
    await router.push(from)
    await vi.waitFor(() => expect(router.currentRoute.value.fullPath).toBe(to))
  })

  // This is how the Log links: with the numeric id exactly as the API sends it.
  it('accepts the id as a number when navigating by name', async () => {
    const { router } = await mount('/dashboard')
    await router.push({ name: 'library', query: { tab: 'albums', id: 10, panel: 'history' } })
    await vi.waitFor(() =>
      expect(router.currentRoute.value.fullPath).toBe('/library/albums/10#history'),
    )
  })

  it('formats the duration and leaves an unknown one empty', () => {
    expect([duration(65), duration(null)]).toEqual(['1:05', ''])
  })
})
