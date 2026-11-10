<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { api } from '../api/client'
import { errorText } from '../api/errors'
import type { components } from '../api/schema'
import AppIcon from '../components/AppIcon.vue'
import BaseAlert from '../components/BaseAlert.vue'
import BaseButton from '../components/BaseButton.vue'
import BaseField from '../components/BaseField.vue'
import JobRunPanel from '../components/JobRunPanel.vue'
import { useJobRun } from '../composables/useJobRun'
import { audienceText } from '../format'

type FoundArtist = components['schemas']['ArtistLookupResult']
type Lookup = components['schemas']['ArtistLookup']

/**
 * Import: looks artists up on YouTube Music by name, link or channel id, lets the user pick
 * several (across searches too) and starts the `import` job, followed in the same view.
 */
const { t, locale } = useI18n()
const job = useJobRun()

const query = ref('')
const searched = ref('')
const results = ref<FoundArtist[]>([])
const searchError = ref('')
const loading = ref(false)
const selected = ref(new Map<string, FoundArtist>())

const picked = computed(() => [...selected.value.values()])

// The search runs by itself once typing stops and there are enough letters. Enter and the
// button search at any length; clearing the field brings back the initial state.
const MIN_CHARS = 3
let latest = 0
let lastQuery = ''
watch(query, (text) => {
  const q = text.trim()
  if (!q) {
    latest++
    lastQuery = ''
    results.value = []
    searched.value = ''
    searchError.value = ''
    loading.value = false
  } else if (q.length >= MIN_CHARS && q !== lastQuery) void search()
})

async function search(): Promise<void> {
  const q = query.value.trim()
  if (q && q === lastQuery && !searchError.value) return
  lastQuery = q
  const ticket = ++latest
  searched.value = ''
  results.value = []
  searchError.value = ''
  if (!q) return
  loading.value = true
  try {
    const page = await api<Lookup>(`/api/v1/catalog/ytmusic/artists/?q=${encodeURIComponent(q)}`)
    if (ticket !== latest) return
    results.value = page.results
    searched.value = q
  } catch (e) {
    if (ticket === latest) searchError.value = errorText(e, t)
  } finally {
    if (ticket === latest) loading.value = false
  }
}

function toggle(artist: FoundArtist, on: boolean): void {
  if (on) selected.value.set(artist.ytmusic_id, artist)
  else selected.value.delete(artist.ytmusic_id)
}

async function start(): Promise<void> {
  const ok = await job.start('import', { artist_ids: picked.value.map((a) => a.ytmusic_id) })
  if (ok) selected.value.clear()
}
</script>

<template>
  <section class="import">
    <header class="page-head">
      <div>
        <h1>{{ t('import.title') }}</h1>
        <p class="page-head__sub">{{ t('import.intro') }}</p>
      </div>
      <RouterLink class="btn btn--secondary" :to="{ name: 'import-folder' }">
        <AppIcon name="folder" />{{ t('import.folder') }}
      </RouterLink>
    </header>

    <form class="search" role="search" @submit.prevent="search">
      <BaseField v-model="query" :label="t('import.search.label')" type="search" :debounce="500" />
      <BaseButton type="submit" :disabled="loading">{{ t('import.search.submit') }}</BaseButton>
    </form>

    <BaseAlert v-if="searchError" variant="error">{{ searchError }}</BaseAlert>
    <p v-else-if="!searched && !loading" class="hint">{{ t('import.search.empty') }}</p>
    <p v-else-if="searched && results.length === 0">
      {{ t('import.search.none', { q: searched }) }}
    </p>
    <ul v-if="results.length" class="results" :aria-label="t('import.search.results')">
      <li v-for="a in results" :key="a.ytmusic_id">
        <label class="artist" :class="{ 'artist--blocked': a.blocked }">
          <input
            type="checkbox"
            :checked="selected.has(a.ytmusic_id)"
            :disabled="a.blocked"
            @change="toggle(a, ($event.target as HTMLInputElement).checked)"
          />
          <img v-if="a.image_url" :src="a.image_url" alt="" loading="lazy" />
          <span v-else class="artist__placeholder" aria-hidden="true"></span>
          <span class="artist__text">
            <strong>{{ a.name }}</strong>
            <small v-if="audienceText(a, locale, t)">{{ audienceText(a, locale, t) }}</small>
            <small v-if="a.album_count !== null && a.single_count !== null">
              {{ t('import.artist.albums', { n: a.album_count }, a.album_count) }} ·
              {{ t('import.artist.singles', { n: a.single_count }, a.single_count) }}
            </small>
            <small v-if="a.blocked" class="artist__tag">{{ t('import.artist.blocked') }}</small>
            <small v-else-if="a.in_library" class="artist__tag">
              {{ t('import.artist.inCatalog') }}
            </small>
          </span>
        </label>
      </li>
    </ul>

    <section v-if="picked.length" class="selected">
      <h2>{{ t('import.selected.title', { n: picked.length }) }}</h2>
      <ul>
        <li v-for="a in picked" :key="a.ytmusic_id">
          <span>{{ a.name }}</span>
          <BaseButton
            variant="secondary"
            :aria-label="t('import.selected.remove', { name: a.name })"
            @click="toggle(a, false)"
          >
            ×
          </BaseButton>
        </li>
      </ul>
    </section>

    <div class="launch" :class="{ 'action-bar': picked.length }">
      <BaseButton
        :variant="picked.length ? 'accent' : 'primary'"
        :disabled="picked.length === 0 || job.active"
        @click="start"
      >
        {{ t('import.start', { n: picked.length }, picked.length) }}
      </BaseButton>
    </div>

    <JobRunPanel :job="job" />
    <p v-if="job.run?.status === 'succeeded'" class="hint">
      <RouterLink :to="{ name: 'library', query: { tab: 'related' } }">
        {{ t('import.related') }}
      </RouterLink>
    </p>
  </section>
