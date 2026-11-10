import { http, HttpResponse } from 'msw'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'

import { ApiError, api } from '../api/client'
import { server } from '../mocks/server'
import { progressOf, useJobsStore } from '../stores/jobs'
import { useSessionStore } from '../stores/session'

describe('api()', () => {
  it('returns the JSON of a successful response', async () => {
    server.use(http.get('/api/t/', () => HttpResponse.json({ ok: true })))
    expect(await api('/api/t/')).toEqual({ ok: true })
  })

  it('sends the CSRF token only on write methods', async () => {
    document.cookie = 'csrftoken=abc123'
    const seen: Record<string, string | null> = {}
    server.use(
      http.get('/api/t/', ({ request }) => {
        seen.get = request.headers.get('X-CSRFToken')
        return HttpResponse.json({})
      }),
      http.post('/api/t/', async ({ request }) => {
        seen.post = request.headers.get('X-CSRFToken')
        return HttpResponse.json(await request.json())
      }),
    )
    await api('/api/t/')
    expect(await api('/api/t/', { method: 'post', body: { a: 1 } })).toEqual({ a: 1 })
    expect(seen).toEqual({ get: null, post: 'abc123' })
  })

  it('identifies itself as the frontend on every request, read or write', async () => {
    const seen: (string | null)[] = []
    server.use(
      http.get('/api/t/', ({ request }) => {
        seen.push(request.headers.get('X-Vibratto-Client'))
        return HttpResponse.json({})
      }),
      http.post('/api/t/', ({ request }) => {
        seen.push(request.headers.get('X-Vibratto-Client'))
        return HttpResponse.json({})
      }),
    )
    await api('/api/t/')
    await api('/api/t/', { method: 'post', body: {} })
    expect(seen).toEqual(['web', 'web'])
  })

  it('marks automatic polling only when asked', async () => {
    const seen: (string | null)[] = []
    server.use(
      http.get('/api/t/', ({ request }) => {
        seen.push(request.headers.get('X-Background-Poll'))
        return HttpResponse.json({})
      }),
    )
    await api('/api/t/')
    await api('/api/t/', { poll: true })
    expect(seen).toEqual([null, '1'])
  })

  it('sends a FormData as multipart, without JSON', async () => {
    let type: string | null = null
    let name = ''
    server.use(
      http.post('/api/t/', async ({ request }) => {
        type = request.headers.get('Content-Type')
        name = await ((await request.formData()).get('file') as File).text()
        return HttpResponse.json({})
      }),
    )
    const body = new FormData()
    body.append('file', new File(['[]'], 'copia.json'))
    await api('/api/t/', { method: 'POST', body })
    expect(type).toMatch(/^multipart\/form-data; boundary=/)
    expect(name).toBe('[]')
  })

  it('sends an empty string if there is no CSRF cookie', async () => {
    document.cookie = 'csrftoken=; max-age=0'
    let token: string | null = null
    server.use(
      http.post('/api/t/', ({ request }) => {
        token = request.headers.get('X-CSRFToken')
        return new HttpResponse(null, { status: 204 })
      }),
    )
    expect(await api('/api/t/', { method: 'POST' })).toBeNull()
    expect(token).toBe('')
  })

  it('reads its CSRF cookie among others, not one that merely ends the same', async () => {
    document.cookie = 'xcsrftoken=falso'
    document.cookie = 'csrftoken=bueno'
    let token: string | null = null
    server.use(
      http.post('/api/t/', ({ request }) => {
        token = request.headers.get('X-CSRFToken')
        return new HttpResponse(null, { status: 204 })
      }),
    )
    await api('/api/t/', { method: 'POST' })
    expect(token).toBe('bueno')
    document.cookie = 'xcsrftoken=; max-age=0'
  })

  it('declares JSON only when it sends a JSON body', async () => {
    const seen: (string | null)[][] = []
    server.use(
      http.all('/api/t/', ({ request }) => {
        seen.push([request.headers.get('Accept'), request.headers.get('Content-Type')])
        return new HttpResponse(null, { status: 204 })
      }),
    )
    await api('/api/t/', { method: 'POST', body: { a: 1 } })
    await api('/api/t/', { method: 'POST' })
    expect(seen).toEqual([
      ['application/json', 'application/json'],
      ['application/json', null],
    ])
  })

  it.each([
    [401, 'unauthorized'],
    [403, 'forbidden'],
    [404, 'notFound'],
    [500, 'server'],
    [400, 'unknown'],
  ])('maps status %s to the %s error', async (status, kind) => {
    server.use(http.get('/api/t/', () => HttpResponse.json({ detail: 'x' }, { status })))
    const err = await api('/api/t/').catch((e: unknown) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect(err).toMatchObject({ kind, status, body: { detail: 'x' }, messageKey: `errors.${kind}` })
  })

  it('maps a network failure to the network error', async () => {
    server.use(http.get('/api/t/', () => HttpResponse.error()))
    await expect(api('/api/t/')).rejects.toMatchObject({ kind: 'network', status: 0 })
  })
})

describe('stores', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('session: fetchMe, login y logout', async () => {
    const s = useSessionStore()
    expect(s.loaded).toBe(false)
    await s.fetchMe()
    expect(s.isAuthenticated).toBe(true)
    expect(s.user?.username).toBe('demo')
    await s.logout()
    expect(s.isAuthenticated).toBe(false)
    await s.login('demo', 'x')
    expect(s.user?.username).toBe('demo')
  })

  it('session: login sends username and password', async () => {
    let sent: unknown = null
    server.use(
      http.post('/api/v1/accounts/login/', async ({ request }) => {
        sent = await request.json()
        return HttpResponse.json({ username: 'ana', language: '' })
      }),
    )
    await useSessionStore().login('ana', 'secreta')
    expect(sent).toEqual({ username: 'ana', password: 'secreta' })
  })

  it('session: 403 also means no session', async () => {
    server.use(http.get('/api/v1/accounts/me/', () => new HttpResponse(null, { status: 403 })))
    const s = useSessionStore()
    await s.fetchMe()
    expect(s.user).toBeNull()
  })

  it('session: 401 means no session, not an error', async () => {
    server.use(http.get('/api/v1/accounts/me/', () => new HttpResponse(null, { status: 401 })))
    const s = useSessionStore()
    await s.fetchMe()
    expect(s.user).toBeNull()
    expect(s.loaded).toBe(true)
  })

  it('session: a server failure does propagate', async () => {
    server.use(http.get('/api/v1/accounts/me/', () => new HttpResponse(null, { status: 500 })))
    await expect(useSessionStore().fetchMe()).rejects.toMatchObject({ kind: 'server' })
  })

  it('session: a non-API error propagates', async () => {
    server.use(http.get('/api/v1/accounts/me/', () => HttpResponse.error()))
    // A network failure is an ApiError too, but it is not “no session”.
    await expect(useSessionStore().fetchMe()).rejects.toMatchObject({ kind: 'network' })
  })

  it('jobs: refresh y tareas activas', async () => {
    const j = useJobsStore()
    await j.refresh()
    expect(j.jobs).toHaveLength(2)
    expect(j.active.map((x) => x.id)).toEqual([1])
  })

  it('jobs: progress percentage, 0 while there is no total', () => {
    const base = { id: 1, kind: 'import', status: 'running', current: '' } as const
    expect(progressOf({ ...base, done: 1, total: 3 })).toBe(33)
    expect(progressOf({ ...base, done: 0, total: 0 })).toBe(0)
  })
})
