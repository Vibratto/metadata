<script setup lang="ts">
import { computed, onMounted, ref, useId } from 'vue'
import { useI18n } from 'vue-i18n'

import { api, ApiError } from '../api/client'
import { errorText } from '../api/errors'
import type { components } from '../api/schema'
import BaseAlert from '../components/BaseAlert.vue'
import BaseButton from '../components/BaseButton.vue'
import BaseCheckbox from '../components/BaseCheckbox.vue'
import BaseDialog from '../components/BaseDialog.vue'
import BaseField from '../components/BaseField.vue'
import ResponsiveList from '../components/ResponsiveList.vue'

type Proxy = components['schemas']['Proxy']
type ProxyCheck = components['schemas']['ProxyCheck']
type IpVersion = components['schemas']['IpVersionEnum']
type Scheme = 'http' | 'https' | 'socks5' | 'socks5h'
type BulkResult = {
  created: number
  duplicates: { line: number }[]
  invalid: { line: number; reason: string }[]
}

const BASE = '/api/v1/proxies/'

/**
 * Outbound proxies (administrators only): list with status, IP version and counters, create,
 * edit, enable or disable, delete with confirmation and connection test.
 */
const { t, te, locale } = useI18n()
const ipVersionId = useId()
const bulkTextId = useId()
const bulkIpVersionId = useId()
const bulkSchemeId = useId()

const SCHEMES: Scheme[] = ['http', 'https', 'socks5', 'socks5h']

const IP_VERSIONS: Record<IpVersion, string> = { ipv4: 'IPv4', ipv6: 'IPv6' }

const proxies = ref<Proxy[]>([])
const message = ref('')
const error = ref('')

const columns = computed(() => [
  { key: 'url', label: t('proxies.columns.url') },
  { key: 'enabled', label: t('proxies.columns.status') },
  { key: 'success_count', label: t('proxies.columns.success') },
  { key: 'failure_count', label: t('proxies.columns.failure') },
  { key: 'last_used_at', label: t('proxies.columns.lastUsed') },
  { key: 'ip_version', label: t('proxies.columns.ipVersion') },
  { key: 'actions', label: t('proxies.columns.actions') },
])

// Create and edit form: `editing` is null when creating.
const formOpen = ref(false)
const editing = ref<Proxy | null>(null)
const url = ref('')
const ipVersion = ref<IpVersion>('ipv4')
const enabled = ref(true)
const urlError = ref('')
const formError = ref('')

// Bulk add: a pasted list, one proxy per line.
const bulkOpen = ref(false)
const bulkText = ref('')
const bulkIpVersion = ref<IpVersion>('ipv4')
const bulkScheme = ref<Scheme>('http')
const bulkEnabled = ref(true)
const bulkError = ref('')
const bulkResult = ref<BulkResult | null>(null)

const toDelete = ref<Proxy | null>(null)
const deleteOpen = ref(false)

function when(value: string | null): string {
  return value ? new Date(value).toLocaleString(locale.value) : t('proxies.never')
}

/** Runs an action showing its success or its error, never both. */
async function run(action: () => Promise<string>): Promise<void> {
  message.value = ''
  error.value = ''
  try {
    message.value = await action()
  } catch (e) {
    error.value = errorText(e, t)
  }
}

const load = () =>
  run(async () => {
    proxies.value = await api<Proxy[]>(BASE)
    return ''
  })

function openForm(proxy: Proxy | null): void {
  editing.value = proxy
  url.value = proxy?.url ?? ''
  ipVersion.value = proxy?.ip_version ?? 'ipv4'
  enabled.value = proxy?.enabled ?? true
  urlError.value = formError.value = ''
  formOpen.value = true
}

async function save(): Promise<void> {
  urlError.value = formError.value = ''
  const proxy = editing.value
  const body = { url: url.value, ip_version: ipVersion.value, enabled: enabled.value }
  try {
    await (proxy
      ? api(`${BASE}${proxy.id}/`, { method: 'PATCH', body })
      : api(BASE, { method: 'POST', body }))
  } catch (e) {
    // `errorText` rethrows anything that is not an API error. The address error goes next
    // to its field; any other, above the form.
    const text = errorText(e, t)
    const field = ((e as ApiError).body as { url?: string[] } | null)?.url
    if (field) urlError.value = field.join(' ')
    else formError.value = text
    return
  }
  formOpen.value = false
  await load()
  message.value = t(proxy ? 'proxies.done.updated' : 'proxies.done.created')
}

