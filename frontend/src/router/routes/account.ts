import type { RouteRecordRaw } from 'vue-router'

import AccountView from '../../views/AccountView.vue'

/** Account settings route. */
export default [
  {
    path: '/account',
    name: 'account',
    component: AccountView,
  },
] satisfies RouteRecordRaw[]
