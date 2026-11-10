<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, useId, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import { api } from '../api/client'
import { type Kind, KINDS } from '../views/library/kinds'
import AppIcon from './AppIcon.vue'
import BaseSelect from './BaseSelect.vue'
import CoverArt from './CoverArt.vue'

/**
 * Global library search, always at hand. Suggests artists, albums and tracks grouped by type
 * while typing, scoped by a selector; picking one opens its page and "See all N" opens the
 * Library tab with the same search. Grouped ARIA combobox; "/" focuses it.
 */
type Scope = 'all' | Kind
interface Hit {
  id: number
  name?: string
  title?: string
  image: string
  subtitle: string
}
interface Group {
  count: number
  results: Hit[]
}
type Groups = Partial<Record<Kind, Group>>
type Entry = { id: string; kind: Kind; hit: Hit } | { id: string; kind: Kind; more: number }

const MIN_CHARS = 2
const DELAY = 300
const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const id = useId()
const listId = `${id}-list`
const query = ref('')
const manualScope = ref<Scope | null>(null)
const input = ref<HTMLInputElement>()
const open = ref(false)
const loading = ref(false)
const groups = ref<Groups>({})
const active = ref(-1)

/** The chosen scope; otherwise the open Library tab; otherwise “All”. */
const scope = computed<Scope>({
  get() {
    if (manualScope.value) return manualScope.value
    const tab = route.name === 'library' ? KINDS.find((k) => k === route.query.tab) : undefined
    return tab ?? 'all'
  },
  set: (value) => (manualScope.value = value),
})

const entries = computed<Entry[]>(() =>
  KINDS.flatMap((kind) => {
    const group = groups.value[kind]
    if (!group || group.results.length === 0) return []
    return [
      ...group.results.map((hit) => ({ id: `${id}-${kind}-${hit.id}`, kind, hit })),
      { id: `${id}-${kind}-more`, kind, more: group.count },
    ]
  }),
)
const scopes = computed(() =>
  (['all', ...KINDS] as Scope[]).map((value) => ({ value, label: t(`search.scope.${value}`) })),
)
const shown = computed(() => KINDS.filter((k) => groups.value[k]?.results.length))
const entriesOf = (kind: Kind) => entries.value.filter((e) => e.kind === kind)
const label = (hit: Hit) => (hit.name ?? hit.title)!
const status = computed(() => {
  if (!open.value) return ''
  if (loading.value) return t('search.loading')
  const n = KINDS.reduce((sum, k) => sum + (groups.value[k]?.count ?? 0), 0)
  return n === 0 ? t('search.empty') : t('search.found', { n })
})

let timer: ReturnType<typeof setTimeout> | undefined
let controller: AbortController | undefined

async function fetchNow(): Promise<void> {
  const text = query.value.trim()
  if (text.length < MIN_CHARS) return close()
  controller?.abort()
  const mine = (controller = new AbortController())
  loading.value = true
  open.value = true
  try {
    const params = new URLSearchParams({ q: text, type: scope.value, limit: '5' })
    const body = await api<Groups>(`/api/v1/catalog/search/?${params}`, { signal: mine.signal })
    if (mine.signal.aborted) return
    groups.value = body
    active.value = -1
  } catch {
    if (!mine.signal.aborted) groups.value = {}
  } finally {
    if (!mine.signal.aborted) loading.value = false
  }
}

function schedule(): void {
  clearTimeout(timer)
  if (query.value.trim().length < MIN_CHARS) return close()
  timer = setTimeout(() => void fetchNow(), DELAY)
}
watch(scope, () => (query.value.trim() ? schedule() : undefined))

function close(): void {
  clearTimeout(timer)
  controller?.abort()
  loading.value = false
  open.value = false
  active.value = -1
}

function goToLibrary(tab: Kind): void {
  void router.push({ name: 'library', query: { tab, search: query.value.trim() } })
  reset()
}

function choose(entry: Entry): void {
  if ('more' in entry) return goToLibrary(entry.kind)
  void router.push({ name: 'library-item', params: { kind: entry.kind, id: entry.hit.id } })
  reset()
}

function reset(): void {
  query.value = ''
  groups.value = {}
  close()
}

/** Enter with nothing highlighted: the Library, on the scope's tab or the first group. */
async function submit(): Promise<void> {
  if (!query.value.trim()) return
  const entry = entries.value[active.value]
  if (open.value && entry) return choose(entry)
  if (scope.value !== 'all') return goToLibrary(scope.value)
  clearTimeout(timer)
  if (loading.value || Object.keys(groups.value).length === 0) await fetchNow()
  goToLibrary(shown.value[0] ?? 'artists')
}

function onKeydown(e: KeyboardEvent): void {
  const n = entries.value.length
  if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
    if (!open.value || n === 0) return
    e.preventDefault()
    active.value = (active.value + (e.key === 'ArrowDown' ? 1 : -1) + n) % n
  } else if (e.key === 'Enter' && open.value && entries.value[active.value]) {
    e.preventDefault()
    choose(entries.value[active.value]!)
  } else if (e.key === 'Escape' && open.value) {
    e.preventDefault()
    close()
  }
}

function onKey(e: KeyboardEvent): void {
  const target = e.target as HTMLElement
  if (e.key !== '/' || target.closest('input, textarea, [role="combobox"], [contenteditable]'))
    return
  e.preventDefault()
  input.value?.focus()
}

