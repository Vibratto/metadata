<script setup lang="ts">
import { useI18n } from 'vue-i18n'

import BaseButton from '../../components/BaseButton.vue'
import JobRunPanel from '../../components/JobRunPanel.vue'
import { useJobRun } from '../../composables/useJobRun'

/**
 * One run's detail. Mounted once per run, so closing it stops its polling.
 */
const props = defineProps<{ id: number }>()
const emit = defineEmits<{ close: [] }>()
const { t } = useI18n()
const job = useJobRun()
void job.follow(props.id)
</script>

<template>
  <section class="run">
    <header>
      <h2>{{ t('log.detailTitle', { id }) }}</h2>
      <BaseButton variant="secondary" @click="emit('close')">{{ t('ui.close') }}</BaseButton>
    </header>
    <JobRunPanel :job="job" />
  </section>
</template>

<style scoped>
.run {
  margin-bottom: var(--space-3);
  padding: var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
}
header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
}
h2 {
  margin: 0;
}
</style>
