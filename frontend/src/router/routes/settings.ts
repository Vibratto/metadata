import type { RouteRecordRaw } from 'vue-router'

import SettingsView from '../../views/SettingsView.vue'

/** Global settings: they affect the whole server. */
export default [
  {
    path: '/settings',
    name: 'settings',
    component: SettingsView,
    meta: {
      navLabel: 'settings.nav',
      navGroup: 'more',
      navOrder: 80,
      navSection: 'admin',
      navIcon: 'sliders',
    },
  },
] satisfies RouteRecordRaw[]
