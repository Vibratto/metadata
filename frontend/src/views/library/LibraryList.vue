<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import AppIcon from '../../components/AppIcon.vue'
import ActiveFilters, { type ActiveFilter } from '../../components/ActiveFilters.vue'
import BaseAlert from '../../components/BaseAlert.vue'
import BaseButton from '../../components/BaseButton.vue'
import BaseField from '../../components/BaseField.vue'
import BaseSelect, { type SelectOption } from '../../components/BaseSelect.vue'
import CoverArt from '../../components/CoverArt.vue'
import EntityFilter from '../../components/EntityFilter.vue'
import FilterPanel from '../../components/FilterPanel.vue'
import JobRunPanel from '../../components/JobRunPanel.vue'
import ResponsiveList from '../../components/ResponsiveList.vue'
import VideoPreviewDialog from '../../components/VideoPreviewDialog.vue'
import { useVideoPreview } from '../../composables/useVideoPreview'
import { entityName } from '../../composables/useEntityLabels'
import { useJobRun } from '../../composables/useJobRun'
import { usePagedList } from '../../composables/usePagedList'
import { audienceText } from '../../format'
import {
  type Artist,
  type Credit,
  type Item,
  SPECS,
  type Tab,
  apiPath,
  duration,
  label,
} from './kinds'

/**
 * One Library tab: paged list with the API's search, ordering and filters. Artist and album
 * filters are picked right here with a searchable selector; all live in the URL and show as
 * readable chips that can be removed one by one or all at once.
 */
const props = defineProps<{ tab: Tab }>()
const { t, locale } = useI18n()
const spec = SPECS[props.tab]
const kind = spec.kind
// Tracks: one row per recording, except inside an album, where all its tracks show.
const fixedQuery = (query: Record<string, string>): Record<string, string> => ({
  ...spec.fixed,
  ...(kind === 'tracks' && !query.album ? { one_per_recording: 'true' } : {}),
})
const list = usePagedList<Item>(apiPath(kind), spec.filters, fixedQuery)

// A related artist's discography is imported from its card; the list reloads when it is
// done, because the artist then leaves this tab for the Artists one.
const importJob = useJobRun()
const importing = ref<number | null>(null)
async function importDiscography(artist: Artist): Promise<void> {
  importing.value = artist.id
  await importJob.start('import', { artist_ids: [artist.ytmusic_id] })
}
watch(
  () => importJob.active,
  (active, was) => {
    if (was && !active) void list.reload()
  },
)
const { preview, showPreview, closePreview } = useVideoPreview()

// Editable copy of the simple filters: applied on submit, not on every keystroke.
const fieldKeys = spec.fields.map((f) => f.key)
const form = reactive<Record<string, string>>({})
const orderings = computed<SelectOption[]>(() => [
  { value: '', label: t('library.ordering.default') },
  ...spec.orderings.map((value) => ({
    value,
    label: t(`library.ordering.${value.replace(/^-(.*)/, '$1_desc')}`),
  })),
])
function sync(): void {
  for (const key of ['search', 'ordering', ...fieldKeys]) form[key] = list.query[key] ?? ''
}
sync()
watch(() => JSON.stringify(list.query), sync)

function apply(): void {
  list.update(
    Object.fromEntries(['search', 'ordering', ...fieldKeys].map((k) => [k, form[k] ?? ''])),
  )
}

const ids = (key: string) => (list.query[key] ?? '').split(',').filter(Boolean)
const setEntity = (key: 'artist' | 'album', value: string) =>
  // Albums by another artist would leave the list empty for no visible reason.
  list.update(
    key === 'artist' && spec.entities.includes('album')
      ? { artist: value, album: '' }
      : { [key]: value },
  )

const filterText = (key: string, value: string) => {
  const name = t(`library.filterLabels.${key}`)
  const field = spec.fields.find((f) => f.key === key)
  const shown = field?.type === 'select' ? t(`library.options.${value}`) : value
  return `${name}: ${shown}`
}

/** One chip per applied filter (one per id for artist and album filters). */
const active = computed<ActiveFilter[]>(() => [
  ...spec.entities.flatMap((key) =>
    ids(key).map((id) => ({
      id: `${key}:${id}`,
      text: `${t(`library.filterLabels.${key}`)}: ${entityName(key === 'artist' ? 'artists' : 'albums', id)}`,
    })),
  ),
  ...spec.fields
    .filter((f) => list.query[f.key])
    .map((f) => ({ id: f.key, text: filterText(f.key, list.query[f.key]!) })),
])

function removeFilter(id: string): void {
  const [key, value] = id.split(':') as [string, string | undefined]
  if (value === undefined) return list.update({ [key]: '' })
  list.update({
    [key]: ids(key)
      .filter((v) => v !== value)
      .join(','),
  })
}
function clearFilters(): void {
  list.update(Object.fromEntries(spec.filters.map((k) => [k, ''])))
}

