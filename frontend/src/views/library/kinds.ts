import type { components } from '../../api/schema'

export type Artist = components['schemas']['Artist']
export type Album = components['schemas']['Album']
export type Track = components['schemas']['Track']
export type Credit = components['schemas']['Credit']
export type HistoryEntry = components['schemas']['HistoryEntry']
export type Item = Artist | Album | Track

/** Kinds of item; each matches a segment of the API (`catalog/<kind>/`). */
export const KINDS = ['artists', 'albums', 'tracks'] as const
export type Kind = (typeof KINDS)[number]

/**
 * Library tabs. "related" lists the artists saved as a profile only: they are artists
 * without music, kept apart so the Artists tab shows what is actually in the library.
 */
export const TABS = [...KINDS, 'related'] as const
export type Tab = (typeof TABS)[number]

/** How a field is edited: numbers travel with their type, not as text. */
export type FieldType = 'text' | 'url' | 'number'

/**
 * A simple list filter (not an entity one): a dropdown of fixed values or a number.
 * `options` are value → i18n key pairs inside `library.options`.
 */
export interface FieldSpec {
  key: string
  type: 'select' | 'number'
  options?: readonly (readonly [string, string])[]
}

const YES_NO = [
  ['true', 'yes'],
  ['false', 'no'],
] as const
const RECORD_TYPES = [
  ['album', 'album'],
  ['single', 'single'],
  ['ep', 'ep'],
] as const

interface KindSpec {
  /** Kind of item the tab lists. */
  kind: Kind
  /** Query sent with every request of the tab; never shown in the URL. */
  fixed: Readonly<Record<string, string>>
  /** Simple filters (besides the entity ones), in form order. */
  fields: readonly FieldSpec[]
  /** Filters by artist or album, which use a searchable picker. */
  entities: readonly ('artist' | 'album')[]
  /** API filters the list keeps in the URL, besides search and ordering. */
  filters: readonly string[]
  /** `ordering` values the list offers (the backend's `ordering_fields`). */
  orderings: readonly string[]
  /** Editable fields, the same ones the history reverts. */
  editable: Readonly<Record<string, FieldType>>
  /** Block kind; artists are not blocked from here. */
  blockKind?: 'album' | 'track'
}

export const SPECS: Record<Tab, KindSpec> = {
  artists: {
    kind: 'artists',
    fixed: { profile_only: 'false' },
    fields: [
      { key: 'has_pending', type: 'select', options: YES_NO },
      { key: 'has_downloads', type: 'select', options: YES_NO },
      { key: 'watched', type: 'select', options: YES_NO },
    ],
    entities: [],
    filters: ['has_pending', 'has_downloads', 'watched'],
    orderings: ['name', '-name', '-track_count', '-pending_count'],
    editable: { name: 'text', image_url: 'url', description: 'text' },
  },
  related: {
    kind: 'artists',
    fixed: { profile_only: 'true' },
    fields: [],
    entities: [],
    filters: [],
    orderings: ['-monthly_listeners', 'name', '-name'],
    editable: { name: 'text', image_url: 'url', description: 'text' },
  },
  albums: {
    kind: 'albums',
    fixed: {},
    fields: [
      { key: 'record_type', type: 'select', options: RECORD_TYPES },
      {
        key: 'download_status',
        type: 'select',
        options: [
          ['complete', 'complete'],
          ['partial', 'partial'],
          ['none', 'none'],
        ],
      },
      { key: 'year_from', type: 'number' },
      { key: 'year_to', type: 'number' },
    ],
    entities: ['artist'],
    filters: ['artist', 'record_type', 'download_status', 'year_from', 'year_to'],
    orderings: ['title', '-title', 'year', '-year', '-track_count', '-pending_count'],
    editable: { title: 'text', year: 'number', cover_url: 'url' },
    blockKind: 'album',
  },
  tracks: {
    kind: 'tracks',
    fixed: {},
    fields: [
      { key: 'downloaded', type: 'select', options: YES_NO },
      { key: 'explicit', type: 'select', options: YES_NO },
      { key: 'record_type', type: 'select', options: RECORD_TYPES },
      { key: 'year_from', type: 'number' },
      { key: 'year_to', type: 'number' },
      { key: 'duration_min', type: 'number' },
      { key: 'duration_max', type: 'number' },
    ],
    entities: ['artist', 'album'],
    filters: [
      'artist',
      'album',
      'downloaded',
      'explicit',
      'record_type',
      'year_from',
      'year_to',
      'duration_min',
      'duration_max',
    ],
    orderings: [
      'title',
      '-title',
      'track_number',
      'album__title',
      '-album__year',
      'duration',
      '-duration',
    ],
    editable: { title: 'text', track_number: 'number', disc_number: 'number' },
    blockKind: 'track',
  },
}

export function apiPath(kind: Kind, id?: number | string): string {
  return id === undefined ? `/api/v1/catalog/${kind}/` : `/api/v1/catalog/${kind}/${id}/`
}

/** Display name: artists have `name`, everything else `title`. */
export function label(item: Item): string {
  return 'name' in item ? item.name : item.title
}

/** The item's YouTube Music id: a channel, a release or a video. `null` if it has none. */
export function externalId(item: Item): string | null {
  return 'video_id' in item ? item.video_id : item.ytmusic_id
}
/** `m:ss` duration from seconds. */
export function duration(seconds: number | null): string {
  if (seconds === null) return ''
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`
}
