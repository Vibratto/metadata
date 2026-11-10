import type { RouteRecordRaw } from 'vue-router'

import DashboardView from '../../views/DashboardView.vue'

/** Dashboard route. */
export default [
  {
    path: '/dashboard',
    name: 'dashboard',
    component: DashboardView,
    meta: { navLabel: 'dashboard.nav', navGroup: 'main', navOrder: 10, navIcon: 'panel' },
  },
] satisfies RouteRecordRaw[]
