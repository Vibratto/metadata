import { describe, expect, it } from 'vitest'

import { messages } from '../locales'

type Tree = { [key: string]: string | Tree }

function paths(tree: Tree, prefix = ''): string[] {
  return Object.entries(tree).flatMap(([k, v]) =>
    typeof v === 'string' ? [`${prefix}${k}`] : paths(v, `${prefix}${k}.`),
  )
}

describe('textos de acceso, panel, cuenta y comunes', () => {
  it.each(['auth', 'dashboard', 'account', 'ui', 'nav'])(
    '“%s” has the same keys in en and es',
    (ns) => {
      const es = paths(messages.es[ns] as Tree)
      expect(es.length).toBeGreaterThan(0)
      expect(paths(messages.en[ns] as Tree)).toEqual(es)
    },
  )
})
