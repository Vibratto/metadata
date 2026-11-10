<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

import AppIcon from '../components/AppIcon.vue'
import { navEntries } from '../components/nav-meta'
import ThemeToggle from '../components/ThemeToggle.vue'
import { useSessionStore } from '../stores/session'

/**
 * "More": on mobile, the account, the sections that do not fit in the bottom bar and the theme.
 */
const { t } = useI18n()
const router = useRouter()
const session = useSessionStore()
const sections = computed(() => navEntries(router.getRoutes()).sections)
</script>

<template>
  <section class="more-view">
    <h1>{{ t('nav.more') }}</h1>
    <RouterLink v-if="session.user" class="more__user card" :to="{ name: 'account' }">
      <span class="more__avatar" aria-hidden="true">
        {{ session.user.username.slice(0, 2).toUpperCase() }}
      </span>
      <span class="more__who">
        <strong>{{ session.user.username }}</strong>
      </span>
      <span class="more__account">{{ t('nav.account') }}</span>
    </RouterLink>
    <template v-for="section in sections" :key="section.key">
      <h2 class="more__title">{{ t(`nav.sections.${section.key}`) }}</h2>
      <ul class="more card">
        <li v-for="r in section.routes" :key="r.name?.toString() ?? r.path">
          <RouterLink :to="r.path">
            <AppIcon :name="r.meta.navIcon ?? 'chevron'" />
            <span>{{ t(r.meta.navLabel as string) }}</span>
            <AppIcon name="chevron" class="more__chevron" />
          </RouterLink>
        </li>
      </ul>
    </template>
    <div class="card more__theme"><ThemeToggle with-label /></div>
  </section>
</template>

<style scoped>
.more-view {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}
.more__user {
  display: flex;
  align-items: center;
  gap: 0.875rem;
  padding: 0.875rem;
  color: var(--color-text);
}
.more__user:hover {
  text-decoration: none;
}
.more__avatar {
  display: grid;
  flex: none;
  place-items: center;
  width: 2.875rem;
  height: 2.875rem;
  border-radius: 50%;
  background: var(--color-accent-soft);
  color: var(--color-accent);
  font-weight: 650;
}
.more__who {
  display: flex;
  flex: 1;
  flex-direction: column;
  line-height: 1.3;
}
.more__who small {
  color: var(--color-muted);
  font-size: 0.875rem;
  font-weight: 500;
}
.more__account {
  padding: 0.375rem 0.75rem;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  font-size: 0.875rem;
}
.more__title {
  margin: var(--space-2) var(--space-1) calc(-1 * var(--space-2));
  color: var(--color-faint);
  font-size: 0.75rem;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}
.more {
  margin: 0;
  padding: 0;
  overflow: hidden;
  list-style: none;
}
li + li {
  border-top: 1px solid var(--color-border);
}
.more a {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  min-height: 3.25rem;
  padding: 0 var(--space-3);
  color: var(--color-text);
  font-weight: 600;
}
.more a:hover {
  background: var(--color-surface-2);
  text-decoration: none;
}
.more__chevron {
  margin-left: auto;
  color: var(--color-faint);
}
.more__theme {
  overflow: hidden;
}
.more__theme :deep(button) {
  min-height: 3.25rem;
}
</style>
