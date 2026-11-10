<script setup lang="ts">
import { nextTick, onMounted, ref, useTemplateRef } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'

import { api } from '../../api/client'
import { errorText } from '../../api/errors'
import BaseAlert from '../../components/BaseAlert.vue'
import BaseButton from '../../components/BaseButton.vue'
import type { HistoryEntry, Item } from './kinds'

/**
 * An item's versions, newest first, with its editable values and, for writers, a revert button.
 */
const props = defineProps<{ path: string }>()
const emit = defineEmits<{ reverted: [item: Item] }>()
const { t, locale } = useI18n()

const route = useRoute()
const section = useTemplateRef('section')
const entries = ref<HistoryEntry[]>([])
const error = ref('')

async function load(): Promise<void> {
  try {
    entries.value = await api<HistoryEntry[]>(`${props.path}history/`)
    // No `scrollBehavior` in the router: scroll to the history when the link asks for it.
    if (route.hash === '#history') {
      await nextTick()
      section.value!.scrollIntoView()
    }
  } catch (e) {
    error.value = errorText(e, t)
  }
}

async function revert(entry: HistoryEntry): Promise<void> {
  error.value = ''
  try {
    const item = await api<Item>(`${props.path}revert/`, {
      method: 'POST',
      body: { history_id: entry.history_id },
    })
    emit('reverted', item)
  } catch (e) {
    error.value = errorText(e, t)
  }
}

// django-simple-history codes; an unknown one is shown as is.
const TYPES: Record<string, string> = { '+': 'created', '~': 'changed', '-': 'deleted' }
const typeLabel = (type: string) =>
  type in TYPES ? t(`library.history.type.${TYPES[type]}`) : type
const show = (value: unknown) => (value === null || value === '' ? '—' : String(value))

onMounted(load)
</script>

<template>
  <section id="history" ref="section" class="history card">
    <h2>{{ t('library.history.title') }}</h2>
    <BaseAlert v-if="error" variant="error">{{ error }}</BaseAlert>
    <ol class="history__entries">
      <li v-for="entry in entries" :key="entry.history_id" class="history__entry">
        <p class="history__meta">
          {{ new Date(entry.history_date).toLocaleString(locale) }} ·
          {{ typeLabel(entry.history_type) }} ·
          {{ entry.history_user ?? t('library.history.system') }}
        </p>
        <dl>
          <div v-for="(value, field) in entry.changes" :key="field">
            <dt>{{ t(`library.fields.${field}`) }}</dt>
            <dd>{{ show(value) }}</dd>
          </div>
        </dl>
        <BaseButton variant="secondary" @click="revert(entry)">
          {{ t('library.history.revert') }}
        </BaseButton>
      </li>
    </ol>
  </section>
</template>

<style scoped>
.history {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding: 1.25rem;
}
.history__entries {
  display: flex;
  flex-direction: column;
  margin: 0;
  padding: 0;
  list-style: none;
}
/* Timeline: one dot per version, joined to the next. */
.history__entry {
  position: relative;
  padding: 0 0 var(--space-3) 1.5rem;
}
.history__entry::before {
  content: '';
  position: absolute;
  top: 0.4rem;
  left: 0;
  width: 0.625rem;
  height: 0.625rem;
  border-radius: 50%;
  background: var(--color-accent);
}
.history__entry:not(:last-child)::after {
  content: '';
  position: absolute;
  top: 1.25rem;
  bottom: 0.25rem;
  left: 0.25rem;
  width: 2px;
  background: var(--color-border);
}
.history__entry:last-child::before {
  background: var(--color-border);
}
.history__meta {
  margin: 0;
  color: var(--color-muted);
  font-size: 0.8125rem;
}
.history dl {
  margin: 0.25rem 0 0.5rem;
}
.history dl div {
  display: flex;
  gap: var(--space-2);
  font-size: 0.875rem;
}
.history dt {
  color: var(--color-muted);
}
.history dd {
  margin: 0;
  overflow-wrap: anywhere;
}
</style>
