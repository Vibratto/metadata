<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { api } from '../api/client'
import { errorText } from '../api/errors'
import type { components } from '../api/schema'
import BaseAlert from '../components/BaseAlert.vue'
import BaseButton from '../components/BaseButton.vue'
import JobRunPanel from '../components/JobRunPanel.vue'
import { useJobRun } from '../composables/useJobRun'

type BackupPreview = components['schemas']['BackupPreview']
type JobRun = components['schemas']['JobRun']

const BASE = '/api/v1/catalog/backup/'

/**
 * Library backup: download the JSON and, to restore, upload a file, preview what it holds
 * and what already exists, then confirm. Restoring runs as a background job.
 */
const { t } = useI18n()
const job = useJobRun()

const file = ref<File | null>(null)
const preview = ref<BackupPreview | null>(null)
const error = ref('')

/** The server validates the file at every step, so it is uploaded with each request. */
function upload(path: string): Promise<unknown> {
  const body = new FormData()
  body.append('file', file.value as File)
  return api(`${BASE}${path}`, { method: 'POST', body })
}

async function choose(event: Event): Promise<void> {
  file.value = (event.target as HTMLInputElement).files?.[0] ?? null
  preview.value = null
  error.value = ''
  if (!file.value) return
  try {
    preview.value = (await upload('preview/')) as BackupPreview
  } catch (e) {
    error.value = errorText(e, t)
  }
}

async function confirm(): Promise<void> {
  error.value = ''
  try {
    const run = (await upload('restore/')) as JobRun
    preview.value = null
    await job.follow(run.id)
  } catch (e) {
    error.value = errorText(e, t)
  }
}
</script>

<template>
  <section class="backup">
    <h1>{{ t('libraryBackup.title') }}</h1>
    <p>{{ t('libraryBackup.intro') }}</p>

    <h2>{{ t('libraryBackup.export.title') }}</h2>
    <a class="backup__link" :href="BASE" download>{{ t('libraryBackup.export.link') }}</a>

    <h2>{{ t('libraryBackup.restore.title') }}</h2>
    <p>{{ t('libraryBackup.restore.hint') }}</p>
    <label for="backup-file">{{ t('libraryBackup.restore.file') }}</label>
    <input
      id="backup-file"
      type="file"
      accept="application/json,.json"
      :disabled="job.active"
      @change="choose"
    />
    <BaseAlert v-if="error" variant="error">{{ error }}</BaseAlert>

    <template v-if="preview">
      <table>
        <caption>
          {{
            t('libraryBackup.restore.previewTitle')
          }}
        </caption>
        <thead>
          <tr>
            <th scope="col">{{ t('libraryBackup.restore.kind') }}</th>
            <th scope="col">{{ t('libraryBackup.restore.total') }}</th>
            <th scope="col">{{ t('libraryBackup.restore.existing') }}</th>
            <th scope="col">{{ t('libraryBackup.restore.new') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(count, kind) in preview" :key="kind">
            <th scope="row">{{ t(`libraryBackup.kinds.${kind}`) }}</th>
            <td>{{ count.total }}</td>
            <td>{{ count.existing }}</td>
            <td>{{ count.total - count.existing }}</td>
          </tr>
        </tbody>
      </table>
      <BaseButton @click="confirm">{{ t('libraryBackup.restore.confirm') }}</BaseButton>
    </template>

    <JobRunPanel :job="job" />
  </section>
</template>

<style scoped>
.backup {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  max-width: 40rem;
}
h1,
h2,
p {
  margin: 0;
}
.backup__link {
  display: inline-flex;
  align-items: center;
  align-self: flex-start;
  min-height: var(--touch-target);
  padding: 0 var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  background: var(--color-surface);
  color: var(--color-text);
  text-decoration: none;
}
input[type='file'] {
  min-height: var(--touch-target);
  font: inherit;
}
table {
  width: 100%;
  border-collapse: collapse;
}
caption {
  text-align: start;
  font-weight: 600;
}
th,
td {
  padding: var(--space-1) var(--space-2);
  border-bottom: 1px solid var(--color-border);
  text-align: end;
}
th[scope='row'],
th[scope='col']:first-child {
  text-align: start;
}
</style>