function onFocusOut(e: FocusEvent): void {
  if (!(e.currentTarget as Node).contains(e.relatedTarget as Node | null)) close()
}

onMounted(() => document.addEventListener('keydown', onKey))
onUnmounted(() => {
  document.removeEventListener('keydown', onKey)
  close()
})
</script>

<template>
  <form class="global-search" role="search" @submit.prevent="submit" @focusout="onFocusOut">
    <label :for="id" class="sr-only">{{ t('search.label') }}</label>
    <BaseSelect
      v-model="scope"
      class="global-search__scope"
      hide-label
      :label="t('search.scopeLabel')"
      :options="scopes"
    />
    <div class="global-search__field">
      <AppIcon name="search" />
      <input
        :id="id"
        ref="input"
        v-model="query"
        type="search"
        role="combobox"
        autocomplete="off"
        aria-autocomplete="list"
        :aria-expanded="open"
        :aria-controls="listId"
        :aria-activedescendant="active >= 0 && open ? entries[active]?.id : undefined"
        enterkeyhint="search"
        :placeholder="t('search.placeholder')"
        @input="schedule"
        @keydown="onKeydown"
      />
      <kbd aria-hidden="true">/</kbd>
    </div>
    <div v-show="open && shown.length" class="global-search__panel">
      <ul :id="listId" role="listbox">
        <li v-for="kind in shown" :key="kind" role="group" :aria-label="t(`search.scope.${kind}`)">
          <p class="global-search__heading" aria-hidden="true">
            {{ t(`search.scope.${kind}`) }}
          </p>
          <ul role="presentation">
            <li
              v-for="entry in entriesOf(kind)"
              :id="entry.id"
              :key="entry.id"
              role="option"
              :aria-selected="entries[active]?.id === entry.id"
              :class="{
                'is-active': entries[active]?.id === entry.id,
                'global-search__more': 'more' in entry,
              }"
              @mousedown.prevent="choose(entry)"
            >
              <template v-if="'more' in entry">
                {{ t(`search.more.${kind}`, { n: entry.more }, entry.more) }}
              </template>
              <template v-else>
                <CoverArt
                  :name="label(entry.hit)"
                  :src="entry.hit.image"
                  :round="kind === 'artists'"
                />
                <span class="global-search__title">{{ label(entry.hit) }}</span>
                <span v-if="entry.hit.subtitle" class="global-search__subtitle">{{
                  entry.hit.subtitle
                }}</span>
              </template>
            </li>
          </ul>
        </li>
      </ul>
    </div>
    <p class="sr-only" aria-live="polite">{{ status }}</p>
  </form>
</template>

<style scoped>
.global-search {
  position: relative;
  display: flex;
  flex: 1;
  align-items: center;
  gap: var(--space-2);
  max-width: 34rem;
  color: var(--color-faint);
}
.global-search__scope {
  flex: none;
  width: auto;
  max-width: 7.5rem;
}
.global-search__field {
  position: relative;
  display: flex;
  flex: 1;
  align-items: center;
  min-width: 0;
}
.global-search .icon {
  position: absolute;
  left: 0.875rem;
  pointer-events: none;
}
input {
  width: 100%;
  padding-left: 2.625rem !important;
  padding-right: 2.5rem !important;
}
kbd {
  position: absolute;
  right: 0.75rem;
  padding: 0 0.375rem;
  border: 1px solid var(--color-border);
  border-radius: 0.375rem;
  font: 500 0.75rem var(--font-family);
  pointer-events: none;
}
input:focus + kbd {
  display: none;
}
.global-search__panel {
  position: absolute;
  top: calc(100% + var(--space-1));
  right: 0;
  left: 0;
  z-index: 30;
  max-height: min(28rem, 70dvh);
  overflow-y: auto;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg, var(--radius));
  background: var(--color-surface, var(--color-bg));
  color: var(--color-text);
  box-shadow: var(--shadow-lg, 0 8px 24px rgb(0 0 0 / 15%));
}
.global-search__panel ul {
  margin: 0;
  padding: var(--space-1);
  list-style: none;
}
.global-search__heading {
  margin: var(--space-2) var(--space-2) var(--space-1);
  color: var(--color-muted);
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
}
[role='option'] {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  min-height: var(--touch-target);
  padding: var(--space-1) var(--space-2);
  border-radius: var(--radius);
  cursor: pointer;
}
[role='option'].is-active {
  background: var(--color-accent-soft);
}
[role='option'] .cover {
  --cover-size: 2rem;
  flex: none;
  font-size: 0.75rem;
}
.global-search__title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.global-search__subtitle {
  overflow: hidden;
  color: var(--color-muted);
  font-size: 0.8125rem;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.global-search__more {
  color: var(--color-accent-strong, var(--color-text));
  font-weight: 500;
}
@media (max-width: 599.98px) {
  kbd {
    display: none;
  }
  input {
    padding-right: 0.75rem !important;
  }
  .global-search {
    position: static;
    flex-wrap: wrap;
  }
  .global-search__scope {
    max-width: 6rem;
  }
  /* On mobile the dropdown spans the full screen width. */
  .global-search__panel {
    position: fixed;
    top: auto;
    inset-inline: var(--space-3);
    margin-top: var(--space-1);
  }
}
</style>
