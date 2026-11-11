import { describe, expect, it } from 'vitest'

import { api } from '../api/client'

// The default mocked answers allow developing without a backend (`VITE_MOCKS=1`).
describe('respuestas simuladas', () => {
  it('gather the ones of every area', async () => {
    expect(await api('/api/v1/accounts/me/')).toHaveProperty('username')
    expect(await api('/api/v1/catalog/summary/')).toHaveProperty('tracks')
  })

  it('simulate the life cycle of a job', async () => {
    const base = '/api/v1/jobs/runs/'
    const started = await api(base, { method: 'POST', body: { kind: 'import', params: { a: 1 } } })
    expect(started).toMatchObject({ id: 3, kind: 'import', params: { a: 1 }, status: 'pending' })
    expect(await api(`${base}3/`)).toMatchObject({ id: 3 })
    expect(await api(`${base}1/`)).toMatchObject({ id: 1, current: 'Daft Punk' })
    expect(await api(`${base}3/stop/`, { method: 'POST' })).toMatchObject({ status: 'stopping' })
  })
})
