import { describe, expect, it } from 'vitest'

import { messages } from '../locales'

describe('locales', () => {
  it('gathers the messages of every area in both languages', () => {
    expect(messages.es).toHaveProperty('app.title')
    expect(messages.en).toHaveProperty('app.title')
  })

  it('has the same top-level keys in English and Spanish', () => {
    expect(Object.keys(messages.es).sort()).toEqual(Object.keys(messages.en).sort())
  })
})

/** Every leaf key path of a message tree (“a.b.c”). */
function leafKeys(tree: object, prefix = ''): string[] {
  return Object.entries(tree).flatMap(([key, value]) =>
    typeof value === 'object' && value !== null
      ? leafKeys(value, `${prefix}${key}.`)
      : [`${prefix}${key}`],
  )
}

describe('translation keys', () => {
  it('no key is missing in English or Spanish', () => {
    const es = leafKeys(messages.es)
    const en = leafKeys(messages.en)
    expect(
      es.filter((k) => !en.includes(k)),
      'missing in English',
    ).toEqual([])
    expect(
      en.filter((k) => !es.includes(k)),
      'missing in Spanish',
    ).toEqual([])
  })

  it('no translation is empty', () => {
    for (const tree of [messages.es, messages.en]) {
      expect(JSON.stringify(tree)).not.toMatch(/:\s*""/)
    }
  })
})
