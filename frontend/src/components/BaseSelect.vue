<script setup lang="ts" generic="T extends string">
import { computed, nextTick, ref, useId } from 'vue'

import AppIcon from './AppIcon.vue'

/** A choosable option: `value` is what the model holds and `label` what is shown. */
export interface SelectOption<V extends string = string> {
  value: V
  label: string
}

/**
 * Dropdown for a short, fixed list of options, styled like the rest of the form controls.
 * Follows the ARIA "select-only combobox" pattern, so it works with the keyboard and with
 * screen readers like a native `<select>`.
 */
const props = defineProps<{
  label: string
  options: SelectOption<T>[]
  /** Keeps the label for screen readers only. */
  hideLabel?: boolean
  error?: string
}>()
const model = defineModel<T>({ required: true })

const id = useId()
const listId = `${id}-list`
const optionId = (i: number) => `${id}-opt-${i}`
const root = ref<HTMLElement>()
const open = ref(false)
const above = ref(false)
const active = ref(-1)

const selectedIndex = computed(() => props.options.findIndex((o) => o.value === model.value))
const selected = computed(() => props.options[selectedIndex.value])

/** Height the list may take (its CSS `max-height`), in pixels. */
const LIST_HEIGHT = 288

function show(): void {
  if (open.value) return
  // Opens upwards when there is no room below and more room above.
  const box = root.value!.getBoundingClientRect()
  const below = document.documentElement.clientHeight - box.bottom
  above.value = below < LIST_HEIGHT && box.top > below
  open.value = true
  move(Math.max(selectedIndex.value, 0))
}

function close(): void {
  open.value = false
  active.value = -1
}

function move(index: number): void {
  active.value = Math.min(Math.max(index, 0), props.options.length - 1)
  void nextTick(() =>
    document.getElementById(optionId(active.value))?.scrollIntoView?.({ block: 'nearest' }),
  )
}

function choose(index: number): void {
  const option = props.options[index]
  if (option) model.value = option.value
  close()
}

/** First option after `from` whose label starts with the typed letter. */
function startingWith(letter: string, from: number): number {
  const n = props.options.length
  for (let step = 1; step <= n; step++) {
    const index = (from + step) % n
    if (props.options[index]!.label.toLowerCase().startsWith(letter)) return index
  }
  return -1
}

function onKey(e: KeyboardEvent): void {
  const { key } = e
  if (key === 'Tab') return close()
  if (key === 'Escape') {
    if (!open.value) return
    // Inside a dialog, Escape closes the list and not the dialog.
    e.preventDefault()
    e.stopPropagation()
    return close()
  }
  if (key === 'Enter' || key === ' ') {
    e.preventDefault()
    return open.value ? choose(active.value) : show()
  }
  if (key === 'ArrowDown' || key === 'ArrowUp') {
    e.preventDefault()
    if (!open.value) return show()
    return move(active.value + (key === 'ArrowDown' ? 1 : -1))
  }
  if (key === 'Home' || key === 'End') {
    e.preventDefault()
    if (!open.value) show()
    return move(key === 'Home' ? 0 : props.options.length - 1)
  }
  if (key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) {
    const index = startingWith(key.toLowerCase(), open.value ? active.value : selectedIndex.value)
    if (index === -1) return
    // Closed, a letter changes the value like a native select; open, it moves the highlight.
    if (open.value) move(index)
    else model.value = props.options[index]!.value
  }
}

function onFocusOut(e: FocusEvent): void {
  if (!root.value?.contains(e.relatedTarget as Node | null)) close()
}
</script>

<template>
  <div ref="root" class="select" @focusout="onFocusOut">
    <span :id="`${id}-label`" class="select__label" :class="{ 'sr-only': hideLabel }">
      {{ label }}
    </span>
    <div
      class="select__button"
      role="combobox"
      tabindex="0"
      aria-haspopup="listbox"
      :aria-expanded="open"
      :aria-controls="listId"
      :aria-labelledby="`${id}-label ${id}-value`"
      :aria-activedescendant="open && active >= 0 ? optionId(active) : undefined"
      :aria-invalid="error ? 'true' : undefined"
      :aria-describedby="error ? `${id}-error` : undefined"
      @click="open ? close() : show()"
      @keydown="onKey"
    >
      <span :id="`${id}-value`" class="select__value">{{ selected?.label }}</span>
      <AppIcon name="chevron" class="select__chevron" />
    </div>
    <ul
      v-show="open"
      :id="listId"
      role="listbox"
      class="select__list"
      :class="{ 'select__list--above': above }"
      :aria-labelledby="`${id}-label`"
    >
      <li
        v-for="(o, i) in options"
        :id="optionId(i)"
        :key="o.value"
        role="option"
        :aria-selected="i === selectedIndex"
        :class="{ 'is-active': i === active }"
        @mousedown.prevent
        @mousemove="active = i"
        @click="choose(i)"
      >
        <span>{{ o.label }}</span>
        <AppIcon v-if="i === selectedIndex" name="check" />
      </li>
    </ul>
    <p v-if="error" :id="`${id}-error`" class="select__error">{{ error }}</p>
  </div>
</template>

<style scoped>
.select {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 0.4375rem;
  min-width: 0;
}
.select__label {
  font-size: 0.875rem;
  font-weight: 550;
}
/* Same box as the text inputs in base.css. */
.select__button {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  min-height: var(--touch-target);
  padding: 0 0.75rem 0 0.875rem;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-surface);
  color: var(--color-text);
  font-size: 1rem;
  cursor: pointer;
  user-select: none;
  transition:
    border-color 0.15s,
    box-shadow 0.15s;
}
.select__button:focus-visible,
.select__button[aria-expanded='true'] {
  border-color: var(--color-accent);
  outline: none;
  box-shadow: 0 0 0 4px var(--color-accent-soft);
}
.select__button[aria-invalid='true'] {
  border-color: var(--color-danger);
}
.select__value {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.select__chevron {
  width: 1rem;
  height: 1rem;
  color: var(--color-muted);
  transform: rotate(90deg);
  transition: transform 0.15s;
}
.select__button[aria-expanded='true'] .select__chevron {
  transform: rotate(-90deg);
}
.select__list {
  position: absolute;
  top: calc(100% + var(--space-1));
  left: 0;
  z-index: 30;
  min-width: 100%;
  max-width: 90vw;
  max-height: 18rem;
  margin: 0;
  padding: var(--space-1);
  overflow-y: auto;
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  background: var(--color-surface);
  box-shadow: var(--shadow-float);
  list-style: none;
}
.select__list--above {
  top: auto;
  bottom: calc(100% + var(--space-1));
}
.select__list li {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  min-height: var(--touch-target);
  padding: 0 var(--space-3);
  border-radius: var(--radius-sm);
  white-space: nowrap;
  cursor: pointer;
}
.select__list li.is-active {
  background: var(--color-accent-soft);
}
.select__list li[aria-selected='true'] {
  font-weight: 600;
}
.select__list .icon {
  width: 1rem;
  height: 1rem;
  color: var(--color-accent);
}
.select__error {
  margin: 0;
  color: var(--color-danger);
}
</style>
