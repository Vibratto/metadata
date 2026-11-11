import { http, HttpResponse } from 'msw'
import { flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { describe, expect, it } from 'vitest'
import { createMemoryHistory, createRouter, type RouteLocationNormalized } from 'vue-router'

import { navEntries } from '../components/nav-meta'
import { messages } from '../locales'
import { server } from '../mocks/server'
import { routes } from '../router'
import { authGuard } from '../router/guards'
import SettingsView from '../views/SettingsView.vue'
import { choose, chosen, dropdown, fill, mountView } from './viewHelpers'

const field = (wrapper: Awaited<ReturnType<typeof mountView>>['wrapper'], label: string) => {
  const id = wrapper
    .findAll('label')
    .find((l) => l.text() === label)
    ?.attributes('for')
  return wrapper.get(`#${id}`)
}

describe('SettingsView', () => {
  it('loads the settings and links to the account', async () => {
    const { wrapper } = await mountView(SettingsView, '/settings')
    expect(chosen(wrapper, 'Download format')).toBe('opus')
    expect((field(wrapper, 'Download folder').element as HTMLInputElement).value).toBe('music')
    expect(wrapper.text()).toContain('{albumartist} {artist} {album} {disc} {track} {title} {year}')
    expect(wrapper.text()).toContain('{album} in the folders')
    expect(wrapper.get('a').attributes('href')).toBe('/account')
  })

  it('saves only the changed settings', async () => {
    const puts: string[] = []
    server.use(
      http.put('/api/v1/preferences/:key/', async ({ params, request }) => {
        puts.push(params.key as string)
        const { value } = (await request.json()) as { value: unknown }
        return HttpResponse.json({ key: params.key, value, default: 'mp3' })
      }),
    )
    const { wrapper } = await mountView(SettingsView, '/settings')
    await choose(wrapper, 'Download format', 'flac')
    await fill(wrapper, 'Download folder', 'songs')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(puts.sort()).toEqual(['download.folder', 'download.format'])
    expect(wrapper.get('[role="status"]').text()).toBe('Settings saved.')

    // Already saved: a second submit does not repeat the requests.
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(puts).toHaveLength(2)
  })

  it('saves the suggestion threshold as a number', async () => {
    const bodies: unknown[] = []
    server.use(
      http.put('/api/v1/preferences/import.suggestion_threshold/', async ({ request }) => {
        const body = (await request.json()) as { value: unknown }
        bodies.push(body)
        return HttpResponse.json({ key: 'import.suggestion_threshold', ...body, default: 1 })
      }),
    )
    const { wrapper } = await mountView(SettingsView, '/settings')
    const threshold = field(wrapper, 'Suggest importing related artists from')
    expect((threshold.element as HTMLInputElement).value).toBe('1000000')
    await fill(wrapper, 'Suggest importing related artists from', '250000')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(bodies).toEqual([{ value: 250000 }])
    expect(wrapper.get('[role="status"]').text()).toBe('Settings saved.')
  })

  it('shows the validation error on its field and saves the others', async () => {
    server.use(
      http.put('/api/v1/preferences/download.name_template/', () =>
        HttpResponse.json({ value: ['Invalid template.'] }, { status: 400 }),
      ),
      http.put('/api/v1/preferences/download.format/', () =>
        HttpResponse.json({ value: ['Invalid format.'] }, { status: 400 }),
      ),
    )
    const { wrapper } = await mountView(SettingsView, '/settings')
    await fill(wrapper, 'Naming template', '{nothing}')
    await choose(wrapper, 'Download format', 'mp3')
    await fill(wrapper, 'Download folder', 'songs')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    const template = field(wrapper, 'Naming template')
    expect(template.attributes('aria-invalid')).toBe('true')
    expect(wrapper.text()).toContain('Invalid template.')
    const format = dropdown(wrapper, 'Download format').get('[role="combobox"]')
    expect(format.attributes('aria-invalid')).toBe('true')
    expect(format.attributes('aria-describedby')).toBeTruthy()
    expect(wrapper.text()).toContain('Invalid format.')
    expect(wrapper.find('[role="status"]').exists()).toBe(false)
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
  })

  it('shows a general error if it fails without field errors', async () => {
    server.use(http.put('/api/v1/preferences/:key/', () => new HttpResponse(null, { status: 500 })))
    const { wrapper } = await mountView(SettingsView, '/settings')
    await fill(wrapper, 'Download folder', 'songs')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toBe('The server failed. Please try again later.')
  })

  it('shows the error if it cannot load the settings and ignores foreign keys', async () => {
    server.use(
      http.get('/api/v1/preferences/', () => HttpResponse.json([{ key: 'other', value: 1 }])),
    )
    const { wrapper } = await mountView(SettingsView, '/settings')
    expect((field(wrapper, 'Download folder').element as HTMLInputElement).value).toBe('')
    server.use(http.get('/api/v1/preferences/', () => new HttpResponse(null, { status: 403 })))
    const failed = await mountView(SettingsView, '/settings')
    expect(failed.wrapper.get('[role="alert"]').text()).toBe('You are not allowed to do this.')
  })
})

describe('SettingsView · artist separators', () => {
  const NAVIDROME = [' / ', ' feat. ', ' feat ', ' ft. ', ' ft ', '; ']
  const separators = (wrapper: Awaited<ReturnType<typeof mountView>>['wrapper']) =>
    wrapper
      .findAll('input[aria-label^="Separator "]')
      .map((i) => (i.element as HTMLInputElement).value)
  const button = (wrapper: Awaited<ReturnType<typeof mountView>>['wrapper'], label: string) =>
    wrapper.get(`button[aria-label="${label}"]`)
  const putsOf = () => {
    const bodies: { key: string; value: unknown }[] = []
    server.use(
      http.put('/api/v1/preferences/:key/', async ({ params, request }) => {
        const { value } = (await request.json()) as { value: unknown }
        bodies.push({ key: params.key as string, value })
        return HttpResponse.json({ key: params.key, value, default: NAVIDROME })
      }),
    )
    return bodies
  }

  it('shows the Tags section with the saved separators, in order, and its hint', async () => {
    const { wrapper } = await mountView(SettingsView, '/settings')
    expect(wrapper.text()).toContain('Tags')
    expect(separators(wrapper)).toEqual(NAVIDROME)
    expect(wrapper.text()).toContain(
      'The first one joins the names that are shown. If you change this list and some file lacks the ARTISTS tag, set the same in Navidrome.',
    )
  })

  it('adds, removes, reorders and saves the list without trimming spaces', async () => {
    const bodies = putsOf()
    const { wrapper } = await mountView(SettingsView, '/settings')
    await button(wrapper, 'Remove separator 2').trigger('click')
    await button(wrapper, 'Move separator 1 down').trigger('click')
    await button(wrapper, 'Move separator 5 up').trigger('click')
    await byText(wrapper, 'Add separator').trigger('click')
    const inputs = wrapper.findAll('input[aria-label^="Separator "]')
    await inputs[inputs.length - 1]!.setValue(' + ')
    expect(separators(wrapper)).toEqual([' feat ', ' / ', ' ft. ', '; ', ' ft ', ' + '])
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(bodies).toEqual([
      { key: 'tags.artist_separators', value: [' feat ', ' / ', ' ft. ', '; ', ' ft ', ' + '] },
    ])
    expect(wrapper.get('[role="status"]').text()).toBe('Settings saved.')
  })

  it('does not allow moving the first up, the last down or removing the only one', async () => {
    const { wrapper } = await mountView(SettingsView, '/settings')
    expect(button(wrapper, 'Move separator 1 up').attributes('disabled')).toBeDefined()
    expect(button(wrapper, 'Move separator 6 down').attributes('disabled')).toBeDefined()
    for (let n = 6; n > 1; n--) await button(wrapper, `Remove separator ${n}`).trigger('click')
    expect(separators(wrapper)).toEqual([' / '])
    expect(button(wrapper, 'Remove separator 1').attributes('disabled')).toBeDefined()
  })

  it("restores Navidrome's and sends nothing if the list does not change", async () => {
    const bodies = putsOf()
    server.use(
      http.get('/api/v1/preferences/', () =>
        HttpResponse.json([
          { key: 'download.folder', value: 'music', default: 'music' },
          { key: 'download.format', value: 'mp3', default: 'mp3' },
          { key: 'download.name_template', value: '{title}', default: '{title}' },
          { key: 'tags.artist_separators', value: ['; '], default: NAVIDROME },
        ]),
      ),
    )
    const { wrapper } = await mountView(SettingsView, '/settings')
    expect(separators(wrapper)).toEqual(['; '])
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(bodies).toEqual([])
    await byText(wrapper, "Restore Navidrome's").trigger('click')
    expect(separators(wrapper)).toEqual(NAVIDROME)
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(bodies).toEqual([{ key: 'tags.artist_separators', value: NAVIDROME }])
  })

  it('shows the validation error of the list', async () => {
    server.use(
      http.put('/api/v1/preferences/tags.artist_separators/', () =>
        HttpResponse.json({ value: ['There are repeated separators.'] }, { status: 400 }),
      ),
    )
    const { wrapper } = await mountView(SettingsView, '/settings')
    await separatorsInput(wrapper, 2).setValue(' / ')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(wrapper.text()).toContain('There are repeated separators.')
    expect(wrapper.get('fieldset').attributes('aria-describedby')).toBeTruthy()
  })
})

const byText = (wrapper: Awaited<ReturnType<typeof mountView>>['wrapper'], text: string) =>
  wrapper.findAll('button').find((b) => b.text() === text)!

const separatorsInput = (wrapper: Awaited<ReturnType<typeof mountView>>['wrapper'], n: number) =>
  wrapper.get(`input[aria-label="Separator ${n}"]`)

describe('settings route', () => {
  it('is reachable and listed in the navigation', async () => {
    setActivePinia(createPinia())
    const router = createRouter({ history: createMemoryHistory(), routes })
    const { sections } = navEntries(router.getRoutes())
    const admin = sections.find((s) => s.key === 'admin')!
    expect(admin.routes.map((r) => r.name)).toContain('settings')
    const to = router.resolve('/settings') as unknown as RouteLocationNormalized
    expect(await authGuard(to)).toBe(true)
  })
})

describe('settings texts', () => {
  type Tree = { [key: string]: string | Tree }
  const paths = (tree: Tree, prefix = ''): string[] =>
    Object.entries(tree).flatMap(([k, v]) =>
      typeof v === 'string' ? [`${prefix}${k}`] : paths(v, `${prefix}${k}.`),
    )

  it('has the same keys in en and es', () => {
    expect(paths(messages.en.settings as Tree)).toEqual(paths(messages.es.settings as Tree))
  })
})
