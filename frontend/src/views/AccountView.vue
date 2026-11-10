<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

import { api } from '../api/client'
import { errorText } from '../api/errors'
import BaseAlert from '../components/BaseAlert.vue'
import BaseButton from '../components/BaseButton.vue'
import BaseField from '../components/BaseField.vue'
import { rememberLocale } from '../i18n'
import { type User, useSessionStore } from '../stores/session'

/**
 * Account settings: language, username and password changes, and sign-out. The language
 * is stored per user on the server (and in the browser for the next start-up).
 */
const { t, locale } = useI18n()
const router = useRouter()
const session = useSessionStore()

const newUsername = ref('')
const usernamePassword = ref('')
const currentPassword = ref('')
const newPassword = ref('')
const message = ref('')
const error = ref('')

/** Switches the language at once and saves it to the account for other devices. */
async function setLocale(event: Event): Promise<void> {
  locale.value = (event.target as HTMLSelectElement).value
  rememberLocale(locale.value)
  await run(async () => {
    await api('/api/v1/accounts/language/', { method: 'PUT', body: { language: locale.value } })
    return t('account.language.saved')
  })
}

/** Runs an account action showing its success or its error, never both. */
async function run(action: () => Promise<string>): Promise<void> {
  message.value = ''
  error.value = ''
  try {
    message.value = await action()
  } catch (e) {
    error.value = errorText(e, t)
  }
}

const changeUsername = () =>
  run(async () => {
    session.user = await api<User>('/api/v1/accounts/username/', {
      method: 'POST',
      body: { username: newUsername.value, current_password: usernamePassword.value },
    })
    newUsername.value = usernamePassword.value = ''
    return t('account.username.done')
  })

const changePassword = () =>
  run(async () => {
    await api('/api/v1/accounts/password/', {
      method: 'POST',
      body: { current_password: currentPassword.value, new_password: newPassword.value },
    })
    currentPassword.value = newPassword.value = ''
    return t('account.password.done')
  })

const logout = () =>
  run(async () => {
    await session.logout()
    await router.push({ name: 'login' })
    return ''
  })
</script>

<template>
  <section class="account">
    <h1>{{ t('account.title') }}</h1>
    <p v-if="session.user">
      {{ t('account.signedInAs', { username: session.user.username }) }}
    </p>
    <BaseAlert v-if="message" variant="success">{{ message }}</BaseAlert>
    <BaseAlert v-if="error" variant="error">{{ error }}</BaseAlert>

    <div class="language">
      <label for="account-language">{{ t('account.language.label') }}</label>
      <select id="account-language" :value="locale" @change="setLocale">
        <option value="es">{{ t('account.language.es') }}</option>
        <option value="en">{{ t('account.language.en') }}</option>
      </select>
    </div>

    <form name="username" @submit.prevent="changeUsername">
      <h2>{{ t('account.username.title') }}</h2>
      <BaseField v-model="newUsername" :label="t('account.username.new')" />
      <BaseField
        v-model="usernamePassword"
        :label="t('account.password.current')"
        type="password"
      />
      <BaseButton type="submit">{{ t('account.username.submit') }}</BaseButton>
    </form>

    <form name="password" @submit.prevent="changePassword">
      <h2>{{ t('account.password.title') }}</h2>
      <BaseField v-model="currentPassword" :label="t('account.password.current')" type="password" />
      <BaseField v-model="newPassword" :label="t('account.password.new')" type="password" />
      <BaseButton type="submit">{{ t('account.password.submit') }}</BaseButton>
    </form>

    <BaseButton variant="secondary" @click="logout">{{ t('account.logout') }}</BaseButton>
  </section>
</template>

<style scoped>
.account {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  max-width: 32rem;
}
form {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}
.language select {
  display: block;
  margin-top: var(--space-1);
}
</style>
