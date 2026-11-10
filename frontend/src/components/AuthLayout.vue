<script setup lang="ts">
import { useI18n } from 'vue-i18n'

import { rememberLocale } from '../i18n'
import AppIcon from './AppIcon.vue'

/**
 * Sign-in screen (login and first setup): the brand and tagline on one side, the form on the
 * other; stacked on mobile. Lets the user pick the language before signing in.
 */
const { t, locale } = useI18n()
const LANGUAGES = [
  ['en', 'English'],
  ['es', 'Español'],
] as const

function choose(code: string): void {
  locale.value = code
  rememberLocale(code)
}
// Background waves: several curves fanning out, like a vibrato.
const waves = Array.from({ length: 9 }, (_, i) => ({
  d: `M0 ${230 + i * 9}C120 ${230 + i * 9} 150 ${90 + i * 14} 300 ${100 + i * 14}S470 ${250 + i * 10} 600 ${200 + i * 16}`,
  opacity: 0.95 - i * 0.09,
  width: 2.2 - i * 0.12,
  color: `hsl(${34 + i * 2} 70% ${62 - i * 3}%)`,
}))
</script>

<template>
  <div class="auth">
    <aside class="auth__side">
      <div class="auth__brand">
        <span class="auth__logo"><AppIcon name="logo" /></span>{{ t('app.title') }}
      </div>
      <svg class="auth__waves" viewBox="0 0 600 400" aria-hidden="true">
        <path
          v-for="w in waves"
          :key="w.d"
          :d="w.d"
          :stroke="w.color"
          :stroke-opacity="w.opacity"
          :stroke-width="w.width"
        />
      </svg>
      <p class="auth__tagline">{{ t('app.tagline') }}</p>
    </aside>
    <main class="auth__main">
      <div class="auth__form">
        <slot />
        <div class="auth__lang">
          <AppIcon name="globe" />
          <button
            v-for="[code, name] in LANGUAGES"
            :key="code"
            type="button"
            :lang="code"
            :aria-pressed="locale === code ? 'true' : 'false'"
            @click="choose(code)"
          >
            {{ name }}
          </button>
        </div>
      </div>
    </main>
  </div>
</template>

<style scoped>
.auth {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
  min-height: 100dvh;
}
.auth__side {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding: var(--space-4) var(--space-3) var(--space-3);
  overflow: hidden;
  background: #17151c;
  color: #f1ede6;
}
.auth__brand {
  display: flex;
  align-items: center;
  gap: 0.625rem;
  font-family: var(--font-display);
  font-size: 1.0625rem;
  font-weight: 680;
}
.auth__logo {
  display: grid;
  place-items: center;
  width: 2rem;
  height: 2rem;
  border-radius: 0.5625rem;
  background: var(--color-logo-bg);
  color: var(--color-accent-strong);
}
.auth__logo .icon {
  stroke-width: 2.4;
}
.auth__waves {
  width: calc(100% + 2 * var(--space-3));
  height: 7rem;
  margin: 0 calc(-1 * var(--space-3));
  fill: none;
  stroke-linecap: round;
}
.auth__tagline {
  max-width: 28rem;
  color: #c9c3cf;
}
.auth__main {
  display: grid;
  flex: 1;
  container-type: inline-size;
  place-items: center;
  padding: var(--space-4) var(--space-3);
}
.auth__form {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  width: 100%;
  padding-inline: clamp(var(--space-2), 4cqi, var(--space-5));
}
.auth__form :deep(form) {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 18rem), 1fr));
  gap: var(--space-3);
  margin-top: var(--space-2);
}
.auth__form :deep(form > .auth__wide),
.auth__form :deep(form > .btn),
.auth__form :deep(form > [role='alert']) {
  grid-column: 1 / -1;
}
.auth__form :deep(h1),
.auth__form :deep(h1 + p) {
  max-inline-size: 65ch;
}
.auth__form :deep(form .btn) {
  min-height: 3rem;
  margin-top: var(--space-1);
}
.auth__form :deep(h1 + p) {
  color: var(--color-muted);
}
.auth__lang {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-1);
  margin-top: var(--space-3);
  color: var(--color-faint);
}
.auth__lang .icon {
  width: 1rem;
  height: 1rem;
}
.auth__lang button {
  min-height: var(--touch-target);
  padding: 0 var(--space-2);
  border: 0;
  background: none;
  color: var(--color-faint);
  font: inherit;
  font-size: 0.875rem;
  cursor: pointer;
}
.auth__lang button[aria-pressed='true'] {
  color: var(--color-text);
  font-weight: 600;
}

@media (min-width: 1024px) {
  .auth {
    flex-direction: row;
  }
  .auth__side {
    flex: 1.05;
    padding: var(--space-5) 3.5rem;
  }
  .auth__waves {
    position: absolute;
    right: -2.5rem;
    bottom: 9rem;
    left: -2.5rem;
    width: calc(100% + 5rem);
    height: auto;
    margin: 0;
  }
  .auth__tagline {
    position: relative;
    margin-top: auto;
    color: #f1ede6;
    font-family: var(--font-display);
    font-size: 2.5rem;
    font-weight: 600;
    letter-spacing: -0.02em;
    line-height: 1.1;
  }
  .auth__main {
    flex: 1;
  }
}
</style>
