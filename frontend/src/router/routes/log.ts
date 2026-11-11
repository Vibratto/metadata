import type { RouteRecordRaw } from 'vue-router'

import LogView from '../../views/log/LogView.vue'

/** Activity: what was done in the application. */
export default [
  {
    path: '/log',
    name: 'log',
    component: LogView,
    meta: { navLabel: 'log.nav', navGroup: 'more', navOrder: 80, navIcon: 'history' },
  },
] satisfies RouteRecordRaw[]
