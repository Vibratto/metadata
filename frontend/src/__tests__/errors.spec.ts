import { describe, expect, it } from 'vitest'

import { ApiError } from '../api/client'
import { errorText } from '../api/errors'

const t = (key: string) => `t:${key}`

describe('errorText', () => {
  it('uses the detail the server returns', () => {
    expect(errorText(new ApiError('unknown', 400, { detail: 'Mal.' }), t)).toBe('Mal.')
  })

  it('joins the messages of several fields', () => {
    const body = { username: ['Short.', 'Odd.'], password: ['Weak.'] }
    expect(errorText(new ApiError('unknown', 400, body), t)).toBe('Short. Odd. Weak.')
  })

  it('with detail and fields it shows only the detail', () => {
    const body = { detail: 'Corto.', username: ['Corto.'] }
    expect(errorText(new ApiError('unknown', 400, body), t)).toBe('Corto.')
  })

  it('accepts a body that is just text', () => {
    expect(errorText(new ApiError('unknown', 400, 'Text'), t)).toBe('Text')
  })

  it('falls back to the generic message if the body has no text', () => {
    expect(errorText(new ApiError('server', 500, null), t)).toBe('t:errors.server')
    expect(errorText(new ApiError('server', 500, 42), t)).toBe('t:errors.server')
  })

  it('rethrows what is not an API error', () => {
    expect(() => errorText(new TypeError('bug'), t)).toThrow('bug')
  })
})
