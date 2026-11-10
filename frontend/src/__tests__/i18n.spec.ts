import { afterEach, describe, expect, it, vi } from 'vitest'

async function load() {
  vi.resetModules()
  return import('../i18n')
}

afterEach(() => {
  vi.unstubAllGlobals()
  localStorage.clear()
})

describe('i18n', () => {
  it('starts in English if the browser is neither English nor Spanish', async () => {
    vi.stubGlobal('navigator', { language: 'fr-FR' })
    expect((await load()).i18n.global.locale.value).toBe('en')
  })

  it('uses the browser language when none is stored', async () => {
    vi.stubGlobal('navigator', { language: 'en-GB' })
    expect((await load()).i18n.global.locale.value).toBe('en')
    vi.stubGlobal('navigator', { language: 'es-ES' })
    expect((await load()).i18n.global.locale.value).toBe('es')
  })

  it('the stored language wins over the browser one', async () => {
    vi.stubGlobal('navigator', { language: 'en-GB' })
    localStorage.setItem('locale', 'es')
    expect((await load()).i18n.global.locale.value).toBe('es')
  })

  it('restores the stored English', async () => {
    vi.stubGlobal('navigator', { language: 'es-ES' })
    localStorage.setItem('locale', 'en')
    expect((await load()).i18n.global.locale.value).toBe('en')
  })

  it('ignores an unknown stored value', async () => {
    vi.stubGlobal('navigator', { language: 'fr-FR' })
    localStorage.setItem('locale', 'fr')
    expect((await load()).i18n.global.locale.value).toBe('en')
  })

  it('stores the chosen language', async () => {
    ;(await load()).rememberLocale('es')
    expect(localStorage.getItem('locale')).toBe('es')
  })

  it('works without storage', async () => {
    const broken = {
      getItem: () => {
        throw new Error('blocked')
      },
      setItem: () => {
        throw new Error('blocked')
      },
    }
    vi.stubGlobal('navigator', { language: 'es-ES' })
    vi.stubGlobal('localStorage', broken)
    const mod = await load()
    expect(mod.i18n.global.locale.value).toBe('es')
    expect(() => mod.rememberLocale('en')).not.toThrow()
  })
})
