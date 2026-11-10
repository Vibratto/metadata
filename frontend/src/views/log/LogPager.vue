<script setup lang="ts">
import { useI18n } from 'vue-i18n'

import BaseButton from '../../components/BaseButton.vue'

/**
 * Previous and next buttons for a `usePagedList` list.
 */
defineProps<{
  list: {
    page: number
    count: number
    hasNext: boolean
    hasPrevious: boolean
    goTo(n: number): void
  }
}>()
const { t } = useI18n()
</script>

<template>
  <nav class="pager">
    <BaseButton variant="secondary" :disabled="!list.hasPrevious" @click="list.goTo(list.page - 1)">
      {{ t('log.previous') }}
    </BaseButton>
    <span>{{ t('log.page', { page: list.page, count: list.count }) }}</span>
    <BaseButton variant="secondary" :disabled="!list.hasNext" @click="list.goTo(list.page + 1)">
      {{ t('log.next') }}
    </BaseButton>
  </nav>
</template>

<style scoped>
.pager {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
  margin-top: var(--space-3);
}
</style>
