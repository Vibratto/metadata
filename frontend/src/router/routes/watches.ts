import type { RouteRecordRaw } from 'vue-router'

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
  // Creating and editing happen in a dialog; these keep old links working.
  { path: '/watches/new', redirect: { name: 'watches', query: { new: '1' } } },
  { path: '/watches/:id(\\d+)', name: 'watch', component: WatchView },
  {
    path: '/watches/:id(\\d+)/edit',
    redirect: (to) => ({ name: 'watch', params: to.params, query: { edit: '1' } }),
  },
] satisfies RouteRecordRaw[]
