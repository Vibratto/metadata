<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'

import { useJobsStore } from '../stores/jobs'

/** How often, in milliseconds, running jobs are checked. */
const POLL_MS = 15000

/**
 * Running-jobs indicator, visible from every view; links to the dashboard, which lists
 * them. Hidden when
 * there are none. A failed check just hides it: the views that need jobs show their own error.
 */
const { t } = useI18n()
const jobs = useJobsStore()
let timer: ReturnType<typeof setInterval> | undefined

const refresh = () => jobs.refresh().catch(() => undefined)

onMounted(() => {
  void refresh()
  timer = setInterval(() => void refresh(), POLL_MS)
})
onUnmounted(() => clearInterval(timer))
</script>

<template>
  <RouterLink v-if="jobs.active.length" class="jobs-indicator" :to="{ name: 'dashboard' }">
    <span class="jobs-indicator__pulse" aria-hidden="true"></span>
    <span class="jobs-indicator__text">{{
      t('jobsIndicator.count', { n: jobs.active.length }, jobs.active.length)
    }}</span>
  </RouterLink>
</template>

<style scoped>
.jobs-indicator {
  display: inline-flex;
  align-items: center;
  gap: 0.625rem;
  min-height: 2.5rem;
  padding: 0 0.875rem 0 0.75rem;
  border: 1px solid var(--color-border);
  border-radius: 999px;
  background: var(--color-surface);
  color: var(--color-text);
  font-size: 0.875rem;
  font-weight: 550;
  white-space: nowrap;
}
.jobs-indicator:hover {
  text-decoration: none;
  border-color: var(--color-accent);
}
.jobs-indicator__pulse {
  width: 0.5rem;
  height: 0.5rem;
  border-radius: 50%;
  background: var(--color-accent-strong);
  box-shadow: 0 0 0 4px var(--color-accent-soft);
  animation: pulse 1.6s ease-in-out infinite;
}
@keyframes pulse {
  50% {
    box-shadow: 0 0 0 7px var(--color-accent-soft);
  }
}
@media (prefers-reduced-motion: reduce) {
  .jobs-indicator__pulse {
    animation: none;
  }
}
/* On mobile only the dot: the text is left for screen readers. */
@media (max-width: 599.98px) {
  .jobs-indicator {
    padding: 0 0.75rem;
  }
  .jobs-indicator__text {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip-path: inset(50%);
  }
}
</style>
