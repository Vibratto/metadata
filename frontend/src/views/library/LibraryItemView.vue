<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import { type ApiError, api } from '../../api/client'
import { errorText } from '../../api/errors'
import BaseAlert from '../../components/BaseAlert.vue'
import BaseButton from '../../components/BaseButton.vue'
import BaseCheckbox from '../../components/BaseCheckbox.vue'
import BaseDialog from '../../components/BaseDialog.vue'
import BaseField from '../../components/BaseField.vue'
import AppIcon from '../../components/AppIcon.vue'
import CoverArt from '../../components/CoverArt.vue'
import VideoPreviewDialog from '../../components/VideoPreviewDialog.vue'
import { useVideoPreview } from '../../composables/useVideoPreview'
import ArtistsEditor from './ArtistsEditor.vue'
import HistoryList from './HistoryList.vue'
import RecordingAppearances from './RecordingAppearances.vue'
import { type Item, type Kind, SPECS, apiPath, duration, externalId, label } from './kinds'
import { audienceText } from '../../format'

/**
 * Page of an artist, album or track: its data, links to what is related, its history, and
 * editing, artist changes, reverting, deleting and blocking.
 */
const { t, locale } = useI18n()
const route = useRoute()
const router = useRouter()

// From one item to another (a track to its album) the router reuses this component.
const kind = ref(route.params.kind as Kind)
const id = ref(route.params.id as string)
const spec = computed(() => SPECS[kind.value])
const path = computed(() => apiPath(kind.value, id.value))
const { preview, showPreview, closePreview } = useVideoPreview()

const item = ref<Item | null>(null)
// Changes on every save to remount the history and the artists editor.
const version = ref(0)
const draft = ref<Record<string, string>>({})
const fieldErrors = ref<Record<string, string>>({})
const error = ref('')
const message = ref('')
const confirmBlock = ref(false)
const confirmDelete = ref(false)
const alsoBlock = ref(false)

const record = computed(() => item.value as Record<string, unknown> | null)

function show(next: Item, notice = ''): void {
  item.value = next
  const values = next as Record<string, unknown>
  draft.value = Object.fromEntries(
    Object.keys(spec.value.editable).map((name) => [name, String(values[name] ?? '')]),
  )
  fieldErrors.value = {}
  error.value = ''
  message.value = notice
  version.value++
}

async function load(): Promise<void> {
  item.value = null
  message.value = error.value = ''
  try {
    show(await api<Item>(path.value))
  } catch (e) {
    error.value = errorText(e, t)
  }
}

async function save(): Promise<void> {
  // Empty numbers are not text for the API.
  const body = Object.fromEntries(
    Object.entries(spec.value.editable).map(([name, type]) => {
      const value = draft.value[name]!
      // An empty number (an album without a year) is `null` for the API, not 0.
      if (type === 'number') return [name, value === '' ? null : Number(value)]
      return [name, value]
    }),
  )
  try {
    show(await api<Item>(path.value, { method: 'PATCH', body }), t('library.edit.done'))
  } catch (e) {
    // `errorText` rethrows anything that is not an API error.
    const text = errorText(e, t)
    const fields = ((e as ApiError).body ?? {}) as Record<string, string[]>
    const own = Object.keys(fields).filter((name) => name in spec.value.editable)
    message.value = ''
    fieldErrors.value = Object.fromEntries(own.map((name) => [name, fields[name]!.join(' ')]))
    // If the failure belongs to the fields, it already shows next to each one.
    error.value = own.length ? '' : text
  }
}

async function block(): Promise<void> {
  confirmBlock.value = false
  message.value = ''
  error.value = ''
  try {
    await api('/api/v1/catalog/blocked/', {
      method: 'POST',
      body: {
        kind: spec.value.blockKind,
        external_id: externalId(item.value!),
        name: label(item.value!),
      },
    })
    message.value = t('library.block.done')
  } catch (e) {
    error.value = errorText(e, t)
  }
}

async function remove(): Promise<void> {
  confirmDelete.value = false
  error.value = ''
  try {
    await api(`${path.value}${alsoBlock.value ? '?block=true' : ''}`, { method: 'DELETE' })
    await router.push({ name: 'library', query: { tab: kind.value } })
  } catch (e) {
    error.value = errorText(e, t)
  }
}

// When leaving for another route the params empty while the page is still mounted: ignore.
watch(
  () => route.params,
  (params) => {
    if (route.name !== 'library-item') return
    kind.value = params.kind as Kind
    id.value = params.id as string
    void load()
  },
)
void load()
</script>

