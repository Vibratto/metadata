<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { api } from '../api/client'
import { errorText } from '../api/errors'
import type { components } from '../api/schema'
import BaseAlert from '../components/BaseAlert.vue'
import BaseButton from '../components/BaseButton.vue'
import BaseDialog from '../components/BaseDialog.vue'
import ResponsiveList from '../components/ResponsiveList.vue'
import { usePagedList } from '../composables/usePagedList'

type BlockedItem = components['schemas']['BlockedItem']

/**
 * Blocked items, with unblocking after confirmation. Only administrators may unblock.
 */
const { t, d } = useI18n()
const list = usePagedList<BlockedItem>('/api/v1/catalog/blocked/')

const columns = computed(() => [
  { key: 'kind', label: t('blocked.columns.kind') },
  { key: 'name', label: t('blocked.columns.name') },
  { key: 'external_id', label: t('blocked.columns.external_id') },
  { key: 'created_at', label: t('blocked.columns.created_at') },
  { key: 'actions', label: t('blocked.columns.actions') },
])

const pending = ref<BlockedItem | null>(null)
const confirming = ref(false)
const message = ref('')
const error = ref('')

function ask(item: BlockedItem): void {
  pending.value = item
  confirming.value = true
}

async function unblock(): Promise<void> {
  const item = pending.value as BlockedItem
  confirming.value = false
  message.value = error.value = ''
  try {
    await api(`/api/v1/catalog/blocked/${item.id}/`, { method: 'DELETE' })
    message.value = t('blocked.done')
    await list.reload()
  } catch (e) {
    error.value = errorText(e, t)
  }
}
</script>

<template>
  <section class="blocked">
    <h1>{{ t('blocked.title') }}</h1>
    <p>{{ t('blocked.intro') }}</p>
    <BaseAlert v-if="message" variant="success">{{ message }}</BaseAlert>
    <BaseAlert v-if="error" variant="error">{{ error }}</BaseAlert>
    <BaseAlert v-if="list.error" variant="error">{{ list.error }}</BaseAlert>

    <p v-if="list.loading" class="blocked__loading" aria-live="polite">
      {{ t('blocked.loading') }}
    </p>
    <p v-else-if="!list.error && list.items.length === 0">{{ t('blocked.empty') }}</p>
    <ResponsiveList v-else-if="!list.error" :columns="columns" :rows="list.items" row-key="id">
      <template #cell-kind="{ row }">{{ t(`blocked.kind.${row.kind}`) }}</template>
      <template #cell-created_at="{ row }">
        <time :datetime="row.created_at">{{ d(new Date(row.created_at)) }}</time>
      </template>
      <template #cell-actions="{ row }">
        <BaseButton variant="danger" @click="ask(row)">{{ t('blocked.unblock') }}</BaseButton>
      </template>
    </ResponsiveList>

    <nav class="blocked__pager" :aria-label="t('blocked.pager.label')">
      <BaseButton
        variant="secondary"
        :disabled="!list.hasPrevious"
        @click="list.goTo(list.page - 1)"
      >
        {{ t('blocked.pager.previous') }}
      </BaseButton>
      <span>{{ t('blocked.pager.page', { page: list.page }) }}</span>
      <BaseButton variant="secondary" :disabled="!list.hasNext" @click="list.goTo(list.page + 1)">
        {{ t('blocked.pager.next') }}
      </BaseButton>
    </nav>

    <BaseDialog v-model="confirming" :title="t('blocked.confirm.title')">
      <p>{{ t('blocked.confirm.text', { name: pending?.name || pending?.external_id }) }}</p>
      <BaseButton variant="danger" class="blocked__confirm" @click="unblock">
        {{ t('blocked.unblock') }}
      </BaseButton>
    </BaseDialog>
  </section>
</template>

<style scoped>
.blocked {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}
.blocked__pager {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
}
</style>
