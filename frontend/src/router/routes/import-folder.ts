import type { RouteRecordRaw } from 'vue-router'

import FolderImportView from '../../views/FolderImportView.vue'

/** Import a music folder; no navigation entry of its own (reached from Import). */
export default [
  { path: '/import/folder', name: 'import-folder', component: FolderImportView },
] satisfies RouteRecordRaw[]
