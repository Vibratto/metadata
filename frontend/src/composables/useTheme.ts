import { ref } from 'vue'

/** `localStorage` key holding the theme. */
export const THEME_KEY = 'vibratto-metadata.theme'

export const THEMES = ['auto', 'light', 'dark'] as const
export type Theme = (typeof THEMES)[number]

const theme = ref<Theme>('auto')

/** Mobile browser bar colour per theme (same as `--color-bg`). */
const THEME_COLORS = { light: '#f7f6f3', dark: '#111014' } as const

/**
 * With a forced theme, `theme-color` follows the theme instead of the system; in automatic
 * mode it gets its original value and `media` back.
 */
function applyThemeColor(value: Theme): void {
  for (const meta of document.querySelectorAll<HTMLMetaElement>('meta[name="theme-color"]')) {
    meta.dataset.autoContent ??= meta.content
    meta.dataset.autoMedia ??= meta.media
    if (value === 'auto') {
      meta.content = meta.dataset.autoContent
      meta.media = meta.dataset.autoMedia
    } else {
      meta.content = THEME_COLORS[value]
      meta.media = 'all'
    }
  }
}

function apply(value: Theme): void {
  applyThemeColor(value)
  theme.value = value
  // Without the attribute `prefers-color-scheme` decides; with it, the chosen theme.
  if (value === 'auto') delete document.documentElement.dataset.theme
  else document.documentElement.dataset.theme = value
}

/**
 * Applies the stored theme (or automatic). Called once at startup, before mounting.
 */
export function initTheme(): void {
  let stored: string | null = null
  try {
    stored = localStorage.getItem(THEME_KEY)
  } catch {
    // Storage is blocked (private mode): follow the system.
  }
  apply(THEMES.find((t) => t === stored) ?? 'auto')
}

/**
 * UI theme: automatic (the system's), light or dark. Remembered in the browser.
 */
export function useTheme() {
  function set(value: Theme): void {
    apply(value)
    try {
      localStorage.setItem(THEME_KEY, value)
    } catch {
      // Without storage the change lasts until the page reloads.
    }
  }
  return { theme, set }
}
