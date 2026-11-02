if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => navigator.serviceWorker.register('/static/sw.js?v=5'));
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
  const recordButton = cameraModal.querySelector('[data-camera-record]');
  const caption = cameraModal.querySelector('[data-camera-caption]');
  const studentLabel = cameraModal.querySelector('[data-camera-student]');
  let stream = null, studentId = null, recorder = null, timer = null, recordingBytes = 0, cancelled = false, busy = false;
  const tell = text => { message.hidden = false; message.textContent = text; };
  const stopCamera = () => {
    clearTimeout(timer);
    if (recorder && recorder.state !== 'inactive') recorder.stop();
    if (stream) stream.getTracks().forEach(track => track.stop());
    stream = null; video.srcObject = null; captureButton.disabled = true; recordButton.disabled = true;
  };
  const closeCamera = () => { if (busy) return; cancelled = true; stopCamera(); cameraModal.hidden = true; document.body.style.overflow = ''; };
  const upload = async (blob, filename) => {
    if (cancelled) return;
    if (!blob || !blob.size || blob.size > 3 * 1024 * 1024) { tell('Capture is too large or empty. Try a shorter video.'); return; }
    const selected = Array.from(cameraModal.querySelectorAll('[name=capture_students]:checked'), el => el.value);
    if (!selected.includes(studentId)) { tell('Keep the selected participant checked.'); return; }
    busy = true; captureButton.disabled = true; recordButton.disabled = true;
    tell('Saving privately to participant records…');
    const form = new FormData();
    form.append('media', blob, filename);
    form.append('caption', caption.value);
    form.append('_csrf_token', cameraModal.dataset.csrf);
    selected.forEach(id => form.append('student_ids', id));
    try {
      const response = await fetch(`/participants/${studentId}/media`, { method:'POST', body:form, credentials:'same-origin' });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || 'Upload failed');
      busy = false; closeCamera(); window.location.reload();
    } catch (error) { tell(error.message || 'Capture could not be saved. Please try again.'); }
    finally { busy = false; captureButton.disabled = !stream; recordButton.disabled = !stream || !window.MediaRecorder; }
  };
  const openCamera = async button => {
    cancelled = false; studentId = button.dataset.studentId; caption.value = '';
    studentLabel.textContent = button.dataset.studentName;
    cameraModal.querySelectorAll('[name=capture_students]').forEach(el => { el.checked = el.value === studentId; });
    cameraModal.hidden = false; document.body.style.overflow = 'hidden'; tell('Starting camera…');
    try {
      const nextStream = await navigator.mediaDevices.getUserMedia({video:{facingMode:{ideal:'environment'},width:{ideal:640},height:{ideal:480}},audio:false});
      if (cancelled) { nextStream.getTracks().forEach(track => track.stop()); return; }
      stream = nextStream; video.srcObject = stream; await video.play(); message.hidden = true;
      captureButton.disabled = false; recordButton.disabled = !window.MediaRecorder;
      if (!window.MediaRecorder) tell('Video capture is unavailable in this browser. Photo capture is available.');
    } catch { tell('Allow camera access in device settings and try again.'); }
  };
  document.querySelectorAll('.camera-open').forEach(button => button.addEventListener('click', () => openCamera(button)));
  cameraModal.querySelector('.camera-close').addEventListener('click', closeCamera);
  cameraModal.querySelector('[data-camera-cancel]').addEventListener('click', closeCamera);
  captureButton.addEventListener('click', () => {
    captureButton.disabled = true;
    canvas.width = Math.min(video.videoWidth || 1280, 1600);
    canvas.height = Math.round(canvas.width * (video.videoHeight || 960) / (video.videoWidth || 1280));
    canvas.getContext('2d').drawImage(video, 0, 0, canvas.width, canvas.height);
    canvas.toBlob(blob => { upload(blob, 'capture.jpg').finally(() => { captureButton.disabled = !stream; }); }, 'image/jpeg', 0.84);
  });
  recordButton.addEventListener('click', () => {
    if (recorder && recorder.state === 'recording') { recorder.stop(); return; }
    const mime = ['video/mp4', 'video/webm;codecs=vp8', 'video/webm'].find(type => MediaRecorder.isTypeSupported(type));
    if (!mime) { tell('Video recording is unavailable on this device.'); return; }
    try { recorder = new MediaRecorder(stream, {mimeType:mime,videoBitsPerSecond:700000}); }
    catch { tell('Video recording could not start. Try a photo.'); return; }
    let chunks = []; recordingBytes = 0; captureButton.disabled = true;
    recorder.ondataavailable = event => {
      if (event.data.size) { chunks.push(event.data); recordingBytes += event.data.size; }
      if (recordingBytes >= 2500000 && recorder.state === 'recording') recorder.stop();
    };
    recorder.onstop = async () => {
      clearTimeout(timer); recordButton.textContent = 'Record video (up to 15 seconds)';
      const type = mime.split(';')[0]; const blob = new Blob(chunks, {type}); chunks = [];
      await upload(blob, type === 'video/mp4' ? 'capture.mp4' : 'capture.webm');
      captureButton.disabled = !stream;
    };
    recorder.onerror = () => { tell('Recording failed. Please try again.'); captureButton.disabled = !stream; };
    recorder.start(250); recordButton.textContent = 'Stop & save video'; tell('Recording silently. Stops automatically after 15 seconds.');
    timer = setTimeout(() => { if (recorder.state === 'recording') recorder.stop(); }, 15000);
  });
  document.addEventListener('visibilitychange', () => { if (document.hidden && !busy) closeCamera(); });
  window.addEventListener('pagehide', () => { cancelled = true; stopCamera(); });
}

