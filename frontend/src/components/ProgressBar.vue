<script setup lang="ts">
import { computed } from 'vue'

/**
 * Progress bar from 0 to 100; `label` is its accessible name.
 */
const props = defineProps<{ value: number; label: string }>()
const percent = computed(() => Math.min(100, Math.max(0, Math.round(props.value))))
</script>

<template>
  <div
    class="progress"
    role="progressbar"
    :aria-label="label"
    aria-valuemin="0"
    aria-valuemax="100"
    :aria-valuenow="percent"
  >
    <div class="progress__fill" :style="{ width: `${percent}%` }" />
  </div>
</template>

<style scoped>
.progress {
  height: 0.375rem;
  overflow: hidden;
  border-radius: 999px;
  background: var(--color-surface-2);
}
.progress__fill {
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, var(--color-accent), var(--color-accent-strong));
  transition: width 0.4s ease;
}
</style>
