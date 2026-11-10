<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import { ApiError, api } from '../../api/client'
import { errorText } from '../../api/errors'
import type { components } from '../../api/schema'
import BaseAlert from '../../components/BaseAlert.vue'
import BaseButton from '../../components/BaseButton.vue'
import BaseCheckbox from '../../components/BaseCheckbox.vue'
import BaseField from '../../components/BaseField.vue'
import type { Page } from '../../composables/usePagedList'

type Artist = components['schemas']['Artist']
type Credit = components['schemas']['Credit']
type Watch = components['schemas']['Watch']
type WatchRequest = components['schemas']['WatchRequest']

/** Form fields that can carry their own API error. */
const FIELDS = ['name', 'interval_hours', 'artist_ids'] as const
type Field = (typeof FIELDS)[number]

/**
 * Create and edit a new-release watch. API validation errors show next to their field.
 */
const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const id = route.params.id as string | undefined

const name = ref('')
const interval = ref('24')
const autoDownload = ref(false)
const enabled = ref(true)
const chosen = ref<Pick<Credit, 'id' | 'name'>[]>([])
const original = ref('')

const query = ref('')
const results = ref<Artist[] | null>(null)

const fieldErrors = ref<Partial<Record<Field, string>>>({})
const error = ref('')

onMounted(async () => {
  if (!id) return
  try {
    const watch = await api<Watch>(`/api/v1/watches/${id}/`)
    name.value = original.value = watch.name
    interval.value = String(watch.interval_hours)
    autoDownload.value = Boolean(watch.auto_download)
    enabled.value = Boolean(watch.enabled)
    chosen.value = watch.artists.map(({ id, name }) => ({ id, name }))
  } catch (e) {
    error.value = errorText(e, t)
  }
})

// Searches by itself once typing stops; clearing the field clears the results.
watch(query, (text) => {
  if (text.trim()) void search()
  else results.value = null
})

let latest = 0
async function search(): Promise<void> {
  error.value = ''
  const ticket = ++latest
  try {
    const page = await api<Page<Artist>>(
      `/api/v1/catalog/artists/?search=${encodeURIComponent(query.value)}`,
    )
    if (ticket !== latest) return
    results.value = page.results.filter((a) => !chosen.value.some((c) => c.id === a.id))
  } catch (e) {
    if (ticket === latest) error.value = errorText(e, t)
  }
}

function add(artist: Artist): void {
  chosen.value.push({ id: artist.id, name: artist.name })
  results.value = (results.value as Artist[]).filter((a) => a.id !== artist.id)
}

/** Swaps artist `index` with the one at `index + step`; the first is the main artist. */
function move(index: number, step: -1 | 1): void {
  const list = chosen.value
  ;[list[index], list[index + step]] = [list[index + step]!, list[index]!]
}

/** Spreads a DRF 400 over the fields; whatever is not a field's goes to the general alert. */
function showErrors(e: unknown): void {
  if (!(e instanceof ApiError) || e.status !== 400 || typeof e.body !== 'object' || !e.body) {
    error.value = errorText(e, t)
    return
  }
  const rest: Record<string, unknown> = { ...e.body }
  for (const field of FIELDS) {
    if (field in rest)
      fieldErrors.value[field] = errorText(new ApiError(e.kind, 400, rest[field]), t)
    delete rest[field]
  }
  if (Object.keys(rest).length) error.value = errorText(new ApiError(e.kind, 400, rest), t)
}

async function save(): Promise<void> {
  fieldErrors.value = {}
  error.value = ''
  const body: WatchRequest = {
    name: name.value,
    interval_hours: Number(interval.value),
    auto_download: autoDownload.value,
    enabled: enabled.value,
    artist_ids: chosen.value.map((a) => a.id),
  }
  try {
    const watch = await api<Watch>(id ? `/api/v1/watches/${id}/` : '/api/v1/watches/', {
      method: id ? 'PATCH' : 'POST',
      body,
    })
    await router.push({ name: 'watch', params: { id: watch.id } })
  } catch (e) {
    showErrors(e)
  }
}
</script>

