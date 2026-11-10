<script setup lang="ts">
import { useI18n } from 'vue-i18n'

/** An applied filter: `id` identifies it and `text` is what people read (never an id). */
export interface ActiveFilter {
  id: string
  text: string
}

/**
 * Row of chips with the applied filters, each readable, plus a "remove all" button.
 */
defineProps<{ filters: ActiveFilter[] }>()
defineEmits<{ remove: [id: string]; clear: [] }>()
const { t } = useI18n()
</script>

<template>
  <div
    v-if="filters.length"
    class="active-filters"
    role="group"
    :aria-label="t('ui.activeFilters.title')"
  >
    <span v-for="f in filters" :key="f.id" class="chip">
      <span>{{ f.text }}</span>
      <button
        type="button"
        :aria-label="t('ui.activeFilters.remove', { name: f.text })"
        @click="$emit('remove', f.id)"
      >
        ×
      </button>
    </span>
    <button type="button" class="active-filters__clear" @click="$emit('clear')">
      {{ t('ui.activeFilters.clear') }}
    </button>
  </div>
</template>

<style scoped>
.active-filters {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-2);
}
.chip button,
.active-filters__clear {
  min-width: var(--touch-target);
  min-height: var(--touch-target);
  border: 0;
  background: none;
  color: inherit;
  cursor: pointer;
}
.active-filters__clear {
  padding-inline: var(--space-2);
  text-decoration: underline;
}
</style>
