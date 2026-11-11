<script setup lang="ts">
import { onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'

import AppNav from './components/AppNav.vue'
import BaseAlert from './components/BaseAlert.vue'
import BaseButton from './components/BaseButton.vue'
import GlobalSearch from './components/GlobalSearch.vue'
import JobsIndicator from './components/JobsIndicator.vue'
import ThemeToggle from './components/ThemeToggle.vue'
import { useSessionStore } from './stores/session'
import './styles/base.css'

const { t } = useI18n()
const route = useRoute()
const session = useSessionStore()

// The PWA service worker is only registered in production: in development it would
// clash with the MSW one, which uses the same scope.
onMounted(() => {
  if (import.meta.env.PROD && 'serviceWorker' in navigator)
    void navigator.serviceWorker.register('/sw.js')
})
</script>

<template>
  <!-- Login and first-run setup take the whole screen, without navigation. Nothing renders
       until the router resolves the first route, so the API is not queried without a session. -->
  <RouterView v-if="route.meta.public" />
  <template v-else-if="route.matched.length">
    <AppNav />
    <div class="app-shell">
      <header class="topbar">
        <span class="topbar__brand">
          <span class="sr-only">{{ t('app.title') }}</span>
        </span>
        <GlobalSearch />
        <JobsIndicator />
        <ThemeToggle />
      </header>
      <BaseAlert
        v-if="session.user?.failed_attempts && !session.noticeDismissed"
        variant="warning"
        class="failed-notice"
      >
        {{ t('auth.failedAttempts', { count: session.user.failed_attempts }) }}
        <BaseButton variant="secondary" @click="session.noticeDismissed = true">
          {{ t('ui.close') }}
        </BaseButton>
      </BaseAlert>
      <main class="app-main">
        <RouterView />
      </main>
    </div>
  </template>
</template>

<style scoped>
.topbar {
  position: sticky;
  top: 0;
  z-index: 9;
  display: flex;
  align-items: center;
  gap: var(--space-2);
  /* Same width and side padding as .app-main, so the search lines up with the page. */
  max-width: var(--content-width);
  margin-inline: auto;
  padding: 0.75rem var(--space-3);
  background: color-mix(in srgb, var(--color-bg) 88%, transparent);
  backdrop-filter: blur(12px);
}
/* The search sits in the middle; the running jobs and the theme go to the right edge. */
.topbar :deep(.global-search) {
  margin-inline: auto;
}
.failed-notice {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-2);
  margin: var(--space-2) var(--space-3);
}

@media (min-width: 600px) {
  .topbar {
    gap: var(--space-3);
    padding-inline: var(--space-4);
  }
}
@media (min-width: 1024px) {
  .topbar {
    padding: 1.125rem var(--space-5);
  }
  .topbar__brand {
    display: none;
  }
}
</style>
