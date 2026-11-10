import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import BaseField from '../components/BaseField.vue'
import { render } from './helpers'

const mountSearch = (props: Record<string, unknown> = {}, locale = 'en') =>
  render(
    BaseField,
    {
      props: { label: 'Search', type: 'search', modelValue: '', ...props },
      attachTo: document.body,
    },
    locale,
  )

describe('BaseField search: clear button', () => {
  it('only shows when there is text, and never on non-search fields', async () => {
    const w = mountSearch()
    expect(w.find('button').exists()).toBe(false)
    await w.setProps({ modelValue: 'daft' })
    expect(w.get('button').attributes('aria-label')).toBe('Clear search')
    expect(w.get('button').attributes('type')).toBe('button')
    const text = render(BaseField, { props: { label: 'Name', modelValue: 'x' } })
    expect(text.find('button').exists()).toBe(false)
  })

  it('translates the label to Spanish', () => {
    expect(mountSearch({ modelValue: 'a' }, 'es').get('button').attributes('aria-label')).toBe(
      'Borrar búsqueda',
    )
  })

  it('clears the field, emits “clear” and returns focus to the field', async () => {
    const w = mountSearch({ modelValue: 'daft' })
    await w.get('button').trigger('click')
    expect(w.emitted('update:modelValue')?.at(-1)).toEqual([''])
    expect(w.emitted('clear')).toHaveLength(1)
    expect(document.activeElement).toBe(w.get('input').element)
  })
})

describe('BaseField search: debounce', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  it('without debounce it emits on every keystroke', async () => {
    const w = mountSearch()
    await w.get('input').setValue('d')
    expect(w.emitted('update:modelValue')).toEqual([['d']])
  })

  it('with debounce it waits for typing to stop and emits only the last value', async () => {
    const w = mountSearch({ debounce: 300 })
    await w.get('input').setValue('d')
    await w.get('input').setValue('da')
    vi.advanceTimersByTime(299)
    expect(w.emitted('update:modelValue')).toBeUndefined()
    vi.advanceTimersByTime(1)
    expect(w.emitted('update:modelValue')).toEqual([['da']])
  })

  it('Enter emits at once', async () => {
    const w = mountSearch({ debounce: 300 })
    await w.get('input').setValue('da')
    await w.get('input').trigger('keydown', { key: 'Enter' })
    expect(w.emitted('update:modelValue')).toEqual([['da']])
    vi.advanceTimersByTime(1000)
    expect(w.emitted('update:modelValue')).toHaveLength(1)
  })

  it('clearing with the “x” emits at once even if something is pending', async () => {
    const w = mountSearch({ debounce: 300, modelValue: 'da' })
    await w.get('input').setValue('dat')
    await w.get('button').trigger('click')
    expect(w.emitted('update:modelValue')).toEqual([['']])
    vi.advanceTimersByTime(1000)
    expect(w.emitted('update:modelValue')).toHaveLength(1)
  })
})
