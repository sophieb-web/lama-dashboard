let isLoading = false;

function sendSuggested(btn) {
  const q = btn.textContent.trim();
  document.getElementById('chat-input').value = q;
  sendMessage();
}

function handleChatKey(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
}

function autoResize(el) {
  el.style.height = 'auto';
  el.style.height = Math.min(el.scrollHeight, 120) + 'px';
}

function sendMessage() {
  if (isLoading) return;
  const input = document.getElementById('chat-input');
  const q = input.value.trim();
  if (!q) return;

  // Hide empty state
  const empty = document.getElementById('chat-empty');
  if (empty) empty.style.display = 'none';

  appendMessage('user', q);
  input.value = '';
  input.style.height = 'auto';

  const loadingId = 'loading-' + Date.now();
  appendMessage('assistant', '<div class="spinner"></div>', loadingId);

  isLoading = true;
  document.getElementById('chat-send').disabled = true;

  fetch('/api/query', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question: q })
  })
    .then(r => r.json())
    .then(data => {
      const loadingEl = document.getElementById(loadingId);
      if (loadingEl) loadingEl.remove();
      const answer = data.answer || data.error || 'No response received.';
      appendMessage('assistant', renderMarkdown(answer));
    })
    .catch(err => {
      const loadingEl = document.getElementById(loadingId);
      if (loadingEl) loadingEl.remove();
      appendMessage('assistant', `<span style="color:#ef4444">Error: ${err.message}</span>`);
    })
    .finally(() => {
      isLoading = false;
      document.getElementById('chat-send').disabled = false;
    });
}

function appendMessage(role, html, id) {
  const messages = document.getElementById('chat-messages');
  const div = document.createElement('div');
  div.className = `message ${role}`;
  if (id) div.id = id;

  const bubble = document.createElement('div');
  bubble.className = 'message-bubble';
  bubble.innerHTML = html;
  div.appendChild(bubble);

  if (role === 'assistant' && !id) {
    const actions = document.createElement('div');
    actions.className = 'message-actions';
    actions.innerHTML = `<button onclick="copyMessage(this)">📋 Copy</button>`;
    div.appendChild(actions);
  }

  messages.appendChild(div);
  messages.scrollTop = messages.scrollHeight;
}

function copyMessage(btn) {
  const bubble = btn.closest('.message').querySelector('.message-bubble');
  navigator.clipboard.writeText(bubble.innerText || bubble.textContent)
    .then(() => { btn.textContent = '✓ Copied'; setTimeout(() => btn.textContent = '📋 Copy', 2000); });
}

function clearChat() {
  const messages = document.getElementById('chat-messages');
  messages.innerHTML = `<div class="chat-empty" id="chat-empty">
    <h3>Ask anything about the Israeli cyber ecosystem</h3>
    <p>Powered by Claude — queries the full 331-company database</p>
    <div class="suggested-prompts">
      <button class="suggested-prompt" onclick="sendSuggested(this)">Which funds led the most seed rounds in Israeli cyber in the last 18 months?</button>
      <button class="suggested-prompt" onclick="sendSuggested(this)">Show me all AI Security companies that raised Series A in 2024–2025</button>
      <button class="suggested-prompt" onclick="sendSuggested(this)">Which companies have 8200 founders and raised over $50M?</button>
      <button class="suggested-prompt" onclick="sendSuggested(this)">Which companies align with Lama's Outcomes Playbook thesis?</button>
      <button class="suggested-prompt" onclick="sendSuggested(this)">What's the median seed round size in Israeli cyber in 2025?</button>
      <button class="suggested-prompt" onclick="sendSuggested(this)">Show me all exits and acquisitions in the last 2 years</button>
      <button class="suggested-prompt" onclick="sendSuggested(this)">Who are the most active co-investors alongside CyberStarts?</button>
      <button class="suggested-prompt" onclick="sendSuggested(this)">Which sectors have the most activity right now?</button>
    </div>
  </div>`;
}

// ── Minimal markdown renderer ─────────────────────────────────────────────

function renderMarkdown(text) {
  // Tables
  text = text.replace(/^\|(.+)\|\s*\n\|[-| :]+\|\s*\n((?:\|.+\|\s*\n?)*)/gm, (_, header, rows) => {
    const ths = header.split('|').filter(s => s.trim()).map(s => `<th>${escHtml(s.trim())}</th>`).join('');
    const trs = rows.trim().split('\n').map(row => {
      const tds = row.split('|').filter(s => s.trim() !== '').map(s => `<td>${escHtml(s.trim())}</td>`).join('');
      return `<tr>${tds}</tr>`;
    }).join('');
    return `<table><thead><tr>${ths}</tr></thead><tbody>${trs}</tbody></table>`;
  });

  // Code blocks
  text = text.replace(/```[\s\S]*?```/g, m => `<code style="background:var(--bg-light);padding:8px;border-radius:4px;display:block;font-size:12px;white-space:pre-wrap">${escHtml(m.slice(3,-3))}</code>`);

  // Bold
  text = text.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  text = text.replace(/__(.+?)__/g, '<strong>$1</strong>');

  // Headers
  text = text.replace(/^### (.+)$/gm, '<h4 style="margin:12px 0 6px;font-size:14px">$1</h4>');
  text = text.replace(/^## (.+)$/gm, '<h3 style="margin:14px 0 8px;font-size:15px">$1</h3>');
  text = text.replace(/^# (.+)$/gm, '<h2 style="margin:16px 0 10px;font-size:16px">$1</h2>');

  // Lists
  text = text.replace(/^[-*] (.+)$/gm, '<li>$1</li>');
  text = text.replace(/(<li>.*<\/li>)/s, '<ul style="margin:6px 0 6px 16px">$1</ul>');

  // Line breaks
  text = text.replace(/\n\n/g, '<br><br>');
  text = text.replace(/\n/g, '<br>');

  return text;
}

function escHtml(s) {
  return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}
