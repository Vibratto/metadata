import { flushPromises } from '@vue/test-utils'
import { http, HttpResponse } from 'msw'
import { describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'

import AppIcon from '../components/AppIcon.vue'
import AuthLayout from '../components/AuthLayout.vue'
import CoverArt from '../components/CoverArt.vue'
import GlobalSearch from '../components/GlobalSearch.vue'
import JobsIndicator from '../components/JobsIndicator.vue'
import { LOCALE_KEY } from '../i18n'
import { server } from '../mocks/server'
import { routes } from '../router'
import { render } from './helpers'
import { sessionPinia } from './viewHelpers'

async function withRouter(component: object, path = '/dashboard') {
  const pinia = sessionPinia()
  const router = createRouter({ history: createMemoryHistory(), routes })
  await router.push(path)
  const w = render(component, { global: { plugins: [pinia, router] }, attachTo: document.body })
  await flushPromises()
  return { w, router }
}

describe('AppIcon', () => {
  it('is decorative: the text next to it already says what it is', () => {
    const svg = render(AppIcon, { props: { name: 'disc' } }).get('svg')
    expect(svg.attributes('aria-hidden')).toBe('true')
    expect(svg.find('path').exists()).toBe(true)
  })
})

describe('CoverArt', () => {
  it('without an image it shows the initials of the name', () => {
    expect(render(CoverArt, { props: { name: 'Aurora Vale' } }).text()).toBe('AV')
    expect(render(CoverArt, { props: { name: 'bruma' } }).text()).toBe('B')
    expect(render(CoverArt, { props: { name: 'Los Cometas del Sur' } }).text()).toBe('LC')
  })

  it('with an image it shows it without alt text, because the name is already next to it', () => {
    const w = render(CoverArt, { props: { name: 'Bruma', src: 'https://img.test/b.jpg' } })
    expect(w.get('img').attributes('src')).toBe('https://img.test/b.jpg')
    expect(w.get('img').attributes('alt')).toBe('')
    expect(w.text()).toBe('')
  })

  it('the same name always gets the same colour', () => {
    const style = (name: string) => render(CoverArt, { props: { name } }).attributes('style')
    expect(style('Bruma')).toBe(style('Bruma'))
  })
})

describe('GlobalSearch', () => {
  it('searches the Library, in artists when outside it', async () => {
    const { w, router } = await withRouter(GlobalSearch)
    expect(w.get('form').attributes('role')).toBe('search')
    await w.get('input').setValue('  luz ')
    await w.get('form').trigger('submit')
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('library')
    expect(router.currentRoute.value.query).toEqual({ tab: 'artists', search: 'luz' })
    w.unmount()
  })

  it('inside the Library it searches the open tab', async () => {
    const { w, router } = await withRouter(GlobalSearch, '/library?tab=tracks')
    await w.get('input').setValue('luz')
    await w.get('form').trigger('submit')
    await flushPromises()
    expect(router.currentRoute.value.query).toEqual({ tab: 'tracks', search: 'luz' })
    w.unmount()
  })

  it('does nothing with an empty search', async () => {
    const { w, router } = await withRouter(GlobalSearch)
    await w.get('form').trigger('submit')
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('dashboard')
    w.unmount()
  })

  it('the “/” key jumps to the search, unless typing in another field', async () => {
    const { w } = await withRouter(GlobalSearch)
    const other = document.createElement('input')
    document.body.append(other)
    other.focus()
    other.dispatchEvent(new KeyboardEvent('keydown', { key: '/', bubbles: true }))
    expect(document.activeElement).toBe(other)
    other.blur()
    document.body.dispatchEvent(new KeyboardEvent('keydown', { key: '/', bubbles: true }))
    expect(document.activeElement).toBe(w.get('input').element)
    other.remove()
    w.unmount()
  })
})

describe('JobsIndicator', () => {
  it('says how many jobs are running and links to them', async () => {
    const { w } = await withRouter(JobsIndicator)
    await vi.waitFor(() => expect(w.text()).toBe('1 running job'))
    expect(w.get('a').attributes('href')).toBe('/dashboard')
    w.unmount()
  })

  it('is hidden when there are none', async () => {
    server.use(http.get('/api/v1/jobs/runs/', () => HttpResponse.json({ count: 0, results: [] })))
    const { w } = await withRouter(JobsIndicator)
    await flushPromises()
    expect(w.find('a').exists()).toBe(false)
    w.unmount()
  })
})

describe('AuthLayout', () => {
  it('shows the brand and the tagline next to the form', () => {
    const w = render(AuthLayout, { slots: { default: '<form>the form</form>' } })
    expect(w.get('.auth__brand').text()).toContain('Vibratto Metadata')
    expect(w.text()).toContain('Your music library, on any screen.')
    expect(w.text()).toContain('the form')
  })

  it('allows changing the language before signing in and remembers it', async () => {
    const w = render(AuthLayout)
    const spanish = w.findAll('.auth__lang button').find((b) => b.text() === 'Español')!
    expect(spanish.attributes('aria-pressed')).toBe('false')
    await spanish.trigger('click')
    expect(w.text()).toContain('Tu biblioteca musical, en cualquier pantalla.')
    expect(localStorage.getItem(LOCALE_KEY)).toBe('es')
    localStorage.clear()
  })
})
