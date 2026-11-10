<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'

import { api } from '../api/client'
import { errorText } from '../api/errors'
import type { components } from '../api/schema'
import AppIcon from '../components/AppIcon.vue'
import BaseAlert from '../components/BaseAlert.vue'
import ProgressBar from '../components/ProgressBar.vue'
import { progressOf, useJobsStore } from '../stores/jobs'
import { useSessionStore } from '../stores/session'

type ActivityLog = components['schemas']['ActivityLog']

type LibrarySummary = components['schemas']['LibrarySummary']

/** How often, in milliseconds, jobs refresh while the dashboard is open. */
const POLL_MS = 5000
/** Actions shown in the recent activity. */
const RECENT = 5

/**
 * Dashboard: greeting, library summary, running jobs, next step and recent activity. Jobs are
 * polled only while mounted.
 */
const { t, te, locale } = useI18n()
const jobs = useJobsStore()
const session = useSessionStore()

const now = new Date()
const hour = now.getHours()
const greeting = t(
  `dashboard.greeting.${hour < 12 ? 'morning' : hour < 20 ? 'afternoon' : 'evening'}`,
  { name: session.user?.username ?? '' },
)
const today = computed(() =>
  now.toLocaleDateString(locale.value, { weekday: 'long', day: 'numeric', month: 'long' }),
)
const recent = ref<ActivityLog[] | null>(null)

const summary = ref<LibrarySummary | null>(null)
const summaryError = ref('')
const jobsError = ref('')
let timer: ReturnType<typeof setInterval> | undefined

/**
 * Recommended next step, in order: wait for jobs, import (empty database, first run),
 * download what is pending, watch for releases. None until the summary has loaded.
 */
const nextStep = computed(() => {
  if (jobs.active.length > 0) return { key: 'wait', pending: 0 }
  const s = summary.value
  if (!s) return null
  if (s.artists === 0) return { key: 'empty', pending: 0 }
  if (s.tracks > s.downloaded) return { key: 'download', pending: s.tracks - s.downloaded }
  return { key: 'watch', pending: 0 }
})

async function refreshJobs(): Promise<void> {
  try {
    await jobs.refresh()
    jobsError.value = ''
  } catch (e) {
    jobsError.value = errorText(e, t)
  }
}

const NEXT_ICON = { wait: 'import', empty: 'disc', download: 'download', watch: 'bell' } as const

function kindLabel(kind: string): string {
  return te(`dashboard.jobs.kind.${kind}`) ? t(`dashboard.jobs.kind.${kind}`) : kind
}

async function loadSummary(): Promise<void> {
  try {
    summary.value = await api<LibrarySummary>('/api/v1/catalog/summary/')
  } catch (e) {
    summaryError.value = errorText(e, t)
  }
}

// Activity is an extra: if it fails the dashboard goes on without it (the Log reports it).
async function loadRecent(): Promise<void> {
  try {
    const page = await api<{ results: ActivityLog[] }>('/api/v1/activity/entries/')
    recent.value = page.results.slice(0, RECENT)
  } catch {
    recent.value = null
  }
}

onMounted(() => {
  timer = setInterval(() => void refreshJobs(), POLL_MS)
  // In parallel: a slow summary must not delay the running jobs.
  void Promise.all([loadSummary(), refreshJobs(), loadRecent()])
})
onUnmounted(() => clearInterval(timer))
</script>

