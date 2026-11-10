import type { RouteRecordRaw } from 'vue-router'

import LogView from '../../views/log/LogView.vue'

/** Log: activity, jobs and technical logs; the tab lives in `?tab=`. */
export default [
  {
    path: '/log',
    name: 'log',
    component: LogView,
    meta: { navLabel: 'log.nav', navGroup: 'more', navOrder: 80, navIcon: 'history' },
  },
] satisfies RouteRecordRaw[]
