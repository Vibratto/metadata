import { describe, expect, it } from 'vitest'
import { ref } from 'vue'

import BaseSelect from '../components/BaseSelect.vue'
import { render } from './helpers'

const options = [
  { value: 'mp3', label: 'MP3' },
  { value: 'flac', label: 'FLAC' },
  { value: 'opus', label: 'Opus' },
  { value: 'ogg', label: 'Ogg' },
]

/** Mounts the select inside a host that keeps the value, as `v-model` would. */
function mount(initial = 'mp3', props: Record<string, unknown> = {}) {
  const value = ref(initial)
  const wrapper = render(
    {
      components: { BaseSelect },
      setup: () => ({ value, options, props }),
      template:
        '<BaseSelect v-model="value" label="Format" :options="options" v-bind="props" /><button id="after">after</button>',
    },
    { attachTo: document.body },
  )
  const box = wrapper.get('[role="combobox"]')
  const key = (name: string) => box.trigger('keydown', { key: name })
  const items = () => wrapper.findAll('[role="option"]')
  const active = () =>
    items()
      .find((o) => o.classes('is-active'))
      ?.text()
  const open = () => box.attributes('aria-expanded') === 'true'
  return { wrapper, value, box, key, items, active, open }
}

describe('BaseSelect', () => {
  it('shows the label and the chosen option, closed', () => {
    const { wrapper, box, open } = mount('flac')
    expect(wrapper.get('.select__label').text()).toBe('Format')
    expect(box.text()).toBe('FLAC')
    expect(open()).toBe(false)
    expect(wrapper.get('[role="listbox"]').isVisible()).toBe(false)
    wrapper.unmount()
  })

  it('has the ARIA wiring of a select-only combobox', async () => {
    const { wrapper, box, items } = mount('flac')
    const list = wrapper.get('[role="listbox"]')
    expect(box.attributes('aria-haspopup')).toBe('listbox')
    expect(box.attributes('aria-controls')).toBe(list.attributes('id'))
    expect(box.attributes('tabindex')).toBe('0')
    const [labelId, valueId] = box.attributes('aria-labelledby')!.split(' ')
    expect(wrapper.get(`#${labelId}`).text()).toBe('Format')
    expect(wrapper.get(`#${valueId}`).text()).toBe('FLAC')
    expect(box.attributes('aria-activedescendant')).toBeUndefined()
    await box.trigger('click')
    expect(items().map((o) => o.attributes('aria-selected'))).toEqual([
      'false',
      'true',
      'false',
      'false',
    ])
    expect(box.attributes('aria-activedescendant')).toBe(items()[1]!.attributes('id'))
    wrapper.unmount()
  })

  it('opens with a click, highlights the chosen option and picks another one', async () => {
    const { wrapper, value, box, items, active, open } = mount('flac')
    await box.trigger('click')
    expect(open()).toBe(true)
    expect(active()).toBe('FLAC')
    await items()[2]!.trigger('click')
    expect(value.value).toBe('opus')
    expect(box.text()).toBe('Opus')
    expect(open()).toBe(false)
    wrapper.unmount()
  })

  it('a second click closes it without changing the value', async () => {
    const { wrapper, value, box, open } = mount()
    await box.trigger('click')
    await box.trigger('click')
    expect(open()).toBe(false)
    expect(value.value).toBe('mp3')
    wrapper.unmount()
  })

  it('hovering an option highlights it', async () => {
    const { wrapper, box, items, active } = mount()
    await box.trigger('click')
    await items()[3]!.trigger('mousemove')
    expect(active()).toBe('Ogg')
    wrapper.unmount()
  })

  it.each(['Enter', ' ', 'ArrowDown', 'ArrowUp'])('opens with the “%s” key', async (name) => {
    const { wrapper, key, active, open } = mount('flac')
    await key(name)
    expect(open()).toBe(true)
    expect(active()).toBe('FLAC')
    wrapper.unmount()
  })

  it('moves with the arrows without leaving the list, and Enter picks', async () => {
    const { wrapper, value, key, active, open } = mount()
    await key('ArrowDown')
    await key('ArrowUp')
    expect(active()).toBe('MP3')
    await key('ArrowDown')
    await key('ArrowDown')
    expect(active()).toBe('Opus')
    await key('ArrowDown')
    await key('ArrowDown')
    expect(active()).toBe('Ogg')
    await key('Enter')
    expect(value.value).toBe('ogg')
    expect(open()).toBe(false)
    wrapper.unmount()
  })

  it('Home and End jump to the first and last option, and Space picks', async () => {
    const { wrapper, value, key, active } = mount('flac')
    await key('End')
    expect(active()).toBe('Ogg')
    await key('Home')
    expect(active()).toBe('MP3')
    await key(' ')
    expect(value.value).toBe('mp3')
    wrapper.unmount()
  })

  it('Escape closes without choosing and does not reach a surrounding dialog', async () => {
    const { wrapper, value, box, key, open } = mount()
    await key('ArrowDown')
    await key('ArrowDown')
    const event = new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true })
    let bubbled = false
    document.body.addEventListener('keydown', () => (bubbled = true), { once: true })
    box.element.dispatchEvent(event)
    await wrapper.vm.$nextTick()
    expect(open()).toBe(false)
    expect(value.value).toBe('mp3')
    expect(event.defaultPrevented).toBe(true)
    expect(bubbled).toBe(false)
    wrapper.unmount()
  })

  it('Escape while closed is left alone, so a dialog can still close', async () => {
    const { wrapper, box } = mount()
    const event = new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true })
    box.element.dispatchEvent(event)
    expect(event.defaultPrevented).toBe(false)
    wrapper.unmount()
  })

  it('Tab closes the list and keeps the value', async () => {
    const { wrapper, value, key, open } = mount()
    await key('ArrowDown')
    await key('ArrowDown')
    await key('Tab')
    expect(open()).toBe(false)
    expect(value.value).toBe('mp3')
    wrapper.unmount()
  })

  it('a letter changes the value while closed, cycling through the matches', async () => {
    const { wrapper, value, key, open } = mount()
    await key('o')
    expect(value.value).toBe('opus')
    await key('O')
    expect(value.value).toBe('ogg')
    await key('o')
    expect(value.value).toBe('opus')
    await key('x')
    expect(value.value).toBe('opus')
    expect(open()).toBe(false)
    wrapper.unmount()
  })

  it('a letter moves the highlight while open, and shortcuts are ignored', async () => {
    const { wrapper, value, box, key, active } = mount()
    await key('ArrowDown')
    await key('f')
    expect(active()).toBe('FLAC')
    await box.trigger('keydown', { key: 'o', ctrlKey: true })
    expect(active()).toBe('FLAC')
    expect(value.value).toBe('mp3')
    wrapper.unmount()
  })

  it('closes when focus leaves it, but not when it moves inside', async () => {
    const { wrapper, box, open } = mount()
    await box.trigger('click')
    await box.trigger('focusout', { relatedTarget: wrapper.get('[role="listbox"]').element })
    expect(open()).toBe(true)
    await box.trigger('focusout', { relatedTarget: wrapper.get('#after').element })
    expect(open()).toBe(false)
    wrapper.unmount()
  })

  it('opens upwards when there is no room below', async () => {
    const { wrapper, box } = mount()
    const root = wrapper.get('.select').element
    root.getBoundingClientRect = () => ({ top: 600, bottom: 644 }) as DOMRect
    await box.trigger('click')
    expect(wrapper.get('[role="listbox"]').classes()).toContain('select__list--above')
    wrapper.unmount()
  })

  it('can hide its label and announce an error', () => {
    const { wrapper, box } = mount('mp3', { hideLabel: true, error: 'Invalid format.' })
    expect(wrapper.get('.select__label').classes()).toContain('sr-only')
    expect(box.attributes('aria-invalid')).toBe('true')
    expect(wrapper.get(`#${box.attributes('aria-describedby')}`).text()).toBe('Invalid format.')
    wrapper.unmount()
  })

  it('shows nothing chosen for a value that is not an option', async () => {
    const { wrapper, box, key, active } = mount('wav')
    expect(box.text()).toBe('')
    await key('ArrowDown')
    expect(active()).toBe('MP3')
    wrapper.unmount()
  })
})
