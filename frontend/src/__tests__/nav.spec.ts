import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'
import { createMemoryHistory, createRouter, type RouteRecordRaw } from 'vue-router'

import AppNav from '../components/AppNav.vue'
import { navEntries } from '../components/nav-meta'
import { useSessionStore } from '../stores/session'
import MoreView from '../views/MoreView.vue'
import { render } from './helpers'

const Empty = { template: '<div />' }
const route = (name: string, meta: RouteRecordRaw['meta']): RouteRecordRaw => ({
  path: `/${name}`,
  name,
  component: Empty,
  meta: { navLabel: 'nav.home', ...meta },
})

// Six main entries (one too many) and three secondary ones, one of them in administration.
const routes: RouteRecordRaw[] = [
  route('m3', { navGroup: 'main', navOrder: 3 }),
  route('m1', { navGroup: 'main', navOrder: 1 }),
  route('m2', { navGroup: 'main', navOrder: 2 }),
  route('m4', { navGroup: 'main', navOrder: 4 }),
  route('m5', { navGroup: 'main', navOrder: 5 }),
  route('s2', { navGroup: 'more', navOrder: 2, navSection: 'admin' }),
  route('s1', {}),
  route('s3', { navGroup: 'more', navOrder: 3, navSection: 'admin' }),
  { path: '/unnamed', component: Empty, meta: { navLabel: 'nav.home' } },
  { path: '/hidden', component: Empty },
  { path: '/more', name: 'more', component: MoreView },
  { path: '/account', name: 'account', component: Empty },
]

function mount(locale = 'en') {
  const pinia = createPinia()
  setActivePinia(pinia)
  useSessionStore().user = { username: 'demo', language: '' }
  const router = createRouter({ history: createMemoryHistory(), routes })
  return {
    router,
    render: (c: object) => render(c, { global: { plugins: [pinia, router] } }, locale),
  }
}

const names = (w: ReturnType<typeof render>, selector: string) =>
  w.findAll(`${selector} a`).map((a) => a.attributes('href'))

describe('navEntries', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('sorts by navOrder and leaves “more” as the default', () => {
    const r = createRouter({ history: createMemoryHistory(), routes })
    const { main, more } = navEntries(r.getRoutes())
    expect(main.map((e) => e.name)).toEqual(['m1', 'm2', 'm3', 'm4'])
    expect(more.map((e) => e.path)).toEqual(['/m5', '/s1', '/unnamed', '/s2', '/s3'])
  })

  it('groups the rest by section: follow-up by default and then administration', () => {
    const r = createRouter({ history: createMemoryHistory(), routes })
    const { sections } = navEntries(r.getRoutes())
    expect(sections.map((s) => [s.key, s.routes.map((e) => e.path)])).toEqual([
      ['follow', ['/m5', '/s1', '/unnamed']],
      ['admin', ['/s2', '/s3']],
    ])
  })

  it('omits sections left empty', () => {
    const r = createRouter({ history: createMemoryHistory(), routes })
    const keys = () => navEntries(r.getRoutes()).sections.map((s) => s.key)
    expect(keys()).toEqual(['follow', 'admin'])
    r.removeRoute('s2')
    r.removeRoute('s3')
    expect(keys()).toEqual(['follow'])
  })
})

describe('AppNav', () => {
  it('on mobile: four main ones and “More”', async () => {
    const ctx = mount()
    await ctx.router.push('/m1')
    const w = ctx.render(AppNav)
    expect(w.get('nav').attributes('aria-label')).toBe('Main navigation')
    expect(names(w, '.nav__main li:not(.nav__more-item)')).toEqual(['/m1', '/m2', '/m3', '/m4'])
    expect(w.get('.nav__more-link').attributes('href')).toBe('/more')
    expect(w.get('.nav__more-link').text()).toBe('More')
    expect(w.get('.nav__main a').classes()).toContain('router-link-exact-active')
  })

  it('on desktop: the brand, the rest grouped by section and the account at the bottom', () => {
    const w = mount().render(AppNav)
    expect(w.get('.nav__brand').text()).toBe('Vibratto Metadata')
    expect(w.findAll('.nav__group-title').map((h) => h.text())).toEqual([
      'Follow-up',
      'Administration',
    ])
    expect(names(w, '.nav__secondary')).toEqual(['/m5', '/s1', '/unnamed', '/s2', '/s3'])
    const user = w.get('.nav__user')
    expect(user.attributes('href')).toBe('/account')
    expect(user.text()).toContain('demo')
  })

  it('every entry carries its icon', () => {
    const w = mount().render(AppNav)
    expect(w.findAll('.nav__main a').every((a) => a.find('svg').exists())).toBe(true)
  })

  it('translates to Spanish', () => {
    const w = mount('es').render(AppNav)
    expect(w.get('.nav__main a').text()).toBe('Inicio')
    expect(w.get('.nav__more-link').text()).toBe('Más')
  })

  it('uses the path as key if it has no name', () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const r = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/x', component: Empty, meta: { navLabel: 'nav.home', navGroup: 'main' } },
        { path: '/more', name: 'more', component: Empty },
      ],
    })
    expect(
      render(AppNav, { global: { plugins: [pinia, r] } }).findAll('.nav__main a'),
    ).toHaveLength(2)
  })
})

describe('MoreView', () => {
  it('lists by section the entries that do not fit the bottom bar', () => {
    const w = mount().render(MoreView)
    expect(w.get('h1').text()).toBe('More')
    expect(w.findAll('h2').map((h) => h.text())).toEqual(['Follow-up', 'Administration'])
    expect(w.findAll('.more a').map((a) => a.attributes('href'))).toEqual([
      '/m5',
      '/s1',
      '/unnamed',
      '/s2',
      '/s3',
    ])
  })

  it('links to the account and allows changing the theme', () => {
    const w = mount().render(MoreView)
    expect(w.get('.more__user').attributes('href')).toBe('/account')
    expect(w.get('.more__user').text()).toContain('demo')
    expect(w.find('button[aria-label^="Theme"]').exists()).toBe(true)
  })
})
