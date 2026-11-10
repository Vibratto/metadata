import { flushPromises } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'

import GlobalSearch from '../components/GlobalSearch.vue'
import { messages } from '../locales'
import { server } from '../mocks/server'
import { routes } from '../router'
import { render } from './helpers'
import { choose, chosen, sessionPinia } from './viewHelpers'

async function mount(path = '/dashboard') {
  const pinia = sessionPinia()
  const router = createRouter({ history: createMemoryHistory(), routes })
  await router.push(path)
  const queries: Record<string, string>[] = []
  server.events.on('request:start', ({ request }) => {
    const url = new URL(request.url)
    if (url.pathname === '/api/v1/catalog/search/')
      queries.push(Object.fromEntries(url.searchParams))
  })
  const w = render(GlobalSearch, { global: { plugins: [pinia, router] }, attachTo: document.body })
  await flushPromises()
  return { w, router, queries }
}

const options = (w: Awaited<ReturnType<typeof mount>>['w']) =>
  w.findAll('.global-search__panel [role="option"]').map((o) => o.text())

async function type(w: Awaited<ReturnType<typeof mount>>['w'], text: string) {
  await w.get('input[role="combobox"]').setValue(text)
  await vi.waitFor(() =>
    expect(w.get('input[role="combobox"]').attributes('aria-expanded')).toBe('true'),
  )
  await vi.waitFor(() =>
    expect(w.findAll('.global-search__panel [role="option"]').length).toBeGreaterThan(0),
  )
}

afterEach(() => server.events.removeAllListeners())

describe('GlobalSearch', () => {
  it('typing requests catalog/search/ with q and the scope, after the wait', async () => {
    const { w, queries } = await mount()
    await w.get('input[role="combobox"]').setValue('disc')
    expect(queries).toHaveLength(0)
    await vi.waitFor(() => expect(queries.at(-1)).toEqual({ q: 'disc', type: 'all', limit: '5' }))
    w.unmount()
  })

  it('with “All” it shows the groups with their counts, from any view', async () => {
    const { w } = await mount('/download')
    await type(w, 'disc')
    const groups = w.findAll('[role="group"]')
    expect(groups.map((g) => g.attributes('aria-label'))).toEqual(['Artists', 'Albums', 'Tracks'])
    expect(options(w).some((o) => o.includes('Discovery') && o.includes('Daft Punk'))).toBe(true)
    expect(options(w)).toContain('See all 2 albums')
    w.unmount()
  })

  it('the scope picker narrows the search to one kind', async () => {
    const { w, queries } = await mount()
    await choose(w, 'Where to search', 'Albums')
    await type(w, 'disc')
    expect(queries.at(-1)).toMatchObject({ type: 'albums' })
    expect(w.findAll('[role="group"]').map((g) => g.attributes('aria-label'))).toEqual(['Albums'])
    w.unmount()
  })

  it('in the Library the default scope is the open tab', async () => {
    const { w } = await mount('/library?tab=tracks')
    expect(chosen(w, 'Where to search')).toBe('Tracks')
    w.unmount()
  })

  it('choosing a result opens its page', async () => {
    const { w, router } = await mount()
    await type(w, 'disc')
    await w
      .findAll('.global-search__panel [role="option"]')
      .find(
        (o) =>
          o.text().includes('Discovery') &&
          !o.text().includes('live') &&
          !o.text().startsWith('Ver'),
      )!
      .trigger('mousedown')
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('library-item')
    expect(router.currentRoute.value.params).toEqual({ kind: 'albums', id: '10' })
    w.unmount()
  })

  it('“See all N” opens the Library tab with the same search', async () => {
    const { w, router } = await mount()
    await type(w, 'disc')
    await w
      .findAll('.global-search__panel [role="option"]')
      .find((o) => o.text() === 'See all 2 albums')!
      .trigger('mousedown')
    await flushPromises()
    expect(router.currentRoute.value.query).toEqual({ tab: 'albums', search: 'disc' })
    w.unmount()
  })

  it('Enter with nothing highlighted opens the Library on the first group with results', async () => {
    const { w, router } = await mount()
    await type(w, 'disc')
    await w.get('form').trigger('submit')
    await flushPromises()
    expect(router.currentRoute.value.query).toEqual({ tab: 'artists', search: 'disc' })
    w.unmount()
  })

  it("Enter with a chosen scope opens that scope's tab", async () => {
    const { w, router } = await mount()
    await choose(w, 'Where to search', 'Tracks')
    await w.get('input[role="combobox"]').setValue('luz')
    await w.get('form').trigger('submit')
    await flushPromises()
    expect(router.currentRoute.value.query).toEqual({ tab: 'tracks', search: 'luz' })
    w.unmount()
  })

  it('works with arrows, Enter and Escape, with combobox roles and aria-live', async () => {
    const { w, router } = await mount()
    const input = w.get('input[role="combobox"]')
    expect(input.attributes('aria-expanded')).toBe('false')
    await type(w, 'disc')
    expect(input.attributes('aria-expanded')).toBe('true')
    expect(input.attributes('aria-controls')).toBe(
      w.get('.global-search__panel [role="listbox"]').attributes('id'),
    )
    expect(w.get('[aria-live="polite"]').text()).not.toBe('')
    await input.trigger('keydown', { key: 'ArrowDown' })
    expect(input.attributes('aria-activedescendant')).toBe(
      w.findAll('.global-search__panel [role="option"]')[0]!.attributes('id'),
    )
    await input.trigger('keydown', { key: 'Escape' })
    expect(input.attributes('aria-expanded')).toBe('false')
    await type(w, 'disc')
    await input.trigger('keydown', { key: 'ArrowDown' })
    await input.trigger('keydown', { key: 'Enter' })
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('library-item')
    w.unmount()
  })

  it('requests nothing with fewer than 2 characters', async () => {
    const { w, queries } = await mount()
    await w.get('input[role="combobox"]').setValue('d')
    await new Promise((r) => setTimeout(r, 400))
    expect(queries).toHaveLength(0)
    w.unmount()
  })

  it('has the new keys in English and Spanish', () => {
    const keys = (tree: object): string[] =>
      Object.entries(tree).flatMap(([k, v]) =>
        typeof v === 'string' ? [k] : keys(v as object).map((x) => `${k}.${x}`),
      )
    expect(keys(messages.en.search as object)).toEqual(keys(messages.es.search as object))
    expect(keys(messages.es.search as object)).toContain('scope.albums')
  })
})
