(() => {
  const panel = document.getElementById('admin-assistant');
  if (!panel) return;
  const toggle = document.getElementById('assistant-toggle');
  const form = document.getElementById('assistant-form');
  const question = document.getElementById('assistant-question');
  const messages = document.getElementById('assistant-messages');
  const status = document.getElementById('assistant-status');
  const send = document.getElementById('assistant-send');
  const reset = document.getElementById('assistant-reset');
  const saveTask = document.getElementById('assistant-save-task');
  let lastExchange = null;
  saveTask.addEventListener('click', () => {
    if (!lastExchange) return;
    const draft = document.createElement('form');
    draft.method = 'POST';
    draft.action = saveTask.dataset.url;
    const values = {action: 'draft', title: lastExchange.question.slice(0, 160), notes: lastExchange.answer.slice(0, 6000), _csrf_token: form.elements._csrf_token.value};
    for (const [name, value] of Object.entries(values)) {
      const input = document.createElement('input');
      input.type = 'hidden'; input.name = name; input.value = value;
      draft.append(input);
    }
    document.body.append(draft);
    draft.submit();
  });
  let history = [];
  let busy = false;
  function setOpen(open) {
    panel.hidden = !open;
    toggle.setAttribute('aria-expanded', String(open));
    (open ? question : toggle).focus();
  }
  toggle.addEventListener('click', () => setOpen(panel.hidden));
  document.getElementById('assistant-close').addEventListener('click', () => setOpen(false));
  panel.addEventListener('keydown', event => { if (event.key === 'Escape') setOpen(false); });
  function append(text, role) {
    const p = document.createElement('p');
    p.className = role === 'user' ? 'assistant-question' : 'assistant-reply';
    p.textContent = text;
    messages.append(p);
    messages.scrollTop = messages.scrollHeight;
  }
  reset.addEventListener('click', () => {
    if (busy) return;
    history = [];
    lastExchange = null;
    saveTask.disabled = true;
    messages.replaceChildren();
    append('New chat. What would you like to know?', 'assistant');
    status.textContent = '';
    question.focus();
  });
  form.addEventListener('submit', async event => {
    event.preventDefault();
    const text = question.value.trim();
    if (busy || !text) return;
    busy = true;
    send.disabled = reset.disabled = true;
    append(text, 'user');
    status.textContent = 'Thinking…';
    const body = new FormData(form);
    body.set('message', text);
    body.set('history', JSON.stringify(history.slice(-10)));
    try {
      const response = await fetch(panel.dataset.endpoint, {method: 'POST', body, headers: {'Accept': 'application/json'}, signal: AbortSignal.timeout(40000)});
      if (response.redirected) throw new Error('Your session has expired. Sign in again.');
      if (!response.headers.get('content-type')?.includes('application/json')) throw new Error('Please refresh the page and try again.');
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || 'Unable to answer right now.');
      append(result.answer, 'assistant');
      lastExchange = {question: text, answer: result.answer};
      saveTask.disabled = false;
      history.push({role: 'user', content: text}, {role: 'assistant', content: result.answer});
      history = history.slice(-10);
      question.value = '';
      status.textContent = 'Based on the current school summary and admin navigation.';
    } catch (error) {
      status.textContent = error.name === 'TimeoutError' ? 'The request timed out. Please try again.' : error.message;
    } finally {
      busy = false;
      send.disabled = reset.disabled = false;
    }
  });
})();