</template>

<style scoped>
.import {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}
.import .page-head {
  margin-bottom: var(--space-2);
}
.search {
  display: flex;
  align-items: flex-end;
  gap: var(--space-2);
  max-width: 48rem;
}
.search > :first-child {
  flex: 1;
}
.search :deep(input) {
  min-height: 3.25rem;
  border-radius: var(--radius);
  font-size: 1.0625rem;
}
.search .btn {
  min-height: 3.25rem;
}
.hint {
  color: var(--color-muted);
}
/* Mobile-first: one column of artists, two from 600 px and three from 1024 px. */
.results {
  display: grid;
  gap: 0.75rem;
  margin: 0;
  padding: 0;
  list-style: none;
}
.artist {
  display: flex;
  align-items: center;
  gap: 0.875rem;
  min-height: var(--touch-target);
  padding: 0.875rem;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  background: var(--color-surface);
  box-shadow: var(--shadow);
  cursor: pointer;
  transition:
    border-color 0.15s,
    box-shadow 0.15s;
}
.artist:hover {
  border-color: var(--color-faint);
}
.artist:has(input:checked) {
  border-color: var(--color-accent);
  box-shadow: 0 0 0 3px var(--color-accent-soft);
}
.artist--blocked {
  cursor: not-allowed;
  opacity: 0.55;
}
/* The checkbox sits on the right, as in a selection list. */
.artist input {
  order: 3;
  width: 1.25rem;
  height: 1.25rem;
  margin-left: auto;
}
.artist img,
.artist__placeholder {
  flex: none;
  width: 3.25rem;
  height: 3.25rem;
  border-radius: 50%;
  background: linear-gradient(140deg, var(--color-accent-strong), var(--color-accent));
  object-fit: cover;
}
.artist__text {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.artist__text strong {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.artist__text small {
  color: var(--color-muted);
  font-size: 0.8125rem;
}
.artist__tag {
  font-weight: 600;
}
.selected {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}
.selected ul {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  margin: 0;
  padding: 0;
  list-style: none;
}
.selected li {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  padding-left: 0.875rem;
  border-radius: 999px;
  background: var(--color-accent-soft);
  font-size: 0.875rem;
  font-weight: 550;
}
.selected li .btn {
  min-height: 2.25rem;
  min-width: 2.25rem;
  border: 0;
  border-radius: 999px;
  background: transparent;
}
.launch {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
}

@media (min-width: 600px) {
  .results {
    grid-template-columns: repeat(2, 1fr);
  }
}
@media (min-width: 1024px) {
  .results {
    grid-template-columns: repeat(3, 1fr);
  }
}
</style>
