<script setup lang="ts">
import { ICONS, type IconName } from './icons'

/**
 * Decorative icon: it always sits next to text that already names it.
 */
defineProps<{ name: IconName }>()
</script>

<template>
  <svg class="icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
    <path v-for="d in ICONS[name]" :key="d" :d="d" />
  </svg>
</template>

<style scoped>
.icon {
  flex: none;
  width: 1.25rem;
  height: 1.25rem;
  fill: none;
  stroke: currentcolor;
  stroke-width: 1.7;
  stroke-linecap: round;
  stroke-linejoin: round;
}
</style>
