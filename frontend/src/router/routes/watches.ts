import type { RouteRecordRaw } from 'vue-router'

import WatchFormView from '../../views/watches/WatchFormView.vue'
import WatchesView from '../../views/watches/WatchesView.vue'
import WatchView from '../../views/watches/WatchView.vue'

/** Release watches: list, creation, detail with history and editing. */
export default [
  {
    path: '/watches',
    name: 'watches',
    component: WatchesView,
    meta: { navLabel: 'watches.nav', navGroup: 'main', navOrder: 40, navIcon: 'bell' },
  },
  { path: '/watches/new', name: 'watches-new', component: WatchFormView },
  { path: '/watches/:id(\\d+)', name: 'watch', component: WatchView },
  { path: '/watches/:id(\\d+)/edit', name: 'watches-edit', component: WatchFormView },
] satisfies RouteRecordRaw[]
