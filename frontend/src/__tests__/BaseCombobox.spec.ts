import { flushPromises } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import BaseCombobox, { type ComboOption } from '../components/BaseCombobox.vue'
import { render } from './helpers'

const ALL: ComboOption[] = [
  { value: '1', label: 'Daft Punk' },
  { value: '2', label: 'Dua Lipa' },
  { value: '3', label: 'Bad Bunny' },
]

function mount(
  search = vi.fn(async (text: string) =>
    ALL.filter((o) => o.label.toLowerCase().includes(text.toLowerCase())),
  ),
) {
  const wrapper = render(BaseCombobox, {
    props: {
      label: 'Artist',
      search,
      delay: 0,
      modelValue: [] as ComboOption[],
      'onUpdate:modelValue': (v: ComboOption[]) => wrapper.setProps({ modelValue: v }),
    },
  })
  return { wrapper, search }
}

describe('BaseCombobox', () => {
  it('has the ARIA roles of a combobox with a listbox', async () => {
    const { wrapper } = mount()
    const input = wrapper.get('input')
    expect(input.attributes('role')).toBe('combobox')
    expect(input.attributes('aria-expanded')).toBe('false')
    await input.trigger('focus')
    await flushPromises()
    expect(input.attributes('aria-expanded')).toBe('true')
    expect(input.attributes('aria-controls')).toBe(wrapper.get('[role=listbox]').attributes('id'))
    expect(wrapper.findAll('[role=option]')).toHaveLength(3)
  })

  it('searches the server once typing stops', async () => {
    const { wrapper, search } = mount()
    await wrapper.get('input').setValue('du')
    await vi.waitFor(() => expect(search).toHaveBeenLastCalledWith('du', expect.any(AbortSignal)))
    await flushPromises()
    expect(wrapper.findAll('[role=option]').map((o) => o.text())).toEqual(['Dua Lipa'])
  })

  it('accepts several values as chips removed with the x', async () => {
    const { wrapper } = mount()
    await wrapper.get('input').trigger('focus')
    await flushPromises()
    await wrapper.findAll('[role=option]')[0]!.trigger('mousedown')
    await wrapper.get('input').trigger('focus')
    await wrapper.get('input').setValue('')
    await flushPromises()
    await wrapper.findAll('[role=option]')[0]!.trigger('mousedown')
    expect(wrapper.findAll('.chip span').map((c) => c.text())).toEqual(['Daft Punk', 'Dua Lipa'])
    await wrapper.get('.chip button').trigger('click')
    expect(wrapper.findAll('.chip span').map((c) => c.text())).toEqual(['Dua Lipa'])
  })

  it('works with the keyboard: arrows, Enter and Escape', async () => {
    const { wrapper } = mount()
    const input = wrapper.get('input')
    await input.trigger('focus')
    await flushPromises()
    expect(input.attributes('aria-activedescendant')).toBe(
      wrapper.findAll('[role=option]')[0]!.attributes('id'),
    )
    await input.trigger('keydown', { key: 'ArrowDown' })
    await input.trigger('keydown', { key: 'Enter' })
    expect(wrapper.findAll('.chip span').map((c) => c.text())).toEqual(['Dua Lipa'])
    await input.trigger('keydown', { key: 'Escape' })
    expect(input.attributes('aria-expanded')).toBe('false')
  })

  it('announces the number of results and the empty state', async () => {
    const { wrapper } = mount()
    await wrapper.get('input').trigger('focus')
    await flushPromises()
    expect(wrapper.get('[aria-live=polite]').text()).toBe('3 results')
    await wrapper.get('input').setValue('zzz')
    await vi.waitFor(() => expect(wrapper.get('[aria-live=polite]').text()).toBe('No results'))
  })

  it('the slow answer of an old search does not overwrite the new one', async () => {
    const resolvers: Record<string, (o: ComboOption[]) => void> = {}
    const search = vi.fn(
      (text: string) => new Promise<ComboOption[]>((resolve) => (resolvers[text] = resolve)),
    )
    const { wrapper } = mount(search)
    await wrapper.get('input').setValue('a')
    await vi.waitFor(() => expect(search).toHaveBeenCalledTimes(1))
    await wrapper.get('input').setValue('ab')
    await vi.waitFor(() => expect(search).toHaveBeenCalledTimes(2))
    resolvers['ab']!([ALL[1]!])
    await flushPromises()
    resolvers['a']!([ALL[0]!])
    await flushPromises()
    expect(wrapper.findAll('[role=option]').map((o) => o.text())).toEqual(['Dua Lipa'])
  })
})