const toggle = (proxy: Proxy) =>
  run(async () => {
    const saved = await api<Proxy>(`${BASE}${proxy.id}/`, {
      method: 'PATCH',
      body: { enabled: !proxy.enabled },
    })
    proxies.value = proxies.value.map((p) => (p.id === saved.id ? saved : p))
    return t('proxies.done.updated')
  })

function openBulk(): void {
  bulkText.value = bulkError.value = ''
  bulkResult.value = null
  bulkOpen.value = true
}

function reasonText(reason: string): string {
  const key = `proxies.bulk.reasons.${reason}`
  return te(key) ? t(key) : reason
}

async function saveBulk(): Promise<void> {
  bulkError.value = ''
  bulkResult.value = null
  const body = {
    text: bulkText.value,
    ip_version: bulkIpVersion.value,
    default_scheme: bulkScheme.value,
    enabled: bulkEnabled.value,
  }
  let result: BulkResult
  try {
    result = await api<BulkResult>(`${BASE}bulk/`, { method: 'POST', body })
  } catch (e) {
    // With no valid line the API answers 400 with per-line detail: shown the same way.
    const failed = e instanceof ApiError ? (e.body as Partial<BulkResult> | null) : null
    if (!failed || !Array.isArray(failed.invalid)) {
      bulkError.value = errorText(e, t)
      return
    }
    result = failed as BulkResult
  }
  bulkResult.value = result
  if (result.created > 0) await load()
}

function askDelete(proxy: Proxy): void {
  toDelete.value = proxy
  deleteOpen.value = true
}

const confirmDelete = () =>
  run(async () => {
    const proxy = toDelete.value as Proxy
    deleteOpen.value = false
    await api(`${BASE}${proxy.id}/`, { method: 'DELETE' })
    proxies.value = proxies.value.filter((p) => p.id !== proxy.id)
    return t('proxies.done.deleted')
  })

const check = (proxy: Proxy) =>
  run(async () => {
    const result = await api<ProxyCheck>(`${BASE}${proxy.id}/check/`, { method: 'POST' })
    const params = { url: proxy.url, status: result.status_code }
    if (result.ok) return t('proxies.check.ok', params)
    // The API answers OK even if the proxy fails: the failure is reported as an error.
    error.value = t(
      result.status_code === null ? 'proxies.check.failed' : 'proxies.check.failedStatus',
      params,
    )
    return ''
  })

onMounted(load)
</script>

