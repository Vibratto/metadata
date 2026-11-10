<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import type { components } from '../../api/schema'
import BaseAlert from '../../components/BaseAlert.vue'
import BaseField from '../../components/BaseField.vue'
import FilterPanel from '../../components/FilterPanel.vue'
import ResponsiveList from '../../components/ResponsiveList.vue'
import { usePagedList } from '../../composables/usePagedList'
import { bindFilter } from './filter'
import LogPager from './LogPager.vue'
import LogSelect from './LogSelect.vue'

type TechnicalLog = components['schemas']['TechnicalLog']

const LEVELS = ['10', '20', '30', '40', '50']

/**
 * Technical logs (administrators only) filtered by minimum level, module, date, job and
 * text; the trace, if any, folds out under the message.
 */
const { t, te, locale } = useI18n()
const list = usePagedList<TechnicalLog>('/api/v1/activity/logs/', [
  'min_level',
  'module',
  'date_from',
  'date_to',
  'task',
])

const columns = computed(() => [
  { key: 'created_at', label: t('log.columns.date') },
  { key: 'level', label: t('log.columns.level') },
  { key: 'logger_name', label: t('log.columns.module') },
  { key: 'msg', label: t('log.columns.message') },
])
// NotSet (0) has no name of its own: the number is shown.
const levelLabel = (level: number) =>
  te(`log.level.${level}`) ? t(`log.level.${level}`) : String(level)
const levels = computed(() => LEVELS.map((value) => ({ value, label: levelLabel(Number(value)) })))
</script>

<template>
  <FilterPanel>
    <div class="log-filters">
      <LogSelect
        :label="t('log.filters.level')"
        :options="levels"
        v-bind="bindFilter(list, 'min_level')"
      />
      <BaseField :label="t('log.filters.module')" v-bind="bindFilter(list, 'module')" />
      <BaseField :label="t('log.filters.task')" type="number" v-bind="bindFilter(list, 'task')" />
      <BaseField
        :label="t('log.filters.search')"
        type="search"
        :debounce="300"
        v-bind="bindFilter(list, 'search')"
      />
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
      new Date(row.created_at).toLocaleString(locale)
    }}</template>
    <template #cell-level="{ row }">{{ levelLabel(row.level) }}</template>
    <template #cell-msg="{ row }">
      <div class="msg">
        <span>{{ row.msg }}</span>
        <details v-if="row.trace">
          <summary>{{ t('log.trace') }}</summary>
          <pre>{{ row.trace }}</pre>
        </details>
      </div>
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
.msg {
  min-width: 0;
  overflow-wrap: anywhere;
}
summary {
  display: flex;
  align-items: center;
  min-height: var(--touch-target);
  cursor: pointer;
}
pre {
  max-height: 16rem;
  margin: 0;
  overflow: auto;
  font-size: 0.875rem;
}
</style>
