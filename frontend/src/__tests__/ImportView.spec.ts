import { http, HttpResponse } from 'msw'
import { describe, expect, it, vi } from 'vitest'

import { messages } from '../locales'
import { server } from '../mocks/server'
import ImportView from '../views/ImportView.vue'
import { fill, mountView } from './viewHelpers'

type Wrapper = Awaited<ReturnType<typeof mountView>>['wrapper']

async function search(wrapper: Wrapper, q: string): Promise<void> {
  await fill(wrapper, 'Artist or YouTube Music link', q)
  await wrapper.get('form').trigger('submit')
}

const item = (wrapper: Wrapper, name: string) =>
  wrapper.findAll('.results li').find((li) => li.text().includes(name))!

const button = (wrapper: Wrapper, text: string) =>
  wrapper.findAll('button').find((b) => b.text().startsWith(text))!

describe('ImportView', () => {
  it('with an empty search it does not ask YouTube Music and says so', async () => {
    let calls = 0
    server.use(
      http.get('/api/v1/catalog/ytmusic/artists/', () => {
        calls += 1
        return HttpResponse.json({ results: [] })
      }),
    )
    const { wrapper } = await mountView(ImportView, '/import')
    expect(wrapper.text()).toContain('Type an artist name')
    await search(wrapper, '   ')
    expect(calls).toBe(0)
    expect(wrapper.text()).toContain('Type an artist name')
  })

  it('searches by itself once typing stops, from 3 letters on', async () => {
    const queries: string[] = []
    server.events.on('request:start', ({ request }) => {
      const url = new URL(request.url)
      if (url.pathname === '/api/v1/catalog/ytmusic/artists/')
        queries.push(url.searchParams.get('q')!)
    })
    const { wrapper } = await mountView(ImportView, '/import')
    await wrapper.get('input[type="search"]').setValue('da')
    await new Promise((r) => setTimeout(r, 700))
    expect(queries).toEqual([])
    await wrapper.get('input[type="search"]').setValue('daf')
    await vi.waitFor(() => expect(wrapper.findAll('.results li')).toHaveLength(2))
    expect(queries).toEqual(['daf'])
    // Enter right after does not repeat the same search.
    await wrapper.get('form').trigger('submit')
    expect(queries).toEqual(['daf'])
    // Clearing the field restores the initial state.
    await wrapper.get('button[aria-label="Clear search"]').trigger('click')
    await vi.waitFor(() => expect(wrapper.find('.results').exists()).toBe(false))
    expect(wrapper.text()).toContain('Type an artist name')
    server.events.removeAllListeners()
  })

  it('shows the results with image, audience, releases and status', async () => {
    const { wrapper } = await mountView(ImportView, '/import')
    await search(wrapper, 'daft')
    await vi.waitFor(() => expect(wrapper.findAll('.results li')).toHaveLength(2))
    const daft = item(wrapper, 'Daft Punk')
    expect(daft.get('img').attributes('src')).toContain('w250-h250')
    expect(daft.text()).toContain('21.4M monthly listeners')
    expect(daft.text()).toContain('4 albums · 12 singles and EPs')
    expect(daft.text()).toContain('Already in the library')
    const tribute = item(wrapper, 'Tribute')
    expect(tribute.find('img').exists()).toBe(false)
    expect(tribute.text()).not.toContain('albums')
    expect(tribute.text()).toContain('Blocked')
    expect(tribute.get('input').attributes('disabled')).toBeDefined()
  })

  it('says there are no results', async () => {
    const { wrapper } = await mountView(ImportView, '/import')
    await search(wrapper, 'nobody')
    await vi.waitFor(() =>
      expect(wrapper.text()).toContain('YouTube Music found no artist matching “nobody”.'),
    )
  })

  it('shows the YouTube Music error and clears it on the next search', async () => {
    server.use(
      http.get(
        '/api/v1/catalog/ytmusic/artists/',
        () => HttpResponse.json({ detail: 'YouTube Music did not answer.' }, { status: 502 }),
        { once: true },
      ),
    )
    const { wrapper } = await mountView(ImportView, '/import')
    await search(wrapper, 'daft')
    await vi.waitFor(() =>
      expect(wrapper.get('[role="alert"]').text()).toBe('YouTube Music did not answer.'),
    )
    expect(wrapper.find('.results').exists()).toBe(false)
    await search(wrapper, 'daft')
    await vi.waitFor(() => expect(wrapper.findAll('.results li')).toHaveLength(2))
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
  })

  it('the selection survives across searches and can be removed', async () => {
    const { wrapper } = await mountView(ImportView, '/import')
    expect(button(wrapper, 'Import').attributes('disabled')).toBeDefined()
    await search(wrapper, 'daft')
    await vi.waitFor(() => expect(wrapper.findAll('.results li')).toHaveLength(2))
    await item(wrapper, 'Daft Punk').get('input').setValue(true)
    await search(wrapper, 'justice')
    await vi.waitFor(() => expect(wrapper.findAll('.results li')).toHaveLength(1))
    await item(wrapper, 'Justice').get('input').setValue(true)
    expect(wrapper.get('.selected h2').text()).toBe('Selected (2)')
    expect(button(wrapper, 'Import').text()).toBe('Import 2 artists')
    await wrapper.get('[aria-label="Remove Justice"]').trigger('click')
    expect(button(wrapper, 'Import').text()).toBe('Import 1 artist')
    expect((item(wrapper, 'Justice').get('input').element as HTMLInputElement).checked).toBe(false)
    await search(wrapper, 'daft')
    await vi.waitFor(() => expect(wrapper.findAll('.results li')).toHaveLength(2))
    const daft = item(wrapper, 'Daft Punk').get('input')
    expect((daft.element as HTMLInputElement).checked).toBe(true)
    await daft.setValue(false)
    expect(wrapper.find('.selected').exists()).toBe(false)
  })

  it('starts the import with the channel ids and follows it', async () => {
    let body: unknown
    server.use(
      http.post('/api/v1/jobs/runs/', async ({ request }) => {
        body = await request.json()
        return HttpResponse.json(
          { id: 3, kind: 'import', status: 'running', done: 0, total: 2, current: 'Justice' },
          { status: 201 },
        )
      }),
      http.get('/api/v1/jobs/runs/3/', () =>
        HttpResponse.json({ id: 3, kind: 'import', status: 'running', done: 1, total: 2 }),
      ),
    )
    const { wrapper } = await mountView(ImportView, '/import')
    await search(wrapper, 'u')
    await vi.waitFor(() => expect(wrapper.findAll('.results li')).toHaveLength(3))
    await item(wrapper, 'Daft Punk').get('input').setValue(true)
    await item(wrapper, 'Justice').get('input').setValue(true)
    await button(wrapper, 'Import').trigger('click')
    await vi.waitFor(() =>
      expect(body).toEqual({
        kind: 'import',
        params: { artist_ids: ['UCdaftpunk0000000000000a', 'UCjustice00000000000000b'] },
      }),
    )
    await vi.waitFor(() => expect(wrapper.get('.job__status').text()).toContain('1 / 2'))
    // The selection empties and another cannot start while this one is running.
    expect(wrapper.find('.selected').exists()).toBe(false)
    await item(wrapper, 'Justice').get('input').setValue(true)
    expect(button(wrapper, 'Import').attributes('disabled')).toBeDefined()
    wrapper.unmount()
  })

  it('after a finished import it points to the Related tab', async () => {
    const done = { id: 4, kind: 'import', status: 'succeeded', done: 1, total: 1 }
    server.use(
      http.post('/api/v1/jobs/runs/', () => HttpResponse.json(done, { status: 201 })),
      http.get('/api/v1/jobs/runs/4/', () => HttpResponse.json(done)),
    )
    const { wrapper } = await mountView(ImportView, '/import')
    expect(wrapper.find('a[href="/library?tab=related"]').exists()).toBe(false)
    await search(wrapper, 'justice')
    await vi.waitFor(() => expect(wrapper.findAll('.results li')).toHaveLength(1))
    await item(wrapper, 'Justice').get('input').setValue(true)
    await button(wrapper, 'Import').trigger('click')
    await vi.waitFor(() =>
      expect(wrapper.get('a[href="/library?tab=related"]').text()).toContain('Related tab'),
    )
    wrapper.unmount()
  })

  it('if the API rejects the import, the selection is kept', async () => {
    server.use(
      http.post('/api/v1/jobs/runs/', () =>
        HttpResponse.json({ detail: 'An import is already running.' }, { status: 409 }),
      ),
    )
    const { wrapper } = await mountView(ImportView, '/import')
    await search(wrapper, 'justice')
    await vi.waitFor(() => expect(wrapper.findAll('.results li')).toHaveLength(1))
    await item(wrapper, 'Justice').get('input').setValue(true)
    await button(wrapper, 'Import').trigger('click')
    await vi.waitFor(() =>
      expect(wrapper.get('.job [role="alert"]').text()).toBe('An import is already running.'),
    )
    expect(wrapper.get('.selected h2').text()).toBe('Selected (1)')
  })

  it('links to “Import a folder”', async () => {
    const { wrapper } = await mountView(ImportView, '/import')
    expect(wrapper.get('a[href="/import/folder"]').text()).toBe('Import a folder')
  })

  it('has the same texts in English and Spanish', () => {
    const keys = (tree: object, prefix = ''): string[] =>
      Object.entries(tree).flatMap(([k, v]) =>
        typeof v === 'string' ? [`${prefix}${k}`] : keys(v, `${prefix}${k}.`),
      )
    expect(keys(messages.en.import as object)).toEqual(keys(messages.es.import as object))
  })
})
