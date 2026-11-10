import { flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import type { Component } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'

import { routes } from '../router'
import { useSessionStore } from '../stores/session'
import { render } from './helpers'

/** Pinia with a session already open. */
export function sessionPinia() {
  const pinia = createPinia()
  setActivePinia(pinia)
  useSessionStore(pinia).user = { username: 'demo', language: '' }
  return pinia
}

/**
 * Mounts a view at `path` with the real router (the routes in `routes/`), Pinia and vue-i18n.
 * No navigation guard, so each view is tested on its own.
 */
export async function mountView(view: Component, path: string) {
  const pinia = sessionPinia()
  const router = createRouter({ history: createMemoryHistory(), routes })
  await router.push(path)
  await router.isReady()
  const wrapper = render(view, { global: { plugins: [pinia, router] } })
  await flushPromises()
  return { wrapper, router, pinia }
}

/** Fills a field by its visible label. */
export async function fill(
  wrapper: ReturnType<typeof render>,
  label: string,
  value: string,
): Promise<void> {
  const field = wrapper.findAll('label').find((l) => l.text() === label)
  const input = wrapper.get(`#${field?.attributes('for')}`)
  await input.setValue(value)
  // Leaving the field emits at once what was typed in debounced search fields.
  await input.trigger('blur')
}

/** The `BaseSelect` with that visible label. */
export function dropdown(wrapper: ReturnType<typeof render>, label: string) {
  const found = wrapper
    .findAll('.select')
    .find((select) => select.get('.select__label').text() === label)
  if (!found) throw new Error(`No “${label}” dropdown`)
  return found
}

/** Text of the option a `BaseSelect` currently shows as chosen. */
export const chosen = (wrapper: ReturnType<typeof render>, label: string): string =>
  dropdown(wrapper, label).get('.select__value').text()

/** Opens the `BaseSelect` with that label and clicks the option with that text. */
export async function choose(
  wrapper: ReturnType<typeof render>,
  label: string,
  option: string,
): Promise<void> {
  const select = dropdown(wrapper, label)
  await select.get('[role="combobox"]').trigger('click')
  const item = select.findAll('[role="option"]').find((o) => o.text() === option)
  if (!item) throw new Error(`No “${option}” option in “${label}”`)
  await item.trigger('click')
}
