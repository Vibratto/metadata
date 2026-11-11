<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

import { useSessionStore } from '../stores/session'
import AppIcon from './AppIcon.vue'
import { navEntries } from './nav-meta'

/**
 * Main navigation. On mobile, a bottom bar with icons: the `main` entries plus "More". From
 * 1024 px, a side bar with the brand, everything grouped by section and the account at the
 * bottom. Same markup, switched by CSS only.
 */
const { t } = useI18n()
const router = useRouter()
const session = useSessionStore()
const entries = computed(() => navEntries(router.getRoutes()))
const initials = computed(() => session.user?.username.slice(0, 2).toUpperCase() ?? '')
</script>

<template>
  <nav class="nav" :aria-label="t('nav.main')">
    <div class="nav__brand">
      {{ t('app.title') }}
    </div>
    <ul class="nav__main">
      <li v-for="r in entries.main" :key="r.name?.toString() ?? r.path">
        <RouterLink :to="r.path">
          <AppIcon :name="r.meta.navIcon ?? 'chevron'" />
          <span>{{ t(r.meta.navLabel as string) }}</span>
        </RouterLink>
      </li>
      <li class="nav__more-item">
        <RouterLink class="nav__more-link" :to="{ name: 'more' }">
          <AppIcon name="more" />
          <span>{{ t('nav.more') }}</span>
        </RouterLink>
      </li>
    </ul>
    <template v-for="section in entries.sections" :key="section.key">
      <h2 :id="`nav-${section.key}`" class="nav__group-title">
        {{ t(`nav.sections.${section.key}`) }}
      </h2>
      <ul class="nav__secondary" :aria-labelledby="`nav-${section.key}`">
        <li v-for="r in section.routes" :key="r.name?.toString() ?? r.path">
          <RouterLink :to="r.path">
            <AppIcon :name="r.meta.navIcon ?? 'chevron'" />
            <span>{{ t(r.meta.navLabel as string) }}</span>
          </RouterLink>
        </li>
      </ul>
    </template>
    <RouterLink v-if="session.user" class="nav__user" :to="{ name: 'account' }">
      <span class="nav__avatar" aria-hidden="true">{{ initials }}</span>
      <span class="nav__who">
        <strong>{{ session.user.username }}</strong>
      </span>
    </RouterLink>
  </nav>
</template>

<style scoped>
.nav {
  position: fixed;
  z-index: 10;
  inset: auto 0 0;
  padding: 0.375rem 0.5rem calc(0.375rem + env(safe-area-inset-bottom));
  border-top: 1px solid var(--color-border);
  background: color-mix(in srgb, var(--color-surface) 92%, transparent);
  backdrop-filter: blur(14px);
}
ul {
  display: flex;
  margin: 0;
  padding: 0;
  list-style: none;
}
li {
  flex: 1;
  min-width: 0;
}
a {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.1875rem;
  min-height: 3.25rem;
  border-radius: var(--radius-sm);
  color: var(--color-faint);
  font-size: 0.6875rem;
  font-weight: 550;
  text-decoration: none;
}
a span {
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
a .icon {
  width: 1.4rem;
  height: 1.4rem;
}
a.router-link-active {
  color: var(--color-text);
}
a.router-link-active .icon {
  color: var(--color-accent);
}
/* On mobile the rest is reached from “More”; groups, brand and account only exist in the
   sidebar. */
.nav__brand,
.nav__group-title,
.nav__secondary,
.nav__user {
  display: none;
}

@media (min-width: 1024px) {
  .nav {
    inset: 0 auto 0 0;
    display: flex;
    flex-direction: column;
    width: var(--nav-side-width);
    padding: var(--space-4) 0.875rem var(--space-3);
    overflow-y: auto;
    border-top: 0;
    border-right: 1px solid var(--color-border);
    background: var(--color-bg);
    backdrop-filter: none;
  }
  ul {
    flex-direction: column;
    gap: 2px;
  }
  li {
    flex: none;
  }
  a {
    flex-direction: row;
    justify-content: flex-start;
    gap: 0.75rem;
    min-height: var(--touch-target);
    padding: 0 0.75rem;
    color: var(--color-muted);
    font-size: 0.9375rem;
    font-weight: 500;
  }
  a .icon {
    width: 1.25rem;
    height: 1.25rem;
  }
  a:hover {
    background: var(--color-surface-2);
    color: var(--color-text);
  }
  a.router-link-active {
    background: var(--color-surface);
    box-shadow: var(--shadow);
  }
  .nav__brand {
    display: flex;
    align-items: center;
    gap: 0.625rem;
    padding: 0 0.625rem var(--space-4);
    font-family: var(--font-display);
    font-size: 1rem;
    font-weight: 680;
    letter-spacing: -0.01em;
    white-space: nowrap;
  }
  .nav__more-item {
    display: none;
  }
  .nav__group-title {
    display: block;
    margin: var(--space-3) 0.625rem 0.375rem;
    color: var(--color-faint);
    font-size: 0.71875rem;
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
  }
  .nav__secondary {
    display: flex;
  }
  .nav__user {
    display: flex;
    gap: 0.625rem;
    margin-top: auto;
    padding: 0.625rem;
    border: 1px solid var(--color-border);
    border-radius: var(--radius);
    background: var(--color-surface);
    color: var(--color-text);
  }
}
.nav__avatar {
  display: grid;
  flex: none;
  place-items: center;
  width: 2.125rem;
  height: 2.125rem;
  border-radius: 50%;
  background: var(--color-accent-soft);
  color: var(--color-accent);
  font-size: 0.8125rem;
  font-weight: 650;
}
.nav__who {
  display: flex;
  flex-direction: column;
  line-height: 1.25;
}
.nav__who small {
  color: var(--color-muted);
  font-size: 0.78rem;
}
</style>
