import { afterAll, afterEach, beforeAll } from 'vitest'

import { server } from '../mocks/server'

// jsdom does not implement showModal/close on <dialog>.
Object.assign(HTMLDialogElement.prototype, {
  showModal(this: HTMLDialogElement) {
    this.setAttribute('open', '')
  },
  close(this: HTMLDialogElement) {
    if (!this.hasAttribute('open')) return
    this.removeAttribute('open')
    this.dispatchEvent(new Event('close'))
  },
})

beforeAll(() => server.listen({ onUnhandledFrame: 'error' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())
