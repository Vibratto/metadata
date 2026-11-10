import { describe, expect, it } from 'vitest'

import { routes } from '../router'

describe('router', () => {
  it('gathers the routes of the modules in routes/', () => {
    expect(routes.map((r) => r.name)).toContain('home')
  })

  const meta = (name: string) => routes.find((r) => r.name === name)?.meta

  it('puts the dashboard in the main bar and the rest in their “More” section', () => {
    expect(meta('dashboard')?.navGroup).toBe('main')
    expect(meta('watches')?.navSection ?? 'follow').toBe('follow')
    expect(meta('settings')?.navSection).toBe('admin')
    expect(routes.find((r) => r.name === 'more')?.path).toBe('/more')
  })

  it('account and home are not navigation entries (the account goes with the user)', () => {
    expect(meta('account')?.navLabel).toBeUndefined()
    expect(meta('home')?.navLabel).toBeUndefined()
  })

  it('every navigation entry has an icon', () => {
    const entries = routes.filter((r) => r.meta?.navLabel)
    expect(entries.every((r) => r.meta?.navIcon)).toBe(true)
  })
})
