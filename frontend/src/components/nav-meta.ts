import 'vue-router'
import type { RouteRecordNormalized } from 'vue-router'

import type { IconName } from './icons'

declare module 'vue-router' {
  /** Project-specific route metadata. */
  interface RouteMeta {
    /** vue-i18n key under which the route shows in the main navigation. */
    navLabel?: string
    /** Navigation group; without one the route goes to “More”. */
    navGroup?: 'main' | 'more'
    /** Position inside the group, ascending (0 by default). */
    navOrder?: number
    /** Section of “More” it belongs to; tracking by default. */
    navSection?: NavSection
    /** Icon of the entry. */
    navIcon?: IconName
  }
}

/** Sections of “More”, in display order. */
export const NAV_SECTIONS = ['follow', 'admin'] as const
export type NavSection = (typeof NAV_SECTIONS)[number]

/** Entries that fit the mobile bottom bar; the rest go to “More”. */
export const MAIN_SLOTS = 4

/**
 * Splits routes with `navLabel` into the main bar and "More", sorted, hiding admin-only ones
 * for non-admins. Main entries beyond the bar's slots go first in "More".
 */
export function navEntries(routes: RouteRecordNormalized[]): {
  main: RouteRecordNormalized[]
  more: RouteRecordNormalized[]
  sections: { key: NavSection; routes: RouteRecordNormalized[] }[]
} {
  const visible = routes
    .filter((r) => r.meta.navLabel)
    .sort((a, b) => (a.meta.navOrder ?? 0) - (b.meta.navOrder ?? 0))
  const main = visible.filter((r) => r.meta.navGroup === 'main')
  const more = visible.filter((r) => r.meta.navGroup !== 'main')
  const rest = [...main.slice(MAIN_SLOTS), ...more]
  const sections = NAV_SECTIONS.map((key) => ({
    key,
    routes: rest.filter((r) => (r.meta.navSection ?? 'follow') === key),
  })).filter((s) => s.routes.length > 0)
  return { main: main.slice(0, MAIN_SLOTS), more: rest, sections }
}
