<script setup lang="ts">
import { useI18n } from 'vue-i18n'

import BaseSelect from '../../components/BaseSelect.vue'

/**
 * Log filter dropdown with "All" (empty) as its first option.
 */
defineProps<{ label: string; options: { value: string; label: string }[] }>()
const model = defineModel<string>({ default: '' })
const { t } = useI18n()
</script>

<template>
  <BaseSelect
    v-model="model"
    :label="label"
    :options="[{ value: '', label: t('log.filters.any') }, ...options]"
  />
</template>
