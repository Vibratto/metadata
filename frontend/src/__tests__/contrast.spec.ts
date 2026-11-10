import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const css = readFileSync('src/styles/tokens.css', 'utf8')

/** Colour tokens of the block starting at `start`, on top of the `:root` ones. */
function theme(start: string | null): Record<string, string> {
  const read = (from: number) =>
    Object.fromEntries(
      [
        ...css
          .slice(css.indexOf('{', from) + 1, css.indexOf('}', from))
          .matchAll(/(--color-[\w-]+):\s*(#[0-9a-f]{6})\s*;/gi),
      ].map((m) => [m[1]!, m[2]!]),
    )
  const base = read(css.indexOf(':root {'))
  return start === null ? base : { ...base, ...read(css.indexOf(start)) }
}

const channel = (v: number) => {
  const c = v / 255
  return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4
}
function luminance(hex: string): number {
  const n = parseInt(hex.slice(1), 16)
  return (
    0.2126 * channel((n >> 16) & 255) + 0.7152 * channel((n >> 8) & 255) + 0.0722 * channel(n & 255)
  )
}
function ratio(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x)
  return (hi! + 0.05) / (lo! + 0.05)
}

/** Text/background pairs that are really rendered (alerts, chips, buttons, hint text). */
const TEXT_PAIRS: [string, string][] = [
  ['--color-text', '--color-bg'],
  ['--color-text', '--color-surface'],
  ['--color-muted', '--color-bg'],
  ['--color-muted', '--color-surface'],
  ['--color-muted', '--color-surface-2'],
  ['--color-faint', '--color-bg'],
  ['--color-faint', '--color-surface'],
  ['--color-accent', '--color-surface'],
  ['--color-accent', '--color-accent-soft'],
  ['--color-info', '--color-info-soft'],
  ['--color-success', '--color-success-soft'],
  ['--color-warning', '--color-warning-soft'],
  ['--color-danger', '--color-danger-soft'],
  ['--color-danger', '--color-surface'],
  ['--color-primary-contrast', '--color-primary'],
  ['--color-primary-contrast', '--color-primary-hover'],
  ['--color-accent-contrast', '--color-accent'],
]

const THEMES: [string, string | null][] = [
  ['light', null],
  ['system dark', ":root:not([data-theme='light'])"],
  ['chosen dark', ":root[data-theme='dark']"],
]

describe.each(THEMES)('AA contrast, %s theme', (_name, start) => {
  const tokens = theme(start)
  it.each(TEXT_PAIRS)('%s on %s reaches 4.5:1', (fg, bg) => {
    expect(tokens[fg], fg).toBeDefined()
    expect(tokens[bg], bg).toBeDefined()
    expect(ratio(tokens[fg]!, tokens[bg]!)).toBeGreaterThanOrEqual(4.5)
  })

  it('focus stands out from the background (3:1)', () => {
    expect(ratio(tokens['--color-focus']!, tokens['--color-bg']!)).toBeGreaterThanOrEqual(3)
    expect(ratio(tokens['--color-focus']!, tokens['--color-surface']!)).toBeGreaterThanOrEqual(3)
  })

  it('the coral logo icon shows on its background (3:1)', () => {
    expect(
      ratio(tokens['--color-accent-strong']!, tokens['--color-logo-bg']!),
    ).toBeGreaterThanOrEqual(3)
  })
})