<template>
  <section class="watch-form">
    <h1>
      {{ id ? t('watches.form.editTitle', { name: original }) : t('watches.form.createTitle') }}
    </h1>
    <BaseAlert v-if="error" variant="error">{{ error }}</BaseAlert>

    <fieldset class="watch-form__fields">
      <form id="watch-form" name="watch" @submit.prevent="save">
        <BaseField v-model="name" :label="t('watches.form.name')" :error="fieldErrors.name" />
        <BaseField
          v-model="interval"
          type="number"
          :label="t('watches.form.interval')"
          :error="fieldErrors.interval_hours"
        />
        <BaseCheckbox v-model="autoDownload" :label="t('watches.form.autoDownload')" />
        <BaseCheckbox v-model="enabled" :label="t('watches.form.enabled')" />
      </form>

      <section class="artists" :aria-label="t('watches.form.artists')">
        <h2>{{ t('watches.form.artists') }}</h2>
        <p v-if="fieldErrors.artist_ids" class="artists__error" role="alert">
          {{ fieldErrors.artist_ids }}
        </p>
        <p v-if="chosen.length === 0">{{ t('watches.form.noArtists') }}</p>
        <ol v-else class="artists__chosen">
          <li v-for="(artist, index) in chosen" :key="artist.id">
            <span>{{ artist.name }}</span>
            <BaseButton
              variant="secondary"
              :disabled="index === 0"
              :aria-label="t('watches.form.up', { name: artist.name })"
              @click="move(index, -1)"
            >
              ↑
            </BaseButton>
            <BaseButton
              variant="secondary"
              :disabled="index === chosen.length - 1"
              :aria-label="t('watches.form.down', { name: artist.name })"
              @click="move(index, 1)"
            >
              ↓
            </BaseButton>
            <BaseButton
              variant="secondary"
              :aria-label="t('watches.form.remove', { name: artist.name })"
              @click="chosen.splice(index, 1)"
            >
              ✕
            </BaseButton>
          </li>
        </ol>

        <form name="artist-search" class="artists__search" @submit.prevent="search">
          <BaseField
            v-model="query"
            type="search"
            :debounce="300"
            :label="t('watches.form.search')"
          />
          <BaseButton type="submit" variant="secondary">{{
            t('watches.form.searchButton')
          }}</BaseButton>
        </form>
        <p v-if="results && results.length === 0">{{ t('watches.form.noResults') }}</p>
        <ul v-else-if="results" class="artists__results">
          <li v-for="artist in results" :key="artist.id">
            <BaseButton variant="secondary" @click="add(artist)">
              {{ t('watches.form.add', { name: artist.name }) }}
            </BaseButton>
          </li>
        </ul>
      </section>
    </fieldset>

    <div class="watch-form__actions">
      <BaseButton type="submit" form="watch-form">{{ t('watches.form.save') }}</BaseButton>
      <RouterLink :to="id ? { name: 'watch', params: { id } } : { name: 'watches' }">
        {{ t('watches.form.cancel') }}
      </RouterLink>
    </div>
  </section>
</template>

<style scoped>
.watch-form,
form,
.artists {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  max-width: 40rem;
}
.artists__chosen,
.artists__results {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  margin: 0;
  padding: 0;
  list-style: none;
}
.artists__chosen li {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}
.artists__chosen span {
  flex: 1;
}
.artists__error {
  margin: 0;
  color: var(--color-danger);
}
.artists__search {
  flex-direction: row;
  align-items: flex-end;
}
.artists__search > :first-child {
  flex: 1;
}
.watch-form__fields {
  min-width: 0;
  margin: 0;
  padding: 0;
  border: 0;
}

.watch-form__actions {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}
.watch-form__actions a {
  display: inline-flex;
  align-items: center;
  min-height: var(--touch-target);
}
</style>
