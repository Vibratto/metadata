import { createPinia } from 'pinia'
import { createApp } from 'vue'

import App from './App.vue'
import { initTheme } from './composables/useTheme'
import { i18n } from './i18n'
import { router } from './router'

// With `VITE_MOCKS=1` the browser answers the API with MSW (development without a backend).
if (import.meta.env.DEV && import.meta.env.VITE_MOCKS) {
  const { worker } = await import('./mocks/browser')
  await worker.start({ onUnhandledFrame: 'bypass' })
}

initTheme()
createApp(App).use(createPinia()).use(router).use(i18n).mount('#app')
