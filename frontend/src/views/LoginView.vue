<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import { api } from '../api/client'
import { errorText } from '../api/errors'
import AuthLayout from '../components/AuthLayout.vue'
import BaseAlert from '../components/BaseAlert.vue'
import BaseButton from '../components/BaseButton.vue'
import BaseField from '../components/BaseField.vue'
import { safeRedirect } from '../router/guards'
import { useSessionStore } from '../stores/session'

/**
 * Sign-in form. Checks the initial setup first: that request also sets the CSRF cookie
 * the POST needs, and redirects to setup when no administrator exists yet.
 */
const { t } = useI18n()
const router = useRouter()
const route = useRoute()
const session = useSessionStore()

const username = ref('')
const password = ref('')
const error = ref('')
const busy = ref(false)

onMounted(async () => {
  try {
    const { needed } = await api<{ needed: boolean }>('/api/v1/accounts/setup/')
    if (needed) await router.replace({ name: 'setup' })
  } catch (e) {
    error.value = errorText(e, t)
  }
})

async function submit(): Promise<void> {
  busy.value = true
  error.value = ''
  try {
    await session.login(username.value, password.value)
    await router.push(safeRedirect(route.query.redirect) ?? { name: 'dashboard' })
  } catch (e) {
    error.value = errorText(e, t)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <AuthLayout>
    <h1>{{ t('auth.login.title') }}</h1>
    <BaseAlert v-if="error" variant="error">{{ error }}</BaseAlert>
    <form @submit.prevent="submit">
      <BaseField v-model="username" :label="t('auth.username')" />
      <BaseField v-model="password" :label="t('auth.password')" type="password" />
      <BaseButton type="submit" :disabled="busy">{{ t('auth.login.submit') }}</BaseButton>
    </form>
  </AuthLayout>
</template>
