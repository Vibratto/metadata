<script setup lang="ts">
import { onMounted, ref, watch as watchValue } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import { api } from '../../api/client'
import { errorText } from '../../api/errors'
import type { components } from '../../api/schema'
import BaseAlert from '../../components/BaseAlert.vue'
import BaseButton from '../../components/BaseButton.vue'
import BaseDialog from '../../components/BaseDialog.vue'
import JobRunPanel from '../../components/JobRunPanel.vue'
import ResponsiveList from '../../components/ResponsiveList.vue'
import { useJobRun } from '../../composables/useJobRun'
import { usePagedList } from '../../composables/usePagedList'

type Watch = components['schemas']['Watch']
type WatchRun = components['schemas']['WatchRun']

/**
 * Watch detail: its settings, "check now" (`watch_check` job), check history and a
 * confirmed delete.
 */
const { t, locale } = useI18n()
const route = useRoute()
const router = useRouter()
const id = route.params.id as string

const watch = ref<Watch | null>(null)
const error = ref('')
const confirming = ref(false)
const runs = usePagedList<WatchRun>(`/api/v1/watches/${id}/runs/`)
const job = useJobRun()

const columns = [
  { key: 'finished_at', label: t('watches.runs.finished') },
  { key: 'status', label: t('watches.runs.status') },
  { key: 'found', label: t('watches.runs.found') },
  { key: 'detail', label: t('watches.runs.detail') },
]

onMounted(async () => {
  try {
    watch.value = await api<Watch>(`/api/v1/watches/${id}/`)
  } catch (e) {
    error.value = errorText(e, t)
  }
})

// The check leaves its result in the history when it closes: reload then.
watchValue(
  () => job.active,
  (active, was) => {
    if (was && !active) void runs.reload()
  },
)

async function remove(): Promise<void> {
  confirming.value = false
  error.value = ''
  try {
    await api(`/api/v1/watches/${id}/`, { method: 'DELETE' })
    await router.push({ name: 'watches' })
  } catch (e) {
    error.value = errorText(e, t)
  }
}
</script>

<template>
  <section class="watch">
    <RouterLink :to="{ name: 'watches' }">{{ t('watches.detail.back') }}</RouterLink>
    <BaseAlert v-if="error" variant="error">{{ error }}</BaseAlert>
    <template v-if="watch">
      <h1>{{ watch.name }}</h1>
      <p>
        {{
          [
            t(watch.enabled ? 'watches.enabled' : 'watches.disabled'),
            t('watches.hours', { n: watch.interval_hours }, Number(watch.interval_hours)),
            ...(watch.auto_download ? [t('watches.autoDownload')] : []),
          ].join(' · ')
        }}
      </p>
      <p>{{ watch.artists.map((a) => a.name).join(', ') }}</p>
      <div class="watch__actions">
        <BaseButton
          :disabled="job.active"
          @click="job.start('watch_check', { watch_id: watch.id })"
        >
          {{ t('watches.detail.check') }}
        </BaseButton>
        <RouterLink class="watch__edit" :to="{ name: 'watches-edit', params: { id } }">
          {{ t('watches.detail.edit') }}
        </RouterLink>
        <BaseButton variant="danger" @click="confirming = true">
          {{ t('watches.detail.delete') }}
        </BaseButton>
      </div>
      <JobRunPanel :job="job" />
      <BaseDialog
        v-model="confirming"
        :title="t('watches.detail.confirmTitle', { name: watch.name })"
      >
        <p>{{ t('watches.detail.confirmText') }}</p>
        <BaseButton variant="danger" @click="remove">{{ t('watches.detail.confirm') }}</BaseButton>
      </BaseDialog>
    </template>

    <h2>{{ t('watches.detail.history') }}</h2>
    <BaseAlert v-if="runs.error" variant="error">{{ runs.error }}</BaseAlert>
    <ResponsiveList :columns="columns" :rows="runs.items" row-key="id">
      <template #cell-finished_at="{ row }">
        {{ new Date(row.finished_at).toLocaleString(locale) }}
      </template>
      <template #cell-status="{ row }">{{ t(`watches.runs.${row.status}`) }}</template>
    </ResponsiveList>
    <nav v-if="runs.hasPrevious || runs.hasNext" class="watch__pages">
      <BaseButton
        variant="secondary"
        :disabled="!runs.hasPrevious"
        @click="runs.goTo(runs.page - 1)"
      >
        {{ t('watches.previous') }}
      </BaseButton>
      <BaseButton variant="secondary" :disabled="!runs.hasNext" @click="runs.goTo(runs.page + 1)">
        {{ t('watches.next') }}
      </BaseButton>
    </nav>
  </section>
</template>

<style scoped>
.watch {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}
.watch__actions,
.watch__pages {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-2);
}
.watch__pages {
  justify-content: space-between;
}
.watch__edit {
  display: inline-flex;
  align-items: center;
  min-height: var(--touch-target);
  padding: 0 var(--space-3);
}
</style>
