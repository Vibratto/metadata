<script setup lang="ts">
/**
 * Inline notice. Errors and warnings are announced as `alert`, the rest as `status`.
 */
withDefaults(defineProps<{ variant?: 'info' | 'success' | 'warning' | 'error' }>(), {
  variant: 'info',
})
</script>

<template>
  <div
    class="alert"
    :class="`alert--${variant}`"
    :role="variant === 'error' || variant === 'warning' ? 'alert' : 'status'"
  >
    <slot />
  </div>
</template>

<style scoped>
.alert {
  padding: 0.875rem 1.125rem;
  border: 1px solid color-mix(in srgb, currentcolor 18%, transparent);
  border-radius: var(--radius);
  font-weight: 500;
}
.alert--info {
  background: var(--color-info-soft);
  color: var(--color-info);
}
.alert--success {
  background: var(--color-success-soft);
  color: var(--color-success);
}
.alert--warning {
  background: var(--color-warning-soft);
  color: var(--color-warning);
}
.alert--error {
  background: var(--color-danger-soft);
  color: var(--color-danger);
}
</style>
