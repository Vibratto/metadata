import type { RouteRecordRaw } from 'vue-router'

import LibraryBackupView from '../../views/LibraryBackupView.vue'

/** Library backup: no navigation entry, other views link to it. */
export default [
  {
    path: '/library/backup',
    name: 'library-backup',
    component: LibraryBackupView,
  },
] satisfies RouteRecordRaw[]
