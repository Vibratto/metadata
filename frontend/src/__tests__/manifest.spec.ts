import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const manifest = JSON.parse(readFileSync('public/manifest.webmanifest', 'utf8'))
const tokens = readFileSync('src/styles/tokens.css', 'utf8')
const bg = (block: string) =>
  new RegExp(`${block}[^}]*--color-bg:\\s*(#[0-9a-f]{6})`, 'is').exec(tokens)![1]!

describe('PWA manifest', () => {
  it('starts with the light theme colours, the same as the app background', () => {
    expect(manifest.background_color).toBe(bg(':root \\{'))
    expect(manifest.theme_color).toBe(bg(':root \\{'))
  })

  it('declares the dark theme colours for browsers that support them', () => {
    expect(manifest.color_scheme_dark).toEqual({
      background_color: bg(":root\\[data-theme='dark'\\]"),
      theme_color: bg(":root\\[data-theme='dark'\\]"),
    })
  })
})
