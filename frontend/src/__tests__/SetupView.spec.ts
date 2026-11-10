import { http, HttpResponse } from 'msw'
import { flushPromises } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import { server } from '../mocks/server'
import { useSessionStore } from '../stores/session'
import SetupView from '../views/SetupView.vue'
import { fill, mountView } from './viewHelpers'

const needed = (codeRequired = false) =>
  server.use(
    http.get('/api/v1/accounts/setup/', () =>
      HttpResponse.json({ needed: true, code_required: codeRequired }),
    ),
  )

async function submit(
  wrapper: Awaited<ReturnType<typeof mountView>>['wrapper'],
  confirm = 'Long-password-1',
) {
  await fill(wrapper, 'Username', 'admin')
  await fill(wrapper, 'Password', 'Long-password-1')
  await fill(wrapper, 'Repeat the password', confirm)
  await wrapper.get('form').trigger('submit')
  await flushPromises()
}

describe('SetupView', () => {
  it('creates the account, opens the session and goes to the dashboard', async () => {
    needed()
    const { wrapper, router, pinia } = await mountView(SetupView, '/setup')
    await submit(wrapper)
    expect(useSessionStore(pinia).isAuthenticated).toBe(true)
    expect(router.currentRoute.value.name).toBe('dashboard')
  })

  it('sends nothing if the passwords do not match', async () => {
    needed()
    let posted = false
    server.use(
      http.post('/api/v1/accounts/setup/', () => {
        posted = true
        return HttpResponse.json({}, { status: 201 })
      }),
    )
    const { wrapper } = await mountView(SetupView, '/setup')
    await submit(wrapper, 'another')
    expect(wrapper.get('[role="alert"]').text()).toBe('The passwords do not match.')
    expect(posted).toBe(false)
  })

  it('shows the server validation errors', async () => {
    needed()
    server.use(
      http.post('/api/v1/accounts/setup/', () =>
        HttpResponse.json({ password: ['Too short.'] }, { status: 400 }),
      ),
    )
    const { wrapper, router } = await mountView(SetupView, '/setup')
    await submit(wrapper)
    expect(wrapper.get('[role="alert"]').text()).toBe('Too short.')
    expect(router.currentRoute.value.name).toBe('setup')
  })

  it('goes back to the login if the account already exists', async () => {
    const { router } = await mountView(SetupView, '/setup')
    expect(router.currentRoute.value.name).toBe('login')
  })

  it('warns if it cannot query the setup status', async () => {
    server.use(http.get('/api/v1/accounts/setup/', () => HttpResponse.error()))
    const { wrapper } = await mountView(SetupView, '/setup')
    expect(wrapper.find('[role="alert"]').exists()).toBe(true)
  })

  it('without a code on the server it neither asks for it nor sends it', async () => {
    needed()
    let body: Record<string, unknown> = {}
    server.use(
      http.post('/api/v1/accounts/setup/', async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>
        return HttpResponse.json({ username: 'admin', language: '' }, { status: 201 })
      }),
    )
    const { wrapper } = await mountView(SetupView, '/setup')
    expect(wrapper.text()).not.toContain('Setup code')
    await submit(wrapper)
    expect(body).not.toHaveProperty('code')
  })

  it('asks for the setup code and sends it with the account', async () => {
    needed(true)
    let body: Record<string, unknown> = {}
    server.use(
      http.post('/api/v1/accounts/setup/', async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>
        return HttpResponse.json({ username: 'admin', language: '' }, { status: 201 })
      }),
    )
    const { wrapper } = await mountView(SetupView, '/setup')
    await fill(wrapper, 'Setup code', 'abc123')
    await submit(wrapper)
    expect(body).toMatchObject({ username: 'admin', code: 'abc123' })
  })

  it('shows the variable and the path of the code as code and as the field hint', async () => {
    needed(true)
    const { wrapper } = await mountView(SetupView, '/setup')
    const codes = wrapper.findAll('.field__hint code').map((c) => c.text())
    expect(codes).toEqual(['VIBRATTO_SETUP_CODE', '/etc/vibratto-metadata/vibratto-metadata.env'])
    const input = wrapper.get('input[type="text"]')
    const hint = wrapper.get(`#${input.attributes('aria-describedby')}`)
    expect(hint.classes()).toContain('field__hint')
  })
})
