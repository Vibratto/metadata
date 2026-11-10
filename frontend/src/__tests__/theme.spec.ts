import { afterEach, describe, expect, it } from 'vitest'

import ThemeToggle from '../components/ThemeToggle.vue'
import { THEME_KEY, initTheme, useTheme } from '../composables/useTheme'
import { render } from './helpers'

const root = document.documentElement

afterEach(() => {
  localStorage.clear()
  useTheme().set('auto')
})

describe('useTheme', () => {
  it('follows the system by default: no forced theme on the document', () => {
    initTheme()
    expect(useTheme().theme.value).toBe('auto')
    expect(root.dataset.theme).toBeUndefined()
  })

  it('choosing a theme applies it to the document and remembers it', () => {
    useTheme().set('dark')
    expect(root.dataset.theme).toBe('dark')
    expect(localStorage.getItem(THEME_KEY)).toBe('dark')
  })

  it('going back to automatic removes the forced theme', () => {
    useTheme().set('light')
    useTheme().set('auto')
    expect(root.dataset.theme).toBeUndefined()
    expect(localStorage.getItem(THEME_KEY)).toBe('auto')
  })

  it('restores the stored theme at startup', () => {
    localStorage.setItem(THEME_KEY, 'light')
    initTheme()
    expect(useTheme().theme.value).toBe('light')
    expect(root.dataset.theme).toBe('light')
  })

  it('ignores a stored value that is not a theme', () => {
    localStorage.setItem(THEME_KEY, 'rosa')
    initTheme()
    expect(useTheme().theme.value).toBe('auto')
  })
})

describe('ThemeToggle', () => {
  it('goes from automatic to light, to dark and back, naming the current theme', async () => {
    const w = render(ThemeToggle)
    const button = w.get('button')
    expect(button.attributes('aria-label')).toBe('Theme: automatic')
    await button.trigger('click')
    expect(button.attributes('aria-label')).toBe('Theme: light')
    await button.trigger('click')
    expect(button.attributes('aria-label')).toBe('Theme: dark')
    expect(root.dataset.theme).toBe('dark')
    await button.trigger('click')
    expect(button.attributes('aria-label')).toBe('Theme: automatic')
  })

  it('translates to Spanish', () => {
    expect(render(ThemeToggle, {}, 'es').get('button').attributes('aria-label')).toBe(
      'Tema: automático',
    )
  })
})
