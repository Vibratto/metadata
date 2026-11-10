import { http, HttpResponse } from 'msw'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import { i18n } from '../i18n'
import { server } from '../mocks/server'
import { useSessionStore } from '../stores/session'

const me = (language: string) =>
  http.get('/api/v1/accounts/me/', () =>
    HttpResponse.json({ username: 'u', failed_attempts: 0, language }),
  )

beforeEach(() => setActivePinia(createPinia()))
afterEach(() => {
  i18n.global.locale.value = 'en'
  localStorage.clear()
})

describe('account language', () => {
  it('is applied when the session loads', async () => {
    server.use(me('es'))
    await useSessionStore().fetchMe()
    expect(i18n.global.locale.value).toBe('es')
    expect(localStorage.getItem('locale')).toBe('es')
  })

  it('without a language stored in the account the current one stays', async () => {
    server.use(me(''))
    await useSessionStore().fetchMe()
    expect(i18n.global.locale.value).toBe('en')
  })
})
