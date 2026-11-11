import { inject, type InjectionKey, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { api } from '../../api/client'
import { errorText } from '../../api/errors'
import type { components } from '../../api/schema'
import { useJobRun } from '../../composables/useJobRun'
import type { Page } from '../../composables/usePagedList'

type JobRun = components['schemas']['JobRun']

/**
 * Ids of the tracks ticked for download. The Library view provides it, because the list
 * below it is mounted again on every search and the selection has to outlive that.
 */
export const TRACK_SELECTION: InjectionKey<Set<number>> = Symbol('track selection')

/**
 * Downloading from the track list: all the pending tracks or a hand-picked selection.
 * Only one download can run at a time, so a running one is followed instead.
 * `reload` is called when a download ends, because the pending tracks have changed.
 */
export function useTrackDownloads(reload: () => unknown) {
  const { t } = useI18n()
  const job = useJobRun()
  // The selection lives outside the page: it survives paging and filter changes.
  const selected = inject(TRACK_SELECTION, () => reactive(new Set<number>()), true)
  const error = ref('')

  /** Follows the latest download if still active; there is at most one, always the newest. */
  async function followActive(): Promise<void> {
    try {
      const [latest] = (await api<Page<JobRun>>('/api/v1/jobs/runs/?kind=download')).results
      if (latest && ['pending', 'running', 'stopping'].includes(latest.status)) {
        await job.follow(latest.id)
      }
    } catch (e) {
      error.value = errorText(e, t)
    }
  }

  async function launch(params: Record<string, unknown>): Promise<void> {
    // If it fails because another one just started (409), follow that one instead of the error.
    if (!(await job.start('download', params))) await followActive()
  }

  function toggle(id: number, on: boolean): void {
    if (on) selected.add(id)
    else selected.delete(id)
  }

  watch(
    () => job.active,
    (now, before) => {
      if (before && !now) {
        selected.clear()
        void reload()
      }
    },
  )

  return {
    job,
    selected,
    error,
    toggle,
    followActive,
    downloadAll: () => launch({ all_pending: true }),
    downloadSelected: () => launch({ track_ids: [...selected].sort((a, b) => a - b) }),
  }
}
