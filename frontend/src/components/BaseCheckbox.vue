<script setup lang="ts">
/**
 * Checkbox whose whole label is the touch target.
 */
defineProps<{ label: string }>()
const model = defineModel<boolean>({ default: false })
</script>

<template>
  <label class="check">
    <input v-model="model" type="checkbox" />
    <span>{{ label }}</span>
  </label>
</template>

<style scoped>
.check {
  display: flex;
  align-items: center;
  gap: 0.625rem;
  min-height: var(--touch-target);
  font-size: 0.9375rem;
  font-weight: 500;
  cursor: pointer;
}
</style>
