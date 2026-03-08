/**
 * content.js — Injects a small follow-up questions overlay on Google Meet
 * Polls /analyze_latest every 10 seconds and displays questions.
 */

const BACKEND_URL = 'http://localhost:8000';
const POLL_INTERVAL = 10000;

let overlay = null;
let lastJSON = '';
let collapsed = false;
let isDragging = false;
let dragOffset = { x: 0, y: 0 };

function createOverlay() {
  if (overlay) return;

  overlay = document.createElement('div');
  overlay.id = 'iiq-overlay';
  overlay.innerHTML = `
    <div id="iiq-header">
      <span id="iiq-title">🎯 Follow-up Questions</span>
      <div id="iiq-controls">
        <button id="iiq-refresh" title="Refresh">⟳</button>
        <button id="iiq-toggle" title="Minimize">−</button>
      </div>
    </div>
    <div id="iiq-body">
      <div id="iiq-questions">
        <div class="iiq-empty">Waiting for conversation...</div>
      </div>
    </div>
  `;

  const style = document.createElement('style');
  style.textContent = `
    #iiq-overlay {
      position: fixed;
      bottom: 80px;
      right: 20px;
      width: 340px;
      max-height: 420px;
      background: rgba(15, 15, 25, 0.92);
      backdrop-filter: blur(16px);
      border: 1px solid rgba(99, 102, 241, 0.3);
      border-radius: 14px;
      z-index: 999999;
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
      color: #e2e8f0;
      box-shadow: 0 8px 32px rgba(0,0,0,0.5), 0 0 0 1px rgba(99,102,241,0.1);
      overflow: hidden;
      transition: width 0.3s ease, max-height 0.3s ease, opacity 0.3s ease;
    }
    #iiq-overlay.collapsed {
      max-height: 44px;
      width: 220px;
    }
    #iiq-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 10px 14px;
      background: rgba(99, 102, 241, 0.12);
      cursor: move;
      user-select: none;
      border-bottom: 1px solid rgba(99, 102, 241, 0.15);
    }
    #iiq-title {
      font-size: 13px;
      font-weight: 700;
      letter-spacing: 0.02em;
    }
    #iiq-controls {
      display: flex;
      gap: 4px;
    }
    #iiq-controls button {
      background: rgba(255,255,255,0.08);
      border: none;
      color: #a5b4fc;
      font-size: 16px;
      width: 26px;
      height: 26px;
      border-radius: 6px;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      transition: background 0.2s;
    }
    #iiq-controls button:hover {
      background: rgba(99, 102, 241, 0.3);
      color: #fff;
    }
    #iiq-body {
      padding: 10px 14px;
      max-height: 360px;
      overflow-y: auto;
    }
    #iiq-overlay.collapsed #iiq-body {
      display: none;
    }
    #iiq-questions {
      display: flex;
      flex-direction: column;
      gap: 8px;
    }
    .iiq-q {
      background: rgba(255,255,255,0.04);
      border: 1px solid rgba(255,255,255,0.06);
      border-radius: 8px;
      padding: 8px 10px;
      font-size: 12.5px;
      line-height: 1.45;
      transition: background 0.2s;
      cursor: default;
    }
    .iiq-q:hover {
      background: rgba(99, 102, 241, 0.1);
      border-color: rgba(99, 102, 241, 0.25);
    }
    .iiq-q-num {
      color: #818cf8;
      font-weight: 800;
      font-size: 11px;
      margin-right: 6px;
      font-family: 'JetBrains Mono', monospace;
    }
    .iiq-q-cat {
      display: inline-block;
      font-size: 9.5px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      padding: 2px 6px;
      border-radius: 4px;
      background: rgba(99,102,241,0.15);
      color: #a5b4fc;
      margin-top: 4px;
    }
    .iiq-empty {
      text-align: center;
      color: #64748b;
      font-size: 12px;
      padding: 16px 0;
    }
    .iiq-updated {
      text-align: right;
      font-size: 10px;
      color: #475569;
      margin-top: 6px;
    }
    #iiq-body::-webkit-scrollbar {
      width: 4px;
    }
    #iiq-body::-webkit-scrollbar-track {
      background: transparent;
    }
    #iiq-body::-webkit-scrollbar-thumb {
      background: rgba(99,102,241,0.3);
      border-radius: 2px;
    }
  `;

  document.head.appendChild(style);
  document.body.appendChild(overlay);

  // Drag functionality
  const header = overlay.querySelector('#iiq-header');
  header.addEventListener('mousedown', (e) => {
    if (e.target.tagName === 'BUTTON') return;
    isDragging = true;
    const rect = overlay.getBoundingClientRect();
    dragOffset.x = e.clientX - rect.left;
    dragOffset.y = e.clientY - rect.top;
    overlay.style.transition = 'none';
  });

  document.addEventListener('mousemove', (e) => {
    if (!isDragging) return;
    overlay.style.left = (e.clientX - dragOffset.x) + 'px';
    overlay.style.top = (e.clientY - dragOffset.y) + 'px';
    overlay.style.right = 'auto';
    overlay.style.bottom = 'auto';
  });

  document.addEventListener('mouseup', () => {
    if (isDragging) {
      isDragging = false;
      overlay.style.transition = '';
    }
  });

  // Toggle collapse
  overlay.querySelector('#iiq-toggle').addEventListener('click', () => {
    collapsed = !collapsed;
    overlay.classList.toggle('collapsed', collapsed);
    overlay.querySelector('#iiq-toggle').textContent = collapsed ? '+' : '−';
  });

  // Refresh button
  overlay.querySelector('#iiq-refresh').addEventListener('click', () => {
    pollQuestions();
  });
}

function renderQuestions(questions) {
  const container = overlay.querySelector('#iiq-questions');
  if (!questions || questions.length === 0) {
    container.innerHTML = '<div class="iiq-empty">No questions yet — waiting for conversation...</div>';
    return;
  }

  container.innerHTML = questions.map((q, i) => {
    const text = typeof q === 'string' ? q : q.question || String(q);
    const cat = typeof q === 'object' && q.category ? q.category : '';
    return `
      <div class="iiq-q">
        <span class="iiq-q-num">Q${i + 1}</span>${escapeHtml(text)}
        ${cat ? `<div><span class="iiq-q-cat">${escapeHtml(cat.replace(/_/g, ' '))}</span></div>` : ''}
      </div>`;
  }).join('');

  const time = new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
  container.innerHTML += `<div class="iiq-updated">Updated ${time}</div>`;
}

async function pollQuestions() {
  try {
    const res = await fetch(`${BACKEND_URL}/analyze_latest`);
    const data = await res.json();

    if (data.error || !data.analysis) return;

    const questions = data.analysis.follow_up_questions || [];
    if (questions.length === 0) return;

    renderQuestions(questions);

    // Brief flash effect on update
    if (!collapsed) {
      overlay.style.borderColor = 'rgba(99, 102, 241, 0.6)';
      setTimeout(() => {
        overlay.style.borderColor = '';
      }, 1500);
    }
  } catch (e) {
    console.debug('[IIQ Overlay] Poll error:', e.message);
  }
}

function escapeHtml(s) {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

// Boot
console.log('[IIQ Overlay] Content script loaded on', window.location.href);
createOverlay();
pollQuestions();
setInterval(pollQuestions, POLL_INTERVAL);
