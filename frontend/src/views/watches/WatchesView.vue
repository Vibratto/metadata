<script setup lang="ts">
import { computed, reactive, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import type { components } from '../../api/schema'
import AppIcon from '../../components/AppIcon.vue'
import BaseAlert from '../../components/BaseAlert.vue'
import ActiveFilters from '../../components/ActiveFilters.vue'
import BaseButton from '../../components/BaseButton.vue'
import BaseField from '../../components/BaseField.vue'
import EntityFilter from '../../components/EntityFilter.vue'
import FilterPanel from '../../components/FilterPanel.vue'
import { entityName } from '../../composables/useEntityLabels'
import CoverArt from '../../components/CoverArt.vue'
import { usePagedList } from '../../composables/usePagedList'

type Watch = components['schemas']['Watch']

/**
 * List of new-release watches with their status; each one opens its detail.
 */
const { t } = useI18n()
const list = usePagedList<Watch>('/api/v1/watches/', ['enabled', 'auto_download', 'artist'])

// Editable copy of search, ordering and states: applied on submit, not on every keystroke.
const FIELDS = ['search', 'ordering', 'enabled', 'auto_download'] as const
const form = reactive<Record<string, string>>({})
function sync(): void {
  for (const key of FIELDS) form[key] = list.query[key] ?? ''
}
sync()
watch(() => JSON.stringify(list.query), sync)
const apply = () => list.update(Object.fromEntries(FIELDS.map((k) => [k, form[k] ?? ''])))

const valueText = (key: 'enabled' | 'auto_download', on: boolean) =>
  t(
    key === 'enabled'
      ? on
        ? 'watches.enabled'
        : 'watches.disabled'
      : on
        ? 'library.yes'
        : 'library.no',
  )
const ids = () => (list.query.artist ?? '').split(',').filter(Boolean)
const active = computed(() => [
  ...ids().map((id) => ({
    id: `artist:${id}`,
    text: `${t('watches.filters.artist')}: ${entityName('artists', id)}`,
  })),
  ...(['enabled', 'auto_download'] as const)
    .filter((k) => list.query[k])
    .map((k) => ({
      id: k,
      text: `${t(`watches.filters.${k}`)}: ${valueText(k, list.query[k] === 'true')}`,
    })),
])
function removeFilter(id: string): void {
  const [key, value] = id.split(':') as [string, string | undefined]
  list.update({
    [key]:
      value === undefined
        ? ''
        : ids()
            .filter((v) => v !== value)
            .join(','),
  })
}
const clearFilters = () => list.update({ enabled: '', auto_download: '', artist: '' })

/** State of a watch: enabled or paused and, if set, automatic download. */
const status = (w: Watch) => [
  t(w.enabled ? 'watches.enabled' : 'watches.disabled'),
  ...(w.auto_download ? [t('watches.autoDownload')] : []),
]
</script>

<template>
  <section class="watches">
    <header class="page-head">
      <div>
        <h1>{{ t('watches.title') }}</h1>
        <p class="page-head__sub">{{ t('watches.intro') }}</p>
      </div>
      <RouterLink class="btn btn--primary" :to="{ name: 'watches-new' }">
        <AppIcon name="plus" />{{ t('watches.new') }}
      </RouterLink>
    </header>
    <FilterPanel>
      <form class="watches__filters" @submit.prevent="apply">
        <BaseField v-model="form.search!" type="search" :label="t('watches.filters.search')" />
        <label class="watches__select">
          {{ t('watches.filters.ordering') }}
          <select v-model="form.ordering">
            <option value="">{{ t('watches.filters.default') }}</option>
            <option value="name">{{ t('watches.filters.name') }}</option>
            <option value="-name">{{ t('watches.filters.name_desc') }}</option>
            <option value="next_run_at">{{ t('watches.filters.next_run_at') }}</option>
          </select>
        </label>
        <label class="watches__select">
          {{ t('watches.filters.enabled') }}
          <select v-model="form.enabled">
            <option value="">{{ t('library.filters.any') }}</option>
            <option value="true">{{ t('watches.enabled') }}</option>
            <option value="false">{{ t('watches.disabled') }}</option>
          </select>
        </label>
        <label class="watches__select">
          {{ t('watches.filters.auto_download') }}
          <select v-model="form.auto_download">
            <option value="">{{ t('library.filters.any') }}</option>
            <option value="true">{{ t('library.yes') }}</option>
            <option value="false">{{ t('library.no') }}</option>
          </select>
        </label>
        <EntityFilter
          :model-value="list.query.artist ?? ''"
          kind="artists"
          hide-chips
          :label="t('watches.filters.artist')"
          @update:model-value="list.update({ artist: $event })"
        />
        <BaseButton type="submit">{{ t('library.filters.apply') }}</BaseButton>
      </form>
    </FilterPanel>
    <ActiveFilters :filters="active" @remove="removeFilter" @clear="clearFilters" />
    <BaseAlert v-if="list.error" variant="error">{{ list.error }}</BaseAlert>
    <template v-if="!list.loading">
      <p v-if="list.items.length === 0" class="watches__empty">{{ t('ui.list.empty') }}</p>
      <ul v-else class="watches__list">
        <li v-for="w in list.items" :key="w.id" class="watch-card card">
          <div class="watch-card__head">
            <h2>
              <RouterLink :to="{ name: 'watch', params: { id: w.id } }">{{ w.name }}</RouterLink>
            </h2>
            <span class="chip" :class="{ 'chip--ok': w.enabled }">{{ status(w).join(' · ') }}</span>
          </div>
          <p class="watch-card__every">
            <AppIcon name="clock" />{{
              t('watches.hours', { n: w.interval_hours }, Number(w.interval_hours))
            }}
          </p>
          <div v-if="w.artists.length" class="watch-card__artists">
            <span class="watch-card__faces" aria-hidden="true">
              <CoverArt v-for="a in w.artists.slice(0, 5)" :key="a.id" :name="a.name" round />
            </span>
            <span>{{ w.artists.map((a) => a.name).join(', ') }}</span>
          </div>
        </li>
      </ul>
    </template>
    <nav v-if="list.hasPrevious || list.hasNext" class="watches__pages">
      <BaseButton
        variant="secondary"
        :disabled="!list.hasPrevious"
        @click="list.goTo(list.page - 1)"
      >
        {{ t('watches.previous') }}
      </BaseButton>
      <BaseButton variant="secondary" :disabled="!list.hasNext" @click="list.goTo(list.page + 1)">
        {{ t('watches.next') }}
      </BaseButton>
    </nav>
  </section>
</template>

<style scoped>
.watches__filters {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 11rem), 1fr));
  gap: var(--space-3);
  align-items: end;
}
.watches__select {
  display: flex;
  flex-direction: column;
  gap: 0.4375rem;
}
.watches {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}
.watches__empty {
  padding: var(--space-5) var(--space-3);
  border: 1px dashed var(--color-border);
  border-radius: var(--radius-lg);
  color: var(--color-muted);
  text-align: center;
}
.watches__list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(18rem, 1fr));
  gap: var(--space-3);
  margin: 0;
  padding: 0;
  list-style: none;
}
/* The whole card leads to the detail: the name link stretches over it. */
.watch-card {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  padding: 1.25rem;
  transition: border-color 0.15s;
}
.watch-card:hover {
  border-color: var(--color-faint);
}
.watch-card__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-2);
}
.watch-card a {
  color: var(--color-text);
}
.watch-card a::after {
  content: '';
  position: absolute;
  inset: 0;
}
.watch-card__every {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  color: var(--color-muted);
  font-size: 0.875rem;
}
.watch-card__every .icon {
  width: 1rem;
  height: 1rem;
}
.watch-card__artists {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding-top: 0.75rem;
  border-top: 1px solid var(--color-border);
  color: var(--color-muted);
  font-size: 0.875rem;
}
.watch-card__faces {
  display: flex;
  flex: none;
}
.watch-card__faces .cover {
  --cover-size: 2rem;
  border: 2px solid var(--color-surface);
}
.watch-card__faces .cover + .cover {
  margin-left: -0.625rem;
}
.watches__pages {
  display: flex;
  justify-content: space-between;
}
</style>
