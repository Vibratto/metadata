import { readFileSync } from 'node:fs'
import { afterEach, describe, expect, it } from 'vitest'

import { THEME_KEY, useTheme } from '../composables/useTheme'

const css = readFileSync('src/styles/tokens.css', 'utf8')

/** `--token: value` declarations of the block starting at `start`. */
function declarations(start: string): Record<string, string> {
  const from = css.indexOf(start)
  expect(from).toBeGreaterThan(-1)
  const body = css.slice(css.indexOf('{', from) + 1, css.indexOf('}', from))
  return Object.fromEntries(
    [...body.matchAll(/(--[\w-]+):\s*([^;]+);/g)].map((m) => [m[1]!, m[2]!.trim()]),
  )
}

describe('dark theme tokens', () => {
  it('the system dark theme and the hand-picked one define the same', () => {
    const system = declarations(":root:not([data-theme='light'])")
    const manual = declarations(":root[data-theme='dark']")
    expect(Object.keys(system).length).toBeGreaterThan(10)
    expect(system).toEqual(manual)
  })

  it('every theme defines a hover colour for the primary button', () => {
    expect(declarations(':root {')['--color-primary-hover']).toBeTruthy()
    expect(declarations(":root[data-theme='dark']")['--color-primary-hover']).toBeTruthy()
  })

  it('the primary button hover does not use brightness', () => {
    const base = readFileSync('src/styles/base.css', 'utf8')
    const rule = base.slice(base.indexOf('.btn--primary:hover'))
    expect(rule.slice(0, rule.indexOf('}'))).not.toContain('brightness')
  })
})

describe('theme-color and first paint', () => {
  afterEach(() => {
    document.head.innerHTML = ''
    localStorage.clear()
    useTheme().set('auto')
  })

  it('when a theme is forced, the browser bar follows the chosen theme', () => {
    document.head.innerHTML = '<meta name="theme-color" content="#f7f6f3">'
    useTheme().set('dark')
    expect(document.querySelector('meta[name="theme-color"]')!.getAttribute('content')).toBe(
      '#111014',
    )
    useTheme().set('light')
    expect(document.querySelector('meta[name="theme-color"]')!.getAttribute('content')).toBe(
      '#f7f6f3',
    )
  })

  it('index.html applies the stored theme before loading the main module', () => {
    const html = readFileSync('index.html', 'utf8')
    const inline = html.indexOf(THEME_KEY)
    expect(inline).toBeGreaterThan(-1)
    expect(inline).toBeLessThan(html.indexOf('src="/src/main.ts"'))
  })
})
