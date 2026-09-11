if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => navigator.serviceWorker.register('/static/sw.js?v=3'));
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

const cameraModal = document.querySelector('[data-camera-modal]');
if (cameraModal) {
  const video = cameraModal.querySelector('[data-camera-video]');
  const canvas = cameraModal.querySelector('[data-camera-canvas]');
  const message = cameraModal.querySelector('[data-camera-message]');
  const captureButton = cameraModal.querySelector('[data-camera-capture]');
  const caption = cameraModal.querySelector('[data-camera-caption]');
  const studentLabel = cameraModal.querySelector('[data-camera-student]');
  let stream = null;
  let studentId = null;
  const stopCamera = () => { if (stream) stream.getTracks().forEach((track) => track.stop()); stream = null; video.srcObject = null; captureButton.disabled = true; };
  const closeCamera = () => { stopCamera(); cameraModal.hidden = true; document.body.style.overflow = ''; };
  const openCamera = async (button) => {
    studentId = button.dataset.studentId;
    studentLabel.textContent = button.dataset.studentName;
    caption.value = '';
    message.textContent = 'Starting camera…';
    message.hidden = false;
    cameraModal.hidden = false;
    document.body.style.overflow = 'hidden';
    try {
      stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: 'environment' } }, audio: false });
      video.srcObject = stream;
      await video.play();
      message.hidden = true;
      captureButton.disabled = false;
    } catch (error) {
      message.textContent = 'Camera access is needed. Allow camera access in device settings and try again.';
    }
  };
  document.querySelectorAll('.camera-open').forEach((button) => button.addEventListener('click', () => openCamera(button)));
  cameraModal.querySelector('.camera-close').addEventListener('click', closeCamera);
  cameraModal.querySelector('[data-camera-cancel]').addEventListener('click', closeCamera);
  captureButton.addEventListener('click', () => {
    captureButton.disabled = true;
    captureButton.textContent = 'Saving…';
    canvas.width = Math.min(video.videoWidth || 1280, 1600);
    canvas.height = Math.round(canvas.width * (video.videoHeight || 960) / (video.videoWidth || 1280));
    canvas.getContext('2d').drawImage(video, 0, 0, canvas.width, canvas.height);
    canvas.toBlob(async (blob) => {
      if (!blob) { message.textContent = 'The photo could not be captured. Please try again.'; message.hidden = false; captureButton.disabled = false; captureButton.textContent = 'Capture & save'; return; }
      const form = new FormData();
      form.append('media', blob, 'camera-capture.jpg');
      form.append('caption', caption.value);
      form.append('_csrf_token', cameraModal.dataset.csrf);
      try {
        const response = await fetch(`/participants/${studentId}/media`, { method: 'POST', body: form, credentials: 'same-origin' });
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || 'Upload failed');
        closeCamera();
        window.location.reload();
      } catch (error) {
        message.textContent = error.message || 'The photo could not be saved. Please try again.';
        message.hidden = false;
      } finally {
        captureButton.disabled = false;
        captureButton.textContent = 'Capture & save';
      }
    }, 'image/jpeg', 0.84);
  });
}
