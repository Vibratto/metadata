/** What `bindFilter` needs from a `usePagedList` list. */
interface FilteredList {
  query: Record<string, string>
  update(changes: Record<string, string>): void
}

/**
 * Binds a filter field to the URL through `usePagedList`. Use it with `v-bind`.
 */
export function bindFilter(list: FilteredList, key: string) {
  return {
    modelValue: list.query[key] ?? '',
    'onUpdate:modelValue': (value: string) => list.update({ [key]: value }),
  }
}
