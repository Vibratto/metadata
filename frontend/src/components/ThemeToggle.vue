<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import { THEMES, useTheme } from '../composables/useTheme'
import AppIcon from './AppIcon.vue'

/**
 * Theme button: each press moves to the next one (automatic → light → dark).
 */
defineProps<{ withLabel?: boolean }>()
const { t } = useI18n()
const { theme, set } = useTheme()

const ICON = { auto: 'contrast', light: 'sun', dark: 'moon' } as const
const label = computed(() => t('theme.label', { theme: t(`theme.${theme.value}`) }))

function next(): void {
  set(THEMES[(THEMES.indexOf(theme.value) + 1) % THEMES.length]!)
}
</script>

<template>
  <button
    type="button"
    class="theme-toggle"
    :class="{ 'theme-toggle--row': withLabel }"
    :aria-label="label"
    :title="label"
    @click="next"
  >
    <AppIcon :name="ICON[theme]" />
    <template v-if="withLabel">
      <span class="theme-toggle__name">{{ t('theme.title') }}</span>
      <span class="theme-toggle__value">{{ t(`theme.${theme}`) }}</span>
    </template>
  </button>
</template>

<style scoped>
.theme-toggle {
  display: inline-grid;
  place-items: center;
  width: var(--touch-target);
  height: var(--touch-target);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-surface);
  color: var(--color-muted);
  cursor: pointer;
}
.theme-toggle:hover {
  color: var(--color-text);
}
.theme-toggle--row {
  display: flex;
  gap: var(--space-3);
  width: 100%;
  padding: 0 var(--space-3);
  border: 0;
  border-radius: 0;
  background: none;
  color: var(--color-text);
  font: inherit;
  text-align: left;
}
.theme-toggle__name {
  flex: 1;
  font-weight: 600;
}
.theme-toggle__value {
  color: var(--color-muted);
}
</style>
