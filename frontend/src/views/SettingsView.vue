<script setup lang="ts">
import { onMounted, reactive, ref, useId } from 'vue'
import { useI18n } from 'vue-i18n'

import { type ApiError, api } from '../api/client'
import { errorText } from '../api/errors'
import type { components } from '../api/schema'
import BaseAlert from '../components/BaseAlert.vue'
import BaseButton from '../components/BaseButton.vue'
import BaseField from '../components/BaseField.vue'

type Preference = components['schemas']['Preference']

/** Keys this view edits; other settings get their own view. */
const THRESHOLD = 'import.suggestion_threshold'
const KEYS = ['download.format', 'download.folder', 'download.name_template', THRESHOLD] as const
type Key = (typeof KEYS)[number]

// Same as `integrations.audio.FORMATS`: the API only validates the type, not the value.
const FORMATS = ['mp3', 'm4a', 'flac', 'opus']
// Placeholders of `integrations.audio.render_path`; passed as a parameter because
// vue-i18n would read the braces in the text as interpolations.
const PLACEHOLDERS = '{albumartist} {artist} {album} {disc} {track} {title} {year}'
const MARKERS = { album: '{album}', title: '{title}', track: '{track}' }

/**
 * Global download settings: format, folder and naming template. Each one is saved with
 * its own `PUT`, so a validation error lands on its field.
 */
const { t } = useI18n()

const values = reactive<Record<Key, string>>({
  'download.format': '',
  'download.folder': '',
  'download.name_template': '',
  [THRESHOLD]: '',
})
const saved = reactive<Partial<Record<Key, string>>>({})
const fieldErrors = reactive<Partial<Record<Key, string>>>({})
const message = ref('')
const error = ref('')

/**
 * Artist separators: a list, so it lives apart from the text fields. The first one joins
 * the display names; surrounding spaces count and are not trimmed.
 */
const SEPARATORS = 'tags.artist_separators'
const separators = ref<string[]>([])
let savedSeparators: string[] = []
let defaultSeparators: string[] = []
const separatorsError = ref('')
const separatorsHint = useId()

function setSeparators(p: Preference): void {
  separators.value = [...(p.value as string[])]
  savedSeparators = [...(p.value as string[])]
  defaultSeparators = [...(p.default as string[])]
}

function move(index: number, by: -1 | 1): void {
  const list = separators.value
  ;[list[index], list[index + by]] = [list[index + by]!, list[index]!]
}

function setAll(entries: Preference[]): void {
  for (const p of entries) {
    if (p.key === SEPARATORS) setSeparators(p)
    if (!(KEYS as readonly string[]).includes(p.key)) continue
    values[p.key as Key] = saved[p.key as Key] = String(p.value)
  }
}

onMounted(async () => {
  try {
    setAll(await api<Preference[]>('/api/v1/preferences/'))
  } catch (e) {
    error.value = errorText(e, t)
  }
})

/** Saves only what changed; a failing field does not stop the others from saving. */
async function save(): Promise<void> {
  message.value = error.value = ''
  for (const key of KEYS) delete fieldErrors[key]
  separatorsError.value = ''
  // A number field hands back a number, and a setting the server did not send has no saved value.
  const changed: string[] = KEYS.filter((key) => String(values[key]) !== (saved[key] ?? ''))
  // The threshold is a number for the API; the form field holds text.
  const edited = {
    ...values,
    [THRESHOLD]: Number(values[THRESHOLD]),
    [SEPARATORS]: separators.value,
  } as Record<string, unknown>
  if (JSON.stringify(separators.value) !== JSON.stringify(savedSeparators)) {
    changed.push(SEPARATORS)
  }
  const results = await Promise.allSettled(
    changed.map((key) =>
      api<Preference>(`/api/v1/preferences/${key}/`, {
        method: 'PUT',
        body: { value: edited[key] },
      }),
    ),
  )
  results.forEach((r, i) => {
    const key = changed[i]!
    if (r.status === 'fulfilled') return setAll([r.value])
    // If it is not an `ApiError`, `errorText` rethrows it: that is a programming error.
    const body = (r.reason as ApiError).body as { value?: string[] } | null
    if (!body?.value) error.value = errorText(r.reason, t)
    else if (key === SEPARATORS) separatorsError.value = body.value.join(' ')
    else fieldErrors[key as Key] = body.value.join(' ')
  })
  if (results.every((r) => r.status === 'fulfilled')) message.value = t('settings.saved')
}
</script>

