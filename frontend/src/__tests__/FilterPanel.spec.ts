import { describe, expect, it } from 'vitest'

import FilterPanel from '../components/FilterPanel.vue'
import { render } from './helpers'

describe('FilterPanel', () => {
  it('starts collapsed on mobile and expands with the button', async () => {
    const w = render(FilterPanel, { slots: { default: '<input id="q" />' } })
    const toggle = w.get('button')
    expect(toggle.text()).toBe('Filters')
    expect(toggle.attributes('aria-expanded')).toBe('false')
    expect(w.get(`#${toggle.attributes('aria-controls')}`).classes()).not.toContain('is-open')
    await toggle.trigger('click')
    expect(toggle.attributes('aria-expanded')).toBe('true')
    expect(w.get('.filters__body').classes()).toContain('is-open')
    expect(w.find('#q').exists()).toBe(true)
  })

  it('translates to Spanish', () => {
    expect(render(FilterPanel, {}, 'es').get('button').text()).toBe('Filtros')
  })
})
