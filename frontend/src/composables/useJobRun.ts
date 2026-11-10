import { computed, onScopeDispose, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { api } from '../api/client'
import { errorText } from '../api/errors'
import type { components } from '../api/schema'

type JobRun = components['schemas']['JobRun']
type JobRunLine = components['schemas']['JobRunLine']

const BASE = '/api/v1/jobs/runs/'
const ACTIVE: ReadonlySet<JobRun['status']> = new Set(['pending', 'running', 'stopping'])

/** How often, in milliseconds, an active job is polled. */
export const POLL_MS = 2000

/**
 * Starts or follows a background job: status, progress and new log lines while it is active.
 * Polling stops when the job closes or the owning view unmounts.
 */
export function useJobRun() {
  const { t } = useI18n()
  const run = ref<JobRun | null>(null)
  const lines = ref<JobRunLine[]>([])
  const error = ref('')
  const active = computed(() => run.value !== null && ACTIVE.has(run.value.status))

  let timer: ReturnType<typeof setTimeout> | undefined
  // Each followed job has its own generation: an in-flight poll of the previous one is dropped.
  let generation = 0

  function track(fresh: JobRun): void {
    clearTimeout(timer)
    generation += 1
    run.value = fresh
    lines.value = []
    void poll(generation)
  }

  async function poll(gen: number): Promise<void> {
    const id = (run.value as JobRun).id
    try {
      // Status first, then lines: if it was already closed, the lines are complete.
      // Automatic polls do not count as activity for the session timeout.
      const fresh = await api<JobRun>(`${BASE}${id}/`, { poll: true })
      let batch: JobRunLine[]
      do {
        // `lines/` answers with an unpaginated list (capped per request).
        batch = await api<JobRunLine[]>(
          `${BASE}${id}/lines/?after=${lines.value.at(-1)?.position ?? 0}`,
          { poll: true },
        )
        if (gen !== generation) return
        lines.value.push(...batch)
      } while (!ACTIVE.has(fresh.status) && batch.length > 0)
      run.value = fresh
      error.value = ''
    } catch (e) {
      if (gen !== generation) return
      error.value = errorText(e, t)
    }
    // Keep polling after a failure: it is usually a short network drop.
    if (error.value || active.value) timer = setTimeout(() => void poll(gen), POLL_MS)
  }

  /** Starts a job; returns `false` (with `error` set) if the API rejects it. */
  async function start(kind: string, params: Record<string, unknown> = {}): Promise<boolean> {
    error.value = ''
    try {
      track(await api<JobRun>(BASE, { method: 'POST', body: { kind, params } }))
      return true
    } catch (e) {
      error.value = errorText(e, t)
      return false
    }
  }

  /** Follows a run that already exists. */
  async function follow(id: number): Promise<void> {
    error.value = ''
    try {
      track(await api<JobRun>(`${BASE}${id}/`))
    } catch (e) {
      error.value = errorText(e, t)
    }
  }

  /** Asks to stop it; polling goes on until the job is really closed. */
  async function stop(): Promise<void> {
    if (!run.value) return
    try {
      run.value = await api<JobRun>(`${BASE}${run.value.id}/stop/`, { method: 'POST' })
    } catch (e) {
      error.value = errorText(e, t)
    }
  }

  onScopeDispose(() => {
    generation += 1
    clearTimeout(timer)
  })

  return reactive({ run, lines, error, active, start, follow, stop })
}

/** What `useJobRun` returns, to hand over to `JobRunPanel`. */
export type JobRunHandle = ReturnType<typeof useJobRun>