<template>
  <section class="settings">
    <h1>{{ t('settings.title') }}</h1>
    <p>
      <RouterLink :to="{ name: 'account' }">{{ t('settings.accountLink') }}</RouterLink>
    </p>
    <BaseAlert v-if="message" variant="success">{{ message }}</BaseAlert>
    <BaseAlert v-if="error" variant="error">{{ error }}</BaseAlert>

    <form name="settings" @submit.prevent="save">
      <div class="select">
        <label for="settings-format">{{ t('settings.format') }}</label>
        <select
          id="settings-format"
          v-model="values['download.format']"
          :aria-invalid="fieldErrors['download.format'] ? 'true' : undefined"
          :aria-describedby="fieldErrors['download.format'] ? 'settings-format-error' : undefined"
        >
          <option v-for="f in FORMATS" :key="f" :value="f">{{ f }}</option>
        </select>
        <p v-if="fieldErrors['download.format']" id="settings-format-error" class="select__error">
          {{ fieldErrors['download.format'] }}
        </p>
      </div>
      <BaseField
        v-model="values['download.folder']"
        :label="t('settings.folder')"
        :error="fieldErrors['download.folder']"
      />
      <BaseField
        v-model="values['download.name_template']"
        :label="t('settings.template')"
        :error="fieldErrors['download.name_template']"
      />
      <p class="hint">
        {{ t('settings.templateHint', { placeholders: PLACEHOLDERS, ...MARKERS }) }}
      </p>

      <BaseField
        v-model="values[THRESHOLD]"
        type="number"
        :label="t('settings.threshold')"
        :error="fieldErrors[THRESHOLD]"
      >
        <template #hint>{{ t('settings.thresholdHint') }}</template>
      </BaseField>

      <fieldset
        class="separators"
        :aria-describedby="separatorsError ? `${separatorsHint}-error` : separatorsHint"
      >
        <legend>{{ t('settings.tags.title') }}</legend>
        <p class="hint">{{ t('settings.tags.separators') }}</p>
        <ol>
          <li v-for="(_, i) in separators" :key="i">
            <input
              v-model="separators[i]"
              :aria-label="t('settings.tags.separator', { n: i + 1 })"
              :aria-invalid="separatorsError ? 'true' : undefined"
              maxlength="10"
            />
            <BaseButton
              variant="ghost"
              :aria-label="t('settings.tags.up', { n: i + 1 })"
              :disabled="i === 0"
              @click="move(i, -1)"
              >↑</BaseButton
            >
            <BaseButton
              variant="ghost"
              :aria-label="t('settings.tags.down', { n: i + 1 })"
              :disabled="i === separators.length - 1"
              @click="move(i, 1)"
              >↓</BaseButton
            >
            <BaseButton
              variant="ghost"
              :aria-label="t('settings.tags.remove', { n: i + 1 })"
              :disabled="separators.length === 1"
              @click="separators.splice(i, 1)"
              >✕</BaseButton
            >
          </li>
        </ol>
        <p :id="separatorsHint" class="hint">{{ t('settings.tags.hint') }}</p>
        <p v-if="separatorsError" :id="`${separatorsHint}-error`" class="select__error">
          {{ separatorsError }}
        </p>
        <div class="separators__actions">
          <BaseButton variant="secondary" @click="separators.push('')">
            {{ t('settings.tags.add') }}
          </BaseButton>
          <BaseButton variant="secondary" @click="separators = [...defaultSeparators]">
            {{ t('settings.tags.reset') }}
          </BaseButton>
        </div>
      </fieldset>
      <BaseButton type="submit">{{ t('settings.save') }}</BaseButton>
    </form>
  </section>
</template>

<style scoped>
.settings,
form {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  max-width: 32rem;
}
.select select {
  display: block;
  width: 100%;
  margin-top: var(--space-1);
}
.select select[aria-invalid='true'] {
  border-color: var(--color-danger);
}
.select__error {
  margin: var(--space-1) 0 0;
  color: var(--color-danger);
}
.hint {
  margin: 0;
  color: var(--color-muted);
}
.separators {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  margin: 0;
  padding: var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius, 0.5rem);
}
.separators legend {
  font-weight: 600;
}
.separators ol {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  margin: 0;
  padding-left: 1.5rem;
}
.separators li > * {
  vertical-align: middle;
}
.separators input {
  width: 8rem;
  /* Spaces count: easier to see in monospace. */
  font-family: var(--font-mono, monospace);
  white-space: pre;
}
.separators input[aria-invalid='true'] {
  border-color: var(--color-danger);
}
.separators__actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}
</style>
