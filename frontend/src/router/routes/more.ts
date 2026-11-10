import type { RouteRecordRaw } from 'vue-router'

import MoreView from '../../views/MoreView.vue'

/** “More”: the remaining sections on mobile; the navigation itself links to it. */
export default [{ path: '/more', name: 'more', component: MoreView }] satisfies RouteRecordRaw[]
