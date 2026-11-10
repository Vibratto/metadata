import { reactive } from 'vue'

import { api } from '../api/client'

/** Readable names of the artists and albums a filter keeps by id in the URL. */
type EntityKind = 'artists' | 'albums'

const names = reactive(new Map<string, string>())
const asked = new Set<string>()
const key = (kind: EntityKind, id: string) => `${kind}:${id}`

/** Remembers a name that is already known (e.g. a chosen option). */
export function rememberEntity(kind: EntityKind, id: string, name: string): void {
  names.set(key(kind, id), name)
}

/**
 * Name of an artist or album by id; `#id` while it loads. Each id is requested once.
 */
export function entityName(kind: EntityKind, id: string): string {
  const k = key(kind, id)
  const known = names.get(k)
  if (known !== undefined) return known
  if (!asked.has(k)) {
    asked.add(k)
    api<{ name?: string; title?: string }>(`/api/v1/catalog/${kind}/${id}/`)
      .then((item) => names.set(k, item.name ?? item.title ?? `#${id}`))
      .catch(() => asked.delete(k))
  }
  return `#${id}`
}
