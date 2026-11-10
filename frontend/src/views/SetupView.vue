<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

import { api } from '../api/client'
import { errorText } from '../api/errors'
import AuthLayout from '../components/AuthLayout.vue'
import BaseAlert from '../components/BaseAlert.vue'
import BaseButton from '../components/BaseButton.vue'
import BaseField from '../components/BaseField.vue'
import { useSessionStore } from '../stores/session'

/**
 * First administrator creation. The server closes it once any user exists, so the
 * view goes back to login when it is no longer needed.
 */
const { t } = useI18n()
const router = useRouter()
const session = useSessionStore()

const username = ref('')
const password = ref('')
const confirm = ref('')
const code = ref('')
const codeRequired = ref(false)
const error = ref('')
const busy = ref(false)

onMounted(async () => {
  try {
    const status = await api<{ needed: boolean; code_required: boolean }>('/api/v1/accounts/setup/')
    codeRequired.value = status.code_required
    if (!status.needed) await router.replace({ name: 'login' })
  } catch (e) {
    error.value = errorText(e, t)
  }
})

async function submit(): Promise<void> {
  error.value = ''
  if (password.value !== confirm.value) {
    error.value = t('auth.setup.mismatch')
    return
  }
  busy.value = true
  try {
    // Setup opens the session on the server; “who am I” mirrors it in the store.
    await api('/api/v1/accounts/setup/', {
      method: 'POST',
      body: {
        username: username.value,
        password: password.value,
        ...(codeRequired.value ? { code: code.value.trim() } : {}),
      },
    })
    await session.fetchMe()
    await router.push({ name: 'dashboard' })
  } catch (e) {
    error.value = errorText(e, t)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <AuthLayout>
    <h1>{{ t('auth.setup.title') }}</h1>
    <p>{{ t('auth.setup.intro') }}</p>
    <BaseAlert v-if="error" variant="error">{{ error }}</BaseAlert>
    <form @submit.prevent="submit">
      <template v-if="codeRequired">
        <BaseField v-model="code" class="auth__wide" :label="t('auth.setup.code')">
          <template #hint>
            <i18n-t keypath="auth.setup.codeHint" scope="global">
              <template #variable><code>VIBRATTO_SETUP_CODE</code></template>
              <template #path><code>/etc/vibratto-metadata/vibratto-metadata.env</code></template>
            </i18n-t>
          </template>
        </BaseField>
      </template>
      <BaseField v-model="username" :label="t('auth.username')" />
      <BaseField v-model="password" :label="t('auth.password')" type="password" />
      <BaseField v-model="confirm" :label="t('auth.setup.confirm')" type="password" />
      <BaseButton type="submit" :disabled="busy">{{ t('auth.setup.submit') }}</BaseButton>
    </form>
  </AuthLayout>
</template>
