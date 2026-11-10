<script setup lang="ts">
import { computed } from 'vue'

/**
 * Cover or photo: the image if there is one, otherwise a gradient with the initials, in a
 * colour fixed per name. Decorative: the name is always written next to it.
 */
const props = withDefaults(defineProps<{ name: string; src?: string | null; round?: boolean }>(), {
  src: null,
  round: false,
})

const HUES = [24, 350, 205, 160, 265, 38, 190, 10]

const initials = computed(() =>
  props.name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0]!.toUpperCase())
    .join(''),
)
const style = computed(() => {
  let h = 0
  for (const c of props.name) h = (h * 31 + c.charCodeAt(0)) >>> 0
  const hue = HUES[h % HUES.length]!
  return `--hue: ${hue}`
})
</script>

<template>
  <span class="cover" :class="{ 'cover--round': round }" :style="style" aria-hidden="true">
    <img v-if="src" :src="src" alt="" loading="lazy" />
    <template v-else>{{ initials }}</template>
  </span>
</template>

<style scoped>
.cover {
  position: relative;
  display: grid;
  flex: none;
  place-items: center;
  width: var(--cover-size, 3rem);
  aspect-ratio: 1;
  overflow: hidden;
  border-radius: var(--radius-sm);
  background: linear-gradient(140deg, hsl(var(--hue) 55% 58%), hsl(calc(var(--hue) + 28) 55% 36%));
  color: rgb(255 255 255 / 92%);
  font-family: var(--font-display);
  font-size: calc(var(--cover-size, 3rem) * 0.34);
  font-weight: 650;
  letter-spacing: 0.02em;
  user-select: none;
}
.cover::after {
  content: '';
  position: absolute;
  inset: 0;
  background: radial-gradient(120% 90% at 20% 10%, rgb(255 255 255 / 22%), transparent 55%);
}
.cover--round {
  border-radius: 50%;
}
img {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
}
</style>
