import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { api } from '../api/client'

/** A background job run, as returned by `/api/v1/jobs/runs/`. */
export interface Job {
  id: number
  kind: string
  status: 'pending' | 'running' | 'stopping' | 'stopped' | 'succeeded' | 'failed' | 'interrupted'
  done: number
  total: number
  current: string
}

/** Percentage (0-100) of a run; the total is 0 until the job knows how much it will do. */
export function progressOf(job: Job): number {
  return job.total > 0 ? Math.round((job.done / job.total) * 100) : 0
}

const ACTIVE: ReadonlySet<Job['status']> = new Set(['pending', 'running', 'stopping'])

/**
 * Background jobs. Whoever uses the store decides when to call `refresh`.
 */
export const useJobsStore = defineStore('jobs', () => {
  const jobs = ref<Job[]>([])
  const active = computed(() => jobs.value.filter((j) => ACTIVE.has(j.status)))

  async function refresh(): Promise<void> {
    // Most recent first; active ones nearly always are, so the first page is enough.
    jobs.value = (await api<{ results: Job[] }>('/api/v1/jobs/runs/', { poll: true })).results
  }

  return { jobs, active, refresh }
})
