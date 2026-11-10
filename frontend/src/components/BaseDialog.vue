<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import BaseButton from './BaseButton.vue'

/**
 * Modal dialog on the native `<dialog>`: the browser handles focus, `Esc` and the inert backdrop.
 */
defineProps<{ title: string; size?: 'wide' }>()
const open = defineModel<boolean>({ default: false })
const { t } = useI18n()
const dialog = ref<HTMLDialogElement>()

// `<dialog>` only opens through its API, not an attribute: sync on mount and on every change.
function sync(): void {
  const el = dialog.value as HTMLDialogElement
  if (open.value && !el.open) el.showModal()
  else if (!open.value && el.open) el.close()
}

onMounted(sync)
watch(open, sync, { flush: 'post' })
</script>

<template>
  <dialog
    ref="dialog"
    class="dialog"
    :class="{ 'dialog--wide': size === 'wide' }"
    @close="open = false"
  >
    <h2>{{ title }}</h2>
    <slot />
    <div class="dialog__actions">
      <BaseButton variant="secondary" @click="open = false">{{ t('ui.close') }}</BaseButton>
    </div>
  </dialog>
</template>

<style scoped>
.dialog {
  width: min(32rem, calc(100vw - 2 * var(--space-3)));
  padding: var(--space-4);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  background: var(--color-surface);
  box-shadow: var(--shadow-float);
  color: var(--color-text);
}
.dialog--wide {
  width: min(48rem, calc(100vw - 2 * var(--space-3)));
  max-height: calc(100dvh - 2 * var(--space-3));
  overflow-y: auto;
}
.dialog h2 {
  margin-bottom: var(--space-3);
}
.dialog :deep(p) {
  margin-bottom: var(--space-3);
  color: var(--color-muted);
}
.dialog::backdrop {
  background: rgb(17 16 20 / 45%);
  backdrop-filter: blur(3px);
}
.dialog__actions {
  display: flex;
  justify-content: flex-end;
  margin-top: var(--space-3);
}
</style>
