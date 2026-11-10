<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { api } from '../../api/client'
import { errorText } from '../../api/errors'
import type { components } from '../../api/schema'
import BaseAlert from '../../components/BaseAlert.vue'
import BaseButton from '../../components/BaseButton.vue'
import BaseField from '../../components/BaseField.vue'

type Recording = components['schemas']['Recording']

/**
 * Albums the recording of a track appears on ("Also appears on") and, for admins, splitting
 * this track off the others or merging another recording into its own.
 */
const props = defineProps<{ trackId: number; recordingId: number }>()
const emit = defineEmits<{ changed: [] }>()

const { t } = useI18n()
const recording = ref<Recording | null>(null)
const absorbed = ref('')
const error = ref('')

// The other appearances; the current track is already on the page.
const others = computed(() => (recording.value?.tracks ?? []).filter((x) => x.id !== props.trackId))

async function load(): Promise<void> {
  error.value = ''
  try {
    recording.value = await api<Recording>(`/api/v1/catalog/recordings/${props.recordingId}/`)
  } catch (e) {
    error.value = errorText(e, t)
  }
}

async function run(path: string, body?: unknown): Promise<void> {
  error.value = ''
  try {
    await api(path, { method: 'POST', body })
    absorbed.value = ''
    emit('changed')
  } catch (e) {
    error.value = errorText(e, t)
  }
}

const split = () => run(`/api/v1/catalog/tracks/${props.trackId}/split/`)
const merge = () =>
  run(`/api/v1/catalog/recordings/${props.recordingId}/merge/`, {
    recording: Number(absorbed.value),
  })

watch(() => [props.trackId, props.recordingId], load, { immediate: true })
</script>

<template>
  <section v-if="recording" class="appearances card">
    <h2>{{ t('library.appearances.title') }}</h2>
    <BaseAlert v-if="error" variant="error">{{ error }}</BaseAlert>
    <ul v-if="others.length">
      <li v-for="other in others" :key="other.id">
        <RouterLink :to="{ name: 'library-item', params: { kind: 'tracks', id: other.id } }">
          {{ other.album_title }}
        </RouterLink>
        <span class="appearances__number">{{ other.disc_number }}-{{ other.track_number }}</span>
      </li>
    </ul>
    <p v-else>{{ t('library.appearances.none') }}</p>

    <BaseButton v-if="others.length" variant="secondary" @click="split">
      {{ t('library.appearances.split') }}
    </BaseButton>
    <form class="appearances__merge" @submit.prevent="merge">
      <BaseField v-model="absorbed" type="number" :label="t('library.appearances.merge_id')">
        <template #hint>{{ t('library.appearances.merge_hint') }}</template>
      </BaseField>
      <BaseButton type="submit" variant="secondary" :disabled="!absorbed">
        {{ t('library.appearances.merge') }}
      </BaseButton>
    </form>
  </section>
</template>

<style scoped>
.appearances {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  padding: 1.25rem;
}
.appearances ul {
  margin: 0;
  padding: 0;
  list-style: none;
}
.appearances li {
  display: flex;
  justify-content: space-between;
  gap: var(--space-2);
  min-height: var(--touch-target);
  align-items: center;
}
.appearances__number {
  color: var(--color-muted);
  font-size: 0.875rem;
}
.appearances__merge {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  align-items: flex-start;
}
</style>
