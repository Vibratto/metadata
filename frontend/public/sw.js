// Minimal service worker: caches the static shell so the app opens offline.
// It never touches /api/: responses carry session data and must always be fresh.
const CACHE = 'vibratto-shell-v1'

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.add('/')))
  self.skipWaiting()
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))),
  )
})

self.addEventListener('fetch', (event) => {
  const { request } = event
  const url = new URL(request.url)
  if (
    request.method !== 'GET' ||
    url.origin !== self.location.origin ||
    url.pathname.startsWith('/api/')
  )
    return

  // Network first, so a new deployment shows up at once; the cache is the fallback.
  event.respondWith(
    fetch(request)
      .then((res) => {
        const copy = res.clone()
        void caches.open(CACHE).then((cache) => cache.put(request, copy))
        return res
      })
      .catch(() => caches.match(request).then((hit) => hit ?? caches.match('/'))),
  )
})
