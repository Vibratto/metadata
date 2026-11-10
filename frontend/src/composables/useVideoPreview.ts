import { ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { api } from '../api/client'
import { errorText } from '../api/errors'
import type { components } from '../api/schema'

type Video = components['schemas']['Video']

/** State of the open preview. */
export interface VideoPreview {
  title: string
  video: Video | null
  error: string
}

/**
 * Preview of a track's candidate video: only one at a time, looked up when requested. Shared by
 * Download and the Library.
 */
export function useVideoPreview() {
  const { t } = useI18n()
  const preview = ref<VideoPreview | null>(null)
  // If it is closed, or another one opens, while looking up, the old answer is dropped.
  let latest = 0

  async function showPreview(track: { id: number; title: string }): Promise<void> {
    const ticket = ++latest
    preview.value = { title: track.title, video: null, error: '' }
    try {
      const video = await api<Video>(`/api/v1/catalog/tracks/${track.id}/video/`)
      if (ticket === latest) preview.value = { title: track.title, video, error: '' }
    } catch (e) {
      if (ticket === latest)
        preview.value = { title: track.title, video: null, error: errorText(e, t) }
    }
  }

  function closePreview(): void {
    latest++
    preview.value = null
  }

  return { preview, showPreview, closePreview }
}
