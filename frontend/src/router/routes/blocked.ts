import type { RouteRecordRaw } from 'vue-router'

import BlockedView from '../../views/BlockedView.vue'

/** Blocked items route. */
export default [
  {
    path: '/blocked',
    name: 'blocked',
    component: BlockedView,
    meta: { navLabel: 'blocked.nav', navGroup: 'more', navOrder: 30, navIcon: 'block' },
  },
] satisfies RouteRecordRaw[]
