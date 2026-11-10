import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { createI18n } from 'vue-i18n'

import { messages } from '../locales'
import HomeView from '../views/HomeView.vue'

function render(locale: 'es' | 'en') {
  const i18n = createI18n({ legacy: false, locale, messages })
  return mount(HomeView, { global: { plugins: [i18n] } })
}

describe('HomeView', () => {
  it('shows the tagline in Spanish', () => {
    expect(render('es').text()).toContain('Tu biblioteca musical')
  })

  it('shows the tagline in English', () => {
    expect(render('en').text()).toContain('Your music library')
  })
})
