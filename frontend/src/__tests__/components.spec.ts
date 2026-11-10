import { describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'

import BaseAlert from '../components/BaseAlert.vue'
import BaseButton from '../components/BaseButton.vue'
import BaseCheckbox from '../components/BaseCheckbox.vue'
import BaseDialog from '../components/BaseDialog.vue'
import BaseField from '../components/BaseField.vue'
import ProgressBar from '../components/ProgressBar.vue'
import ResponsiveList from '../components/ResponsiveList.vue'
import { render } from './helpers'

describe('BaseButton', () => {
  it('renders the slot, the variant and the type', () => {
    const w = render(BaseButton, {
      slots: { default: 'Save' },
      props: { variant: 'danger', type: 'submit' },
    })
    expect(w.text()).toBe('Save')
    expect(w.classes()).toContain('btn--danger')
    expect(w.attributes('type')).toBe('submit')
  })

  it('is primary and of type button by default', () => {
    const w = render(BaseButton)
    expect(w.classes()).toContain('btn--primary')
    expect(w.attributes('type')).toBe('button')
  })
})

describe('BaseField', () => {
  it('links label and field and updates the model', async () => {
    const w = render(BaseField, { props: { label: 'Username', modelValue: '' } })
    const input = w.get('input')
    expect(w.get('label').attributes('for')).toBe(input.attributes('id'))
    expect(input.attributes('type')).toBe('text')
    expect(input.attributes('aria-invalid')).toBeUndefined()
    await input.setValue('ana')
    expect(w.emitted('update:modelValue')?.[0]).toEqual(['ana'])
  })

  it('announces the error linked to the field', () => {
    const w = render(BaseField, {
      props: { label: 'Password', type: 'password', error: 'Obligatoria' },
    })
    const input = w.get('input')
    expect(input.attributes('aria-invalid')).toBe('true')
    expect(w.get(`#${input.attributes('aria-describedby')}`).text()).toBe('Obligatoria')
  })
})

describe('BaseCheckbox', () => {
  it('updates the model when the label is clicked', async () => {
    const w = render(BaseCheckbox, { props: { label: 'Recordarme', modelValue: false } })
    await w.get('input').setValue(true)
    expect(w.text()).toBe('Recordarme')
    expect(w.emitted('update:modelValue')?.[0]).toEqual([true])
  })
})

describe('BaseAlert', () => {
  it.each([
    ['error', 'alert'],
    ['warning', 'alert'],
    ['info', 'status'],
    ['success', 'status'],
  ] as const)('%s uses the %s role', (variant, role) => {
    expect(render(BaseAlert, { props: { variant } }).attributes('role')).toBe(role)
  })

  it('is informative by default', () => {
    expect(render(BaseAlert).classes()).toContain('alert--info')
  })
})

describe('ProgressBar', () => {
  it('exposes the value and the accessible name', () => {
    const w = render(ProgressBar, { props: { value: 42.4, label: 'Download' } })
    expect(w.attributes('aria-valuenow')).toBe('42')
    expect(w.attributes('aria-label')).toBe('Download')
  })

  it.each([
    [-5, '0'],
    [250, '100'],
  ])('acota %s a %s', (value, expected) => {
    expect(render(ProgressBar, { props: { value, label: 'x' } }).attributes('aria-valuenow')).toBe(
      expected,
    )
  })
})

describe('ResponsiveList', () => {
  const columns = [
    { key: 'name', label: 'Name' },
    { key: 'year', label: 'Year' },
  ]
  const rows = [{ id: 1, name: 'Kind of Blue', year: 1959 }]

  it('renders one row per item with the header of each cell', () => {
    const w = render(ResponsiveList, { props: { columns, rows, rowKey: 'id' } })
    expect(w.findAll('tbody tr')).toHaveLength(1)
    expect(w.findAll('td').map((td) => td.attributes('data-label'))).toEqual(['Name', 'Year'])
    expect(w.text()).toContain('Kind of Blue')
  })

  it('allows customising a cell', () => {
    const w = render(ResponsiveList, {
      props: { columns, rows, rowKey: 'id' },
      slots: { 'cell-year': '<template #cell-year="{ row }">Year {{ row.year }}</template>' },
    })
    expect(w.text()).toContain('Year 1959')
  })

  it('shows the empty list text in each language', () => {
    expect(render(ResponsiveList, { props: { columns, rows: [], rowKey: 'id' } }).text()).toBe(
      'Nothing to show.',
    )
    expect(
      render(ResponsiveList, { props: { columns, rows: [], rowKey: 'id' } }, 'es').text(),
    ).toBe('No hay nada que mostrar.')
  })
})

describe('BaseDialog', () => {
  // jsdom no implementa showModal/close de <dialog>.
  const showModal = vi.fn(function (this: HTMLDialogElement) {
    this.setAttribute('open', '')
  })
  const close = vi.fn(function (this: HTMLDialogElement) {
    this.removeAttribute('open')
  })
  Object.assign(HTMLDialogElement.prototype, { showModal, close })

  it('opens and closes the dialog following the model', async () => {
    const w = render(BaseDialog, {
      props: { title: 'Warning', modelValue: false },
      slots: { default: 'Contenido' },
      attachTo: document.body,
    })
    expect(showModal).not.toHaveBeenCalled()
    await w.setProps({ modelValue: true })
    await nextTick()
    expect(showModal).toHaveBeenCalledOnce()
    // Reopening while already open does not call showModal again.
    await w.setProps({ modelValue: true })
    await w.setProps({ modelValue: false })
    expect(close).toHaveBeenCalledOnce()
    await w.setProps({ modelValue: false })
    expect(close).toHaveBeenCalledOnce()
    w.unmount()
  })

  it('opens from the start if the model is already true', async () => {
    showModal.mockClear()
    const w = render(BaseDialog, {
      props: { title: 'Warning', modelValue: true },
      attachTo: document.body,
    })
    await nextTick()
    expect(showModal).toHaveBeenCalledOnce()
    w.unmount()
  })

  it('emits the close with the button and with the browser close event', async () => {
    const w = render(BaseDialog, { props: { title: 'Warning', modelValue: true } })
    expect(w.get('h2').text()).toBe('Warning')
    await w.get('button').trigger('click')
    expect(w.emitted('update:modelValue')).toEqual([[false]])
    // Esc: the browser closes the <dialog> and reports it with `close`.
    const esc = render(BaseDialog, { props: { title: 'Warning', modelValue: true } })
    await esc.get('dialog').trigger('close')
    expect(esc.emitted('update:modelValue')).toEqual([[false]])
  })
})
