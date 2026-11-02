const CACHE = 'snow-school-coach-v11-attendance';
const ASSETS = [
  '/static/css/style.css?v=20261031attendance',
  '/static/js/app.js?v=20261031attendance',
  '/static/css/admin.css?v=20261023staff',
  '/static/img/horseshoe-logo.png',
  '/static/css/horseshoe.css?v=20261026brand',
  '/static/img/horseshoe/logo-red.png'
];

self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(ASSETS)));
  self.skipWaiting();
});

self.addEventListener('activate', event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(key => key !== CACHE).map(key => caches.delete(key)))));
  self.clients.claim();
});

self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);
  // Cache only public static assets, never participant or staff records.
  if (event.request.method !== 'GET' || url.origin !== self.location.origin || !url.pathname.startsWith('/static/')) return;
  event.respondWith(
    fetch(event.request)
      .then(response => {
        const copy = response.clone();
        caches.open(CACHE).then(cache => cache.put(event.request, copy));
        return response;
      })
      .catch(() => caches.match(event.request))
  );
});
