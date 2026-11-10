import { createI18n } from 'vue-i18n'

import { messages } from './locales'

/** `localStorage` key holding the language chosen in the account settings. */
export const LOCALE_KEY = 'locale'

/** Spanish when the browser asks for it; English for everything else. */
function browserLocale(): 'es' | 'en' {
  return globalThis.navigator?.language?.toLowerCase().startsWith('es') ? 'es' : 'en'
}

function storedLocale(): 'es' | 'en' {
  try {
    const stored = localStorage.getItem(LOCALE_KEY)
    return stored === 'en' || stored === 'es' ? stored : browserLocale()
  } catch {
    // Storage is blocked (private mode): fall back to the browser language.
    return browserLocale()
  }
}

/** Remembers the chosen language; without storage it only lasts for the session. */
export function rememberLocale(locale: string): void {
  try {
    localStorage.setItem(LOCALE_KEY, locale)
  } catch {
    // Without storage the change still holds until the page reloads.
  }
}

/** The stored language or, failing that, the browser one (English unless it is Spanish). */
export const i18n = createI18n({
  legacy: false,
  locale: storedLocale(),
  fallbackLocale: 'en',
  messages,
})
