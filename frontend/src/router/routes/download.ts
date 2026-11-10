import type { RouteRecordRaw } from 'vue-router'

import DownloadView from '../../views/DownloadView.vue'

/** Route for downloading pending tracks. */
export default [
  {
    path: '/download',
    name: 'download',
    component: DownloadView,
    meta: { navLabel: 'download.nav', navGroup: 'main', navOrder: 40, navIcon: 'download' },
    // The list only shows pending tracks: the filter is fixed in the URL because
    // `usePagedList` sends the API only what is there.
    beforeEnter: (to) =>
      to.query.downloaded === 'false' || { ...to, query: { ...to.query, downloaded: 'false' } },
  },
] satisfies RouteRecordRaw[]