// Native details remains usable without JavaScript; start compact on small screens.
const adminMenu = document.querySelector('.admin-menu');
if (adminMenu) {
  const adminMobile = window.matchMedia('(max-width: 900px)');
  const syncAdminMenu = () => { adminMenu.open = !adminMobile.matches; };
  syncAdminMenu();
  adminMobile.addEventListener('change', syncAdminMenu);
  adminMenu.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && adminMobile.matches && adminMenu.open) {
      adminMenu.open = false;
      adminMenu.querySelector('summary').focus();
    }
  });
}

const availabilityForm = document.querySelector('[data-availability]');
if (availabilityForm) {
  availabilityForm.querySelector('[data-apply-pattern]').addEventListener('click', () => {
    const weekdays = new Set(Array.from(availabilityForm.querySelectorAll('[data-weekday]:checked'), el => el.dataset.weekday));
    const periods = new Set(Array.from(availabilityForm.querySelectorAll('[data-pattern-period]:checked'), el => el.dataset.patternPeriod));
    availabilityForm.querySelectorAll('[data-slot-day]').forEach(el => { el.checked = weekdays.has(el.dataset.slotDay) && periods.has(el.dataset.slotPeriod); });
    availabilityForm.querySelector('[name=reviewed]').checked = false;
  });
}


const attendanceForm = document.querySelector('.session-roster-form');
if (attendanceForm) {
  const saveBar = attendanceForm.querySelector('.attendance-save-bar');
  const status = attendanceForm.querySelector('[data-attendance-status]');
  const fields = [...attendanceForm.querySelectorAll('input[type="checkbox"], input[type="text"]')];
  const snapshot = () => JSON.stringify(fields.map(field => field.type === 'checkbox' ? field.checked : field.value));
  const original = snapshot();
  const updateAttendanceStatus = () => {
    const changed = snapshot() !== original;
    status.textContent = changed ? 'Unsaved changes' : 'No unsaved changes';
    saveBar.classList.toggle('has-changes', changed);
  };
  attendanceForm.addEventListener('input', updateAttendanceStatus);
  attendanceForm.addEventListener('change', updateAttendanceStatus);
  attendanceForm.addEventListener('submit', () => { status.textContent = 'Saving attendance…'; });
  const positionAttendanceSave = () => {
    const nav = document.querySelector('.coach-bottom-nav');
    const height = nav && getComputedStyle(nav).position === 'fixed' ? nav.getBoundingClientRect().height : 0;
    attendanceForm.style.setProperty('--attendance-nav-height', `${height}px`);
  };
  window.addEventListener('resize', positionAttendanceSave);
  window.addEventListener('pageshow', updateAttendanceStatus);
  positionAttendanceSave();
}
