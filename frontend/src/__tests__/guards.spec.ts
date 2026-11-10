import { http, HttpResponse } from 'msw'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'
import type { RouteLocationNormalized } from 'vue-router'

import { server } from '../mocks/server'
import { authGuard, safeRedirect } from '../router/guards'

const private_ = { fullPath: '/dashboard?x=1', meta: {} } as RouteLocationNormalized
const public_ = { fullPath: '/login', meta: { public: true } } as unknown as RouteLocationNormalized
const anonymous = () =>
  server.use(http.get('/api/v1/accounts/me/', () => new HttpResponse(null, { status: 401 })))

describe('authGuard', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('lets a session through to a private route', async () => {
    expect(await authGuard(private_)).toBe(true)
  })

  it('goes to the login remembering the target if there is no session', async () => {
    anonymous()
    expect(await authGuard(private_)).toEqual({
      name: 'login',
      query: { redirect: '/dashboard?x=1' },
    })
  })

  it('takes whoever already has a session away from public routes', async () => {
    expect(await authGuard(public_)).toEqual({ name: 'dashboard' })
  })

  it('lets public routes be seen without a session', async () => {
    anonymous()
    expect(await authGuard(public_)).toBe(true)
  })

  it('treats as anonymous if the server fails', async () => {
    server.use(http.get('/api/v1/accounts/me/', () => new HttpResponse(null, { status: 500 })))
    expect(await authGuard(public_)).toBe(true)
  })

  it('asks the server only once', async () => {
    let calls = 0
    server.use(
      http.get('/api/v1/accounts/me/', () => {
        calls += 1
        return HttpResponse.json({ username: 'demo', language: '' })
      }),
    )
    await authGuard(private_)
    await authGuard(private_)
    expect(calls).toBe(1)
  })
})

describe('safeRedirect', () => {
  it('accepts internal paths', () => {
    expect(safeRedirect('/dashboard?a=1')).toBe('/dashboard?a=1')
  })

  it.each(['//evil.example', '/\\evil.example', 'https://evil.example', '', undefined, ['/a']])(
    'rejects %j',
    (value) => {
      expect(safeRedirect(value)).toBeNull()
    },
  )
})
