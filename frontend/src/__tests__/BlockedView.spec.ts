import { http, HttpResponse } from 'msw'
import { beforeAll, describe, expect, it, vi } from 'vitest'

import { messages } from '../locales'
import { server } from '../mocks/server'
import BlockedView from '../views/BlockedView.vue'
import { mountView } from './viewHelpers'

const BLOCKED = '/api/v1/catalog/blocked/'

beforeAll(() => {
  // jsdom no implementa showModal/close de <dialog>.
  Object.assign(HTMLDialogElement.prototype, {
    showModal(this: HTMLDialogElement) {
      this.setAttribute('open', '')
    },
    close(this: HTMLDialogElement) {
      this.removeAttribute('open')
      this.dispatchEvent(new Event('close'))
    },
  })
})

/** Mounts the view with a session and waits for the first load. */
async function mount(path = '/blocked') {
  const view = await mountView(BlockedView, path)
  await vi.waitFor(() => expect(view.wrapper.find('.blocked__loading').exists()).toBe(false))
  return view
}

const rows = (wrapper: Awaited<ReturnType<typeof mount>>['wrapper']) => wrapper.findAll('tbody tr')

describe('BlockedView', () => {
  it('lists the blocked items with their kind, YouTube Music id and date', async () => {
    const { wrapper } = await mount()
    await vi.waitFor(() => expect(rows(wrapper)).toHaveLength(2))
    const first = rows(wrapper)[0]!.text()
    expect(first).toContain('Album')
    expect(first).toContain('Discovery')
    expect(first).toContain('MPREb_discovery')
    expect(first).toContain('2026')
    expect(rows(wrapper)[1]!.text()).toContain('Track')
  })

  it('shows no pager when everything fits on one page', async () => {
    const { wrapper } = await mount()
    expect(wrapper.find('.blocked__pager').exists()).toBe(false)
  })

  it('says nothing is blocked', async () => {
    server.use(http.get(BLOCKED, () => HttpResponse.json({ count: 0, results: [] })))
    const { wrapper } = await mount()
    await vi.waitFor(() => expect(wrapper.text()).toContain('Nothing is blocked.'))
    expect(wrapper.find('table').exists()).toBe(false)
  })

  it('shows the error when the list fails to load', async () => {
    server.use(http.get(BLOCKED, () => new HttpResponse(null, { status: 500 })))
    const { wrapper } = await mount()
    await vi.waitFor(() => expect(wrapper.text()).toContain('The server failed'))
  })

  it('unblocks after confirming and reloads the list', async () => {
    // The default mock answers; the test only watches what gets deleted.
    const deleted: string[] = []
    const record = ({ request }: { request: Request }) => {
      if (request.method === 'DELETE') deleted.push(new URL(request.url).pathname)
    }
    server.events.on('request:start', record)
    const { wrapper } = await mount()
    await vi.waitFor(() => expect(rows(wrapper)).toHaveLength(2))

    await rows(wrapper)[0]!.get('button').trigger('click')
    const dialog = wrapper.get('dialog')
    expect(dialog.attributes('open')).toBeDefined()
    expect(dialog.text()).toContain('Discovery')
    expect(deleted).toEqual([])

    server.use(http.get(BLOCKED, () => HttpResponse.json({ count: 0, results: [] })))
    await dialog.get('.blocked__confirm').trigger('click')
    await vi.waitFor(() => expect(deleted).toEqual([`${BLOCKED}1/`]))
    await vi.waitFor(() => expect(wrapper.text()).toContain('Unblocked.'))
    await vi.waitFor(() => expect(rows(wrapper)).toHaveLength(0))
    expect(dialog.attributes('open')).toBeUndefined()
    server.events.removeListener('request:start', record)
  })

  it('cancelar no desbloquea', async () => {
    const deleted = vi.fn()
    server.use(http.delete(`${BLOCKED}:id/`, deleted))
    const { wrapper } = await mount()
    await vi.waitFor(() => expect(rows(wrapper)).toHaveLength(2))
    await rows(wrapper)[1]!.get('button').trigger('click')
    await wrapper.get('dialog .btn--secondary').trigger('click')
    expect(wrapper.get('dialog').attributes('open')).toBeUndefined()
    expect(deleted).not.toHaveBeenCalled()
  })

  it('shows the error if it cannot unblock', async () => {
    server.use(http.delete(`${BLOCKED}:id/`, () => new HttpResponse(null, { status: 403 })))
    const { wrapper } = await mount()
    await vi.waitFor(() => expect(rows(wrapper)).toHaveLength(2))
    await rows(wrapper)[0]!.get('button').trigger('click')
    await wrapper.get('.blocked__confirm').trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('You are not allowed to do this'))
    expect(rows(wrapper)).toHaveLength(2)
  })

  it('pages with previous and next', async () => {
    const pages: string[] = []
    server.use(
      http.get(BLOCKED, ({ request }) => {
        const page = new URL(request.url).searchParams.get('page') ?? '1'
        pages.push(page)
        return HttpResponse.json({
          count: 30,
          next: page === '1' ? 'x?page=2' : null,
          previous: page === '2' ? 'x?page=1' : null,
          results: [],
        })
      }),
    )
    const { wrapper, router } = await mount()
    const [previous, next] = wrapper.findAll('.blocked__pager button')
    expect(previous!.attributes('disabled')).toBeDefined()
    await next!.trigger('click')
    await vi.waitFor(() => expect(router.currentRoute.value.query.page).toBe('2'))
    await vi.waitFor(() => expect(pages).toContain('2'))
    await vi.waitFor(() =>
      expect(wrapper.findAll('.blocked__pager button')[1]!.attributes('disabled')).toBeDefined(),
    )
    await wrapper.findAll('.blocked__pager button')[0]!.trigger('click')
    await vi.waitFor(() => expect(router.currentRoute.value.query.page).toBe('1'))
  })

  it('has the same texts in English and Spanish', () => {
    const keys = (tree: object, prefix = ''): string[] =>
      Object.entries(tree).flatMap(([k, v]) =>
        typeof v === 'string' ? [prefix + k] : keys(v as object, `${prefix}${k}.`),
      )
    expect(keys(messages.en.blocked as object)).toEqual(keys(messages.es.blocked as object))
  })

  it('is in the “more” group of the navigation', async () => {
    const { router } = await mount()
    expect(router.resolve({ name: 'blocked' }).meta).toMatchObject({
      navLabel: 'blocked.nav',
      navGroup: 'more',
    })
  })
})
