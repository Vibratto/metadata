import { createPinia } from 'pinia'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'

import App from '../App.vue'
import { routes } from '../router'
import { useSessionStore } from '../stores/session'
import { render } from './helpers'

describe('App', () => {
  it('mounts the navigation and the active view', async () => {
    const router = createRouter({ history: createMemoryHistory(), routes })
    await router.push('/')
    const w = render(App, { global: { plugins: [createPinia(), router] } })
    expect(w.find('nav').exists()).toBe(true)
    expect(w.get('main.app-main').text()).toContain('Vibratto Metadata')
  })

  it('with a session it shows the top bar: search and theme', async () => {
    const pinia = createPinia()
    const router = createRouter({ history: createMemoryHistory(), routes })
    await router.push('/dashboard')
    useSessionStore(pinia).user = { username: 'demo', language: '' }
    const w = render(App, { global: { plugins: [pinia, router] } })
    expect(w.find('.topbar [role="search"]').exists()).toBe(true)
    expect(w.find('.topbar button[aria-label^="Theme"]').exists()).toBe(true)
  })

  it('renders nothing until the router resolves the first route', () => {
    const router = createRouter({ history: createMemoryHistory(), routes })
    const w = render(App, { global: { plugins: [createPinia(), router] } })
    expect(w.find('nav').exists()).toBe(false)
    expect(w.find('.topbar').exists()).toBe(false)
  })

  it('on screens without a session (login) there is no navigation or top bar', async () => {
    const router = createRouter({ history: createMemoryHistory(), routes })
    await router.push('/login')
    const w = render(App, { global: { plugins: [createPinia(), router] } })
    expect(w.find('nav').exists()).toBe(false)
    expect(w.find('.topbar').exists()).toBe(false)
  })

  it('warns about failed attempts and can be dismissed', async () => {
    const pinia = createPinia()
    const router = createRouter({ history: createMemoryHistory(), routes })
    await router.push('/')
    const w = render(App, { global: { plugins: [pinia, router] } })
    expect(w.find('.failed-notice').exists()).toBe(false)
    const session = useSessionStore(pinia)
    session.user = { username: 'demo', language: '', failed_attempts: 2 }
    await w.vm.$nextTick()
    expect(w.get('.failed-notice').text()).toContain('2 failed sign-in attempts')
    await w.get('.failed-notice button').trigger('click')
    expect(w.find('.failed-notice').exists()).toBe(false)
  })

  it('registers the service worker only in production', async () => {
    const register = vi.fn()
    vi.stubGlobal('navigator', { serviceWorker: { register } })
    const router = createRouter({ history: createMemoryHistory(), routes })
    const mountApp = () => render(App, { global: { plugins: [createPinia(), router] } })
    mountApp()
    expect(register).not.toHaveBeenCalled()
    vi.stubEnv('PROD', true)
    mountApp()
    expect(register).toHaveBeenCalledWith('/sw.js')
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.unstubAllEnvs()
  })
})
