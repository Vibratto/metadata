import type { RouteRecordRaw } from 'vue-router'

import UtilitiesView from '../../views/UtilitiesView.vue'

/** Route of the library maintenance utilities. */
export default [
  {
    path: '/utilities',
    name: 'utilities',
    component: UtilitiesView,
    meta: {
      navLabel: 'utilities.nav',
      navGroup: 'more',
      navOrder: 50,
      navSection: 'admin',
      navIcon: 'wrench',
    },
  },
] satisfies RouteRecordRaw[]
