import type { RouteRecordRaw } from 'vue-router'

import ImportView from '../../views/ImportView.vue'

/** Import artists from YouTube Music. */
export default [
  {
    path: '/import',
    name: 'import',
    component: ImportView,
    meta: { navLabel: 'import.nav', navGroup: 'main', navOrder: 30, navIcon: 'import' },
  },
] satisfies RouteRecordRaw[]
