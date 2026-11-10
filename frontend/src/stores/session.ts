import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { ApiError, api } from '../api/client'
import type { components } from '../api/schema'
import { i18n, rememberLocale } from '../i18n'

/** The signed-in user as “who am I” returns it (type generated from the OpenAPI schema). */
export type User = components['schemas']['Profile'] & { failed_attempts?: number }

/**
 * User session. `loaded` tells "not asked yet" apart from "no session".
 */
/** Applies the language the user chose in their account, if any. */
function applyAccountLanguage(language: string): void {
  if (language !== 'es' && language !== 'en') return
  i18n.global.locale.value = language
  rememberLocale(language)
}

export const useSessionStore = defineStore('session', () => {
  const user = ref<User | null>(null)
  const loaded = ref(false)
  /** The failed-attempts notice was already dismissed in this session. */
  const noticeDismissed = ref(false)
  const isAuthenticated = computed(() => user.value !== null)

  async function fetchMe(): Promise<void> {
    try {
      user.value = await api<User>('/api/v1/accounts/me/')
      applyAccountLanguage(user.value.language)
    } catch (e) {
      // 401/403 only mean “no session”; any other failure must surface.
      if (!(e instanceof ApiError) || (e.kind !== 'unauthorized' && e.kind !== 'forbidden')) throw e
      user.value = null
    } finally {
      loaded.value = true
    }
  }

  async function login(username: string, password: string): Promise<void> {
    user.value = await api<User>('/api/v1/accounts/login/', {
      method: 'POST',
      body: { username, password },
    })
    loaded.value = true
    applyAccountLanguage(user.value.language)
    noticeDismissed.value = false
  }

  async function logout(): Promise<void> {
    await api('/api/v1/accounts/logout/', { method: 'POST' })
    user.value = null
  }

  return { user, loaded, noticeDismissed, isAuthenticated, fetchMe, login, logout }
})
