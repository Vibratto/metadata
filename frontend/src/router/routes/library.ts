import type { RouteRecordRaw } from 'vue-router'

import LibraryItemView from '../../views/library/LibraryItemView.vue'
import LibraryView from '../../views/library/LibraryView.vue'
import { KINDS } from '../../views/library/kinds'

/** Library: one list per tab and a page for each artist, album or track. */
export default [
  {
    path: '/library',
    name: 'library',
    component: LibraryView,
    meta: { navLabel: 'library.nav', navGroup: 'main', navOrder: 20, navIcon: 'disc' },
    // Other views (the Log) link to an item with `?tab=…&id=…&panel=history`.
    beforeEnter: (to) => {
      const { tab, id, panel } = to.query
      if (!KINDS.some((k) => k === tab) || typeof id !== 'string' || !/^\d+$/.test(id)) return true
      return {
        name: 'library-item',
        params: { kind: tab as string, id },
        hash: panel === 'history' ? '#history' : '',
      }
    },
  },
  {
    path: '/library/:kind(artists|albums|tracks)/:id(\\d+)',
    name: 'library-item',
    component: LibraryItemView,
  },
] satisfies RouteRecordRaw[]
