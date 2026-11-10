<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'

import ActivityTab from './ActivityTab.vue'
import JobsTab from './JobsTab.vue'
import TechnicalTab from './TechnicalTab.vue'

/**
 * Log section with three tabs: activity, jobs and technical logs (administrators only).
 * The tab and its filters live in the URL.
 */
const { t } = useI18n()
const route = useRoute()

const panels = { activity: ActivityTab, jobs: JobsTab, technical: TechnicalTab }
type Tab = keyof typeof panels

const tabs: Tab[] = ['activity', 'jobs', 'technical']
// An unknown tab in the URL falls back to Activity instead of failing.
const tab = computed<Tab>(() => {
  const asked = route.query.tab as Tab
  return tabs.includes(asked) ? asked : 'activity'
})
</script>

<template>
  <section class="log">
    <h1>{{ t('log.title') }}</h1>
    <nav class="tabs segmented" :aria-label="t('log.tabs.label')">
      <!-- Only the query changes: RouterLink would mark them all active, so it is marked by hand. -->
      <RouterLink
        v-for="name in tabs"
        :key="name"
        :to="{ query: { tab: name } }"
        :aria-current="name === tab ? 'page' : undefined"
        replace
      >
        {{ t(`log.tabs.${name}`) }}
      </RouterLink>
    </nav>
    <component :is="panels[tab]" :key="tab" />
  </section>
</template>

<style scoped>
.log {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}
.tabs {
  align-self: flex-start;
  margin-bottom: var(--space-2);
}
@media (max-width: 599.98px) {
  .tabs {
    align-self: stretch;
  }
}
</style>
