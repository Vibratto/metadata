<script setup lang="ts">
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
</script>

<template>
  <main class="home">
    <h1>{{ t('app.title') }}</h1>
    <p>{{ t('app.tagline') }}</p>
  </main>
</template>

<style scoped>
/* Mobile-first: the base layout is the mobile one, widened with media queries. */
.home {
  padding: 1rem;
}
</style>
