<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import BaseButton from '../components/BaseButton.vue'
import BaseField from '../components/BaseField.vue'
import JobRunPanel from '../components/JobRunPanel.vue'
import ResponsiveList from '../components/ResponsiveList.vue'
import { useJobRun } from '../composables/useJobRun'

/** A file the job could not link and why (a code translated here). */
interface Unlinked {
  file: string
  reason: string
}

/** Summary the `folder_import` job leaves when it closes. */
interface Summary {
  linked?: number
  already_linked?: number
  unlinked?: Unlinked[]
}

/**
 * Imports a folder of already downloaded music: asks for a subfolder of the downloads
 * folder, starts `folder_import`, follows it and lists the files that were not linked.
 */
const { t, te } = useI18n()
const job = useJobRun()
const folder = ref('')

// The summary only exists once the job has closed; until then it comes empty.
const summary = computed(() => (job.run?.summary ?? {}) as Summary)
const unlinked = computed(() => summary.value.unlinked ?? [])
const columns = computed(() => [
  { key: 'file', label: t('importFolder.unlinked.file') },
  { key: 'reason', label: t('importFolder.unlinked.reason') },
])

function reasonText(reason: string): string {
  const key = `importFolder.reason.${reason}`
  return te(key) ? t(key) : reason
}

const start = () => job.start('folder_import', { folder: folder.value.trim() })
</script>

<template>
  <section class="folder-import">
    <h1>{{ t('importFolder.title') }}</h1>
    <p>{{ t('importFolder.intro') }}</p>

    <form @submit.prevent="start">
      <BaseField v-model="folder" :label="t('importFolder.folder')" />
      <p class="folder-import__hint">{{ t('importFolder.hint') }}</p>
      <BaseButton type="submit" :disabled="job.active">{{ t('importFolder.start') }}</BaseButton>
    </form>

    <JobRunPanel :job="job" />

    <template v-if="summary.linked !== undefined">
      <p class="folder-import__result">
        {{
          t('importFolder.result', {
            linked: summary.linked,
            already: summary.already_linked ?? 0,
            unlinked: unlinked.length,
          })
        }}
      </p>
      <h2>{{ t('importFolder.unlinked.title') }}</h2>
      <ResponsiveList :columns="columns" :rows="unlinked" row-key="file">
        <template #cell-reason="{ row }">{{ reasonText(row.reason) }}</template>
      </ResponsiveList>
    </template>
  </section>
</template>

<style scoped>
.folder-import,
form {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}
.folder-import {
  max-width: 48rem;
  margin-inline: auto;
}
.folder-import__hint {
  margin: 0;
  color: var(--color-muted);
}
.folder-import__result {
  margin: 0;
  font-weight: 600;
}
</style>
