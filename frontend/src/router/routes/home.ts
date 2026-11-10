import type { RouteRecordRaw } from 'vue-router'

import HomeView from '../../views/HomeView.vue'

/** Home screen routes. */
export default [{ path: '/', name: 'home', component: HomeView }] satisfies RouteRecordRaw[]
