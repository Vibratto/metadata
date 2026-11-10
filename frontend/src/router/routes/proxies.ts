import type { RouteRecordRaw } from 'vue-router'

import ProxiesView from '../../views/ProxiesView.vue'

/** Outgoing proxies route. */
export default [
  {
    path: '/proxies',
    name: 'proxies',
    component: ProxiesView,
    meta: {
      navLabel: 'proxies.nav',
      navGroup: 'more',
      navOrder: 60,
      navSection: 'admin',
      navIcon: 'globe',
    },
  },
] satisfies RouteRecordRaw[]
