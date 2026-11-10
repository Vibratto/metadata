<script setup lang="ts">
import { onBeforeUnmount, ref, useId, useSlots, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import AppIcon from './AppIcon.vue'

/**
 * Text field with its label and error message wired up for screen readers. Search fields
 * (`type="search"`) have their own clear button, the same in every browser, and with
 * `debounce` (ms) emit the value once typing stops; Enter and the clear button emit at once.
 */
const props = defineProps<{ label: string; type?: string; error?: string; debounce?: number }>()
const emit = defineEmits<{ clear: [] }>()
const slots = useSlots()
const model = defineModel<string>({ default: '' })
const id = useId()
const { t } = useI18n()
const input = ref<HTMLInputElement>()

// What was typed: with debounce it runs ahead of the emitted value.
const draft = ref(model.value)
watch(model, (value) => {
  draft.value = value
})

let timer: ReturnType<typeof setTimeout> | undefined
function flush(): void {
  clearTimeout(timer)
  timer = undefined
  if (model.value !== draft.value) model.value = draft.value
}
function onInput(): void {
  clearTimeout(timer)
  if (props.type === 'search' && props.debounce) timer = setTimeout(flush, props.debounce)
  else flush()
}
function clear(): void {
  clearTimeout(timer)
  draft.value = ''
  model.value = ''
  emit('clear')
  input.value?.focus()
}
onBeforeUnmount(() => clearTimeout(timer))
</script>

<template>
  <div class="field">
    <label :for="id">{{ label }}</label>
    <div class="field__control">
      <input
        :id="id"
        ref="input"
        v-model="draft"
        :type="type ?? 'text'"
        :aria-invalid="error ? 'true' : undefined"
        :aria-describedby="
          [slots.hint ? `${id}-hint` : '', error ? `${id}-error` : ''].filter(Boolean).join(' ') ||
          undefined
        "
        @input="onInput"
        @keydown.enter="flush"
        @blur="flush"
      />
      <button
        v-if="type === 'search' && draft"
        type="button"
        class="field__clear"
        :aria-label="t('ui.clearSearch')"
        @click="clear"
      >
        <AppIcon name="close" />
      </button>
    </div>
    <p v-if="slots.hint" :id="`${id}-hint`" class="field__hint"><slot name="hint" /></p>
    <p v-if="error" :id="`${id}-error`" class="field__error">{{ error }}</p>
  </div>
</template>

<style scoped>
.field {
  display: flex;
  flex-direction: column;
  gap: 0.4375rem;
}
/* The native “x” is removed: ours behaves the same in every browser. */
.field__control {
  position: relative;
  display: flex;
}
.field__control input {
  flex: 1;
  min-width: 0;
}
.field__control input[type='search'] {
  padding-right: var(--touch-target);
}
.field__control input[type='search']::-webkit-search-cancel-button {
  appearance: none;
  display: none;
}
.field__clear {
  position: absolute;
  top: 0;
  right: 0;
  display: grid;
  place-items: center;
  width: var(--touch-target);
  height: 100%;
  min-height: var(--touch-target);
  padding: 0;
  border: 0;
  background: none;
  color: var(--color-muted);
  cursor: pointer;
}
.field__clear:hover {
  color: var(--color-text);
}
.field__clear .icon {
  width: 1.125rem;
  height: 1.125rem;
}
input[aria-invalid='true'] {
  border-color: var(--color-danger);
}
.field__hint {
  max-inline-size: 65ch;
  margin: 0;
  color: var(--color-muted);
  font-size: 0.8125rem;
  text-decoration: none;
}
.field__hint :deep(code) {
  overflow-wrap: anywhere;
  text-decoration: none;
}
.field__error {
  margin: 0;
  color: var(--color-danger);
  font-size: 0.875rem;
}
</style>
