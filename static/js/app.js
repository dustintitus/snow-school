if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => navigator.serviceWorker.register('/static/sw.js'));
}

const connectivity = document.querySelector('[data-connectivity]');
function updateConnectivity() {
  if (!connectivity) return;
  const online = navigator.onLine;
  connectivity.classList.toggle('is-offline', !online);
  connectivity.querySelector('strong').textContent = online ? 'Online' : 'Offline';
  connectivity.querySelector('small').textContent = online
    ? 'Updates save immediately'
    : 'Reconnect before recording class updates';
}
window.addEventListener('online', updateConnectivity);
window.addEventListener('offline', updateConnectivity);
updateConnectivity();
