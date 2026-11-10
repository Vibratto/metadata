import { computed, reactive, ref, watch, type Ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import { api } from '../api/client'
import { errorText } from '../api/errors'

/** One page of a DRF list. */
export interface Page<T> {
  count: number
  next?: string | null
  previous?: string | null
  results: T[]
}

/**
 * Paged API list whose page, search, ordering and the given filters live in the URL query,
 * so links, reloads and the back button keep the view. Other query keys are kept but not
 * sent to the API.
 *
 * @param path Ruta de la API, p. ej. `/api/v1/catalog/tracks/`.
 * @param filters Claves de filtro que acepta ese endpoint.
 * @param fixed Parámetros que se mandan siempre y no van en la URL; dependen de la query.
 */
export function usePagedList<T>(
  path: string,
  filters: readonly string[] = [],
  fixed: (query: Record<string, string>) => Record<string, string> = () => ({}),
) {
  const { t } = useI18n()
  const route = useRoute()
  const router = useRouter()
  const owner = route.name
  const keys = ['page', 'search', 'ordering', ...filters]

  const items = ref([]) as Ref<T[]>
  const count = ref(0)
  const hasNext = ref(false)
  const hasPrevious = ref(false)
  const loading = ref(false)
  const error = ref('')

  /** URL values the API understands, without empty ones. */
  const query = computed(() => {
    const out: Record<string, string> = {}
    for (const key of keys) {
      const value = route.query[key]
      if (typeof value === 'string' && value !== '') out[key] = value
    }
    return out
  })
  const page = computed(() => Number(query.value.page ?? 1))

  // Only the latest request counts: with quick searches an old answer never overwrites a new one.
  let latest = 0

  async function reload(): Promise<void> {
    const ticket = ++latest
    loading.value = true
    try {
      const data = await api<Page<T>>(
        `${path}?${new URLSearchParams({ ...fixed(query.value), ...query.value })}`,
      )
      if (ticket !== latest) return
      items.value = data.results
      count.value = data.count
      hasNext.value = Boolean(data.next)
      hasPrevious.value = Boolean(data.previous)
      error.value = ''
    } catch (e) {
      if (ticket === latest) error.value = errorText(e, t)
    } finally {
      if (ticket === latest) loading.value = false
    }
  }

  /** Changes search, ordering or filters (empty removes them) and goes back to page one. */
  function update(changes: Record<string, string>): void {
    const next: Record<string, unknown> = { ...route.query, ...changes }
    delete next.page
    for (const [key, value] of Object.entries(next)) if (value === '') delete next[key]
    void router.replace({ query: next as Record<string, string> })
  }

  function goTo(n: number): void {
    void router.replace({ query: { ...route.query, page: String(n) } })
  }

  // When leaving for another route the query changes before the view unmounts: do not reload.
  watch(
    () => JSON.stringify(query.value),
    () => {
      if (route.name === owner) void reload()
    },
    { immediate: true },
  )

  return reactive({
    items,
    count,
    page,
    hasNext,
    hasPrevious,
    loading,
    error,
    query,
    reload,
    update,
    goTo,
  })
}
