import { flushPromises } from '@vue/test-utils'
import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'

import { messages } from '../locales'
import { server } from '../mocks/server'
import { routes } from '../router'
import LibraryBackupView from '../views/LibraryBackupView.vue'
import { mountView } from './viewHelpers'

type Tree = { [key: string]: string | Tree }

function paths(tree: Tree, prefix = ''): string[] {
  return Object.entries(tree).flatMap(([k, v]) =>
    typeof v === 'string' ? [`${prefix}${k}`] : paths(v, `${prefix}${k}.`),
  )
}

async function mount() {
  return mountView(LibraryBackupView, '/library/backup')
}

/** Picks a file in the file input, as a user would. */
async function choose(wrapper: Awaited<ReturnType<typeof mount>>['wrapper'], content = '[]') {
  const input = wrapper.get('input[type="file"]')
  const files = content ? [new File([content], 'backup.json')] : []
  Object.defineProperty(input.element, 'files', { value: files, configurable: true })
  await input.trigger('change')
  await flushPromises()
}

describe('LibraryBackupView', () => {
  it('has a route and no navigation entry', () => {
    const route = routes.find((r) => r.name === 'library-backup')
    expect(route?.path).toBe('/library/backup')
    expect(route).not.toHaveProperty('meta')
  })

  it('has the same texts in English and Spanish', () => {
    const es = paths(messages.es.libraryBackup as Tree)
    expect(paths(messages.en.libraryBackup as Tree)).toEqual(es)
  })

  it('links to the backup download', async () => {
    const { wrapper } = await mount()
    const link = wrapper.get('a[download]')
    expect(link.attributes('href')).toBe('/api/v1/catalog/backup/')
    expect(link.text()).toBe('Download the backup')
  })

  it('shows the preview of the chosen file', async () => {
    const { wrapper } = await mount()
    expect(wrapper.find('table').exists()).toBe(false)
    await choose(wrapper)
    const rows = wrapper.findAll('tbody tr').map((r) => r.findAll('th, td').map((c) => c.text()))
    expect(rows).toEqual([
      ['Artists', '3', '1', '2'],
      ['Albums', '5', '2', '3'],
      ['Tracks', '40', '12', '28'],
      ['Downloads', '30', '12', '18'],
    ])
  })

  it('does nothing if the file is removed', async () => {
    const { wrapper } = await mount()
    await choose(wrapper)
    await choose(wrapper, '')
    expect(wrapper.find('table').exists()).toBe(false)
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
  })

  it('rejects an invalid file with the server message', async () => {
    server.use(
      http.post('/api/v1/catalog/backup/preview/', () =>
        HttpResponse.json({ detail: 'The file is not valid JSON.' }, { status: 400 }),
      ),
    )
    const { wrapper } = await mount()
    await choose(wrapper, '{roto')
    expect(wrapper.get('[role="alert"]').text()).toBe('The file is not valid JSON.')
    expect(wrapper.find('table').exists()).toBe(false)
  })

  it('on confirm it uploads the file and follows the job', async () => {
    let sent = ''
    server.use(
      http.post('/api/v1/catalog/backup/restore/', async ({ request }) => {
        sent = await ((await request.formData()).get('file') as File).text()
        return HttpResponse.json({ id: 7, status: 'pending' }, { status: 201 })
      }),
      http.get('/api/v1/jobs/runs/7/', () =>
        HttpResponse.json({ id: 7, status: 'succeeded', done: 1, total: 1, current: '' }),
      ),
    )
    const { wrapper } = await mount()
    await choose(wrapper, '[{"model": "catalog.artist"}]')
    await wrapper.get('button').trigger('click')
    await flushPromises()
    expect(sent).toBe('[{"model": "catalog.artist"}]')
    expect(wrapper.find('table').exists()).toBe(false)
    expect(wrapper.text()).toContain('Finished')
  })

  it('shows the error if an import is already running', async () => {
    server.use(
      http.post('/api/v1/catalog/backup/restore/', () =>
        HttpResponse.json({ detail: 'A job of this kind is already running.' }, { status: 409 }),
      ),
    )
    const { wrapper } = await mount()
    await choose(wrapper)
    await wrapper.get('button').trigger('click')
    await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toBe('A job of this kind is already running.')
    expect(wrapper.find('table').exists()).toBe(true)
  })
})
