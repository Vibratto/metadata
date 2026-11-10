<script setup lang="ts">
import { ref, useId } from 'vue'
import { useI18n } from 'vue-i18n'

import AppIcon from './AppIcon.vue'

/**
 * Filter panel: collapsible on mobile, always open from 1024 px. Each view slots its fields.
 */
const { t } = useI18n()
const open = ref(false)
const bodyId = useId()
</script>

<template>
  <section class="filters">
    <button
      type="button"
      class="filters__toggle"
      :aria-expanded="open"
      :aria-controls="bodyId"
      @click="open = !open"
    >
      <AppIcon name="sliders" />{{ t('ui.filters.title') }}
    </button>
    <div :id="bodyId" class="filters__body" :class="{ 'is-open': open }">
      <slot />
    </div>
  </section>
</template>

<style scoped>
.filters {
  margin-bottom: var(--space-3);
}
.filters__toggle {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  width: 100%;
  min-height: var(--touch-target);
  padding: 0 var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-surface);
  color: var(--color-text);
  font: inherit;
  font-weight: 600;
  text-align: left;
  cursor: pointer;
}
.filters__body {
  display: none;
  margin-top: var(--space-2);
  padding: var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  background: var(--color-surface);
}
.filters__body.is-open {
  display: block;
}

/* On desktop, a bar of compact pill-shaped filters. */
@media (min-width: 1024px) {
  .filters__toggle {
    display: none;
  }
  .filters__body {
    display: block;
    margin: 0;
    padding: 0;
    border: 0;
    background: none;
  }
  .filters__body :deep(input:not([type='checkbox'])),
  .filters__body :deep(select) {
    min-height: 2.5rem;
    border-radius: 999px;
    font-size: 0.875rem;
  }
  .filters__body :deep(label) {
    color: var(--color-muted);
    font-size: 0.8125rem;
  }
}
</style>