<template>
  <section class="item">
    <RouterLink class="item__back" :to="{ name: 'library', query: { tab: kind } }">
      <AppIcon name="back" />{{ t('library.back') }}
    </RouterLink>
    <BaseAlert v-if="message" variant="success">{{ message }}</BaseAlert>
    <BaseAlert v-if="error" variant="error">{{ error }}</BaseAlert>

    <template v-if="item && record">
      <header class="item__hero">
        <CoverArt
          class="item__cover"
          :name="label(item)"
          :src="String(record.image_url || record.cover_url || '') || null"
          :round="kind === 'artists'"
        />
        <div class="item__heading">
          <p class="item__kind">{{ t(`library.kindOne.${kind}`) }}</p>
          <h1>{{ label(item) }}</h1>
          <p v-if="'description' in item && item.description" class="item__description">
            {{ item.description }}
          </p>
          <dl class="item__data">
            <div v-if="'artists' in item && item.artists.length" class="item__artists">
              <dt class="sr-only">{{ t('library.fields.artists') }}</dt>
              <dd>
                <template v-for="(artist, i) in item.artists" :key="artist.id">
                  <span v-if="i > 0">, </span>
                  <RouterLink
                    :to="{ name: 'library-item', params: { kind: 'artists', id: artist.id } }"
                  >
                    {{ artist.name }}
                  </RouterLink>
                </template>
              </dd>
            </div>
            <div v-if="'album' in item">
              <dt>{{ t('library.fields.album') }}</dt>
              <dd>
                <RouterLink
                  :to="{ name: 'library-item', params: { kind: 'albums', id: item.album } }"
                >
                  {{ t('library.links.album') }}
                </RouterLink>
              </dd>
            </div>
            <div v-if="'year' in item && item.year">
              <dt>{{ t('library.fields.year') }}</dt>
              <dd>{{ item.year }}</dd>
            </div>
            <div v-if="'subscribers' in item && audienceText(item, locale, t)">
              <dt>{{ t('library.fields.audience') }}</dt>
              <dd>{{ audienceText(item, locale, t) }}</dd>
            </div>
            <template v-if="'downloaded' in item">
              <div>
                <dt>{{ t('library.fields.track_number') }}</dt>
                <dd>{{ item.disc_number }}-{{ item.track_number }}</dd>
              </div>
              <div v-if="item.duration !== null">
                <dt>{{ t('library.fields.duration') }}</dt>
                <dd>{{ duration(item.duration) }}</dd>
              </div>
              <div>
                <dt>{{ t('library.fields.downloaded') }}</dt>
                <dd class="item__downloaded chip" :class="{ 'chip--ok': item.downloaded }">
                  {{ item.downloaded ? t('library.yes') : t('library.no') }}
                </dd>
              </div>
            </template>
            <div v-if="externalId(item)">
              <dt>{{ t('library.fields.external_id') }}</dt>
              <dd class="mono">{{ externalId(item) }}</dd>
            </div>
          </dl>
          <nav class="item__links" :aria-label="t('library.links.title')">
            <RouterLink
              v-if="kind === 'artists'"
              class="btn btn--secondary"
              :to="{ name: 'library', query: { tab: 'albums', artist: item.id } }"
            >
              {{ t('library.links.albums') }}
            </RouterLink>
            <RouterLink
              v-if="kind !== 'tracks'"
              class="btn btn--secondary"
              :to="{ name: 'library', query: { tab: 'tracks', [kind.slice(0, -1)]: item.id } }"
            >
              {{ t('library.links.tracks') }}
            </RouterLink>
            <BaseButton
              v-if="kind === 'tracks'"
              variant="secondary"
              :aria-label="`${t('library.preview.open')}: ${label(item)}`"
              @click="showPreview({ id: item.id, title: label(item) })"
            >
              <AppIcon name="play" />{{ t('library.preview.open') }}
            </BaseButton>
            <RouterLink
              v-if="kind === 'tracks'"
              class="btn btn--secondary"
              :to="{ name: 'track-upload', params: { id: item.id } }"
            >
              <AppIcon name="upload" />{{ t('library.links.upload') }}
            </RouterLink>
          </nav>
        </div>
      </header>

      <div class="item__grid">
        <div class="item__main">
          <form class="item__edit card" @submit.prevent="save">
            <h2>{{ t('library.edit.title') }}</h2>
            <div class="item__fields">
              <BaseField
                v-for="(type, name) in spec.editable"
                :key="name"
                v-model="draft[name]"
                :type="type"
                :label="t(`library.fields.${name}`)"
                :error="fieldErrors[name]"
              />
            </div>
            <BaseButton type="submit" class="item__save">{{ t('library.edit.save') }}</BaseButton>
          </form>

          <ArtistsEditor
            v-if="'artists' in item"
            :key="`artists-${version}`"
            :artists="item.artists"
            :path="path"
            @saved="show($event, t('library.artists.done'))"
          />
        </div>

        <div class="item__aside">
          <RecordingAppearances
            v-if="'recording' in item"
            :key="`recording-${version}`"
            :track-id="item.id"
            :recording-id="item.recording"
            @changed="load"
          />
          <HistoryList
            :key="`history-${version}`"
            :path="path"
            @reverted="show($event, t('library.history.done'))"
          />

          <section v-if="spec.blockKind" class="item__danger card">
            <h2>{{ t('library.danger.title') }}</h2>
            <p>{{ t('library.danger.text') }}</p>
            <div class="item__danger-actions">
              <template v-if="externalId(item)">
                <BaseButton variant="danger" @click="confirmBlock = true">
                  {{ t('library.block.action') }}
                </BaseButton>
                <BaseDialog v-model="confirmBlock" :title="t('library.block.title')">
                  <p>{{ t(`library.block.confirm.${kind}`, { name: label(item) }) }}</p>
                  <BaseButton variant="danger" @click="block">{{
                    t('library.block.action')
                  }}</BaseButton>
                </BaseDialog>
              </template>
              <BaseButton variant="danger" @click="confirmDelete = true">
                {{ t('library.delete.action') }}
              </BaseButton>
              <BaseDialog v-model="confirmDelete" :title="t('library.delete.title')">
                <p>{{ t(`library.delete.confirm.${kind}`, { name: label(item) }) }}</p>
                <BaseCheckbox
                  v-if="externalId(item)"
                  v-model="alsoBlock"
                  :label="t('library.delete.also_block')"
                />
                <BaseButton variant="danger" @click="remove">{{
                  t('library.delete.action')
                }}</BaseButton>
              </BaseDialog>
            </div>
          </section>
        </div>
      </div>
    </template>
    <VideoPreviewDialog :preview="preview" @close="closePreview" />
  </section>
