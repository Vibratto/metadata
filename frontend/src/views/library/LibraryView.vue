<script setup lang="ts">
import { computed, provide, reactive } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'

import LibraryList from './LibraryList.vue'
import { TABS, type Tab } from './kinds'
import { TRACK_SELECTION } from './useTrackDownloads'

/**
 * Library: one tab per kind of item, plus the related artists saved as profiles. The tab
 * lives in the URL (`tab`) next to the filters, so a link opens the same filtered list.
 */
const { t } = useI18n()
const route = useRoute()
const tab = computed<Tab>(() => TABS.find((k) => k === route.query.tab) ?? 'artists')
// Tracks ticked for download: kept here so a search, which mounts a new list, keeps them.
provide(TRACK_SELECTION, reactive(new Set<number>()))
</script>

<template>
  <section class="library">
    <h1>{{ t('library.title') }}</h1>
    <nav class="segmented library__tabs" :aria-label="t('library.tabs')">
      <RouterLink
        v-for="k in TABS"
        :key="k"
        :to="{ name: 'library', query: { tab: k } }"
        :aria-current="k === tab ? 'page' : undefined"
      >
        {{ t(`library.kind.${k}`) }}
      </RouterLink>
    </nav>
    <!-- One list per tab: switching mounts a fresh one with its own API path. A search
         remounts it too, so the global search can fill in the field. -->
    <LibraryList :key="`${tab}-${route.query.search ?? ''}`" :tab="tab" />
  </section>
</template>

<style scoped>
.library {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}
.library__tabs {
  align-self: flex-start;
}
@media (max-width: 599.98px) {
  .library__tabs {
    align-self: stretch;
  }
}
</style>
