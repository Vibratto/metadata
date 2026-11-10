/** Tree of texts as a messages JSON file describes it. */
interface Dictionary {
  [key: string]: string | Dictionary
}

function collect(files: Record<string, { default: Dictionary }>): Dictionary {
  return Object.assign({}, ...Object.values(files).map((f) => f.default))
}

// One file per area (`app.json`, `library.json`...) with its own top-level
// namespace, so each view adds its own without touching the others.
/** English and Spanish messages, gathered from `en/*.json` and `es/*.json`. */
export const messages = {
  es: collect(import.meta.glob<{ default: Dictionary }>('./es/*.json', { eager: true })),
  en: collect(import.meta.glob<{ default: Dictionary }>('./en/*.json', { eager: true })),
}
