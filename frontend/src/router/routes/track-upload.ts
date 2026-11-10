import type { RouteRecordRaw } from 'vue-router'

import TrackUploadView from '../../views/TrackUploadView.vue'

/** Manual upload of a track's audio; reached from the track, not from the menu. */
export default [
  {
    path: '/tracks/:id(\\d+)/upload',
    name: 'track-upload',
    component: TrackUploadView,
  },
] satisfies RouteRecordRaw[]
