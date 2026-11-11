<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import type { JobRunHandle } from '../composables/useJobRun'
import { progressOf } from '../stores/jobs'
import BaseAlert from './BaseAlert.vue'
import BaseButton from './BaseButton.vue'
import ProgressBar from './ProgressBar.vue'

/** Something the job could not do, as the server words it for the user. */
interface Problem {
  item: string
  reason: string
}

/**
 * Status and progress of a job followed with `useJobRun`, a stop button while it is active
 * and, once it closes, what it could not do. Renders nothing until there is a job or an error.
 */
const props = defineProps<{ job: JobRunHandle }>()
const { t } = useI18n()

const summary = computed(() => (props.job.run?.summary ?? {}) as Record<string, unknown>)
const failure = computed(() => (summary.value.error as string | undefined) ?? '')
const problems = computed(() => (summary.value.problems as Problem[] | undefined) ?? [])
const omitted = computed(() => (summary.value.problems_omitted as number | undefined) ?? 0)
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
      <p v-if="job.run.current" class="job__current">
        {{ t('ui.job.current', { item: job.run.current }) }}
      </p>
      <BaseAlert v-if="failure" variant="error">{{ failure }}</BaseAlert>
      <div v-if="problems.length" class="job__problems">
        <h3>{{ t('ui.job.problems', { count: problems.length + omitted }) }}</h3>
        <ul>
          <li v-for="(problem, index) in problems" :key="index">
            <strong>{{ problem.item }}</strong> — {{ problem.reason }}
          </li>
          <li v-if="omitted" class="job__more">{{ t('ui.job.more', { count: omitted }) }}</li>
        </ul>
      </div>
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
  overflow-wrap: anywhere;
}
.job__problems {
  padding: var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  background: var(--color-surface);
}
.job__problems h3 {
  margin: 0 0 var(--space-2);
  font-size: 1rem;
}
.job__problems ul {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  max-height: 16rem;
  margin: 0;
  padding-left: var(--space-4);
  overflow-y: auto;
  overflow-wrap: anywhere;
}
.job__more {
  color: var(--color-muted);
  list-style: none;
}
</style>