</template>

<style scoped>
.item__description {
  max-width: 60ch;
  margin: 0;
  color: var(--color-muted);
  white-space: pre-line;
}
.item {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}
.item__back {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  align-self: flex-start;
  min-height: var(--touch-target);
  color: var(--color-muted);
}
.item__back .icon {
  width: 1rem;
  height: 1rem;
}
.item__hero {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-4);
  text-align: center;
}
.item__cover {
  --cover-size: 11rem;
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-float);
}
.item__cover.cover--round {
  border-radius: 50%;
}
.item__heading {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-2);
  min-width: 0;
}
.item__kind {
  color: var(--color-muted);
  font-size: 0.875rem;
  font-weight: 500;
}
.item__heading h1 {
  overflow-wrap: anywhere;
}
.item__data {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 0.375rem;
  margin: 0;
}
.item__data div {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  min-height: 1.75rem;
  padding: 0 0.625rem;
  border-radius: 999px;
  background: var(--color-surface-2);
  font-size: 0.8125rem;
}
.item__data dt {
  color: var(--color-muted);
}
.item__data dt::after {
  content: ':';
}
.item__data dd {
  margin: 0;
  font-weight: 550;
  overflow-wrap: anywhere;
}
.item__data .item__artists {
  flex-basis: 100%;
  justify-content: center;
  background: none;
  font-size: 1.0625rem;
}
.item__artists a {
  color: var(--color-text);
  font-weight: 650;
}
.item__downloaded.chip {
  min-height: 0;
  padding: 0 0.5rem;
}
.item__links {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: var(--space-2);
  margin-top: var(--space-2);
}
.item__grid,
.item__main,
.item__aside {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: var(--space-3);
  align-items: start;
}
.item__edit {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding: 1.25rem;
}
.item__fields {
  display: grid;
  gap: var(--space-3);
}
.item__save {
  align-self: flex-end;
}
.item__danger {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  padding: 1.25rem;
  border-color: color-mix(in srgb, var(--color-danger) 25%, var(--color-border));
}
.item__danger p {
  color: var(--color-muted);
  font-size: 0.875rem;
}
.item__danger-actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}

@media (min-width: 600px) {
  .item__fields {
    grid-template-columns: repeat(auto-fit, minmax(10rem, 1fr));
  }
}
@media (min-width: 1024px) {
  .item__hero {
    flex-direction: row;
    align-items: flex-end;
    text-align: left;
  }
  .item__heading,
  .item__data,
  .item__links {
    align-items: flex-start;
    justify-content: flex-start;
  }
  .item__heading h1 {
    font-size: 2.5rem;
  }
  .item__data .item__artists {
    justify-content: flex-start;
    padding: 0;
  }
  .item__grid {
    grid-template-columns: minmax(0, 7fr) minmax(0, 5fr);
  }
  .item__grid > .item__aside:only-child {
    grid-column: 1 / -1;
    max-width: 48rem;
  }
}
</style>
