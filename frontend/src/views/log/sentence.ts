import type { components } from '../../api/schema'

type ActivityLog = components['schemas']['ActivityLog']

/** What `useI18n` gives and a sentence needs. */
interface Translator {
  t(key: string, named?: Record<string, unknown>): string
  te(key: string): boolean
}

/**
 * The sentence that tells an activity entry to the user. The action code never reaches the
 * screen: one without a sentence of its own gets a generic one.
 */
export function activitySentence(entry: ActivityLog, { t, te }: Translator): string {
  const key = `log.actions.${entry.action.replaceAll('.', '_')}`
  return te(key) ? t(key, entry.detail as Record<string, unknown>) : t('log.actions.other')
}
