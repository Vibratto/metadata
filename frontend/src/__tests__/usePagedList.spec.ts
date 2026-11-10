import { flushPromises } from '@vue/test-utils'
import { http, HttpResponse } from 'msw'
import { describe, expect, it, vi } from 'vitest'
import { defineComponent } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'

import { usePagedList } from '../composables/usePagedList'
import { server } from '../mocks/server'
import { render } from './helpers'

interface Item {
  id: number
}

/** Mounts a minimal component using the list (inside RouterView or bare) and returns what it exposes. */
async function setup(path = '/list', mount: 'router-view' | 'direct' = 'router-view') {
  const requests: URL[] = []
  server.use(
    http.get('/api/v1/things/', ({ request }) => {
      const url = new URL(request.url)
      requests.push(url)
      const page = Number(url.searchParams.get('page') ?? 1)
      return HttpResponse.json({
        count: 3,
        next: page < 2 ? 'http://x/?page=2' : null,
        previous: page > 1 ? 'http://x/?page=1' : null,
        results: [{ id: page }],
      })
    }),
  )
  let list!: ReturnType<typeof usePagedList<Item>>
  const View = defineComponent({
    setup() {
      list = usePagedList<Item>('/api/v1/things/', ['kind'])
      return () => null
    },
  })
  const Other = { template: '<div />' }
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/list', name: 'list', component: View },
      { path: '/other', name: 'other', component: Other },
    ],
  })
  await router.push(path)
  const wrapper = render(mount === 'direct' ? View : { template: '<RouterView />' }, {
    global: { plugins: [router] },
  })
  await vi.waitFor(() => expect(list.loading).toBe(false))
  return { list, router, requests, wrapper }
}

describe('usePagedList', () => {
  it('loads the first page with its total', async () => {
    const { list } = await setup()
    expect(list.items).toEqual([{ id: 1 }])
    expect(list.count).toBe(3)
    expect(list.page).toBe(1)
    expect([list.hasPrevious, list.hasNext]).toEqual([false, true])
    expect(list.error).toBe('')
  })

  it('passes the API only the page, search, ordering and declared filters', async () => {
    const { requests } = await setup('/list?page=2&search=a&ordering=-id&kind=x&tab=log')
    expect(Object.fromEntries(requests[0]!.searchParams)).toEqual({
      page: '2',
      search: 'a',
      ordering: '-id',
      kind: 'x',
    })
  })

  it('changes page keeping it in the URL', async () => {
    const { list, router } = await setup()
    list.goTo(2)
    await vi.waitFor(() => expect(list.items).toEqual([{ id: 2 }]))
    expect(router.currentRoute.value.query).toEqual({ page: '2' })
    expect([list.hasPrevious, list.hasNext]).toEqual([true, false])
  })

  it('filtering goes back to page one and drops empty filters', async () => {
    const { list, router } = await setup('/list?page=2&kind=x')
    list.update({ search: 'daft', kind: '' })
    await vi.waitFor(() => expect(router.currentRoute.value.query).toEqual({ search: 'daft' }))
    expect(list.query).toEqual({ search: 'daft' })
  })

  it('shows the API error', async () => {
    const { list } = await setup()
    server.use(http.get('/api/v1/things/', () => new HttpResponse(null, { status: 500 })))
    await list.reload()
    expect(list.error).toBe('The server failed. Please try again later.')
    expect(list.loading).toBe(false)
  })

  it.each([
    ['successful', () => HttpResponse.json({ count: 1, results: [{ id: 1 }] })],
    ['fallida', () => HttpResponse.error()],
  ])('drops a %s answer that arrives after a newer one', async (_, late) => {
    const { list } = await setup()
    let release!: () => void
    const gate = new Promise<void>((r) => (release = r))
    server.use(
      http.get('/api/v1/things/', async ({ request }) => {
        const slow = new URL(request.url).searchParams.get('search') === 'lenta'
        if (!slow) return HttpResponse.json({ count: 1, results: [{ id: 2 }] })
        await gate
        return late()
      }),
    )
    list.update({ search: 'lenta' })
    await flushPromises()
    list.update({ search: 'rapida' })
    await vi.waitFor(() => expect(list.items).toEqual([{ id: 2 }]))
    release()
    await new Promise((r) => setTimeout(r, 20))
    expect(list.items).toEqual([{ id: 2 }])
    expect(list.error).toBe('')
    expect(list.loading).toBe(false)
  })

  // With transitions or KeepAlive the view stays mounted for a moment after the route changes.
  it('does not reload when leaving for another route', async () => {
    const { router, requests } = await setup('/list', 'direct')
    await router.push({ name: 'other', query: { kind: 'y' } })
    await flushPromises()
    expect(requests).toHaveLength(1)
  })
})
