<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { api } from '../api/client'
import { errorText } from '../api/errors'
import type { components } from '../api/schema'
import AppIcon from '../components/AppIcon.vue'
import BaseAlert from '../components/BaseAlert.vue'
import BaseButton from '../components/BaseButton.vue'
import BaseCheckbox from '../components/BaseCheckbox.vue'
import BaseField from '../components/BaseField.vue'
import VideoPreviewDialog from '../components/VideoPreviewDialog.vue'
import EntityFilter from '../components/EntityFilter.vue'
import FilterPanel from '../components/FilterPanel.vue'
import JobRunPanel from '../components/JobRunPanel.vue'
import ResponsiveList from '../components/ResponsiveList.vue'
import { useJobRun } from '../composables/useJobRun'
import { bindFilter } from './log/filter'
import { useVideoPreview } from '../composables/useVideoPreview'
import { usePagedList, type Page } from '../composables/usePagedList'

type Track = components['schemas']['Track']
type JobRun = components['schemas']['JobRun']

/**
 * Download: pending tracks filtered by artist and album, to download the selected ones or all.
 * Only one download can run at a time, so a running one is followed instead.
 */
const { t } = useI18n()
const list = usePagedList<Track>('/api/v1/catalog/tracks/', [
  'downloaded',
  'artist',
  'album',
  'search',
])
const job = useJobRun()

// The selection lives outside the page: it survives paging and filter changes.
const selected = reactive(new Set<number>())
const error = ref('')
const columns = computed(() => [
  { key: 'title', label: t('download.columns.title') },
  { key: 'artists', label: t('download.columns.artists') },
  { key: 'preview', label: t('download.columns.preview') },
])

const { preview, showPreview, closePreview } = useVideoPreview()

/** Follows the latest download if still active; there is at most one, always the newest. */
async function followActive(): Promise<void> {
  try {
    const [latest] = (await api<Page<JobRun>>('/api/v1/jobs/runs/?kind=download')).results
    if (latest && ['pending', 'running', 'stopping'].includes(latest.status)) {
      await job.follow(latest.id)
    }
  } catch (e) {
    error.value = errorText(e, t)
  }
}

async function launch(params: Record<string, unknown>): Promise<void> {
  // If it fails because another one just started (409), follow that one instead of the error.
  if (!(await job.start('download', params))) await followActive()
}

function toggle(id: number, on: boolean): void {
  if (on) selected.add(id)
  else selected.delete(id)
}

function setArtist(value: string): void {
  // An album by another artist would leave the list empty for no visible reason.
  list.update({ artist: value, album: '' })
}

// When a download ends the pending tracks change: reload and clear the selection.
watch(
  () => job.active,
  (now, before) => {
    if (before && !now) {
      selected.clear()
      void list.reload()
    }
  },
)

onMounted(async () => {
  void followActive()
})
</script>

<template>
  <section class="download">
    <header class="page-head">
      <div>
        <h1>{{ t('download.title') }}</h1>
        <p class="page-head__sub">{{ t('download.pending', { count: list.count }) }}</p>
      </div>
      <BaseButton
        variant="secondary"
        :disabled="job.active || list.count === 0"
        @click="launch({ all_pending: true })"
      >
        {{ t('download.all') }}
      </BaseButton>
    </header>
    <BaseAlert v-if="error" variant="error">{{ error }}</BaseAlert>

    <FilterPanel>
      <div class="dl-filters">
        <BaseField
          :label="t('download.filters.search')"
          type="search"
          :debounce="300"
          v-bind="bindFilter(list, 'search')"
        />
        <EntityFilter
          :model-value="list.query.artist ?? ''"
          kind="artists"
          :label="t('download.filters.artist')"
          @update:model-value="setArtist"
        />
        <EntityFilter
          :model-value="list.query.album ?? ''"
          kind="albums"
          :artists="list.query.artist"
          :label="t('download.filters.album')"
          @update:model-value="list.update({ album: $event })"
        />
      </div>
    </FilterPanel>

    <BaseAlert v-if="job.active" variant="info">{{ t('download.running') }}</BaseAlert>
    <JobRunPanel :job="job" />

    <VideoPreviewDialog :preview="preview" @close="closePreview" />

    <BaseAlert v-if="list.error" variant="error">{{ list.error }}</BaseAlert>
    <ResponsiveList :columns="columns" :rows="list.items" row-key="id">
      <template #cell-title="{ row }">
        <BaseCheckbox
          :label="row.title"
          :model-value="selected.has(row.id)"
          @update:model-value="toggle(row.id, $event)"
        />
        <span v-if="row.copyable" class="chip chip--ok download__copy">
          {{ t('download.copy') }}
        </span>
      </template>
      <template #cell-artists="{ row }">
        {{ row.artists.map((a) => a.name).join(', ') }}
      </template>
      <template #cell-preview="{ row }">
        <BaseButton variant="secondary" @click="showPreview(row)">
          <AppIcon name="play" />{{ t('download.preview') }}
        </BaseButton>
      </template>
    </ResponsiveList>

    <nav v-if="list.hasPrevious || list.hasNext" class="pages">
      <BaseButton
        variant="secondary"
        :disabled="!list.hasPrevious"
        @click="list.goTo(list.page - 1)"
      >
        {{ t('download.previous') }}
      </BaseButton>
      <span>{{ t('download.page', { page: list.page }) }}</span>
      <BaseButton variant="secondary" :disabled="!list.hasNext" @click="list.goTo(list.page + 1)">
        {{ t('download.next') }}
      </BaseButton>
    </nav>

    <!-- Sticky bar with the download of the selection: always at hand while scrolling the list. -->
    <div class="actions" :class="{ 'action-bar': selected.size }">
      <span v-if="selected.size">{{
        t('download.selected', { count: selected.size }, selected.size)
      }}</span>
      <BaseButton
        :variant="selected.size ? 'accent' : 'primary'"
        :disabled="job.active || selected.size === 0"
        @click="launch({ track_ids: [...selected].sort((a, b) => a - b) })"
      >
        <AppIcon name="download" />{{ t('download.chosen', { count: selected.size }) }}
      </BaseButton>
    </div>
  </section>
</template>

<style scoped>
.download {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}
.download .page-head {
  margin-bottom: var(--space-1);
}
.dl-filters {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}
.dl-filters label {
  display: flex;
  flex-direction: column;
  gap: 0.4375rem;
}
.actions {
  display: flex;
  justify-content: flex-end;
}
.actions.action-bar {
  justify-content: space-between;
}
.pages {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
  color: var(--color-muted);
}

@media (min-width: 600px) {
  .dl-filters {
    flex-direction: row;
  }
  .dl-filters label {
    flex: 0 1 16rem;
  }
}
</style>
