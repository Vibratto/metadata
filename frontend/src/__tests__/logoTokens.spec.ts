import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const css = readFileSync('src/styles/tokens.css', 'utf8')

describe('brand tokens', () => {
  it('the logo background does not invert in dark mode', () => {
    const definitions = css.match(/--color-logo-bg:\s*([^;]+);/g) ?? []
    expect(definitions.length).toBeGreaterThan(0)
    expect(new Set(definitions).size).toBe(1)
  })

  it('the sign-in logo uses the brand token', () => {
    expect(readFileSync('src/components/AuthLayout.vue', 'utf8')).toContain('var(--color-logo-bg)')
  })

  it('the navigation shows the name without a logo', () => {
    for (const f of ['src/components/AppNav.vue', 'src/App.vue']) {
      expect(readFileSync(f, 'utf8')).not.toContain('name="logo"')
    }
  })
})