<template>
  <section class="proxies">
    <h1>{{ t('proxies.title') }}</h1>
    <p>{{ t('proxies.intro') }}</p>
    <BaseAlert v-if="message" variant="success">{{ message }}</BaseAlert>
    <BaseAlert v-if="error" variant="error">{{ error }}</BaseAlert>

    <div>
      <BaseButton @click="openForm(null)">{{ t('proxies.add') }}</BaseButton>
      <BaseButton variant="secondary" @click="openBulk">{{ t('proxies.bulk.add') }}</BaseButton>
    </div>

    <ResponsiveList :columns="columns" :rows="proxies" row-key="id">
      <template #cell-url="{ row }">
        <span class="proxies__url">{{ row.url }}</span>
      </template>
      <template #cell-enabled="{ row }">
        {{ t(row.enabled ? 'proxies.status.enabled' : 'proxies.status.disabled') }}
      </template>
      <template #cell-last_used_at="{ row }">{{ when(row.last_used_at) }}</template>
      <template #cell-ip_version="{ row }">{{ IP_VERSIONS[row.ip_version as IpVersion] }}</template>
      <template #cell-actions="{ row }">
        <div class="proxies__actions">
          <BaseButton variant="secondary" @click="openForm(row)">
            {{ t('proxies.actions.edit') }}
          </BaseButton>
          <BaseButton variant="secondary" @click="toggle(row)">
            {{ t(row.enabled ? 'proxies.actions.disable' : 'proxies.actions.enable') }}
          </BaseButton>
          <BaseButton variant="secondary" @click="check(row)">
            {{ t('proxies.actions.check') }}
          </BaseButton>
          <BaseButton variant="danger" @click="askDelete(row)">
            {{ t('proxies.actions.delete') }}
          </BaseButton>
        </div>
      </template>
    </ResponsiveList>

    <BaseDialog
      v-model="formOpen"
      :title="t(editing ? 'proxies.form.editTitle' : 'proxies.form.createTitle')"
    >
      <form name="proxy" class="proxies__form" @submit.prevent="save">
        <BaseAlert v-if="formError" variant="error">{{ formError }}</BaseAlert>
        <BaseField v-model="url" :label="t('proxies.form.url')" type="url" :error="urlError" />
        <div class="proxies__select">
          <label :for="ipVersionId">{{ t('proxies.form.ipVersion') }}</label>
          <select :id="ipVersionId" v-model="ipVersion">
            <option v-for="(label, value) in IP_VERSIONS" :key="value" :value="value">
              {{ label }}
            </option>
          </select>
        </div>
        <BaseCheckbox v-model="enabled" :label="t('proxies.form.enabled')" />
        <BaseButton type="submit">{{ t('proxies.form.save') }}</BaseButton>
      </form>
    </BaseDialog>

    <BaseDialog v-model="deleteOpen" :title="t('proxies.delete.title')">
      <p>{{ t('proxies.delete.confirm', { url: toDelete?.url }) }}</p>
      <BaseButton variant="danger" @click="confirmDelete">
        {{ t('proxies.delete.submit') }}
      </BaseButton>
    </BaseDialog>

    <BaseDialog v-model="bulkOpen" :title="t('proxies.bulk.title')">
      <form name="bulk" class="proxies__form" @submit.prevent="saveBulk">
        <BaseAlert v-if="bulkError" variant="error">{{ bulkError }}</BaseAlert>
        <div class="proxies__select">
          <label :for="bulkTextId">{{ t('proxies.bulk.text') }}</label>
          <textarea :id="bulkTextId" v-model="bulkText" rows="8" spellcheck="false" />
          <p class="proxies__hint">{{ t('proxies.bulk.hint') }}</p>
        </div>
        <div class="proxies__select">
          <label :for="bulkIpVersionId">{{ t('proxies.bulk.ipVersion') }}</label>
          <select :id="bulkIpVersionId" v-model="bulkIpVersion">
            <option v-for="(label, value) in IP_VERSIONS" :key="value" :value="value">
              {{ label }}
            </option>
          </select>
        </div>
        <div class="proxies__select">
          <label :for="bulkSchemeId">{{ t('proxies.bulk.defaultScheme') }}</label>
          <select :id="bulkSchemeId" v-model="bulkScheme">
            <option v-for="scheme in SCHEMES" :key="scheme" :value="scheme">{{ scheme }}</option>
          </select>
        </div>
        <BaseCheckbox v-model="bulkEnabled" :label="t('proxies.bulk.enabled')" />
        <BaseButton type="submit">{{ t('proxies.bulk.submit') }}</BaseButton>
      </form>
      <div v-if="bulkResult" class="proxies__result">
        <p>
          {{
            t('proxies.bulk.summary', {
              created: bulkResult.created,
              duplicates: bulkResult.duplicates.length,
              invalid: bulkResult.invalid.length,
            })
          }}
        </p>
        <template v-if="bulkResult.invalid.length">
          <h3>{{ t('proxies.bulk.invalidTitle') }}</h3>
          <ul>
            <li v-for="item in bulkResult.invalid" :key="item.line">
              {{ t('proxies.bulk.line', { line: item.line, reason: reasonText(item.reason) }) }}
            </li>
          </ul>
        </template>
      </div>
    </BaseDialog>
  </section>
</template>

<style scoped>
.proxies {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}
.proxies__url {
  overflow-wrap: anywhere;
}
.proxies__actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}
.proxies__select {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}
.proxies__form {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}
.proxies__form textarea {
  width: 100%;
  font: inherit;
}
.proxies__hint {
  margin: 0;
  font-size: 0.875rem;
  opacity: 0.8;
}
.proxies__result {
  margin-top: var(--space-3);
}
</style>
