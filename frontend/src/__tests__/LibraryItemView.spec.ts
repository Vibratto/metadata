import { http, HttpResponse } from 'msw'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import libraryHandlers from '../mocks/handlers/library'
import { server } from '../mocks/server'
import LibraryItemView from '../views/library/LibraryItemView.vue'
import { trackRequests } from './settle'
import { fill, mountView } from './viewHelpers'

// jsdom does not implement showModal/close on <dialog>.
Object.assign(HTMLDialogElement.prototype, {
  showModal(this: HTMLDialogElement) {
    this.setAttribute('open', '')
  },
  close(this: HTMLDialogElement) {
    this.removeAttribute('open')
  },
})

type Wrapper = Awaited<ReturnType<typeof mountView>>['wrapper']

async function open(path: string) {
  const ctx = await mountView(LibraryItemView, path)
  await settle()
  return ctx
}

const button = (wrapper: Wrapper, text: string) =>
  wrapper.findAll('button').find((b) => b.text() === text || b.attributes('aria-label') === text)!
const link = (wrapper: Wrapper, text: string) => wrapper.findAll('a').find((a) => a.text() === text)

/** JSON body of the next request with that method and path. */
function capture(method: string, path: string): Promise<unknown> {
  return new Promise((resolve) => {
    server.events.on('request:start', ({ request }) => {
      if (request.method === method && new URL(request.url).pathname === path)
        void request.clone().json().then(resolve)
    })
  })
}

// Other areas also mock the library lists: here the Library ones win.
let settle: () => Promise<void>
beforeEach(() => {
  server.use(...libraryHandlers)
  settle = trackRequests()
})
afterEach(() => server.events.removeAllListeners())

