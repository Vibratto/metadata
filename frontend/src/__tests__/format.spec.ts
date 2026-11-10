import { describe, expect, it } from 'vitest'

import { audienceText, compactNumber } from '../format'

const t = (key: string, named: Record<string, unknown>) => `${key}:${named.n}`

describe('compactNumber', () => {
  it('shortens big figures in the given language', () => {
    expect(compactNumber(12_400_000, 'en')).toBe('12.4M')
    expect(compactNumber(12_400_000, 'es')).toBe('12,4\u00a0M')
    expect(compactNumber(950, 'en')).toBe('950')
  })
})

describe('audienceText', () => {
  it('prefers monthly listeners over subscribers', () => {
    expect(audienceText({ monthly_listeners: 2_000_000, subscribers: 500 }, 'en', t)).toBe(
      'ui.audience.listeners:2M',
    )
  })

  it('falls back to subscribers', () => {
    expect(audienceText({ monthly_listeners: null, subscribers: 31_000 }, 'en', t)).toBe(
      'ui.audience.subscribers:31K',
    )
  })

  it('is empty when neither figure is known', () => {
    expect(audienceText({ monthly_listeners: null, subscribers: null }, 'en', t)).toBe('')
    expect(audienceText({}, 'en', t)).toBe('')
  })
})
