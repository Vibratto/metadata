<script setup lang="ts">
import { computed } from 'vue'

import { api } from '../api/client'
import { entityName, rememberEntity } from '../composables/useEntityLabels'
import type { Page } from '../composables/usePagedList'
import BaseCombobox, { type ComboOption } from './BaseCombobox.vue'

/**
 * Artist or album filter: a server-searched picker whose value is the comma-separated ids,
 * as the URL stores them and the API accepts them.
 */
const props = defineProps<{
  kind: 'artists' | 'albums'
  label: string
  /** Ids (comma-separated) of the artists that narrow the albums down. */
  artists?: string
  hideChips?: boolean
}>()
const model = defineModel<string>({ default: '' })

const ids = computed(() => (model.value ? model.value.split(',').filter(Boolean) : []))
const selected = computed<ComboOption[]>({
  get: () => ids.value.map((id) => ({ value: id, label: entityName(props.kind, id) })),
  set(options) {
    for (const o of options) rememberEntity(props.kind, o.value, o.label)
    model.value = options.map((o) => o.value).join(',')
  },
})

async function search(text: string, signal: AbortSignal): Promise<ComboOption[]> {
  const query = new URLSearchParams({ page_size: '20' })
  if (text) query.set('search', text)
  if (props.kind === 'albums' && props.artists) query.set('artist', props.artists)
  // Related artists saved as bare profiles have no music to filter by.
  if (props.kind === 'artists') query.set('profile_only', 'false')
  const page = await api<Page<{ id: number; name?: string; title?: string }>>(
    `/api/v1/catalog/${props.kind}/?${query}`,
    { signal },
  )
  return page.results.map((r) => ({ value: String(r.id), label: (r.name ?? r.title)! }))
}
</script>

<template>
  <BaseCombobox v-model="selected" :label="label" :search="search" :hide-chips="hideChips" />
</template>
