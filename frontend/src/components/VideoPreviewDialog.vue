<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import type { VideoPreview } from '../composables/useVideoPreview'
import BaseAlert from './BaseAlert.vue'
import BaseDialog from './BaseDialog.vue'

/**
 * Modal with a track's video preview. The `<iframe>` only exists while the modal is open, so
 * closing it (button, `Esc` or outside click) stops the video; focus returns to the opener.
 */
const props = defineProps<{ preview: VideoPreview | null }>()
const emit = defineEmits<{ close: [] }>()
const { t } = useI18n()

const open = computed({
  get: () => props.preview !== null,
  set: (value) => {
    if (!value) emit('close')
  },
})
</script>

<template>
  <BaseDialog
    v-model="open"
    size="wide"
    :title="t('download.previewOf', { title: preview?.title ?? '' })"
  >
    <template v-if="preview">
      <BaseAlert v-if="preview.error" variant="error">{{ preview.error }}</BaseAlert>
      <p v-else-if="!preview.video">{{ t('download.searching') }}</p>
      <template v-else>
        <iframe
          class="video-preview"
          :src="preview.video.embed_url"
          :title="preview.title"
          allow="encrypted-media; picture-in-picture"
          referrerpolicy="strict-origin-when-cross-origin"
          allowfullscreen
        ></iframe>
      </template>
    </template>
  </BaseDialog>
</template>

<style scoped>
.video-preview {
  width: 100%;
  aspect-ratio: 16 / 9;
  border: 0;
  border-radius: var(--radius);
}
</style>