<template>
  <section class="dashboard">
    <header class="page-head">
      <div>
        <p class="dashboard__date">{{ today }}</p>
        <h1>{{ greeting }}</h1>
      </div>
      <div class="page-head__actions">
        <RouterLink class="btn btn--secondary" :to="{ name: 'import-folder' }">
          <AppIcon name="folder" />{{ t('dashboard.actions.folder') }}
        </RouterLink>
        <RouterLink class="btn btn--primary" :to="{ name: 'import' }">
          <AppIcon name="plus" />{{ t('dashboard.actions.artists') }}
        </RouterLink>
      </div>
    </header>

    <h2 class="sr-only">{{ t('dashboard.library') }}</h2>
    <BaseAlert v-if="summaryError" variant="error">{{ summaryError }}</BaseAlert>
    <dl v-if="summary" class="stats">
      <div
        v-for="key in ['artists', 'albums', 'recordings', 'tracks', 'downloaded'] as const"
        :key="key"
      >
        <dt>{{ t(`dashboard.summary.${key}`) }}</dt>
        <dd>{{ summary[key].toLocaleString(locale) }}</dd>
      </div>
    </dl>

    <div class="dashboard__grid">
      <div class="dashboard__col">
        <section class="card">
          <h2 class="card__head">{{ t('dashboard.jobs.title') }}</h2>
          <BaseAlert v-if="jobsError" variant="error" class="card__alert">{{
            jobsError
          }}</BaseAlert>
          <p v-if="jobs.active.length === 0" class="card__empty">{{ t('dashboard.jobs.empty') }}</p>
          <ul v-else class="jobs">
            <li v-for="job in jobs.active" :key="job.id">
              <div class="jobs__line">
                <span class="chip chip--accent">{{ kindLabel(job.kind) }}</span>
                <span class="jobs__current">{{ job.current }}</span>
                <small v-if="job.total">{{ job.done }} / {{ job.total }}</small>
              </div>
              <ProgressBar
                :value="progressOf(job)"
                :label="t('dashboard.jobs.progress', { kind: kindLabel(job.kind) })"
              />
            </li>
          </ul>
        </section>

        <section v-if="nextStep" class="next-step card" :aria-label="t('dashboard.next.title')">
          <span class="next-step__icon" aria-hidden="true"
            ><AppIcon :name="NEXT_ICON[nextStep.key as keyof typeof NEXT_ICON]"
          /></span>
          <div class="next-step__text">
            <h2>{{ t(`dashboard.next.${nextStep.key}.title`) }}</h2>
            <p>{{ t(`dashboard.next.${nextStep.key}.text`, { n: nextStep.pending }) }}</p>
          </div>
          <p v-if="nextStep.key === 'empty'" class="next-step__actions">
            <RouterLink class="btn btn--accent" :to="{ name: 'import' }">{{
              t('dashboard.next.empty.artists')
            }}</RouterLink>
            <RouterLink class="btn btn--secondary" :to="{ name: 'import-folder' }">{{
              t('dashboard.next.empty.folder')
            }}</RouterLink>
          </p>
          <p v-else-if="nextStep.key !== 'wait'" class="next-step__actions">
            <RouterLink
              class="btn btn--accent"
              :to="{ name: nextStep.key === 'download' ? 'download' : 'watches' }"
              >{{ t(`dashboard.next.${nextStep.key}.action`) }}</RouterLink
            >
          </p>
        </section>
      </div>

      <section v-if="recent" class="recent card">
        <div class="card__head">
          <h2>{{ t('dashboard.recent.title') }}</h2>
          <RouterLink :to="{ name: 'log' }">{{ t('dashboard.recent.all') }}</RouterLink>
        </div>
        <p v-if="recent.length === 0" class="card__empty">{{ t('dashboard.recent.empty') }}</p>
        <ul v-else>
          <li v-for="entry in recent" :key="entry.id">
            <span class="recent__icon" aria-hidden="true"><AppIcon name="history" /></span>
            <span class="recent__text">
              <span class="mono">{{ entry.action }}</span>
              <small>
                {{ entry.username || t('log.system') }} ·
                {{
                  new Date(entry.created_at).toLocaleString(locale, {
                    dateStyle: 'medium',
                    timeStyle: 'short',
                  })
                }}
              </small>
            </span>
          </li>
        </ul>
      </section>
    </div>
  </section>
</template>

<style scoped>
.dashboard {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}
.dashboard .page-head {
  margin-bottom: var(--space-2);
}
.dashboard__date {
  margin-bottom: var(--space-1);
  color: var(--color-muted);
  font-size: 0.875rem;
  font-weight: 500;
}
.dashboard__date::first-letter {
  text-transform: uppercase;
}
/* Mobile-first: two columns of totals on mobile and four from 600 px. */
.stats {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: var(--space-2);
  margin: 0;
}
.stats div {
  padding: var(--space-3) 1.25rem;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  background: var(--color-surface);
  box-shadow: var(--shadow);
}
dt {
  color: var(--color-muted);
  font-size: 0.875rem;
  font-weight: 500;
}
dd {
  margin: var(--space-1) 0 0;
  font-family: var(--font-display);
  font-size: 1.875rem;
  font-weight: 640;
  letter-spacing: -0.02em;
  line-height: 1.1;
}
.dashboard__grid,
.dashboard__col {
  display: grid;
  gap: var(--space-3);
  align-items: start;
}
.card__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
  padding: var(--space-3) 1.25rem;
  border-bottom: 1px solid var(--color-border);
}
h2.card__head {
  display: block;
}
.card__empty {
  padding: var(--space-3) 1.25rem;
  color: var(--color-muted);
}
.card__alert {
  margin: var(--space-3) 1.25rem 0;
}
.jobs,
.recent ul {
  margin: 0;
  padding: 0;
  list-style: none;
}
.jobs li {
  display: grid;
  gap: 0.75rem;
  padding: var(--space-3) 1.25rem;
}
.jobs li + li,
.recent li + li {
  border-top: 1px solid var(--color-border);
}
.jobs__line {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}
.jobs__current {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.jobs__line small {
  color: var(--color-muted);
  font-size: 0.8125rem;
}
.next-step {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-3);
  padding: 1.25rem;
  background: linear-gradient(120deg, var(--color-surface), var(--color-accent-soft));
}
.next-step__icon,
.recent__icon {
  display: grid;
  flex: none;
  place-items: center;
  width: 3rem;
  height: 3rem;
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  background: var(--color-surface);
  color: var(--color-accent);
}
.next-step__text {
  flex: 1 1 14rem;
}
.next-step__text p {
  margin-top: 0.125rem;
  color: var(--color-muted);
}
.next-step__actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}
.recent li {
  display: flex;
  align-items: center;
  gap: 0.875rem;
  padding: 0.75rem 1.25rem;
}
.recent__icon {
  width: 2.125rem;
  height: 2.125rem;
  border-radius: var(--radius-sm);
  color: var(--color-muted);
}
.recent__icon .icon {
  width: 1rem;
  height: 1rem;
}
.recent__text {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.recent__text .mono {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.recent__text small {
  color: var(--color-faint);
  font-size: 0.8125rem;
}

@media (min-width: 600px) {
  .stats {
    grid-template-columns: repeat(4, 1fr);
    gap: var(--space-3);
  }
}
@media (min-width: 1024px) {
  .dashboard__grid {
    grid-template-columns: 3fr 2fr;
  }
}
</style>
