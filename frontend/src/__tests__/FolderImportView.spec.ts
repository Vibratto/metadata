import { http, HttpResponse } from 'msw'
import { describe, expect, it, vi } from 'vitest'

import { routes } from '../router'
import { server } from '../mocks/server'
import FolderImportView from '../views/FolderImportView.vue'
import { fill, mountView } from './viewHelpers'

async function launch(folder = ' Daft Punk ') {
  const { wrapper } = await mountView(FolderImportView, '/import/folder')
  await fill(wrapper, 'Folder', folder)
  await wrapper.get('form').trigger('submit')
  return wrapper
}

describe('FolderImportView', () => {
  it('has its own route without a navigation entry', () => {
    const route = routes.find((r) => r.name === 'import-folder')
    expect(route?.path).toBe('/import/folder')
    expect(route?.meta?.navLabel).toBeUndefined()
  })

  it('starts folder_import with the folder and lists the unlinked files', async () => {
    const sent: unknown[] = []
    server.events.on('request:start', async ({ request }) => {
      if (request.method === 'POST') sent.push(await request.clone().json())
    })
    const wrapper = await launch()

    await vi.waitFor(() => expect(wrapper.findAll('tbody tr')).toHaveLength(2))
    server.events.removeAllListeners()
    expect(sent).toEqual([{ kind: 'folder_import', params: { folder: 'Daft Punk' } }])
    expect(wrapper.text()).toContain('2 linked, 0 were already linked and 2 not linked.')
    expect(wrapper.get('tbody tr').text()).toContain('Daft Punk/demo.mp3')
    expect(wrapper.get('tbody tr').text()).toContain('No tags or no title')
    expect(wrapper.text()).toContain('Daft Punk/one.mp3 → “One More Time”')
  })

  it('shows the reason code when it has no translation', async () => {
    const run = {
      id: 30,
      kind: 'folder_import',
      status: 'succeeded',
      done: 1,
      total: 1,
      current: '',
      summary: { linked: 1, unlinked: [{ file: 'a.mp3', reason: 'nuevo' }] },
    }
    // Creation also returns the run: otherwise the view renders the default summary first.
    server.use(
      http.post('/api/v1/jobs/runs/', () => HttpResponse.json(run, { status: 201 })),
      http.get('/api/v1/jobs/runs/30/', () => HttpResponse.json(run)),
    )
    const wrapper = await launch('')
    // The mocked creation already carries a finished summary: wait for the polled one.
    await vi.waitFor(() => expect(wrapper.find('tbody tr').text()).toContain('nuevo'))
    expect(wrapper.text()).toContain('1 linked, 0 were already linked and 1 not linked.')
  })

  it('says no files are left unlinked', async () => {
    server.use(
      http.get('/api/v1/jobs/runs/30/', () =>
        HttpResponse.json({
          id: 30,
          status: 'succeeded',
          done: 3,
          total: 3,
          current: '',
          summary: { linked: 0, already_linked: 3 },
        }),
      ),
    )
    const wrapper = await launch()
    await vi.waitFor(() =>
      expect(wrapper.text()).toContain('0 linked, 3 were already linked and 0 not linked.'),
    )
    expect(wrapper.find('table').exists()).toBe(false)
  })

  it('shows no result while the job is still running', async () => {
    server.use(
      http.post('/api/v1/jobs/runs/', () =>
        HttpResponse.json(
          { id: 31, kind: 'folder_import', status: 'running', done: 1, total: 3, summary: {} },
          { status: 201 },
        ),
      ),
      http.get('/api/v1/jobs/runs/31/', () =>
        HttpResponse.json({ id: 31, status: 'running', done: 1, total: 3, current: 'a.mp3' }),
      ),
    )
    const wrapper = await launch()
    await vi.waitFor(() => expect(wrapper.text()).toContain('a.mp3'))
    expect(wrapper.get('button[type="submit"]').attributes('disabled')).toBeDefined()
    expect(wrapper.find('table').exists()).toBe(false)
    wrapper.unmount()
  })

  it('shows the error if the API rejects the job', async () => {
    server.use(
      http.post('/api/v1/jobs/runs/', () =>
        HttpResponse.json({ detail: 'No permitido.' }, { status: 403 }),
      ),
    )
    const wrapper = await launch()
    await vi.waitFor(() => expect(wrapper.text()).toContain('No permitido.'))
  })

  it('has the same texts in en and es', async () => {
    const { messages } = await import('../locales')
    const keys = (tree: object): string[] =>
      Object.entries(tree).flatMap(([k, v]) =>
        typeof v === 'string' ? [k] : keys(v).map((c) => `${k}.${c}`),
      )
    expect(keys(messages.en.importFolder as object)).toEqual(
      keys(messages.es.importFolder as object),
    )
  })
})
