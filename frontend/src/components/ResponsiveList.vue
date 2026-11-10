<script setup lang="ts" generic="T extends object">
import { useI18n } from 'vue-i18n'

/** A list column: the field key and its already translated header. */
export interface Column {
  key: string
  label: string
}

/**
 * Table on desktop, card list on mobile (under 600 px). Same markup both ways:
 * on mobile each cell shows its header through CSS (`data-label`).
 */
const props = defineProps<{ columns: Column[]; rows: T[]; rowKey: keyof T & string }>()
const { t } = useI18n()

function cell(row: T, key: string): unknown {
  return (row as Record<string, unknown>)[key]
}
</script>

<template>
  <p v-if="props.rows.length === 0" class="list-empty">{{ t('ui.list.empty') }}</p>
  <table v-else class="list">
    <thead>
      <tr>
        <th v-for="c in props.columns" :key="c.key" scope="col">{{ c.label }}</th>
      </tr>
    </thead>
    <tbody>
      <tr v-for="row in props.rows" :key="String(row[props.rowKey])">
        <td v-for="c in props.columns" :key="c.key" :data-label="c.label">
          <slot :name="`cell-${c.key}`" :row="row">{{ cell(row, c.key) }}</slot>
        </td>
      </tr>
    </tbody>
  </table>
</template>

<style scoped>
.list-empty {
  padding: var(--space-4);
  border: 1px dashed var(--color-border);
  border-radius: var(--radius-lg);
  color: var(--color-muted);
  text-align: center;
}
.list {
  width: 100%;
  overflow: hidden;
  border-collapse: separate;
  border-spacing: 0;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  background: var(--color-surface);
  box-shadow: var(--shadow);
}
th,
td {
  padding: 0.75rem var(--space-3);
  text-align: left;
}
th {
  border-bottom: 1px solid var(--color-border);
}
tbody tr + tr td {
  border-top: 1px solid var(--color-border);
}
tbody tr:hover td {
  background: color-mix(in srgb, var(--color-surface-2) 50%, transparent);
}

@media (max-width: 599.98px) {
  /* The header is kept for screen readers only; each cell carries its own. */
  thead {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip-path: inset(50%);
  }
  .list,
  tbody {
    display: block;
    border: 0;
    background: none;
    box-shadow: none;
  }
  tbody tr {
    display: block;
    margin-bottom: var(--space-2);
    padding: 0.375rem 0;
    border: 1px solid var(--color-border);
    border-radius: var(--radius-lg);
    background: var(--color-surface);
  }
  tbody tr + tr td {
    border-top: 0;
  }
  td {
    display: flex;
    justify-content: space-between;
    gap: var(--space-3);
    padding: 0.375rem var(--space-3);
    text-align: right;
  }
  td::before {
    content: attr(data-label);
    color: var(--color-muted);
    font-weight: 500;
    text-align: left;
  }
}
</style>
