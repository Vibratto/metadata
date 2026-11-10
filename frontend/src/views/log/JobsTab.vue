<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import type { components } from '../../api/schema'
import BaseAlert from '../../components/BaseAlert.vue'
import BaseField from '../../components/BaseField.vue'
import FilterPanel from '../../components/FilterPanel.vue'
import ResponsiveList from '../../components/ResponsiveList.vue'
import { usePagedList } from '../../composables/usePagedList'
import { bindFilter } from './filter'
import JobRunDetail from './JobRunDetail.vue'
import LogPager from './LogPager.vue'
import LogSelect from './LogSelect.vue'

type JobRun = components['schemas']['JobRun']

const KINDS = ['import', 'download', 'maintenance', 'watch_check']
const STATUSES: JobRun['status'][] = [
  'pending',
  'running',
  'stopping',
  'stopped',
  'succeeded',
  'failed',
  'interrupted',
]

/**
 * Job runs filtered by kind, status and start date. The open run lives in `?run=`, outside
 * the filters, so opening or closing it does not reload the list.
 */
const { t, te, locale } = useI18n()
const route = useRoute()
const router = useRouter()
const list = usePagedList<JobRun>('/api/v1/jobs/runs/', [
  'kind',
  'status',
  'started_after',
  'started_before',
])

const columns = computed(() => [
  { key: 'id', label: t('log.columns.id') },
  { key: 'kind', label: t('log.columns.kind') },
  { key: 'status', label: t('log.columns.status') },
  { key: 'user', label: t('log.columns.user') },
  { key: 'started_at', label: t('log.columns.started') },
  { key: 'progress', label: t('log.columns.progress') },
])
// Kinds registered later (by other views) are shown with their code.
const kindLabel = (kind: string) => (te(`log.kind.${kind}`) ? t(`log.kind.${kind}`) : kind)
const kinds = computed(() => KINDS.map((value) => ({ value, label: kindLabel(value) })))
const statuses = computed(() =>
  STATUSES.map((value) => ({ value, label: t(`ui.job.status.${value}`) })),
)

const openRun = computed(() => Number(route.query.run) || 0)
function close(): void {
  const query = { ...route.query }
  delete query.run
  void router.replace({ query })
}
</script>

<template>
  <JobRunDetail v-if="openRun" :id="openRun" :key="openRun" @close="close" />
  <FilterPanel>
    <div class="log-filters">
      <LogSelect
        :label="t('log.filters.kind')"
        :options="kinds"
        v-bind="bindFilter(list, 'kind')"
      />
      <LogSelect
        :label="t('log.filters.status')"
        :options="statuses"
        v-bind="bindFilter(list, 'status')"
      />
      <BaseField
        :label="t('log.filters.dateFrom')"
        type="datetime-local"
        v-bind="bindFilter(list, 'started_after')"
      />
      <BaseField
        :label="t('log.filters.dateTo')"
        type="datetime-local"
        v-bind="bindFilter(list, 'started_before')"
      />
    </div>
  </FilterPanel>
  <BaseAlert v-if="list.error" variant="error">{{ list.error }}</BaseAlert>
  <ResponsiveList :columns="columns" :rows="list.items" row-key="id">
    <template #cell-id="{ row }">
      <RouterLink
        class="detail"
        :to="{ query: { ...route.query, run: row.id } }"
        :aria-label="t('log.detailTitle', { id: row.id })"
        replace
      >
        {{ row.id }}
      </RouterLink>
    </template>
    <template #cell-kind="{ row }">{{ kindLabel(row.kind) }}</template>
    <template #cell-status="{ row }">{{ t(`ui.job.status.${row.status}`) }}</template>
    <template #cell-started_at="{ row }">{{
      new Date(row.started_at).toLocaleString(locale)
    }}</template>
    <template #cell-progress="{ row }">{{
      row.total > 0 ? `${row.done} / ${row.total}` : ''
    }}</template>
  </ResponsiveList>
  <LogPager :list="list" />
</template>

<style scoped>
.log-filters {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(12rem, 1fr));
  gap: var(--space-3);
}
.detail {
  display: inline-flex;
  align-items: center;
  min-width: var(--touch-target);
  min-height: var(--touch-target);
}
</style>