// Search once typing stops; Enter and the button still apply every filter at once.
watch(() => form.search, apply)

const columns = computed(() => {
  const keys = {
    artists: ['name'],
    albums: ['title', 'artists', 'year'],
    tracks: ['title', 'artists', 'duration', 'downloaded', 'preview'],
  }[kind]
  return keys.map((key) => ({ key, label: t(`library.fields.${key}`) }))
})

/** Link that opens an artist's album list, skipping their page. */
const artistLink = (credit: Credit) => ({
  name: 'library',
  query: { tab: 'albums', artist: String(credit.id) },
})
const year = (row: Item) => ('year' in row ? (row.year ?? '') : '')
const audience = (row: Item) => ('subscribers' in row ? audienceText(row, locale.value, t) : '')
const suggested = (row: Item): Artist | null =>
  'suggest_import' in row && row.suggest_import ? row : null
/** Track and pending counts, when the API sends them. */
const counts = (row: Item): string => {
  const r = row as { track_count?: number; pending_count?: number }
  return r.track_count === undefined
    ? ''
    : t('library.counts', { tracks: r.track_count, pending: r.pending_count ?? 0 })
}
const image = (row: Item) =>
  'image_url' in row ? row.image_url : 'cover_url' in row ? row.cover_url : ''
const cell = (row: Item, key: string) => (row as Record<string, unknown>)[key]
</script>

<template>
  <div class="library-list">
    <FilterPanel>
      <form class="library-list__filters" @submit.prevent="apply">
        <BaseField
          v-model="form.search"
          type="search"
          :debounce="300"
          :label="t('library.filters.search')"
        />
        <BaseSelect
          v-model="form.ordering!"
          :label="t('library.filters.ordering')"
          :options="orderings"
        />
        <EntityFilter
          v-if="spec.entities.includes('artist')"
          :model-value="list.query.artist ?? ''"
          kind="artists"
          hide-chips
          :label="t('library.filterLabels.artist')"
          @update:model-value="setEntity('artist', $event)"
        />
        <EntityFilter
          v-if="spec.entities.includes('album')"
          :model-value="list.query.album ?? ''"
          kind="albums"
          hide-chips
          :artists="list.query.artist"
          :label="t('library.filterLabels.album')"
          @update:model-value="setEntity('album', $event)"
        />
        <template v-for="f in spec.fields" :key="f.key">
          <BaseSelect
            v-if="f.type === 'select'"
            v-model="form[f.key]!"
            :label="t(`library.filterLabels.${f.key}`)"
            :options="[
              { value: '', label: t('library.filters.any') },
              ...(f.options ?? []).map(([value, text]) => ({
                value,
                label: t(`library.options.${text}`),
              })),
            ]"
          />
          <BaseField
            v-else
            v-model="form[f.key]!"
            :type="f.type"
            :label="t(`library.filterLabels.${f.key}`)"
          />
        </template>
        <BaseButton type="submit">{{ t('library.filters.apply') }}</BaseButton>
      </form>
    </FilterPanel>

    <ActiveFilters :filters="active" @remove="removeFilter" @clear="clearFilters" />

    <p v-if="tab === 'related'" class="library-list__intro">{{ t('library.related.intro') }}</p>
    <JobRunPanel v-if="importing !== null" :job="importJob" />
    <BaseAlert v-if="list.error" variant="error">{{ list.error }}</BaseAlert>
    <p v-if="list.loading" role="status">{{ t('library.loading') }}</p>
    <template v-if="kind !== 'tracks'">
      <p v-if="list.items.length === 0 && !list.loading" class="library-list__empty">
        {{ t('ui.list.empty') }}
      </p>
      <ul v-else class="covers" :class="`covers--${kind}`">
        <li v-for="row in list.items" :key="row.id">
          <CoverArt :name="label(row)" :src="image(row)" :round="kind === 'artists'" />
          <RouterLink :to="{ name: 'library-item', params: { kind, id: row.id } }">
            {{ label(row) }}
          </RouterLink>
          <small v-if="tab !== 'related' && ('artists' in row || year(row) || counts(row))">
            <template v-if="'artists' in row">
              <template v-for="(c, i) in row.artists" :key="c.id">
                <template v-if="i">, </template>
                <RouterLink class="covers__artist" :to="artistLink(c)">{{ c.name }}</RouterLink>
              </template>
            </template>
            <template v-if="year(row)"> · {{ year(row) }}</template>
            <template v-if="counts(row)"> · {{ counts(row) }}</template>
          </small>
          <small v-if="audience(row)">{{ audience(row) }}</small>
          <BaseButton
            v-if="tab === 'related' && suggested(row)"
            variant="secondary"
            :disabled="importJob.active"
            @click="importDiscography(suggested(row)!)"
          >
            {{ t('library.related.import') }}
          </BaseButton>
        </li>
      </ul>
    </template>
    <ResponsiveList v-else :columns="columns" :rows="list.items" row-key="id">
      <template #cell-name="{ row }">
        <RouterLink :to="{ name: 'library-item', params: { kind, id: row.id } }">
          {{ label(row) }}
        </RouterLink>
      </template>
      <template #cell-title="{ row }">
        <CoverArt class="library-list__thumb" :name="label(row)" :src="image(row)" />
        <RouterLink :to="{ name: 'library-item', params: { kind, id: row.id } }">
          {{ label(row) }}
        </RouterLink>
        <span v-if="cell(row, 'also_on')" class="chip library-list__also">
          {{ t('library.also_on', { n: cell(row, 'also_on') as number }) }}
        </span>
      </template>
      <template #cell-artists="{ row }">
        <template v-for="(c, i) in cell(row, 'artists') as Credit[]" :key="c.id">
          <template v-if="i">, </template>
          <RouterLink :to="artistLink(c)">{{ c.name }}</RouterLink>
        </template>
      </template>
      <template #cell-duration="{ row }">
        {{ duration(cell(row, 'duration') as number | null) }}
      </template>
      <template #cell-preview="{ row }">
        <BaseButton
          variant="secondary"
          :aria-label="`${t('download.preview')}: ${label(row)}`"
          @click="showPreview({ id: row.id, title: label(row) })"
        >
          <AppIcon name="play" />{{ t('download.preview') }}
        </BaseButton>
      </template>
      <template #cell-downloaded="{ row }">
        <span class="chip" :class="{ 'chip--ok': cell(row, 'downloaded') }">{{
          cell(row, 'downloaded') ? t('library.yes') : t('library.no')
        }}</span>
      </template>
    </ResponsiveList>

    <VideoPreviewDialog :preview="preview" @close="closePreview" />

    <nav class="library-list__pages" :aria-label="t('library.pages')">
      <BaseButton
        variant="secondary"
        :disabled="!list.hasPrevious"
        @click="list.goTo(list.page - 1)"
      >
        {{ t('library.previous') }}
      </BaseButton>
      <span>{{ t('library.page', { page: list.page, count: list.count }) }}</span>
      <BaseButton variant="secondary" :disabled="!list.hasNext" @click="list.goTo(list.page + 1)">
        {{ t('library.next') }}
      </BaseButton>
    </nav>
  </div>
