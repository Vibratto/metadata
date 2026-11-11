<script setup lang="ts">
import { computed, reactive } from 'vue'
import { useI18n } from 'vue-i18n'

import BaseButton from '../components/BaseButton.vue'
import BaseCheckbox from '../components/BaseCheckbox.vue'
import JobRunPanel from '../components/JobRunPanel.vue'
import { useJobRun } from '../composables/useJobRun'

/** Summary of the `maintenance` job: one entry per operation run. */
interface Summary {
  retag?: { retagged: number; failed: number }
  replaygain?: { albums: number; files: number; failed: number }
  relocate?: { moved: number; unchanged: number; failed: number }
  check_files?: { checked: number; missing: number[] }
  complete_artists?: { reviewed: number; completed: number; unchanged: number; errors: number }
  lyrics?: { found: number; not_found: number; failed: number }
  complete_albums?: { albums: number; tracks: number; reused_recordings: number; errors: number }
}

// Same order the backend runs them in.
const OPERATIONS = [
  'retag',
  'replaygain',
  'relocate',
  'check_files',
  'complete_artists',
  'lyrics',
  'complete_albums',
] as const
// Relocating is opt-in: it is done once, after changing the naming template. Completing
// albums too: it asks YouTube Music for every album in the library.
const OPTIONAL = new Set<string>(['relocate', 'complete_albums'])

/**
 * Utilidades de mantenimiento: elegir operaciones, lanzar la tarea `maintenance`, seguirla y
 * ver su resumen final.
 *
 * Maintenance utilities: pick operations, start the `maintenance` job, follow it and show
 * its final summary.
 */
const { t } = useI18n()
const job = useJobRun()
const chosen = reactive(Object.fromEntries(OPERATIONS.map((op) => [op, !OPTIONAL.has(op)])))
const operations = computed(() => OPERATIONS.filter((op) => chosen[op]))
// Retagged and moved within one scan, Navidrome takes the file for a new track;
// ReplayGain rewrites the tags too.
const conflict = computed(() => chosen.relocate && (chosen.retag || chosen.replaygain))

const summary = computed(() => {
  const value = job.run && !job.active ? (job.run.summary as Summary) : {}
  return Object.keys(value).length ? value : null
})

const start = () => job.start('maintenance', { operations: operations.value })
</script>

<template>
  <section class="utilities">
    <h1>{{ t('utilities.title') }}</h1>
    <p>{{ t('utilities.intro') }}</p>

    <fieldset>
      <legend>{{ t('utilities.operations') }}</legend>
      <BaseCheckbox
        v-for="op in OPERATIONS"
        :key="op"
        v-model="chosen[op]"
        :label="t(`utilities.operation.${op}`)"
      />
    </fieldset>
    <p v-if="conflict" class="hint" role="alert">{{ t('utilities.conflict') }}</p>
    <BaseButton :disabled="!operations.length || conflict || job.active" @click="start">
      {{ t('utilities.start') }}
    </BaseButton>

    <JobRunPanel :job="job" />

    <section v-if="summary" class="summary">
      <h2>{{ t('utilities.summary.title') }}</h2>
      <ul>
        <li v-if="summary.retag">{{ t('utilities.summary.retag', summary.retag) }}</li>
        <li v-if="summary.replaygain">
          {{ t('utilities.summary.replaygain', summary.replaygain) }}
        </li>
        <li v-if="summary.relocate">{{ t('utilities.summary.relocate', summary.relocate) }}</li>
        <template v-if="summary.check_files">
          <li>
            {{
              t('utilities.summary.check_files', {
                checked: summary.check_files.checked,
                missing: summary.check_files.missing.length,
              })
            }}
          </li>
          <li v-if="summary.check_files.missing.length">
            {{
              t('utilities.summary.missing', {
                ids: summary.check_files.missing.map((id) => `#${id}`).join(', '),
              })
            }}
          </li>
        </template>
        <li v-if="summary.complete_artists">
          {{ t('utilities.summary.complete_artists', summary.complete_artists) }}
        </li>
        <li v-if="summary.lyrics">{{ t('utilities.summary.lyrics', summary.lyrics) }}</li>
        <li v-if="summary.complete_albums">
          {{ t('utilities.summary.complete_albums', summary.complete_albums) }}
        </li>
      </ul>
    </section>

    <RouterLink :to="{ name: 'library-backup' }">
      {{ t('utilities.backup') }}
    </RouterLink>
  </section>
</template>

<style scoped>
.utilities {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  max-width: 40rem;
  margin-inline: auto;
}
fieldset {
  margin: 0;
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
}
.utilities > .btn {
  align-self: flex-start;
}
.summary ul {
  margin: 0;
  padding-left: var(--space-3);
}
.utilities > a {
  display: inline-flex;
  align-items: center;
  min-height: var(--touch-target);
}
</style>
