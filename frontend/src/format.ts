/** "12.4M" for 12 400 000, in the given locale. */
export function compactNumber(value: number, locale: string): string {
  return new Intl.NumberFormat(locale, { notation: 'compact', maximumFractionDigits: 1 }).format(
    value,
  )
}

/**
 * How big an artist is, as text: monthly listeners when YouTube Music gives them, otherwise
 * subscribers. Empty when neither is known.
 */
export function audienceText(
  artist: { monthly_listeners?: number | null; subscribers?: number | null },
  locale: string,
  t: (key: string, named: Record<string, unknown>) => string,
): string {
  if (artist.monthly_listeners)
    return t('ui.audience.listeners', { n: compactNumber(artist.monthly_listeners, locale) })
  if (artist.subscribers)
    return t('ui.audience.subscribers', { n: compactNumber(artist.subscribers, locale) })
  return ''
}
