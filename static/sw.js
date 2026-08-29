const CACHE = 'snow-school-coach-v1';
const ASSETS = [
  '/static/css/style.css',
  '/static/js/app.js',
  '/static/img/horseshoe-logo.png'
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
  if (event.request.method !== 'GET' || event.request.mode === 'navigate') return;
  event.respondWith(caches.match(event.request).then(cached => cached || fetch(event.request)));
});
