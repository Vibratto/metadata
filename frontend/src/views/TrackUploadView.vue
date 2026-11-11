<script setup lang="ts">
import { onMounted, ref, useId } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'

import { api, ApiError, csrfToken, kindOf } from '../api/client'
import { errorText } from '../api/errors'
import type { components } from '../api/schema'
import BaseAlert from '../components/BaseAlert.vue'
import BaseButton from '../components/BaseButton.vue'
import ProgressBar from '../components/ProgressBar.vue'

type Track = components['schemas']['Track']

/**
 * Hand upload of a track's audio. The server validates, converts and tags it; this view
 * only picks the file and follows the upload.
 */
const { t } = useI18n()
const id = Number(useRoute().params.id)
const inputId = useId()

const track = ref<Track | null>(null)
const file = ref<File | null>(null)
const progress = ref<number | null>(null)
const done = ref(false)
const error = ref('')

onMounted(async () => {
  try {
    track.value = await api<Track>(`/api/v1/catalog/tracks/${id}/`)
  } catch (e) {
    error.value = errorText(e, t)
  }
})

function pick(event: Event): void {
  file.value = (event.target as HTMLInputElement).files?.[0] ?? null
  done.value = false
}

/** `fetch` does not report upload progress; `XMLHttpRequest` does. */
function send(body: File): Promise<void> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', `/api/v1/catalog/tracks/${id}/upload/`)
    xhr.setRequestHeader('Accept', 'application/json')
    xhr.setRequestHeader('X-CSRFToken', csrfToken())
    xhr.responseType = 'json'
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) progress.value = (e.loaded / e.total) * 100
    }
    xhr.onload = () =>
      xhr.status < 300
        ? resolve()
        : reject(new ApiError(kindOf(xhr.status), xhr.status, xhr.response))
    xhr.onerror = () => reject(new ApiError('network', 0))
    const form = new FormData()
    form.append('file', body)
    xhr.send(form)
  })
}

async function upload(): Promise<void> {
  if (!file.value) return
  error.value = ''
  done.value = false
  progress.value = 0
  try {
    await send(file.value)
    done.value = true
  } catch (e) {
    error.value = errorText(e, t)
  } finally {
    progress.value = null
  }
}
</script>

<template>
  <section class="upload">
    <h1>{{ t('trackUpload.title') }}</h1>
    <p v-if="track">{{ t('trackUpload.intro', { title: track.title }) }}</p>
    <BaseAlert v-if="done" variant="success">{{ t('trackUpload.done') }}</BaseAlert>
    <BaseAlert v-if="error" variant="error">{{ error }}</BaseAlert>

    <form @submit.prevent="upload">
      <label :for="inputId">{{ t('trackUpload.file') }}</label>
      <input
        :id="inputId"
        type="file"
        accept="audio/*,.mp3,.m4a,.flac,.opus,.ogg,.wav"
        :aria-describedby="`${inputId}-hint`"
        @change="pick"
      />
      <p :id="`${inputId}-hint`" class="upload__hint">{{ t('trackUpload.hint') }}</p>
      <ProgressBar v-if="progress !== null" :value="progress" :label="t('trackUpload.progress')" />
      <BaseButton type="submit" :disabled="!file || progress !== null">
        {{ t('trackUpload.submit') }}
      </BaseButton>
    </form>
  </section>
</template>

<style scoped>
.upload,
form {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  max-width: 32rem;
  margin-inline: auto;
}
input[type='file'] {
  min-height: var(--touch-target);
  font: inherit;
}
.upload__hint {
  margin: 0;
  color: var(--color-muted);
}
</style>
