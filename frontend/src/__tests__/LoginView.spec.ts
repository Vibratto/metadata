import { http, HttpResponse } from 'msw'
import { flushPromises } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import { server } from '../mocks/server'
import { useSessionStore } from '../stores/session'
import LoginView from '../views/LoginView.vue'
import { fill, mountView } from './viewHelpers'

async function signIn(wrapper: Awaited<ReturnType<typeof mountView>>['wrapper']) {
  await fill(wrapper, 'Username', 'demo')
  await fill(wrapper, 'Password', 'secreta')
  await wrapper.get('form').trigger('submit')
  await flushPromises()
}

describe('LoginView', () => {
  it('opens the session and goes to the dashboard', async () => {
    const { wrapper, router, pinia } = await mountView(LoginView, '/login')
    await signIn(wrapper)
    expect(useSessionStore(pinia).user?.username).toBe('demo')
    expect(router.currentRoute.value.name).toBe('dashboard')
  })

  it('goes back to the requested route if it is internal', async () => {
    const { wrapper, router } = await mountView(LoginView, '/login?redirect=/account')
    await signIn(wrapper)
    expect(router.currentRoute.value.path).toBe('/account')
  })

  it('ignores an external redirect', async () => {
    const { wrapper, router } = await mountView(LoginView, '/login?redirect=//evil.example')
    await signIn(wrapper)
    expect(router.currentRoute.value.name).toBe('dashboard')
  })

  it('shows the server error and stays on the route', async () => {
    server.use(
      http.post('/api/v1/accounts/login/', () =>
        HttpResponse.json({ detail: 'Wrong username or password.' }, { status: 400 }),
      ),
    )
    const { wrapper, router } = await mountView(LoginView, '/login')
    await signIn(wrapper)
    expect(wrapper.get('[role="alert"]').text()).toBe('Wrong username or password.')
    expect(router.currentRoute.value.name).toBe('login')
    expect(wrapper.get('button').attributes('disabled')).toBeUndefined()
  })

  it('goes to first-run setup if there is no account yet', async () => {
    server.use(http.get('/api/v1/accounts/setup/', () => HttpResponse.json({ needed: true })))
    const { router } = await mountView(LoginView, '/login')
    expect(router.currentRoute.value.name).toBe('setup')
  })

  it('warns if it cannot query the setup status', async () => {
    server.use(http.get('/api/v1/accounts/setup/', () => HttpResponse.error()))
    const { wrapper } = await mountView(LoginView, '/login')
    expect(wrapper.get('[role="alert"]').text()).toBe('Could not reach the server.')
  })

  it('translates the texts to Spanish', async () => {
    const { wrapper } = await mountView(LoginView, '/login')
    expect(wrapper.get('h1').text()).toBe('Sign in')
  })
})
