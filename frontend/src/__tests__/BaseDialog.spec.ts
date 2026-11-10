import { describe, expect, it } from 'vitest'

import BaseDialog from '../components/BaseDialog.vue'
import { render } from './helpers'

describe('BaseDialog', () => {
  it('is narrow by default and takes wide content with size="wide"', () => {
    const normal = render(BaseDialog, { props: { title: 'A', modelValue: false } })
    expect(normal.get('dialog').classes()).not.toContain('dialog--wide')
    const wide = render(BaseDialog, { props: { title: 'A', modelValue: false, size: 'wide' } })
    expect(wide.get('dialog').classes()).toContain('dialog--wide')
  })
})
