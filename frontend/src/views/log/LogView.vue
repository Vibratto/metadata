<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

import type { components } from '../../api/schema'
import BaseAlert from '../../components/BaseAlert.vue'
import BaseField from '../../components/BaseField.vue'
import FilterPanel from '../../components/FilterPanel.vue'
import ResponsiveList from '../../components/ResponsiveList.vue'
import { usePagedList } from '../../composables/usePagedList'
import { bindFilter } from './filter'
import LogPager from './LogPager.vue'
import { activitySentence } from './sentence'

type ActivityLog = components['schemas']['ActivityLog']

/** Library tab where the history of each library type lives. */
const LIBRARY_TABS: Record<string, string> = {
  'catalog.artist': 'artists',
  'catalog.album': 'albums',
  'catalog.track': 'tracks',
}

/**
 * Activity: what was done in the application, newest first, told in plain sentences. The
 * dates filtered by live in the URL.
 */
const i18n = useI18n()
const { t, locale } = i18n
const router = useRouter()
const list = usePagedList<ActivityLog>('/api/v1/activity/entries/', ['date_from', 'date_to'])

const columns = computed(() => [
  { key: 'created_at', label: t('log.columns.date') },
  { key: 'action', label: t('log.columns.action') },
  { key: 'object', label: t('log.columns.object') },
])
// The Library is another view: until its route exists, no link is made.
const hasLibrary = router.hasRoute('library')
</script>

<template>
  <section class="log">
    <h1>{{ t('log.title') }}</h1>
    <FilterPanel>
      <div class="log-filters">
        <BaseField
          :label="t('log.filters.dateFrom')"
          type="date"
          v-bind="bindFilter(list, 'date_from')"
        />
        <BaseField
          :label="t('log.filters.dateTo')"
          type="date"
          v-bind="bindFilter(list, 'date_to')"
        />
      </div>
    </FilterPanel>
    <BaseAlert v-if="list.error" variant="error">{{ list.error }}</BaseAlert>
    <ResponsiveList :columns="columns" :rows="list.items" row-key="id">
      <template #cell-created_at="{ row }">{{
        new Date(row.created_at).toLocaleString(locale, { dateStyle: 'medium', timeStyle: 'short' })
      }}</template>
      <template #cell-action="{ row }">{{ activitySentence(row, i18n) }}</template>
      <template #cell-object="{ row }">
        <RouterLink
          v-if="hasLibrary && LIBRARY_TABS[row.object_type]"
          class="history"
          :to="{
            name: 'library',
            query: { tab: LIBRARY_TABS[row.object_type], id: row.object_id, panel: 'history' },
          }"
        >
          {{ t('log.history') }}
        </RouterLink>
      </template>
    </ResponsiveList>
    <LogPager :list="list" />
  </section>
</template>

<style scoped>
.log {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}
.log-filters {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(12rem, 1fr));
  gap: var(--space-3);
}
.history {
  display: inline-flex;
  align-items: center;
  min-height: var(--touch-target);
}
</style>
