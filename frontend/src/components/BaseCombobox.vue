<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, useId } from 'vue'
import { useI18n } from 'vue-i18n'

/** A choosable option: `value` is the id and `label` what is shown. */
export interface ComboOption {
  value: string
  label: string
}

/**
 * Server-searched ARIA combobox for large lists. Debounced, cancels the previous request,
 * supports several values shown as removable chips, and is fully keyboard operable.
 */
const props = withDefaults(
  defineProps<{
    label: string
    /** Fetches the options matching the text. */
    search: (text: string, signal: AbortSignal) => Promise<ComboOption[]>
    multiple?: boolean
    /** Debounce after the last keystroke, in milliseconds. */
    delay?: number
    /** Hides the chips when another part of the view already shows the selection. */
    hideChips?: boolean
  }>(),
  { multiple: true, delay: 300, hideChips: false },
)
const model = defineModel<ComboOption[]>({ default: () => [] })
const { t } = useI18n()
const id = useId()
const listId = `${id}-list`
const text = ref('')
const open = ref(false)
const loading = ref(false)
const failed = ref(false)
const results = ref<ComboOption[]>([])
const active = ref(-1)
const input = ref<HTMLInputElement>()

let timer: ReturnType<typeof setTimeout> | undefined
let controller: AbortController | undefined

const choices = computed(() =>
  results.value.filter((o) => !model.value.some((m) => m.value === o.value)),
)
const optionId = (i: number) => `${id}-opt-${i}`
const status = computed(() => {
  if (!open.value) return ''
  if (loading.value) return t('ui.combobox.loading')
  if (failed.value) return t('ui.combobox.error')
  return choices.value.length === 0
    ? t('ui.combobox.empty')
    : t('ui.combobox.results', { n: choices.value.length })
})

async function fetchNow(): Promise<void> {
  controller?.abort()
  const mine = (controller = new AbortController())
  loading.value = true
  failed.value = false
  try {
    const found = await props.search(text.value.trim(), mine.signal)
    if (mine.signal.aborted) return
    results.value = found
    active.value = found.length ? 0 : -1
  } catch {
    if (!mine.signal.aborted) {
      results.value = []
      failed.value = true
    }
  } finally {
    if (!mine.signal.aborted) loading.value = false
  }
}

function schedule(): void {
  open.value = true
  clearTimeout(timer)
  timer = setTimeout(() => void fetchNow(), props.delay)
}

function onFocus(): void {
  if (open.value) return
  open.value = true
  void fetchNow()
}

function pick(option: ComboOption): void {
  model.value = props.multiple ? [...model.value, option] : [option]
  text.value = ''
  if (props.multiple) {
    results.value = results.value.filter((o) => o.value !== option.value)
    active.value = Math.min(active.value, choices.value.length - 1)
  } else {
    close()
  }
}

function remove(option: ComboOption): void {
  model.value = model.value.filter((m) => m.value !== option.value)
  void nextTick(() => input.value?.focus())
}

function close(): void {
  clearTimeout(timer)
  controller?.abort()
  loading.value = false
  open.value = false
  active.value = -1
}

function onKey(e: KeyboardEvent): void {
  if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
    e.preventDefault()
    if (!open.value) return onFocus()
    const n = choices.value.length
    if (n) active.value = (active.value + (e.key === 'ArrowDown' ? 1 : -1) + n) % n
  } else if (e.key === 'Enter') {
    const option = choices.value[active.value]
    if (open.value && option) {
      e.preventDefault()
      pick(option)
    }
  } else if (e.key === 'Escape' && open.value) {
    e.preventDefault()
    e.stopPropagation()
    close()
  } else if (e.key === 'Backspace' && text.value === '' && model.value.length) {
    model.value = model.value.slice(0, -1)
  }
}

onBeforeUnmount(close)
</script>

<template>
  <div
    class="combo"
    @focusout="(e) => !(e.currentTarget as Node).contains(e.relatedTarget as Node) && close()"
  >
    <label :for="id">{{ label }}</label>
    <div class="combo__box">
      <ul v-if="model.length && !hideChips" class="combo__chips">
        <li v-for="o in model" :key="o.value" class="chip">
          <span>{{ o.label }}</span>
          <button
            type="button"
            :aria-label="t('ui.combobox.remove', { name: o.label })"
            @click="remove(o)"
          >
            ×
          </button>
        </li>
      </ul>
      <input
        :id="id"
        ref="input"
        v-model="text"
        type="text"
        role="combobox"
        autocomplete="off"
        aria-autocomplete="list"
        :aria-expanded="open"
        :aria-controls="listId"
        :aria-activedescendant="active >= 0 && open ? optionId(active) : undefined"
        :placeholder="t('ui.combobox.placeholder')"
        @focus="onFocus"
        @input="schedule"
        @keydown="onKey"
      />
    </div>
    <ul v-show="open && choices.length" :id="listId" role="listbox" class="combo__list">
      <li
        v-for="(o, i) in choices"
        :id="optionId(i)"
        :key="o.value"
        role="option"
        :aria-selected="i === active"
        :class="{ 'is-active': i === active }"
        @mousedown.prevent="pick(o)"
      >
        {{ o.label }}
      </li>
    </ul>
    <p class="sr-only" aria-live="polite">{{ status }}</p>
    <p v-if="open && !loading && status && !choices.length" class="combo__hint">{{ status }}</p>
  </div>
</template>

<style scoped>
.combo {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 0.4375rem;
}
.combo__box {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}
.combo__chips {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-1);
  margin: 0;
  padding: 0;
  list-style: none;
}
.combo__chips button {
  min-width: var(--touch-target);
  min-height: var(--touch-target);
  border: 0;
  background: none;
  color: inherit;
  cursor: pointer;
}
.combo__list {
  position: absolute;
  top: 100%;
  z-index: 20;
  width: 100%;
  max-height: 16rem;
  margin: 0;
  padding: var(--space-1);
  overflow-y: auto;
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  background: var(--color-surface, var(--color-bg));
  box-shadow: var(--shadow-lg, 0 8px 24px rgb(0 0 0 / 15%));
  list-style: none;
}
.combo__list li {
  min-height: var(--touch-target);
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius);
  cursor: pointer;
}
.combo__list li.is-active {
  background: var(--color-accent-soft);
}
.combo__hint {
  margin: 0;
  color: var(--color-muted);
  font-size: 0.875rem;
}
@media (max-width: 599.98px) {
  .combo__list {
    position: fixed;
    inset-inline: var(--space-3);
    width: auto;
  }
}
</style>
