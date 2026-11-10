<script setup lang="ts">
/**
 * Touch-friendly button (44 px minimum hit area). Its look lives in the global `btn` and
 * `btn--*` classes (base.css), so a `RouterLink` can look the same.
 */
withDefaults(
  defineProps<{
    variant?: 'primary' | 'secondary' | 'danger' | 'accent' | 'ghost'
    type?: 'button' | 'submit'
  }>(),
  {
    variant: 'primary',
    type: 'button',
  },
)
</script>

<template>
  <button :type="type" class="btn" :class="`btn--${variant}`"><slot /></button>
</template>