describe('LibraryItemView', () => {
  it("shows a track's data with links to its artists and album", async () => {
    const { wrapper } = await open('/library/tracks/100')
    expect(wrapper.get('h1').text()).toBe('Get Lucky')
    const text = wrapper.get('.item__data').text()
    expect(text).toContain('1-8')
    expect(text).toContain('6:09')
    expect(text).toContain('5NV6Rdv1a3I')
    expect(wrapper.get('.item__downloaded').text()).toBe('Yes')
    expect(link(wrapper, 'Pharrell Williams')?.attributes('href')).toBe('/library/artists/2')
    expect(link(wrapper, 'View the album')?.attributes('href')).toBe('/library/albums/10')
  })

  it('a track page has “Preview” and opens the modal with the video', async () => {
    server.use(
      http.get('/api/v1/catalog/tracks/:id/video/', () =>
        HttpResponse.json({ video_id: 'abcdefghijk', embed_url: 'https://e/embed/a' }),
      ),
    )
    const { wrapper } = await open('/library/tracks/100')
    await button(wrapper, 'Preview: Get Lucky').trigger('click')
    await vi.waitFor(() =>
      expect(wrapper.get('dialog[open] iframe').attributes('src')).toBe('https://e/embed/a'),
    )
  })

  it('an album page has no preview', async () => {
    const { wrapper } = await open('/library/albums/10')
    expect(wrapper.find('[aria-label^="Preview"]').exists()).toBe(false)
  })

  it('a track page shows its album cover', async () => {
    const { wrapper } = await open('/library/tracks/100')
    expect(wrapper.get('img').attributes('src')).toBe('https://example.com/ram.jpg')
  })

  describe('recording on several albums', () => {
    const shared = (extra: object = {}) =>
      http.get('/api/v1/catalog/recordings/:id/', () =>
        HttpResponse.json({
          id: 100,
          title: 'Get Lucky',
          duration: 369,
          explicit: false,
          video_id: '5NV6Rdv1a3I',
          artists: [],
          track_count: 2,
          downloaded: true,
          tracks: [
            {
              id: 100,
              album: 10,
              album_title: 'Random Access Memories',
              title: 'Get Lucky',
              disc_number: 1,
              track_number: 8,
              downloaded: true,
            },
            {
              id: 150,
              album: 11,
              album_title: 'Get Lucky (single)',
              title: 'Get Lucky',
              disc_number: 1,
              track_number: 1,
              downloaded: false,
            },
          ],
          ...extra,
        }),
      )

    it('lists the other albums the recording appears on', async () => {
      server.use(shared())
      const { wrapper } = await open('/library/tracks/100')
      const section = wrapper.get('.appearances')
      expect(section.get('h2').text()).toBe('Also appears on')
      expect(section.findAll('li').map((li) => li.text())).toEqual(['Get Lucky (single)1-1'])
      expect(link(wrapper, 'Get Lucky (single)')?.attributes('href')).toBe('/library/tracks/150')
    })

    it('splits the track from the others', async () => {
      server.use(shared())
      let split = false
      server.events.on('request:start', ({ request }) => {
        if (request.method === 'POST' && request.url.endsWith('/catalog/tracks/100/split/'))
          split = true
      })
      const { wrapper } = await open('/library/tracks/100')
      await button(wrapper, 'Split from the others').trigger('click')
      await vi.waitFor(() => expect(split).toBe(true))
      await settle()
    })

    it('merges another recording into this one', async () => {
      const body = capture('POST', '/api/v1/catalog/recordings/100/merge/')
      const { wrapper } = await open('/library/tracks/100')
      expect(wrapper.text()).toContain('This recording is only on this album.')
      expect(button(wrapper, 'Split from the others')).toBeUndefined()
      await fill(wrapper, 'Id of the recording to absorb', '7')
      await wrapper.get('.appearances__merge').trigger('submit')
      expect(await body).toEqual({ recording: 7 })
    })

    it('shows the API rejection on merge', async () => {
      server.use(
        http.post('/api/v1/catalog/recordings/100/merge/', () =>
          HttpResponse.json({ detail: 'Same album.' }, { status: 400 }),
        ),
      )
      const { wrapper } = await open('/library/tracks/100')
      await fill(wrapper, 'Id of the recording to absorb', '7')
      await wrapper.get('.appearances__merge').trigger('submit')
      await vi.waitFor(() =>
        expect(wrapper.get('.appearances [role="alert"]').text()).toContain('Same album.'),
      )
    })
  })

  it('links to the audio upload of a track', async () => {
    const { wrapper } = await open('/library/tracks/101')
    expect(link(wrapper, 'Upload audio')?.attributes('href')).toBe('/tracks/101/upload')
    expect(wrapper.get('.item__downloaded').text()).toBe('No')
  })

  it('goes from a track to its album reloading the page', async () => {
    const { wrapper, router } = await open('/library/tracks/101')
    expect(wrapper.text()).not.toContain('YouTube Music ID')
    await link(wrapper, 'View the album')!.trigger('click')
    await settle()
    await vi.waitFor(() => expect(router.currentRoute.value.path).toBe('/library/albums/10'))
    await vi.waitFor(() => expect(wrapper.find('h1').text()).toBe('Random Access Memories'))
    expect(wrapper.get('img').attributes('src')).toBe('https://example.com/ram.jpg')
    expect(link(wrapper, 'View their tracks')?.attributes('href')).toBe(
      '/library?tab=tracks&album=10',
    )
  })

  it('does not reload when leaving the page', async () => {
    const { router } = await open('/library/artists/1')
    const fetched = vi.fn()
    server.events.on('request:start', fetched)
    await router.push('/library')
    await settle()
    expect(fetched).not.toHaveBeenCalled()
  })

  it("shows an artist's profile with links to their albums and tracks, without credits or blocking", async () => {
    const { wrapper } = await open('/library/artists/1')
    expect(link(wrapper, 'View their albums')?.attributes('href')).toBe(
      '/library?tab=albums&artist=1',
    )
    expect(link(wrapper, 'View their tracks')?.attributes('href')).toBe(
      '/library?tab=tracks&artist=1',
    )
    expect(wrapper.find('img').exists()).toBe(false)
    expect(wrapper.get('.item__description').text()).toBe('French electronic duo.')
    const data = wrapper.get('.item__data').text()
    expect(data).toContain('21.4M monthly listeners')
    expect(data).toContain('UCdaftpunk0000000000000a')
    expect(wrapper.find('.artists-editor').exists()).toBe(false)
    expect(button(wrapper, 'Block')).toBeUndefined()
    expect(link(wrapper, 'Back to the library')?.attributes('href')).toBe('/library?tab=artists')
  })

  it('shows the error if the item does not exist', async () => {
    const { wrapper } = await open('/library/tracks/999')
    expect(wrapper.get('[role="alert"]').text()).toBe('Not found.')
    expect(wrapper.find('h1').exists()).toBe(false)
  })

  describe('editing', () => {
    it('saves the fields with their type and shows the result', async () => {
      const { wrapper } = await open('/library/tracks/100')
      const body = capture('PATCH', '/api/v1/catalog/tracks/100/')
      await fill(wrapper, 'Title', 'Get Lucky (Edit)')
      await fill(wrapper, 'Track number', '9')
      await wrapper.get('form').trigger('submit')
      await settle()
      expect(await body).toEqual({ title: 'Get Lucky (Edit)', track_number: 9, disc_number: 1 })
      expect(wrapper.get('h1').text()).toBe('Get Lucky (Edit)')
      expect(wrapper.get('[role="status"]').text()).toBe('Changes saved.')
    })

    it('sends an empty year as null', async () => {
      const { wrapper } = await open('/library/albums/10')
      const body = capture('PATCH', '/api/v1/catalog/albums/10/')
      await fill(wrapper, 'Year', '')
      await wrapper.get('form').trigger('submit')
      expect(await body).toMatchObject({
        year: null,
        cover_url: 'https://example.com/ram.jpg',
      })
    })

    it('shows each validation error on its field', async () => {
      server.use(
        http.patch('/api/v1/catalog/artists/1/', () =>
          HttpResponse.json({ name: ['Required.'], other: ['x'] }, { status: 400 }),
        ),
      )
      const { wrapper } = await open('/library/artists/1')
      await wrapper.get('form').trigger('submit')
      await settle()
      expect(wrapper.get('.field__error').text()).toBe('Required.')
      expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    })

    it("shows a general error when it is not a field's", async () => {
      server.use(
        http.patch('/api/v1/catalog/artists/1/', () => new HttpResponse(null, { status: 500 })),
      )
      const { wrapper } = await open('/library/artists/1')
      await wrapper.get('form').trigger('submit')
      await settle()
      expect(wrapper.get('[role="alert"]').text()).toBe(
        'The server failed. Please try again later.',
      )
      expect(wrapper.find('.field__error').exists()).toBe(false)
    })
  })

  describe('credits', () => {
    it('removes, reorders, adds from the library and saves in order', async () => {
      const { wrapper } = await open('/library/tracks/100')
      const body = capture('PUT', '/api/v1/catalog/tracks/100/artists/')
      expect(button(wrapper, 'Move Daft Punk up').attributes('disabled')).toBeDefined()
      expect(button(wrapper, 'Move Pharrell Williams down').attributes('disabled')).toBeDefined()
      await button(wrapper, 'Move Daft Punk down').trigger('click')
      await button(wrapper, 'Move Daft Punk up').trigger('click')
      await button(wrapper, 'Remove Daft Punk').trigger('click')
      await fill(wrapper, 'Search a catalogue artist', 'daft')
      await wrapper.get('.artists-editor form').trigger('submit')
      await settle()
      const add = wrapper.findAll('.artists-editor__found button')
      expect(add[1]?.attributes('disabled')).toBeDefined()
      await add[0]!.trigger('click')
      await button(wrapper, 'Save artists').trigger('click')
      await settle()
      expect(await body).toEqual({ artists: [2, 1] })
      expect(wrapper.get('[role="status"]').text()).toBe('Artists updated.')
      expect(link(wrapper, 'Pharrell Williams')).toBeDefined()
    })

    it('searches library artists by itself once typing stops', async () => {
      const { wrapper } = await open('/library/tracks/100')
      await wrapper.get('.artists-editor input[type="search"]').setValue('daft')
      await vi.waitFor(() =>
        expect(wrapper.findAll('.artists-editor__found button').length).toBeGreaterThan(0),
      )
    })

    it('does not allow saving without artists', async () => {
      const { wrapper } = await open('/library/albums/10')
      await button(wrapper, 'Remove Daft Punk').trigger('click')
      expect(button(wrapper, 'Save artists').attributes('disabled')).toBeDefined()
    })

    it('shows search and save errors', async () => {
      server.use(
        http.get('/api/v1/catalog/artists/', () => new HttpResponse(null, { status: 500 })),
        http.put('/api/v1/catalog/albums/10/artists/', () =>
          HttpResponse.json({ artists: ['Does not exist.'] }, { status: 400 }),
        ),
      )
      const { wrapper } = await open('/library/albums/10')
      await wrapper.get('.artists-editor form').trigger('submit')
      await settle()
      expect(wrapper.get('.artists-editor [role="alert"]').text()).toContain('The server failed')
      await button(wrapper, 'Save artists').trigger('click')
      await settle()
      expect(wrapper.get('.artists-editor [role="alert"]').text()).toBe('Does not exist.')
    })
  })

  describe('history', () => {
    it('lists the versions and reverts to one', async () => {
      const { wrapper } = await open('/library/tracks/100')
      const entries = wrapper.findAll('.history__entry')
      expect(entries).toHaveLength(2)
      expect(entries[0]!.text()).toContain('Changed')
      expect(entries[0]!.text()).toContain('demo')
      expect(entries[1]!.text()).toContain('Created')
      expect(entries[1]!.text()).toContain('System')
      const body = capture('POST', '/api/v1/catalog/tracks/100/revert/')
      await entries[1]!.get('button').trigger('click')
      await settle()
      expect(await body).toEqual({ history_id: 1 })
      expect(wrapper.get('[role="status"]').text()).toBe('Reverted to the chosen version.')
    })

    it('scrolls to the history when the link asks for it', async () => {
      const scroll = vi.fn()
      Element.prototype.scrollIntoView = scroll
      const { wrapper } = await open('/library/tracks/100#history')
      expect(scroll).toHaveBeenCalledOnce()
      expect(scroll.mock.contexts[0]).toBe(wrapper.get('#history').element)
    })

    it('shows an unknown type as is and empty values as a dash', async () => {
      server.use(
        http.get('/api/v1/catalog/albums/10/history/', () =>
          HttpResponse.json([
            {
              history_id: 5,
              history_date: '2026-10-01T10:00:00Z',
              history_type: '-',
              history_user: 'demo',
              changes: { year: null, cover_url: '' },
            },
            {
              history_id: 4,
              history_date: '2026-10-01T09:00:00Z',
              history_type: '?',
              history_user: 'demo',
              changes: {},
            },
          ]),
        ),
      )
      const { wrapper } = await open('/library/albums/10')
      const entries = wrapper.findAll('.history__entry')
      expect(entries[0]!.text()).toContain('Deleted')
      expect(entries[0]!.findAll('dd').map((d) => d.text())).toEqual(['—', '—'])
      expect(entries[1]!.text()).toContain('?')
    })

    it('shows load and revert errors', async () => {
      server.use(
        http.get(
          '/api/v1/catalog/artists/1/history/',
          () => new HttpResponse(null, { status: 500 }),
        ),
      )
      const { wrapper } = await open('/library/artists/1')
      expect(wrapper.get('.history [role="alert"]').text()).toContain('The server failed')

      server.use(
        http.post('/api/v1/catalog/tracks/100/revert/', () =>
          HttpResponse.json({ detail: 'That version does not exist.' }, { status: 404 }),
        ),
      )
      const track = await open('/library/tracks/100')
      await track.wrapper.get('.history__entry button').trigger('click')
      await settle()
      expect(track.wrapper.get('.history [role="alert"]').text()).toBe(
        'That version does not exist.',
      )
    })
  })

  describe('deleting', () => {
    function deleted() {
      const seen: string[] = []
      server.events.on('request:start', ({ request }) => {
        if (request.method === 'DELETE') seen.push(request.url)
      })
      return seen
    }

    it('asks for confirmation and deletes the track', async () => {
      const { wrapper } = await open('/library/tracks/100')
      const seen = deleted()
      await button(wrapper, 'Delete').trigger('click')
      expect(wrapper.findAll('dialog')[1]!.text()).toContain('Delete the track “Get Lucky”?')
      await wrapper.findAll('dialog')[1]!.get('.btn--danger').trigger('click')
      await settle()
      expect(seen.map((u) => new URL(u).pathname + new URL(u).search)).toEqual([
        '/api/v1/catalog/tracks/100/',
      ])
    })

    it('can block at the same time', async () => {
      const { wrapper } = await open('/library/albums/10')
      const seen = deleted()
      await button(wrapper, 'Delete').trigger('click')
      await wrapper.findAll('dialog')[1]!.get('input[type="checkbox"]').setValue(true)
      await wrapper.findAll('dialog')[1]!.get('.btn--danger').trigger('click')
      await settle()
      expect(new URL(seen[0]!).search).toBe('?block=true')
    })
  })

  describe('blocking', () => {
    it('asks for confirmation and blocks the track', async () => {
      const { wrapper } = await open('/library/tracks/100')
      await button(wrapper, 'Block').trigger('click')
      await settle()
      expect(wrapper.get('dialog').text()).toContain('Block the track “Get Lucky”?')
      const body = capture('POST', '/api/v1/catalog/blocked/')
      await wrapper.get('dialog .btn--danger').trigger('click')
      await settle()
      expect(await body).toEqual({
        kind: 'track',
        external_id: '5NV6Rdv1a3I',
        name: 'Get Lucky',
      })
      expect(wrapper.get('[role="status"]').text()).toBe(
        "Blocked: it won't be imported or downloaded again.",
      )
      expect(wrapper.get('dialog').attributes('open')).toBeUndefined()
    })

    it('can be cancelled without blocking', async () => {
      const { wrapper } = await open('/library/tracks/100')
      const posted = vi.fn()
      server.events.on('request:start', ({ request }) => {
        if (request.method === 'POST') posted()
      })
      await button(wrapper, 'Block').trigger('click')
      await settle()
      await button(wrapper, 'Close').trigger('click')
      await settle()
      expect(wrapper.get('dialog').attributes('open')).toBeUndefined()
      expect(posted).not.toHaveBeenCalled()
    })

    it('shows the error if it was already blocked', async () => {
      server.use(
        http.post('/api/v1/catalog/blocked/', () =>
          HttpResponse.json({ non_field_errors: ['It is already blocked.'] }, { status: 400 }),
        ),
      )
      const { wrapper } = await open('/library/albums/10')
      await button(wrapper, 'Block').trigger('click')
      await wrapper.get('dialog .btn--danger').trigger('click')
      await settle()
      expect(wrapper.get('[role="alert"]').text()).toBe('It is already blocked.')
    })

    it('does not offer blocking for what has no YouTube Music id', async () => {
      server.use(
        http.get('/api/v1/catalog/tracks/101/', () =>
          HttpResponse.json({
            id: 101,
            album: 10,
            title: 'Local',
            track_number: 1,
            disc_number: 1,
            duration: null,
            video_id: null,
            artists: [],
            downloaded: false,
          }),
        ),
      )
      const { wrapper } = await open('/library/tracks/101')
      expect(button(wrapper, 'Block')).toBeUndefined()
      expect(wrapper.text()).not.toContain('Duration')
      expect(wrapper.text()).not.toContain('YouTube Music ID')
    })
  })
})
