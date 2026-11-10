import { flushPromises } from '@vue/test-utils'
import { expect, vi } from 'vitest'

import { server } from '../mocks/server'

/**
 * Counts in-flight requests and returns a wait until none is left and the view has rendered.
 */
export function trackRequests(): () => Promise<void> {
  let open = 0
  server.events.on('request:start', () => void open++)
  server.events.on('request:end', () => void open--)
  return async () => {
    do {
      await vi.waitFor(() => expect(open).toBe(0))
      await flushPromises()
    } while (open > 0)
  }
}
