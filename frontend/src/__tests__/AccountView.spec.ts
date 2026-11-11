import { http, HttpResponse } from 'msw'
import { flushPromises } from '@vue/test-utils'
import { afterEach, describe, expect, it } from 'vitest'

import { server } from '../mocks/server'
import { useSessionStore } from '../stores/session'
import AccountView from '../views/AccountView.vue'
import { choose, fill, mountView } from './viewHelpers'

afterEach(() => localStorage.clear())

async function mountSignedIn(path = '/account') {
  const ctx = await mountView(AccountView, path)
  await useSessionStore(ctx.pinia).fetchMe()
  await flushPromises()
  return ctx
}

describe('AccountView', () => {
  it('shows who is signed in', async () => {
    const { wrapper } = await mountSignedIn()
    expect(wrapper.text()).toContain('Signed in as demo.')
  })

  it('switches the language, remembers it and saves it to the account', async () => {
    const puts: unknown[] = []
    server.use(
      http.put('/api/v1/accounts/language/', async ({ request }) => {
        const body = await request.json()
        puts.push(body)
        return HttpResponse.json(body)
      }),
    )
    const { wrapper } = await mountSignedIn()
    await choose(wrapper, 'Language', 'Español')
    await flushPromises()
    expect(wrapper.get('h1').text()).toBe('Mi cuenta')
    expect(localStorage.getItem('locale')).toBe('es')
    expect(puts).toEqual([{ language: 'es' }])
    expect(wrapper.get('[role="status"]').text()).toBe('Idioma guardado.')
  })

  it('changes the username and updates the session', async () => {
    const { wrapper, pinia } = await mountSignedIn()
    await fill(wrapper, 'New username', 'nuevo')
    await fill(wrapper.findAll('form')[0] ? wrapper : wrapper, 'Current password', 'secreta')
    await wrapper.get('form[name="username"]').trigger('submit')
    await flushPromises()
    expect(useSessionStore(pinia).user?.username).toBe('nuevo')
    expect(wrapper.get('[role="status"]').text()).toBe('Username changed.')
  })

  it('changes the password and clears the fields', async () => {
    const { wrapper } = await mountSignedIn()
    const form = wrapper.get('form[name="password"]')
    const inputs = form.findAll('input')
    await inputs[0]?.setValue('vieja')
    await inputs[1]?.setValue('New-password-1')
    await form.trigger('submit')
    await flushPromises()
    expect(wrapper.get('[role="status"]').text()).toBe('Password changed.')
    expect(inputs.map((i) => (i.element as HTMLInputElement).value)).toEqual(['', ''])
  })

  it('shows the server error and removes the previous success', async () => {
    const { wrapper } = await mountSignedIn()
    const form = wrapper.get('form[name="password"]')
    await form.trigger('submit')
    await flushPromises()
    expect(wrapper.find('[role="status"]').exists()).toBe(true)
    server.use(
      http.post('/api/v1/accounts/password/', () =>
        HttpResponse.json({ current_password: ['It is not correct.'] }, { status: 400 }),
      ),
    )
    await form.trigger('submit')
    await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toBe('It is not correct.')
    expect(wrapper.find('[role="status"]').exists()).toBe(false)
  })

  it('signs out and goes to the login', async () => {
    const { wrapper, router, pinia } = await mountSignedIn()
    await wrapper
      .findAll('button')
      .find((b) => b.text() === 'Sign out')
      ?.trigger('click')
    await flushPromises()
    expect(useSessionStore(pinia).isAuthenticated).toBe(false)
    expect(router.currentRoute.value.name).toBe('login')
  })

  it('shows the error if it cannot sign out', async () => {
    server.use(http.post('/api/v1/accounts/logout/', () => new HttpResponse(null, { status: 500 })))
    const { wrapper, router } = await mountSignedIn()
    await wrapper
      .findAll('button')
      .find((b) => b.text() === 'Sign out')
      ?.trigger('click')
    await flushPromises()
    expect(wrapper.find('[role="alert"]').exists()).toBe(true)
    expect(router.currentRoute.value.name).toBe('account')
  })

  it('renders nothing about the user until there is one', async () => {
    const { wrapper, pinia } = await mountView(AccountView, '/account')
    useSessionStore(pinia).user = null
    await flushPromises()
    expect(wrapper.text()).not.toContain('Signed in')
  })
})
