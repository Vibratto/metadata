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
import LogSelect from './LogSelect.vue'

type ActivityLog = components['schemas']['ActivityLog']

/** Library tab where the history of each library type lives. */
const LIBRARY_TABS: Record<string, string> = {
  'catalog.artist': 'artists',
  'catalog.album': 'albums',
  'catalog.track': 'tracks',
}
const OBJECT_TYPES = [
  ...Object.keys(LIBRARY_TABS),
  'jobs.jobrun',
  'watches.watch',
  'proxies.proxy',
  'auth.user',
]

/**
 * Activity history filtered by date, user, action and object.
 */
const { t, te, locale } = useI18n()
const router = useRouter()
const list = usePagedList<ActivityLog>('/api/v1/activity/entries/', [
  'date_from',
  'date_to',
  'username',
  'action',
  'object_type',
])

const columns = computed(() => [
  { key: 'created_at', label: t('log.columns.date') },
  { key: 'username', label: t('log.columns.user') },
  { key: 'action', label: t('log.columns.action') },
  { key: 'object', label: t('log.columns.object') },
])
const typeLabel = (type: string) =>
  te(`log.objectType.${type}`) ? t(`log.objectType.${type}`) : type
const types = computed(() => OBJECT_TYPES.map((value) => ({ value, label: typeLabel(value) })))
// The Library is another view: until its route exists, no link is made.
const hasLibrary = router.hasRoute('library')
</script>

<template>
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
      <BaseField :label="t('log.filters.username')" v-bind="bindFilter(list, 'username')" />
      <BaseField :label="t('log.filters.action')" v-bind="bindFilter(list, 'action')" />
      <LogSelect
        :label="t('log.filters.objectType')"
        :options="types"
        v-bind="bindFilter(list, 'object_type')"
      />
    </div>
  </FilterPanel>
  <BaseAlert v-if="list.error" variant="error">{{ list.error }}</BaseAlert>
  <ResponsiveList :columns="columns" :rows="list.items" row-key="id">
    <template #cell-created_at="{ row }">{{
      new Date(row.created_at).toLocaleString(locale)
    }}</template>
    <template #cell-username="{ row }">{{ row.username || t('log.system') }}</template>
    <template #cell-object="{ row }">
      <template v-if="row.object_type">
        {{ t('log.object', { type: typeLabel(row.object_type), id: row.object_id }) }}
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
    </template>
  </ResponsiveList>
  <LogPager :list="list" />
</template>

<style scoped>
.log-filters {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(12rem, 1fr));
  gap: var(--space-3);
}
.history {
  display: inline-flex;
  align-items: center;
  min-height: var(--touch-target);
  margin-left: var(--space-2);
}
</style>