</template>

<style scoped>
.library-list__intro {
  margin: 0;
  color: var(--color-muted);
}
.library-list__thumb {
  --cover-size: 2.5rem;
  display: inline-grid;
  margin-inline-end: var(--space-2);
  vertical-align: middle;
}
.library-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}
.library-list :deep(.filters) {
  margin-bottom: 0;
}
.library-list__filters {
  display: grid;
  gap: var(--space-3);
}
.library-list__empty {
  padding: var(--space-5) var(--space-3);
  border: 1px dashed var(--color-border);
  border-radius: var(--radius-lg);
  color: var(--color-muted);
  text-align: center;
}
.library-list__pages {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
  color: var(--color-muted);
  font-size: 0.875rem;
}
/* Cover grid: the whole card leads to the item (the link stretches over it). */
.covers {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(9.5rem, 1fr));
  gap: var(--space-4) var(--space-3);
  margin: 0;
  padding: 0;
  list-style: none;
}
.covers li {
  position: relative;
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.covers .cover {
  --cover-size: 100%;
  width: 100%;
  margin-bottom: 0.625rem;
  border-radius: var(--radius);
  font-size: 2.25rem;
  transition: transform 0.2s ease;
}
.covers .cover--round {
  border-radius: 50%;
}
.covers li:hover .cover {
  transform: translateY(-2px);
}
.covers a {
  overflow: hidden;
  color: var(--color-text);
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.covers a::after {
  content: '';
  position: absolute;
  inset: 0;
}
.covers small {
  overflow: hidden;
  color: var(--color-muted);
  font-size: 0.8125rem;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.covers .covers__artist {
  position: relative;
  z-index: 1;
  display: inline;
  color: inherit;
  font-weight: inherit;
  text-decoration: underline;
}
.covers .covers__artist::after {
  content: none;
}
.covers--artists li {
  text-align: center;
}

@media (min-width: 600px) {
  .library-list__filters {
    grid-template-columns: repeat(2, 1fr);
    align-items: end;
  }
  .covers {
    grid-template-columns: repeat(auto-fill, minmax(11rem, 1fr));
  }
}

@media (min-width: 1024px) {
  .library-list__filters {
    grid-template-columns: repeat(auto-fit, minmax(11rem, 1fr));
  }
}
</style>
