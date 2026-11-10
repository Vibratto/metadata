<script setup lang="ts">
import { useI18n } from 'vue-i18n'

import type { JobRunHandle } from '../composables/useJobRun'
import { progressOf } from '../stores/jobs'
import BaseAlert from './BaseAlert.vue'
import BaseButton from './BaseButton.vue'
import ProgressBar from './ProgressBar.vue'

/**
 * Status, progress and log of a job followed with `useJobRun`, plus a stop button while
 * active. Renders nothing until there is a job or an error.
 */
defineProps<{ job: JobRunHandle }>()
const { t } = useI18n()
</script>

<template>
  <section v-if="job.run || job.error" class="job">
    <BaseAlert v-if="job.error" variant="error">{{ job.error }}</BaseAlert>
    <template v-if="job.run">
      <p class="job__status">
        <span>{{ t(`ui.job.status.${job.run.status}`) }}</span>
        <span v-if="job.run.total > 0">{{ job.run.done }} / {{ job.run.total }}</span>
      </p>
      <ProgressBar :value="progressOf(job.run)" :label="t('ui.job.progress')" />
      <p v-if="job.run.current" class="job__current">{{ job.run.current }}</p>
      <ol v-if="job.lines.length" class="job__lines" role="log" :aria-label="t('ui.job.lines')">
        <li
          v-for="line in job.lines"
          :key="line.position"
          :class="`job__line job__line--${line.level}`"
        >
          {{ line.message }}
        </li>
      </ol>
      <BaseButton
        v-if="job.active"
        variant="danger"
        :disabled="job.run.status === 'stopping'"
        @click="job.stop()"
      >
        {{ t('ui.job.stop') }}
      </BaseButton>
    </template>
  </section>
</template>

<style scoped>
.job {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}
.job__status {
  display: flex;
  justify-content: space-between;
  margin: 0;
  font-weight: 600;
}
.job__current {
  margin: 0;
  color: var(--color-muted);
}
.job__lines {
  max-height: 16rem;
  margin: 0;
  padding: var(--space-2) var(--space-3);
  overflow-y: auto;
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  background: var(--color-surface);
  font-family: ui-monospace, monospace;
  font-size: 0.875rem;
  list-style: none;
}
.job__line--warning {
  color: var(--color-warning);
}
.job__line--error {
  color: var(--color-danger);
}
</style>
